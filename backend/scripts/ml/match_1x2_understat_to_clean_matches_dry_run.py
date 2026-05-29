# Role du fichier : rapprocher les matchs xG Understat extraits en CSV avec ml.clean_matches, en dry-run, sans modifier PostgreSQL ni ml.features.

from __future__ import annotations

import argparse
import csv
import os
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

DEFAULT_UNDERSTAT_CSV_PATH = (
    REPORT_DIR / "110_1x2_understat_dom_all_leagues_seasons_v3_matches.csv"
)

SUMMARY_PATH = REPORT_DIR / "114_1x2_understat_clean_match_dry_run_summary.txt"
MATCHED_CSV_PATH = REPORT_DIR / "115_1x2_understat_clean_match_dry_run_matches.csv"
COVERAGE_CSV_PATH = REPORT_DIR / "116_1x2_understat_clean_match_dry_run_by_league_season.csv"
SAMPLES_CSV_PATH = REPORT_DIR / "117_1x2_understat_clean_match_dry_run_samples.csv"
NEXT_ACTION_PATH = REPORT_DIR / "118_1x2_understat_clean_match_dry_run_next_action.txt"

LEAGUE_SLUG_TO_CLEAN_CODE = {
    "EPL": "E0",
    "La_liga": "SP1",
    "Bundesliga": "D1",
    "Serie_A": "I1",
    "Ligue_1": "F1",
}

COMMON_TEAM_ALIASES = {
    "ac ajaccio": "ajaccio",
    "ajaccio gfco": "gazelec ajaccio",
    "amiens sc": "amiens",
    "ang SCO": "angers",
    "angers sco": "angers",
    "arsenal fc": "arsenal",
    "as monaco": "monaco",
    "as roma": "roma",
    "ath bilbao": "athletic bilbao",
    "ath madrid": "atletico madrid",
    "athletico madrid": "atletico madrid",
    "athletic club": "athletic bilbao",
    "bayern": "bayern munich",
    "bayern monaco": "bayern munich",
    "bayern munich": "bayern munich",
    "bayer leverkusen": "bayer leverkusen",
    "betis": "real betis",
    "bmg": "borussia m gladbach",
    "bologna fc": "bologna",
    "brighton and hove albion": "brighton",
    "brighton hove albion": "brighton",
    "borussia dortmund": "borussia dortmund",
    "borussia m gladbach": "borussia m gladbach",
    "borussia moenchengladbach": "borussia m gladbach",
    "borussia monchengladbach": "borussia m gladbach",
    "ca osasuna": "osasuna",
    "cagliari calcio": "cagliari",
    "celta": "celta vigo",
    "celta de vigo": "celta vigo",
    "chievo verona": "chievo",
    "cologne": "fc cologne",
    "deportivo la coruna": "deportivo la coruna",
    "dortmund": "borussia dortmund",
    "ein frankfurt": "eintracht frankfurt",
    "eintracht frankfurt": "eintracht frankfurt",
    "fc bayern munich": "bayern munich",
    "fc cologne": "fc cologne",
    "fc koln": "fc cologne",
    "fc koeln": "fc cologne",
    "fc nantes": "nantes",
    "fc schalke 04": "schalke 04",
    "fiorentina viola": "fiorentina",
    "fortuna dusseldorf": "fortuna dusseldorf",
    "freiburg sc": "freiburg",
    "frosinone calcio": "frosinone",
    "genoa cfc": "genoa",
    "girona fc": "girona",
    "hamburg": "hamburger sv",
    "hamburger": "hamburger sv",
    "hannover": "hannover 96",
    "hannover 96": "hannover 96",
    "hellas verona": "verona",
    "hertha": "hertha berlin",
    "hertha bsc": "hertha berlin",
    "hoffenheim": "tsg hoffenheim",
    "internazionale": "internazionale",
    "inter": "internazionale",
    "inter milan": "internazionale",
    "juventus fc": "juventus",
    "koln": "fc cologne",
    "köln": "fc cologne",
    "la coruna": "deportivo la coruna",
    "las palmas": "las palmas",
    "lazio roma": "lazio",
    "leeds": "leeds united",
    "leeds utd": "leeds united",
    "leicester": "leicester city",
    "leicester city": "leicester city",
    "leverkusen": "bayer leverkusen",
    "levante ud": "levante",
    "lille osc": "lille",
    "man city": "manchester city",
    "man united": "manchester united",
    "man utd": "manchester united",
    "manchester utd": "manchester united",
    "mgladbach": "borussia m gladbach",
    "monchengladbach": "borussia m gladbach",
    "moenchengladbach": "borussia m gladbach",
    "montpellier hsc": "montpellier",
    "newcastle": "newcastle united",
    "newcastle utd": "newcastle united",
    "nott forest": "nottingham forest",
    "nottm forest": "nottingham forest",
    "nottingham forest": "nottingham forest",
    "olympique lyonnais": "lyon",
    "olympique marseille": "marseille",
    "osasuna ca": "osasuna",
    "paris saint germain": "paris saint germain",
    "paris sg": "paris saint germain",
    "psg": "paris saint germain",
    "queens park rangers": "queens park rangers",
    "qpr": "queens park rangers",
    "rayo": "rayo vallecano",
    "rayo vallekano": "rayo vallecano",
    "real betis balompie": "real betis",
    "real sociedad de futbol": "real sociedad",
    "rennes": "stade rennes",
    "rb leipzig": "rb leipzig",
    "roma as": "roma",
    "sc freiburg": "freiburg",
    "schalke": "schalke 04",
    "sevilla fc": "sevilla",
    "sheffield utd": "sheffield united",
    "sp gijon": "sporting gijon",
    "spurs": "tottenham",
    "st etienne": "saint etienne",
    "saint-etienne": "saint etienne",
    "stade de reims": "reims",
    "stade rennais": "stade rennes",
    "tottenham hotspur": "tottenham",
    "tsg hoffenheim": "tsg hoffenheim",
    "ud almeria": "almeria",
    "udinese calcio": "udinese",
    "vfb stuttgart": "stuttgart",
    "werder bremen": "werder bremen",
    "west brom": "west bromwich albion",
    "west bromwich": "west bromwich albion",
    "wolves": "wolverhampton wanderers",
    "wolverhampton": "wolverhampton wanderers",
    "wolverhampton wanderers": "wolverhampton wanderers",
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
    "and",
}


# Charge les variables backend/.env sans afficher les secrets.
def load_backend_env() -> None:
    if not BACKEND_ENV_PATH.exists():
        raise FileNotFoundError(f"Fichier .env introuvable : {BACKEND_ENV_PATH}")

    for line in BACKEND_ENV_PATH.read_text(encoding="utf-8").splitlines():
        clean_line = line.strip()

        if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
            continue

        key, value = clean_line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Recupere l'URL PostgreSQL depuis les variables d'environnement.
def get_database_url() -> str:
    load_backend_env()
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL introuvable dans backend/.env")

    return database_url


# Cree le dossier de preuves ML si necessaire.
def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Convertit une valeur date en objet date Python.
def to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if value is None:
        return None

    text_value = str(value).strip()

    if not text_value:
        return None

    for date_format in ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(text_value[:10], date_format).date()
        except ValueError:
            continue

    return None


# Convertit une valeur vers int quand cela est possible.
def to_int(value: Any) -> int | None:
    if value is None:
        return None

    text_value = str(value).strip()

    if not text_value or text_value.lower() in {"nan", "none", "null"}:
        return None

    try:
        return int(float(text_value))
    except (TypeError, ValueError):
        return None


# Convertit une valeur vers float quand cela est possible.
def to_float(value: Any) -> float | None:
    if value is None:
        return None

    text_value = str(value).strip().replace(",", ".")

    if not text_value or text_value.lower() in {"nan", "none", "null"}:
        return None

    try:
        return float(text_value)
    except (TypeError, ValueError):
        return None


# Construit le libelle de saison RubyBets a partir de l'annee Understat.
def build_clean_season_label(season_year: int | None) -> str | None:
    if season_year is None:
        return None

    return f"{season_year}_{season_year + 1}"


# Normalise les noms d'equipes pour comparer Football-Data.co.uk et Understat.
def normalize_team_name(team_name: Any) -> str:
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


# Calcule une similarite simple entre deux noms d'equipes deja normalises.
def team_similarity(left_name: str, right_name: str) -> float:
    if not left_name or not right_name:
        return 0.0

    if left_name == right_name:
        return 1.0

    left_words = set(left_name.split())
    right_words = set(right_name.split())

    overlap = 0.0

    if left_words and right_words:
        overlap = len(left_words & right_words) / max(len(left_words | right_words), 1)

    sequence_score = SequenceMatcher(None, left_name, right_name).ratio()

    return round(max(sequence_score, overlap), 4)


# Lit et prepare les matchs Understat complets depuis le CSV V3.
def read_understat_matches(csv_path: Path) -> list[dict[str, Any]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV Understat introuvable : {csv_path}")

    rows: list[dict[str, Any]] = []
    seen_understat_ids: set[str] = set()

    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        for raw_row in reader:
            league_slug = str(raw_row.get("league_slug", "")).strip()
            clean_league_code = LEAGUE_SLUG_TO_CLEAN_CODE.get(league_slug)
            season_year = to_int(raw_row.get("season_year"))
            clean_season = build_clean_season_label(season_year)
            match_date = to_date(raw_row.get("date"))
            home_goals = to_int(raw_row.get("home_goals"))
            away_goals = to_int(raw_row.get("away_goals"))
            home_xg = to_float(raw_row.get("home_xg"))
            away_xg = to_float(raw_row.get("away_xg"))
            understat_match_id = to_int(raw_row.get("understat_match_id"))
            is_result = str(raw_row.get("is_result", "")).strip().lower() in {"true", "1", "yes"}

            if not clean_league_code or not clean_season or not is_result:
                continue

            if (
                match_date is None
                or home_goals is None
                or away_goals is None
                or home_xg is None
                or away_xg is None
                or understat_match_id is None
            ):
                continue

            understat_id_key = str(understat_match_id)

            if understat_id_key in seen_understat_ids:
                continue

            seen_understat_ids.add(understat_id_key)

            rows.append(
                {
                    "understat_match_id": understat_match_id,
                    "league_slug": league_slug,
                    "league_code": clean_league_code,
                    "season": clean_season,
                    "match_date": match_date,
                    "home_team": raw_row.get("home_team", ""),
                    "away_team": raw_row.get("away_team", ""),
                    "home_team_norm": normalize_team_name(raw_row.get("home_team")),
                    "away_team_norm": normalize_team_name(raw_row.get("away_team")),
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "home_xg": home_xg,
                    "away_xg": away_xg,
                    "match_url": raw_row.get("match_url", ""),
                    "source_url": raw_row.get("source_url", ""),
                }
            )

    return rows


# Recupere les matchs nettoyes RubyBets sans les modifier.
def fetch_clean_matches(database_url: str) -> list[dict[str, Any]]:
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
            return [dict(row) for row in cursor.fetchall()]


# Prepare les matchs nettoyes dans un format comparable au CSV Understat.
def normalize_clean_matches(clean_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    supported_league_codes = set(LEAGUE_SLUG_TO_CLEAN_CODE.values())

    for clean_match in clean_matches:
        league_code = str(clean_match.get("league_code", "")).strip()
        season = str(clean_match.get("season", "")).strip()
        match_date = to_date(clean_match.get("match_date"))
        home_goals = to_int(clean_match.get("home_goals"))
        away_goals = to_int(clean_match.get("away_goals"))

        if league_code not in supported_league_codes:
            continue

        if not season or match_date is None or home_goals is None or away_goals is None:
            continue

        normalized_rows.append(
            {
                "clean_match_id": clean_match.get("id"),
                "league_code": league_code,
                "season": season,
                "match_date": match_date,
                "home_team": clean_match.get("home_team"),
                "away_team": clean_match.get("away_team"),
                "home_team_norm": normalize_team_name(clean_match.get("home_team")),
                "away_team_norm": normalize_team_name(clean_match.get("away_team")),
                "home_goals": home_goals,
                "away_goals": away_goals,
                "result": clean_match.get("result"),
            }
        )

    return normalized_rows


# Indexe les matchs RubyBets par ligue et saison pour accelerer le matching.
def index_clean_matches(clean_matches: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    clean_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for clean_match in clean_matches:
        key = (clean_match["league_code"], clean_match["season"])
        clean_by_group[key].append(clean_match)

    return clean_by_group


# Verifie si les scores reels sont identiques entre Understat et RubyBets.
def scores_match(understat_match: dict[str, Any], clean_match: dict[str, Any]) -> bool:
    return (
        understat_match["home_goals"] == clean_match["home_goals"]
        and understat_match["away_goals"] == clean_match["away_goals"]
    )


# Cherche le meilleur match RubyBets correspondant a une ligne Understat.
def find_best_clean_candidate(
    understat_match: dict[str, Any],
    clean_candidates: list[dict[str, Any]],
    used_clean_ids: set[int],
    date_tolerance_days: int,
    min_team_score: float,
    min_match_score: float,
    allow_score_mismatch: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    best_candidate = None
    best_details = {
        "best_similarity": 0.0,
        "best_home_similarity": 0.0,
        "best_away_similarity": 0.0,
        "best_date_delta_days": "",
        "best_score_match": False,
        "best_clean_home_team": "",
        "best_clean_away_team": "",
    }

    for clean_match in clean_candidates:
        clean_match_id = clean_match.get("clean_match_id")

        if clean_match_id in used_clean_ids:
            continue

        date_delta_days = abs((understat_match["match_date"] - clean_match["match_date"]).days)

        if date_delta_days > date_tolerance_days:
            continue

        score_is_identical = scores_match(understat_match, clean_match)

        if not allow_score_mismatch and not score_is_identical:
            continue

        home_score = team_similarity(understat_match["home_team_norm"], clean_match["home_team_norm"])
        away_score = team_similarity(understat_match["away_team_norm"], clean_match["away_team_norm"])
        average_score = round((home_score + away_score) / 2, 4)

        score_bonus = 0.04 if score_is_identical else 0.0
        date_bonus = 0.02 if date_delta_days == 0 else 0.0
        ranking_score = round(average_score + score_bonus + date_bonus, 4)
        current_best_score = float(best_details["best_similarity"] or 0.0)

        if ranking_score > current_best_score:
            best_candidate = clean_match
            best_details = {
                "best_similarity": average_score,
                "best_home_similarity": home_score,
                "best_away_similarity": away_score,
                "best_date_delta_days": date_delta_days,
                "best_score_match": score_is_identical,
                "best_clean_home_team": clean_match.get("home_team", ""),
                "best_clean_away_team": clean_match.get("away_team", ""),
            }

    if not best_candidate:
        return None, best_details

    is_accepted = (
        float(best_details["best_similarity"]) >= min_match_score
        and float(best_details["best_home_similarity"]) >= min_team_score
        and float(best_details["best_away_similarity"]) >= min_team_score
        and (allow_score_mismatch or bool(best_details["best_score_match"]))
    )

    if not is_accepted:
        return None, best_details

    return best_candidate, best_details


# Effectue le rapprochement complet Understat vers ml.clean_matches en dry-run.
def match_understat_to_clean_matches(
    understat_matches: list[dict[str, Any]],
    clean_matches: list[dict[str, Any]],
    date_tolerance_days: int,
    min_team_score: float,
    min_match_score: float,
    allow_score_mismatch: bool,
    sample_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clean_by_group = index_clean_matches(clean_matches)
    used_clean_ids: set[int] = set()
    matched_rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for understat_match in understat_matches:
        group_key = (understat_match["league_code"], understat_match["season"])
        clean_candidates = clean_by_group.get(group_key, [])
        best_candidate, best_details = find_best_clean_candidate(
            understat_match=understat_match,
            clean_candidates=clean_candidates,
            used_clean_ids=used_clean_ids,
            date_tolerance_days=date_tolerance_days,
            min_team_score=min_team_score,
            min_match_score=min_match_score,
            allow_score_mismatch=allow_score_mismatch,
        )

        if best_candidate:
            clean_match_id = int(best_candidate["clean_match_id"])
            used_clean_ids.add(clean_match_id)
            matched_rows.append(
                {
                    "clean_match_id": clean_match_id,
                    "understat_match_id": understat_match["understat_match_id"],
                    "league_code": understat_match["league_code"],
                    "season": understat_match["season"],
                    "clean_date": best_candidate["match_date"],
                    "understat_date": understat_match["match_date"],
                    "date_delta_days": best_details["best_date_delta_days"],
                    "clean_home_team": best_candidate["home_team"],
                    "clean_away_team": best_candidate["away_team"],
                    "understat_home_team": understat_match["home_team"],
                    "understat_away_team": understat_match["away_team"],
                    "clean_home_goals": best_candidate["home_goals"],
                    "clean_away_goals": best_candidate["away_goals"],
                    "understat_home_goals": understat_match["home_goals"],
                    "understat_away_goals": understat_match["away_goals"],
                    "score_match": best_details["best_score_match"],
                    "home_similarity": best_details["best_home_similarity"],
                    "away_similarity": best_details["best_away_similarity"],
                    "match_similarity": best_details["best_similarity"],
                    "home_xg": understat_match["home_xg"],
                    "away_xg": understat_match["away_xg"],
                    "result": best_candidate["result"],
                    "match_url": understat_match["match_url"],
                }
            )
        elif len(samples) < sample_limit:
            samples.append(
                {
                    "sample_type": "unmatched_understat_match",
                    "league_code": understat_match["league_code"],
                    "season": understat_match["season"],
                    "understat_match_id": understat_match["understat_match_id"],
                    "clean_match_id": "",
                    "understat_date": understat_match["match_date"],
                    "clean_date": "",
                    "understat_home_team": understat_match["home_team"],
                    "understat_away_team": understat_match["away_team"],
                    "clean_home_team": best_details["best_clean_home_team"],
                    "clean_away_team": best_details["best_clean_away_team"],
                    "understat_score": f"{understat_match['home_goals']}-{understat_match['away_goals']}",
                    "clean_score": "",
                    "home_similarity": best_details["best_home_similarity"],
                    "away_similarity": best_details["best_away_similarity"],
                    "match_similarity": best_details["best_similarity"],
                    "date_delta_days": best_details["best_date_delta_days"],
                    "score_match": best_details["best_score_match"],
                }
            )

    if len(samples) < sample_limit:
        matched_clean_ids = {row["clean_match_id"] for row in matched_rows}
        understat_group_keys = {(row["league_code"], row["season"]) for row in understat_matches}

        for clean_match in clean_matches:
            if len(samples) >= sample_limit:
                break

            if clean_match["clean_match_id"] in matched_clean_ids:
                continue

            if (clean_match["league_code"], clean_match["season"]) not in understat_group_keys:
                continue

            samples.append(
                {
                    "sample_type": "unmatched_clean_match",
                    "league_code": clean_match["league_code"],
                    "season": clean_match["season"],
                    "understat_match_id": "",
                    "clean_match_id": clean_match["clean_match_id"],
                    "understat_date": "",
                    "clean_date": clean_match["match_date"],
                    "understat_home_team": "",
                    "understat_away_team": "",
                    "clean_home_team": clean_match["home_team"],
                    "clean_away_team": clean_match["away_team"],
                    "understat_score": "",
                    "clean_score": f"{clean_match['home_goals']}-{clean_match['away_goals']}",
                    "home_similarity": "",
                    "away_similarity": "",
                    "match_similarity": "",
                    "date_delta_days": "",
                    "score_match": "",
                }
            )

    return matched_rows, samples


# Agrege les volumes par ligue et saison pour decider ce qui est exploitable.
def build_coverage_rows(
    understat_matches: list[dict[str, Any]],
    clean_matches: list[dict[str, Any]],
    matched_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    understat_counts: dict[tuple[str, str], int] = defaultdict(int)
    clean_counts: dict[tuple[str, str], int] = defaultdict(int)
    matched_counts: dict[tuple[str, str], int] = defaultdict(int)

    for understat_match in understat_matches:
        understat_counts[(understat_match["league_code"], understat_match["season"])] += 1

    for clean_match in clean_matches:
        clean_counts[(clean_match["league_code"], clean_match["season"])] += 1

    for matched_row in matched_rows:
        matched_counts[(matched_row["league_code"], matched_row["season"])] += 1

    all_keys = sorted(set(understat_counts) | set(clean_counts))
    coverage_rows: list[dict[str, Any]] = []

    for league_code, season in all_keys:
        understat_rows = understat_counts.get((league_code, season), 0)
        clean_rows = clean_counts.get((league_code, season), 0)
        matched = matched_counts.get((league_code, season), 0)
        clean_match_rate = round(matched / clean_rows, 4) if clean_rows else 0.0
        understat_match_rate = round(matched / understat_rows, 4) if understat_rows else 0.0

        if understat_rows == 0:
            status = "NO_UNDERSTAT_ROWS"
        elif clean_rows == 0:
            status = "NO_CLEAN_MATCHES"
        elif clean_match_rate >= 0.95 and understat_match_rate >= 0.95:
            status = "MATCHING_AVAILABLE"
        elif clean_match_rate >= 0.80 and understat_match_rate >= 0.80:
            status = "MATCHING_REVIEW_NEEDED"
        elif clean_match_rate >= 0.60 or understat_match_rate >= 0.60:
            status = "MATCHING_PARTIAL"
        else:
            status = "MATCHING_LOW_COVERAGE"

        coverage_rows.append(
            {
                "league_code": league_code,
                "season": season,
                "understat_rows": understat_rows,
                "clean_rows": clean_rows,
                "matched_rows": matched,
                "unmatched_understat_rows": max(understat_rows - matched, 0),
                "unmatched_clean_rows": max(clean_rows - matched, 0),
                "clean_match_rate": clean_match_rate,
                "understat_match_rate": understat_match_rate,
                "status": status,
                "usable_for_rolling_xg": status in {"MATCHING_AVAILABLE", "MATCHING_REVIEW_NEEDED"},
            }
        )

    return coverage_rows


# Calcule le statut global du dry-run de matching.
def decide_global_status(coverage_rows: list[dict[str, Any]], total_matched: int, total_clean: int) -> str:
    if total_matched == 0:
        return "V8_UNDERSTAT_MATCHING_DRY_RUN_BLOCKED"

    overall_rate = total_matched / total_clean if total_clean else 0.0
    available_groups = sum(1 for row in coverage_rows if row["status"] == "MATCHING_AVAILABLE")
    review_groups = sum(1 for row in coverage_rows if row["status"] == "MATCHING_REVIEW_NEEDED")

    if overall_rate >= 0.90 and available_groups + review_groups > 0:
        return "V8_UNDERSTAT_MATCHING_DRY_RUN_AVAILABLE"

    if overall_rate >= 0.70:
        return "V8_UNDERSTAT_MATCHING_DRY_RUN_PARTIAL_REVIEW_NEEDED"

    return "V8_UNDERSTAT_MATCHING_DRY_RUN_LOW_COVERAGE"


# Ecrit un CSV avec les lignes matchees et leurs xG Understat.
def write_matched_csv(matched_rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "clean_match_id",
        "understat_match_id",
        "league_code",
        "season",
        "clean_date",
        "understat_date",
        "date_delta_days",
        "clean_home_team",
        "clean_away_team",
        "understat_home_team",
        "understat_away_team",
        "clean_home_goals",
        "clean_away_goals",
        "understat_home_goals",
        "understat_away_goals",
        "score_match",
        "home_similarity",
        "away_similarity",
        "match_similarity",
        "home_xg",
        "away_xg",
        "result",
        "match_url",
    ]

    with MATCHED_CSV_PATH.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matched_rows)


# Ecrit un CSV de couverture par ligue et saison.
def write_coverage_csv(coverage_rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "league_code",
        "season",
        "understat_rows",
        "clean_rows",
        "matched_rows",
        "unmatched_understat_rows",
        "unmatched_clean_rows",
        "clean_match_rate",
        "understat_match_rate",
        "status",
        "usable_for_rolling_xg",
    ]

    with COVERAGE_CSV_PATH.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(coverage_rows)


# Ecrit un CSV d'echantillons non matches pour diagnostic manuel.
def write_samples_csv(samples: list[dict[str, Any]]) -> None:
    fieldnames = [
        "sample_type",
        "league_code",
        "season",
        "understat_match_id",
        "clean_match_id",
        "understat_date",
        "clean_date",
        "understat_home_team",
        "understat_away_team",
        "clean_home_team",
        "clean_away_team",
        "understat_score",
        "clean_score",
        "home_similarity",
        "away_similarity",
        "match_similarity",
        "date_delta_days",
        "score_match",
    ]

    with SAMPLES_CSV_PATH.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(samples)


# Ecrit la synthese texte exploitable comme preuve RNCP.
def write_summary(
    understat_csv_path: Path,
    understat_matches: list[dict[str, Any]],
    clean_matches: list[dict[str, Any]],
    matched_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
    status: str,
    args: argparse.Namespace,
) -> None:
    total_understat = len(understat_matches)
    total_clean = len(clean_matches)
    total_matched = len(matched_rows)
    overall_clean_rate = round(total_matched / total_clean, 4) if total_clean else 0.0
    overall_understat_rate = round(total_matched / total_understat, 4) if total_understat else 0.0
    available_groups = sum(1 for row in coverage_rows if row["status"] == "MATCHING_AVAILABLE")
    review_groups = sum(1 for row in coverage_rows if row["status"] == "MATCHING_REVIEW_NEEDED")
    partial_or_low_groups = sum(
        1
        for row in coverage_rows
        if row["status"] in {"MATCHING_PARTIAL", "MATCHING_LOW_COVERAGE"}
    )

    lines = [
        "RubyBets - ML 1X2 V8 Understat matching dry-run",
        "114 - Synthese rapprochement Understat vers ml.clean_matches",
        "",
        "Objectif :",
        "Verifier si les matchs xG Understat extraits peuvent etre rapproches avec ml.clean_matches avant toute insertion en base.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Aucune integration produit d'Understat.",
        "- Dry-run experimental interne uniquement.",
        "",
        "Parametres :",
        f"- CSV Understat : {understat_csv_path}",
        f"- Date tolerance days : {args.date_tolerance_days}",
        f"- Min team score : {args.min_team_score}",
        f"- Min match score : {args.min_match_score}",
        f"- Allow score mismatch : {args.allow_score_mismatch}",
        "",
        "Resultat global :",
        f"- Understat rows loaded : {total_understat}",
        f"- Clean matches loaded : {total_clean}",
        f"- Matched rows : {total_matched}",
        f"- Overall clean match rate : {overall_clean_rate}",
        f"- Overall Understat match rate : {overall_understat_rate}",
        f"- Matching available groups : {available_groups}",
        f"- Matching review needed groups : {review_groups}",
        f"- Partial or low coverage groups : {partial_or_low_groups}",
        f"- Status : {status}",
        "",
        "Fichiers generes :",
        str(SUMMARY_PATH),
        str(MATCHED_CSV_PATH),
        str(COVERAGE_CSV_PATH),
        str(SAMPLES_CSV_PATH),
        str(NEXT_ACTION_PATH),
        "",
        "Decision attendue :",
        "- Si le matching est disponible : valider le CSV 115 et le CSV 116, puis creer une etape de calcul rolling xG pre-match en dry-run.",
        "- Si le matching est partiel : analyser le CSV 117 et renforcer les alias d'equipes avant toute suite.",
        "- Ne pas entrainer de modele maintenant.",
        "",
        "Statut de suivi :",
        "- Tache realisee si les fichiers 114, 115, 116, 117 et 118 sont generes.",
        "- Statut source a mettre a jour : a produire -> realise pour le matching dry-run Understat vers ml.clean_matches.",
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


# Ecrit la prochaine action recommandee apres le matching dry-run.
def write_next_action(status: str) -> None:
    if status == "V8_UNDERSTAT_MATCHING_DRY_RUN_AVAILABLE":
        decision = "Le matching dry-run est exploitable. La prochaine action est de valider les CSV 115 et 116, puis de creer un calcul rolling xG pre-match en dry-run."
    elif status == "V8_UNDERSTAT_MATCHING_DRY_RUN_PARTIAL_REVIEW_NEEDED":
        decision = "Le matching est partiel mais potentiellement exploitable. La prochaine action est d'analyser les groupes faibles dans le CSV 116 et les echantillons du CSV 117."
    else:
        decision = "Le matching n'est pas assez fiable. La prochaine action est de renforcer les alias d'equipes, les tolerances et le diagnostic des dates/scores."

    lines = [
        "RubyBets - ML 1X2 V8 Understat matching dry-run",
        "118 - Prochaine action recommandee",
        "",
        "Resultat :",
        f"Status : {status}",
        "",
        "Decision :",
        decision,
        "",
        "Ordre des prochaines actions :",
        "1. Controler reports/evidence/ml_training/116_1x2_understat_clean_match_dry_run_by_league_season.csv.",
        "2. Verifier les groupes avec MATCHING_PARTIAL ou MATCHING_LOW_COVERAGE.",
        "3. Controler un echantillon du fichier 115 : clean_match_id, understat_match_id, date, equipes, score et xG.",
        "4. Controler le fichier 117 si des matchs restent non matches.",
        "5. Ne calculer les rolling xG pre-match qu'apres validation du matching.",
        "",
        "Garde-fou :",
        "Understat reste une source experimentale interne. Aucune integration produit, API ou frontend pour le moment.",
    ]

    NEXT_ACTION_PATH.write_text("\n".join(lines), encoding="utf-8")


# Parse les arguments de lancement du script.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run de matching entre le CSV Understat V3 et ml.clean_matches."
    )
    parser.add_argument(
        "--understat-csv",
        default=str(DEFAULT_UNDERSTAT_CSV_PATH),
        help="Chemin du CSV Understat V3 a utiliser.",
    )
    parser.add_argument(
        "--date-tolerance-days",
        type=int,
        default=1,
        help="Tolerance de date entre Understat et clean_matches.",
    )
    parser.add_argument(
        "--min-team-score",
        type=float,
        default=0.62,
        help="Score minimum de similarite pour chaque equipe.",
    )
    parser.add_argument(
        "--min-match-score",
        type=float,
        default=0.76,
        help="Score moyen minimum de similarite pour accepter un matching.",
    )
    parser.add_argument(
        "--allow-score-mismatch",
        action="store_true",
        help="Autorise un matching meme si le score final ne correspond pas exactement.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=300,
        help="Nombre maximum d'echantillons de diagnostic a exporter.",
    )
    return parser.parse_args()


# Orchestre le dry-run complet de matching et la generation des preuves.
def run_matching_dry_run(args: argparse.Namespace) -> None:
    ensure_report_dir()
    database_url = get_database_url()
    understat_csv_path = Path(args.understat_csv)

    print("Chargement du CSV Understat V3...")
    understat_matches = read_understat_matches(understat_csv_path)
    print(f"Understat rows loaded: {len(understat_matches)}")

    print("Chargement de ml.clean_matches...")
    clean_matches = normalize_clean_matches(fetch_clean_matches(database_url))
    print(f"Clean matches loaded: {len(clean_matches)}")

    print("Matching Understat -> ml.clean_matches en dry-run...")
    matched_rows, samples = match_understat_to_clean_matches(
        understat_matches=understat_matches,
        clean_matches=clean_matches,
        date_tolerance_days=args.date_tolerance_days,
        min_team_score=args.min_team_score,
        min_match_score=args.min_match_score,
        allow_score_mismatch=args.allow_score_mismatch,
        sample_limit=args.sample_limit,
    )
    coverage_rows = build_coverage_rows(understat_matches, clean_matches, matched_rows)
    status = decide_global_status(coverage_rows, len(matched_rows), len(clean_matches))

    print("Generation des preuves CSV et synthese...")
    write_matched_csv(matched_rows)
    write_coverage_csv(coverage_rows)
    write_samples_csv(samples)
    write_summary(
        understat_csv_path=understat_csv_path,
        understat_matches=understat_matches,
        clean_matches=clean_matches,
        matched_rows=matched_rows,
        coverage_rows=coverage_rows,
        status=status,
        args=args,
    )
    write_next_action(status)

    total_clean = len(clean_matches)
    total_understat = len(understat_matches)
    clean_rate = round(len(matched_rows) / total_clean, 4) if total_clean else 0.0
    understat_rate = round(len(matched_rows) / total_understat, 4) if total_understat else 0.0

    print("OK - Matching dry-run Understat termine.")
    print(f"Matched rows: {len(matched_rows)}")
    print(f"Clean match rate: {clean_rate}")
    print(f"Understat match rate: {understat_rate}")
    print(f"Status: {status}")
    print(f"Summary saved: {SUMMARY_PATH}")
    print(f"Matched CSV saved: {MATCHED_CSV_PATH}")
    print(f"Coverage CSV saved: {COVERAGE_CSV_PATH}")
    print(f"Samples CSV saved: {SAMPLES_CSV_PATH}")
    print(f"Next action saved: {NEXT_ACTION_PATH}")


# Lance le script depuis la ligne de commande.
def main() -> None:
    args = parse_args()
    run_matching_dry_run(args)


if __name__ == "__main__":
    main()


# Schema de communication :
# reports/evidence/ml_training/110_1x2_understat_dom_all_leagues_seasons_v3_matches.csv
#     ↓
# backend/scripts/ml/match_1x2_understat_to_clean_matches_dry_run.py
#     ↔ backend/.env → PostgreSQL ml.clean_matches (lecture seule)
#     ↓
# reports/evidence/ml_training/114_summary.txt + 115_matches.csv + 116_by_league_season.csv + 117_samples.csv + 118_next_action.txt
