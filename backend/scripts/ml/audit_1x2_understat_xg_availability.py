# Rôle du fichier : auditer la disponibilité des données xG Understat et vérifier si elles peuvent être rapprochées des matchs RubyBets, sans modifier la base, l'API, le frontend ou les modèles.

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request

import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "86_1x2_understat_xg_availability_summary.txt"
CSV_PATH = REPORT_DIR / "87_1x2_understat_xg_availability_by_league_season.csv"
SAMPLES_PATH = REPORT_DIR / "88_1x2_understat_xg_matchability_samples.csv"

UNDERSTAT_BASE_URL = "https://understat.com/league/{league}/{season_start}"
REQUEST_TIMEOUT_SECONDS = 25
REQUEST_DELAY_SECONDS = 0.8

LEAGUE_MAPPING = {
    "E0": "EPL",
    "SP1": "La_liga",
    "D1": "Bundesliga",
    "I1": "Serie_A",
    "F1": "Ligue_1",
}

UNDERSTAT_MIN_SEASON_START = 2014
MATCH_SCORE_THRESHOLD = 0.76
TEAM_SCORE_MINIMUM = 0.62

STATUS_OK = "V8_XG_AUDIT_OK"
STATUS_PARTIAL = "V8_XG_AUDIT_PARTIAL"
STATUS_BLOCKED = "V8_XG_AUDIT_BLOCKED_OR_UNAVAILABLE"
STATUS_NOT_USEFUL = "V8_XG_AUDIT_NOT_USEFUL"

COMMON_TEAM_ALIASES = {
    "man united": "manchester united",
    "man utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "wolves": "wolverhampton wanderers",
    "nottm forest": "nottingham forest",
    "nott forest": "nottingham forest",
    "sheffield utd": "sheffield united",
    "west brom": "west bromwich albion",
    "newcastle": "newcastle united",
    "leeds": "leeds united",
    "qpr": "queens park rangers",
    "ath madrid": "atletico madrid",
    "athletico madrid": "atletico madrid",
    "ath bilbao": "athletic bilbao",
    "athletic club": "athletic bilbao",
    "betis": "real betis",
    "celta": "celta vigo",
    "rayo": "rayo vallecano",
    "la coruna": "deportivo la coruna",
    "sp gijon": "sporting gijon",
    "inter": "internazionale",
    "inter milan": "internazionale",
    "ac milan": "milan",
    "as roma": "roma",
    "ss lazio": "lazio",
    "bayern munich": "bayern munich",
    "bayern": "bayern munich",
    "dortmund": "borussia dortmund",
    "mgladbach": "borussia m gladbach",
    "monchengladbach": "borussia m gladbach",
    "moenchengladbach": "borussia m gladbach",
    "leverkusen": "bayer leverkusen",
    "koln": "fc cologne",
    "köln": "fc cologne",
    "cologne": "fc cologne",
    "hamburg": "hamburger sv",
    "hertha": "hertha berlin",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "paris saint germain": "paris saint germain",
    "marseille": "olympique marseille",
    "lyon": "olympique lyonnais",
    "rennes": "stade rennes",
    "st etienne": "saint etienne",
    "saint-etienne": "saint etienne",
}

COMMON_WORDS_TO_REMOVE = {
    "fc",
    "cf",
    "ac",
    "afc",
    "sc",
    "sv",
    "ud",
    "sd",
    "rc",
    "cd",
    "club",
    "football",
    "calcio",
    "de",
    "la",
    "the",
}


# Charge les variables du fichier backend/.env sans afficher les secrets.
def load_backend_env() -> None:
    if not BACKEND_ENV_PATH.exists():
        raise FileNotFoundError(f"Fichier .env introuvable : {BACKEND_ENV_PATH}")

    for line in BACKEND_ENV_PATH.read_text(encoding="utf-8").splitlines():
        clean_line = line.strip()

        if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
            continue

        key, value = clean_line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Récupère l'URL PostgreSQL depuis backend/.env.
def get_database_url() -> str:
    load_backend_env()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL introuvable dans backend/.env")

    return database_url


# Crée le dossier de preuves ML si nécessaire.
def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Charge uniquement les matchs nettoyés nécessaires à l'audit de rapprochement xG.
def fetch_clean_matches(database_url: str) -> list[dict]:
    query = """
        SELECT
            id,
            match_date,
            league_code,
            season,
            home_team,
            away_team,
            home_goals,
            away_goals,
            result
        FROM ml.clean_matches
        WHERE is_valid = TRUE
        ORDER BY match_date ASC, id ASC;
    """

    with psycopg.connect(database_url) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            return list(cursor.fetchall())


# Extrait l'année de début depuis une saison au format 2022_2023.
def get_season_start_year(season: str) -> int | None:
    if not season or "_" not in season:
        return None

    try:
        return int(str(season).split("_", 1)[0])
    except ValueError:
        return None


# Convertit une date PostgreSQL ou chaîne en objet date.
def to_date(value: object) -> date | None:
    if isinstance(value, date):
        return value

    if isinstance(value, datetime):
        return value.date()

    if value is None:
        return None

    text_value = str(value).strip()

    for date_format in ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(text_value[:10], date_format).date()
        except ValueError:
            continue

    return None


# Normalise les noms d'équipes pour améliorer le rapprochement Football-Data / Understat.
def normalize_team_name(team_name: object) -> str:
    if team_name is None:
        return ""

    text = str(team_name).lower().strip()
    text = text.replace("&", " and ")
    text = text.replace("'", "")
    text = text.replace(".", " ")
    text = text.replace("-", " ")

    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text in COMMON_TEAM_ALIASES:
        return COMMON_TEAM_ALIASES[text]

    words = [word for word in text.split() if word not in COMMON_WORDS_TO_REMOVE]
    normalized = " ".join(words).strip()

    return COMMON_TEAM_ALIASES.get(normalized, normalized)


# Calcule une similarité simple entre deux noms normalisés.
def team_similarity(left_name: str, right_name: str) -> float:
    if not left_name or not right_name:
        return 0.0

    if left_name == right_name:
        return 1.0

    left_words = set(left_name.split())
    right_words = set(right_name.split())

    if left_words and right_words:
        overlap = len(left_words & right_words) / max(len(left_words | right_words), 1)
    else:
        overlap = 0.0

    sequence_score = SequenceMatcher(None, left_name, right_name).ratio()

    return round(max(sequence_score, overlap), 4)


# Télécharge une page Understat avec un user-agent explicite.
def fetch_understat_html(understat_league: str, season_start: int) -> str:
    url = UNDERSTAT_BASE_URL.format(league=understat_league, season_start=season_start)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 RubyBets-RNCP-Data-Audit/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


# Extrait datesData depuis le HTML Understat.
def extract_understat_dates_data(html: str) -> list[dict]:
    match = re.search(r"datesData\s*=\s*JSON\.parse\('(.+?)'\)", html, flags=re.DOTALL)

    if not match:
        raise RuntimeError("Bloc datesData introuvable dans la page Understat")

    encoded_json = match.group(1)
    decoded_json = encoded_json.encode("utf-8").decode("unicode_escape")
    decoded_json = decoded_json.replace("\\/", "/")

    return json.loads(decoded_json)


# Convertit une valeur numérique Understat en float.
def to_float(value: object) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Transforme les matchs Understat en format minimal comparable avec ml.clean_matches.
def normalize_understat_matches(raw_matches: list[dict], league_code: str, season: str) -> list[dict]:
    normalized_matches = []

    for raw_match in raw_matches:
        if str(raw_match.get("isResult", "")).lower() in {"false", "0"}:
            continue

        home = raw_match.get("h") or {}
        away = raw_match.get("a") or {}
        goals = raw_match.get("goals") or {}
        xg = raw_match.get("xG") or {}
        match_datetime = str(raw_match.get("datetime", ""))
        match_date = to_date(match_datetime[:10])
        home_xg = to_float(xg.get("h"))
        away_xg = to_float(xg.get("a"))

        if match_date is None or home_xg is None or away_xg is None:
            continue

        normalized_matches.append(
            {
                "understat_id": raw_match.get("id"),
                "league_code": league_code,
                "season": season,
                "match_date": match_date,
                "home_team": home.get("title"),
                "away_team": away.get("title"),
                "home_team_norm": normalize_team_name(home.get("title")),
                "away_team_norm": normalize_team_name(away.get("title")),
                "home_goals": to_float(goals.get("h")),
                "away_goals": to_float(goals.get("a")),
                "home_xg": home_xg,
                "away_xg": away_xg,
            }
        )

    return normalized_matches


# Charge les matchs Understat pour une ligue et une saison, avec gestion des erreurs réseau.
def fetch_understat_matches_for_group(league_code: str, season: str) -> tuple[list[dict], str]:
    understat_league = LEAGUE_MAPPING.get(league_code)
    season_start = get_season_start_year(season)

    if not understat_league or season_start is None:
        return [], "unsupported_league_or_season"

    if season_start < UNDERSTAT_MIN_SEASON_START:
        return [], "season_before_understat_coverage"

    try:
        html = fetch_understat_html(understat_league, season_start)
        raw_matches = extract_understat_dates_data(html)
        normalized_matches = normalize_understat_matches(raw_matches, league_code, season)
        time.sleep(REQUEST_DELAY_SECONDS)
        return normalized_matches, "ok"
    except urllib.error.HTTPError as error:
        return [], f"http_error_{error.code}"
    except urllib.error.URLError as error:
        return [], f"url_error_{error.reason}"
    except Exception as error:  # noqa: BLE001
        return [], f"parse_or_fetch_error_{type(error).__name__}"


# Prépare les matchs RubyBets dans un format comparable avec Understat.
def normalize_clean_match(clean_match: dict) -> dict:
    return {
        "clean_match_id": clean_match.get("id"),
        "league_code": clean_match.get("league_code"),
        "season": clean_match.get("season"),
        "match_date": to_date(clean_match.get("match_date")),
        "home_team": clean_match.get("home_team"),
        "away_team": clean_match.get("away_team"),
        "home_team_norm": normalize_team_name(clean_match.get("home_team")),
        "away_team_norm": normalize_team_name(clean_match.get("away_team")),
        "result": clean_match.get("result"),
    }


# Rapproche les matchs RubyBets et Understat par date puis similarité des équipes.
def match_clean_to_understat(clean_matches: list[dict], understat_matches: list[dict]) -> tuple[list[dict], list[dict]]:
    understat_by_date = defaultdict(list)

    for understat_match in understat_matches:
        understat_by_date[understat_match["match_date"]].append(understat_match)

    used_understat_ids = set()
    matched_rows = []
    unmatched_samples = []

    for clean_match in clean_matches:
        match_date = clean_match["match_date"]

        if match_date is None:
            continue

        candidate_dates = [match_date, match_date - timedelta(days=1), match_date + timedelta(days=1)]
        best_candidate = None
        best_score = 0.0
        best_home_score = 0.0
        best_away_score = 0.0

        for candidate_date in candidate_dates:
            for understat_match in understat_by_date.get(candidate_date, []):
                understat_id = understat_match.get("understat_id")

                if understat_id in used_understat_ids:
                    continue

                home_score = team_similarity(clean_match["home_team_norm"], understat_match["home_team_norm"])
                away_score = team_similarity(clean_match["away_team_norm"], understat_match["away_team_norm"])
                average_score = round((home_score + away_score) / 2, 4)

                if average_score > best_score:
                    best_candidate = understat_match
                    best_score = average_score
                    best_home_score = home_score
                    best_away_score = away_score

        if (
            best_candidate
            and best_score >= MATCH_SCORE_THRESHOLD
            and best_home_score >= TEAM_SCORE_MINIMUM
            and best_away_score >= TEAM_SCORE_MINIMUM
        ):
            used_understat_ids.add(best_candidate.get("understat_id"))
            matched_rows.append(
                {
                    "clean_match_id": clean_match.get("clean_match_id"),
                    "understat_id": best_candidate.get("understat_id"),
                    "league_code": clean_match.get("league_code"),
                    "season": clean_match.get("season"),
                    "clean_date": clean_match.get("match_date"),
                    "understat_date": best_candidate.get("match_date"),
                    "clean_home_team": clean_match.get("home_team"),
                    "clean_away_team": clean_match.get("away_team"),
                    "understat_home_team": best_candidate.get("home_team"),
                    "understat_away_team": best_candidate.get("away_team"),
                    "home_similarity": best_home_score,
                    "away_similarity": best_away_score,
                    "match_similarity": best_score,
                    "home_xg": best_candidate.get("home_xg"),
                    "away_xg": best_candidate.get("away_xg"),
                }
            )
        elif len(unmatched_samples) < 200:
            unmatched_samples.append(
                {
                    "sample_type": "unmatched_clean_match",
                    "league_code": clean_match.get("league_code"),
                    "season": clean_match.get("season"),
                    "clean_match_id": clean_match.get("clean_match_id"),
                    "clean_date": clean_match.get("match_date"),
                    "clean_home_team": clean_match.get("home_team"),
                    "clean_away_team": clean_match.get("away_team"),
                    "best_similarity": best_score,
                    "best_understat_home_team": best_candidate.get("home_team") if best_candidate else "",
                    "best_understat_away_team": best_candidate.get("away_team") if best_candidate else "",
                }
            )

    return matched_rows, unmatched_samples


# Calcule un statut d'audit global selon la couverture et les erreurs rencontrées.
def decide_audit_status(overall_match_rate: float, fetched_groups: int, failed_groups: int, total_groups: int) -> str:
    if fetched_groups == 0:
        return STATUS_BLOCKED

    if overall_match_rate >= 0.70:
        return STATUS_OK

    if overall_match_rate >= 0.45 and failed_groups < total_groups:
        return STATUS_PARTIAL

    return STATUS_NOT_USEFUL


# Écrit le CSV de couverture par ligue et saison.
def write_coverage_csv(rows: list[dict]) -> None:
    fieldnames = [
        "league_code",
        "understat_league",
        "season",
        "clean_rows",
        "understat_rows",
        "matched_rows",
        "match_rate",
        "fetch_status",
        "usable_for_xg_rolling_features",
    ]

    with CSV_PATH.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Écrit un CSV d'exemples pour contrôler manuellement la qualité du rapprochement.
def write_samples_csv(matched_rows: list[dict], unmatched_samples: list[dict]) -> None:
    fieldnames = [
        "sample_type",
        "league_code",
        "season",
        "clean_match_id",
        "understat_id",
        "clean_date",
        "understat_date",
        "clean_home_team",
        "clean_away_team",
        "understat_home_team",
        "understat_away_team",
        "home_similarity",
        "away_similarity",
        "match_similarity",
        "home_xg",
        "away_xg",
        "best_similarity",
        "best_understat_home_team",
        "best_understat_away_team",
    ]

    sample_rows = []

    for row in matched_rows[:200]:
        sample_rows.append({"sample_type": "matched", **row})

    sample_rows.extend(unmatched_samples[:200])

    with SAMPLES_PATH.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for row in sample_rows:
            writer.writerow({fieldname: row.get(fieldname, "") for fieldname in fieldnames})


# Écrit le résumé texte de l'audit V8 xG.
def write_summary(
    status: str,
    clean_total_rows: int,
    eligible_clean_rows: int,
    total_groups: int,
    fetched_groups: int,
    failed_groups: int,
    total_understat_rows: int,
    total_matched_rows: int,
    overall_match_rate: float,
    coverage_rows: list[dict],
) -> None:
    best_groups = sorted(coverage_rows, key=lambda row: float(row["match_rate"]), reverse=True)[:10]
    failed_statuses = defaultdict(int)

    for row in coverage_rows:
        if row["fetch_status"] != "ok":
            failed_statuses[row["fetch_status"]] += 1

    lines = [
        "RubyBets - ML 1X2 V8 Understat xG availability audit",
        "86 - Synthese d'audit disponibilite xG historique",
        "",
        "Objectif :",
        "Verifier si les donnees xG historiques Understat peuvent etre recuperees et rapprochees des matchs RubyBets avant de lancer une V8 globale.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Les donnees xG sont auditees uniquement comme source d'enrichissement ML experimentale interne.",
        "",
        "Dataset RubyBets :",
        f"- Matchs nettoyes charges : {clean_total_rows}",
        f"- Matchs dans les ligues/saisons compatibles Understat depuis 2014_2015 : {eligible_clean_rows}",
        f"- Groupes ligue/saison audites : {total_groups}",
        "",
        "Audit Understat :",
        f"- Groupes recuperes avec statut ok : {fetched_groups}",
        f"- Groupes non recuperes / non disponibles : {failed_groups}",
        f"- Matchs Understat avec xG recuperes : {total_understat_rows}",
        f"- Matchs rapproches avec RubyBets : {total_matched_rows}",
        f"- Taux de rapprochement global : {overall_match_rate:.4f}",
        "",
        "Decision d'audit :",
        f"- Status : {status}",
    ]

    if status == STATUS_OK:
        lines.extend(
            [
                "- Decision : la source xG semble suffisamment exploitable pour preparer une V8 avec rolling xG pre-match.",
                "- Suite recommandee : construire un dataset xG rapproche, puis calculer uniquement des moyennes xG connues avant chaque match.",
            ]
        )
    elif status == STATUS_PARTIAL:
        lines.extend(
            [
                "- Decision : la source xG est partiellement exploitable, mais le rapprochement ou la recuperation doivent etre ameliores avant une V8 fiable.",
                "- Suite recommandee : verifier les exemples 88, completer les alias equipes ou reduire le perimetre aux ligues/saisons les mieux rapprochees.",
            ]
        )
    elif status == STATUS_BLOCKED:
        lines.extend(
            [
                "- Decision : l'audit n'a pas pu recuperer de donnees Understat exploitables.",
                "- Suite recommandee : verifier la connexion internet, un eventuel blocage HTTP, ou tester une autre source xG historique.",
            ]
        )
    else:
        lines.extend(
            [
                "- Decision : la source xG n'est pas assez exploitable dans cet etat pour lancer une V8 globale fiable.",
                "- Suite recommandee : tester une autre source data ou travailler sur une strategie forte confiance separee.",
            ]
        )

    lines.extend(["", "Top groupes rapproches :"])

    for row in best_groups:
        lines.append(
            "- "
            f"{row['league_code']} {row['season']} | "
            f"clean={row['clean_rows']} | understat={row['understat_rows']} | "
            f"matched={row['matched_rows']} | rate={float(row['match_rate']):.4f} | status={row['fetch_status']}"
        )

    if failed_statuses:
        lines.extend(["", "Statuts non OK rencontres :"])

        for fetch_status, count in sorted(failed_statuses.items()):
            lines.append(f"- {fetch_status} : {count}")

    lines.extend(
        [
            "",
            "Fichiers generes :",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(CSV_PATH.relative_to(PROJECT_ROOT)),
            str(SAMPLES_PATH.relative_to(PROJECT_ROOT)),
            "",
            "Statut de suivi :",
            "- Tache realisee : audit de disponibilite et de rapprochement Understat xG V8 si les fichiers 86, 87 et 88 sont generes.",
            "- Statut source a mettre a jour : a produire -> realise pour les fichiers reports/evidence/ml_training/86, 87 et 88.",
        ]
    )

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


# Orchestre l'audit complet : base RubyBets, pages Understat, rapprochement, preuves.
def main() -> None:
    print("Audit V8 - disponibilite des donnees xG Understat...")
    ensure_report_dir()

    database_url = get_database_url()

    print("Chargement des matchs nettoyes depuis ml.clean_matches...")
    clean_matches_raw = fetch_clean_matches(database_url)
    clean_total_rows = len(clean_matches_raw)
    print(f"Matchs nettoyes charges : {clean_total_rows}")

    clean_by_group = defaultdict(list)

    for raw_match in clean_matches_raw:
        league_code = raw_match.get("league_code")
        season = raw_match.get("season")
        season_start = get_season_start_year(str(season))

        if league_code not in LEAGUE_MAPPING:
            continue

        if season_start is None or season_start < UNDERSTAT_MIN_SEASON_START:
            continue

        clean_by_group[(league_code, season)].append(normalize_clean_match(raw_match))

    eligible_clean_rows = sum(len(rows) for rows in clean_by_group.values())
    total_groups = len(clean_by_group)

    print(f"Matchs eligibles Understat : {eligible_clean_rows}")
    print(f"Groupes ligue/saison a auditer : {total_groups}")

    coverage_rows = []
    all_matched_rows = []
    all_unmatched_samples = []
    total_understat_rows = 0
    total_matched_rows = 0
    fetched_groups = 0
    failed_groups = 0

    for index, ((league_code, season), clean_group_matches) in enumerate(sorted(clean_by_group.items()), start=1):
        understat_league = LEAGUE_MAPPING[league_code]
        print(f"[{index}/{total_groups}] Recuperation Understat : {league_code} {season} -> {understat_league}")

        understat_matches, fetch_status = fetch_understat_matches_for_group(str(league_code), str(season))

        if fetch_status == "ok":
            fetched_groups += 1
        else:
            failed_groups += 1

        matched_rows, unmatched_samples = match_clean_to_understat(clean_group_matches, understat_matches)
        match_rate = round(len(matched_rows) / len(clean_group_matches), 4) if clean_group_matches else 0.0
        usable_for_xg = int(fetch_status == "ok" and match_rate >= 0.70)

        total_understat_rows += len(understat_matches)
        total_matched_rows += len(matched_rows)
        all_matched_rows.extend(matched_rows)
        all_unmatched_samples.extend(unmatched_samples)

        coverage_rows.append(
            {
                "league_code": league_code,
                "understat_league": understat_league,
                "season": season,
                "clean_rows": len(clean_group_matches),
                "understat_rows": len(understat_matches),
                "matched_rows": len(matched_rows),
                "match_rate": f"{match_rate:.4f}",
                "fetch_status": fetch_status,
                "usable_for_xg_rolling_features": usable_for_xg,
            }
        )

    overall_match_rate = round(total_matched_rows / eligible_clean_rows, 4) if eligible_clean_rows else 0.0
    status = decide_audit_status(overall_match_rate, fetched_groups, failed_groups, total_groups)

    write_coverage_csv(coverage_rows)
    write_samples_csv(all_matched_rows, all_unmatched_samples)
    write_summary(
        status=status,
        clean_total_rows=clean_total_rows,
        eligible_clean_rows=eligible_clean_rows,
        total_groups=total_groups,
        fetched_groups=fetched_groups,
        failed_groups=failed_groups,
        total_understat_rows=total_understat_rows,
        total_matched_rows=total_matched_rows,
        overall_match_rate=overall_match_rate,
        coverage_rows=coverage_rows,
    )

    print("OK - Audit V8 Understat xG termine.")
    print(f"Status: {status}")
    print(f"Eligible clean rows: {eligible_clean_rows}")
    print(f"Understat rows fetched: {total_understat_rows}")
    print(f"Matched rows: {total_matched_rows}")
    print(f"Overall match rate: {overall_match_rate:.4f}")
    print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}")
    print(f"CSV saved: {CSV_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Samples saved: {SAMPLES_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()


# Schema de communication :
# backend/.env -> DATABASE_URL
#        ↓
# PostgreSQL ml.clean_matches (lecture seule)
#        ↓
# Understat pages league/season (lecture web)
#        ↓
# audit_1x2_understat_xg_availability.py
#        ↓
# reports/evidence/ml_training/86, 87, 88
