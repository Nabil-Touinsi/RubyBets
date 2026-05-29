# Rôle du fichier : auditer la couverture des cotes historiques 1X2 dans ml.raw_matches.raw_data pour préparer la phase expérimentale V6 Market prior.

from pathlib import Path
import csv
import json
import os

import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "74_1x2_market_odds_coverage_summary.txt"
CSV_PATH = REPORT_DIR / "75_1x2_market_odds_coverage_by_season.csv"

MIN_ACCEPTED_COVERAGE_RATE = 0.70

ODDS_GROUPS = {
    "avg_pre_match": ["AvgH", "AvgD", "AvgA"],
    "b365_pre_match": ["B365H", "B365D", "B365A"],
    "max_pre_match": ["MaxH", "MaxD", "MaxA"],
    "b365_closing": ["B365CH", "B365CD", "B365CA"],
    "avg_closing": ["AvgCH", "AvgCD", "AvgCA"],
}

PREFERRED_GROUP_ORDER = [
    "avg_pre_match",
    "b365_pre_match",
    "max_pre_match",
    "b365_closing",
    "avg_closing",
]

ALL_ODDS_COLUMNS = [
    column
    for columns in ODDS_GROUPS.values()
    for column in columns
]


# Charge les variables du fichier backend/.env sans afficher de secret.
def load_backend_env() -> None:
    if not BACKEND_ENV_PATH.exists():
        raise FileNotFoundError(f"Fichier .env introuvable : {BACKEND_ENV_PATH}")

    for line in BACKEND_ENV_PATH.read_text(encoding="utf-8").splitlines():
        clean_line = line.strip()

        if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
            continue

        key, value = clean_line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Récupère l'URL PostgreSQL depuis l'environnement local.
def get_database_url() -> str:
    load_backend_env()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL introuvable dans backend/.env")

    return database_url


# Crée le dossier de preuves ML si nécessaire.
def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Convertit une valeur brute de cote en nombre exploitable.
def parse_odd_value(value) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        numeric_value = float(value)
    else:
        cleaned_value = str(value).strip().replace(",", ".")

        if not cleaned_value:
            return None

        try:
            numeric_value = float(cleaned_value)
        except ValueError:
            return None

    if numeric_value <= 1.0:
        return None

    return numeric_value


# Lit une valeur dans raw_data, que PostgreSQL retourne un dict ou une chaîne JSON.
def get_raw_data_value(raw_data, column: str):
    if raw_data is None:
        return None

    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            return None

    if not isinstance(raw_data, dict):
        return None

    return raw_data.get(column)


# Vérifie si les trois cotes d'un groupe 1X2 sont présentes et numériques.
def has_complete_odds_group(raw_data, columns: list[str]) -> bool:
    return all(parse_odd_value(get_raw_data_value(raw_data, column)) is not None for column in columns)


# Prépare une structure de comptage vide pour l'audit global ou par saison.
def build_empty_stats() -> dict:
    return {
        "total_rows": 0,
        "column_counts": {column: 0 for column in ALL_ODDS_COLUMNS},
        "group_counts": {group_name: 0 for group_name in ODDS_GROUPS},
    }


# Met à jour les compteurs de couverture pour une ligne brute.
def update_stats(stats: dict, raw_data) -> None:
    stats["total_rows"] += 1

    for column in ALL_ODDS_COLUMNS:
        if parse_odd_value(get_raw_data_value(raw_data, column)) is not None:
            stats["column_counts"][column] += 1

    for group_name, columns in ODDS_GROUPS.items():
        if has_complete_odds_group(raw_data, columns):
            stats["group_counts"][group_name] += 1


# Calcule un pourcentage de couverture lisible.
def coverage_rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0

    return round(count / total, 4)


# Charge les matchs bruts importés depuis PostgreSQL sans modifier la base.
def fetch_raw_matches(database_url: str) -> list[dict]:
    query = """
        SELECT
            batch.league_code,
            batch.season,
            raw.raw_date,
            raw.raw_home_team,
            raw.raw_away_team,
            raw.raw_result,
            raw.raw_data
        FROM ml.raw_matches AS raw
        INNER JOIN ml.import_batches AS batch
            ON batch.id = raw.import_batch_id
        ORDER BY batch.season ASC, batch.league_code ASC, raw.id ASC;
    """

    with psycopg.connect(database_url) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            return list(cursor.fetchall())


# Agrège la couverture des cotes au global et par ligue/saison.
def audit_market_odds_coverage(raw_matches: list[dict]) -> tuple[dict, dict]:
    overall_stats = build_empty_stats()
    season_stats = {}

    for match in raw_matches:
        raw_data = match["raw_data"]
        season_key = (match["league_code"], match["season"])

        if season_key not in season_stats:
            season_stats[season_key] = build_empty_stats()

        update_stats(overall_stats, raw_data)
        update_stats(season_stats[season_key], raw_data)

    return overall_stats, season_stats


# Sélectionne le meilleur groupe de cotes selon l'ordre métier prévu pour la V6.
def select_recommended_group(overall_stats: dict) -> tuple[str | None, str, float]:
    total_rows = overall_stats["total_rows"]

    for group_name in PREFERRED_GROUP_ORDER:
        group_count = overall_stats["group_counts"][group_name]
        group_rate = coverage_rate(group_count, total_rows)

        if group_rate >= MIN_ACCEPTED_COVERAGE_RATE:
            return group_name, "V6_AUDIT_OK", group_rate

    best_group_name = max(
        ODDS_GROUPS,
        key=lambda group_name: overall_stats["group_counts"][group_name],
    )
    best_group_rate = coverage_rate(overall_stats["group_counts"][best_group_name], total_rows)

    return best_group_name, "V6_AUDIT_INSUFFICIENT_COVERAGE", best_group_rate


# Formate une ligne de synthèse pour un groupe de cotes.
def format_group_line(group_name: str, stats: dict) -> str:
    total_rows = stats["total_rows"]
    group_count = stats["group_counts"][group_name]
    group_rate = coverage_rate(group_count, total_rows)
    columns = ", ".join(ODDS_GROUPS[group_name])

    return f"- {group_name} ({columns}) : {group_count}/{total_rows} = {group_rate:.4f}"


# Construit le résumé texte de l'audit V6.
def build_summary(overall_stats: dict, season_stats: dict) -> str:
    recommended_group, audit_status, recommended_rate = select_recommended_group(overall_stats)
    total_rows = overall_stats["total_rows"]

    lines = [
        "RubyBets - ML 1X2 V6 market odds coverage audit",
        "74 - Synthese de couverture des cotes historiques",
        "",
        "Objectif :",
        "Verifier si les cotes historiques 1X2 sont presentes dans ml.raw_matches.raw_data avant de lancer une experimentation Market prior.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Les cotes sont auditees uniquement comme signal ML experimental interne.",
        "",
        "Dataset audite :",
        f"- Matchs bruts charges : {total_rows}",
        f"- Groupes ligue/saison audites : {len(season_stats)}",
        "",
        "Couverture globale par groupe :",
    ]

    for group_name in PREFERRED_GROUP_ORDER:
        lines.append(format_group_line(group_name, overall_stats))

    lines.extend([
        "",
        "Couverture globale par colonne :",
    ])

    for column in ALL_ODDS_COLUMNS:
        column_count = overall_stats["column_counts"][column]
        column_rate = coverage_rate(column_count, total_rows)
        lines.append(f"- {column} : {column_count}/{total_rows} = {column_rate:.4f}")

    lines.extend([
        "",
        "Decision d'audit :",
        f"- Status : {audit_status}",
        f"- Groupe recommande : {recommended_group}",
        f"- Colonnes recommandees : {', '.join(ODDS_GROUPS[recommended_group]) if recommended_group else 'Aucune'}",
        f"- Couverture du groupe recommande : {recommended_rate:.4f}",
        f"- Seuil minimum attendu : {MIN_ACCEPTED_COVERAGE_RATE:.4f}",
        "",
    ])

    if audit_status == "V6_AUDIT_OK":
        lines.extend([
            "Suite recommandee :",
            "Lancer l'etape V6 suivante : transformer ces cotes en probabilites implicites normalisees, puis tester une baseline odds only.",
        ])
    else:
        lines.extend([
            "Suite recommandee :",
            "Ne pas lancer l'entrainement V6 tant que la couverture n'est pas suffisante ou tant qu'un perimetre saison/ligue plus stable n'est pas defini.",
        ])

    lines.extend([
        "",
        "Fichiers generes :",
        str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
        str(CSV_PATH.relative_to(PROJECT_ROOT)),
        "",
        "Statut de suivi :",
        "- Tache realisee : audit de couverture des cotes historiques V6.",
        "- Statut source a mettre a jour : realise si les fichiers 74 et 75 sont generes.",
        "- Fichiers concernes : reports/evidence/ml_training/74 et 75.",
        "",
    ])

    return "\n".join(lines)


# Prépare une ligne CSV de couverture pour une ligue et une saison.
def build_season_csv_row(league_code: str, season: str, stats: dict) -> dict:
    total_rows = stats["total_rows"]

    row = {
        "league_code": league_code,
        "season": season,
        "total_rows": total_rows,
    }

    for group_name in PREFERRED_GROUP_ORDER:
        group_count = stats["group_counts"][group_name]
        row[f"{group_name}_rows"] = group_count
        row[f"{group_name}_coverage_rate"] = coverage_rate(group_count, total_rows)

    return row


# Sauvegarde le CSV de couverture par ligue et saison.
def save_season_csv(season_stats: dict) -> None:
    fieldnames = ["league_code", "season", "total_rows"]

    for group_name in PREFERRED_GROUP_ORDER:
        fieldnames.extend([
            f"{group_name}_rows",
            f"{group_name}_coverage_rate",
        ])

    rows = []

    for league_code, season in sorted(season_stats):
        rows.append(build_season_csv_row(league_code, season, season_stats[(league_code, season)]))

    with CSV_PATH.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Sauvegarde les preuves texte et CSV de l'audit.
def save_reports(summary: str, season_stats: dict) -> None:
    ensure_report_dir()
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    save_season_csv(season_stats)


# Lance l'audit complet de couverture des cotes historiques.
def main() -> None:
    database_url = get_database_url()

    print("Chargement des matchs bruts depuis ml.raw_matches...", flush=True)
    raw_matches = fetch_raw_matches(database_url)

    if not raw_matches:
        raise RuntimeError("Aucun match brut trouve dans ml.raw_matches. Audit V6 impossible.")

    print(f"Matchs bruts charges : {len(raw_matches)}", flush=True)
    print("Audit de couverture des cotes historiques 1X2...", flush=True)

    overall_stats, season_stats = audit_market_odds_coverage(raw_matches)
    summary = build_summary(overall_stats, season_stats)
    save_reports(summary, season_stats)

    recommended_group, audit_status, recommended_rate = select_recommended_group(overall_stats)

    print("OK - Audit de couverture des cotes V6 termine.", flush=True)
    print(f"Status: {audit_status}", flush=True)
    print(f"Recommended odds group: {recommended_group}", flush=True)
    print(f"Recommended coverage: {recommended_rate:.4f}", flush=True)
    print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"CSV saved: {CSV_PATH.relative_to(PROJECT_ROOT)}", flush=True)


if __name__ == "__main__":
    main()


# Schema de communication :
# audit_1x2_market_odds_coverage.py
#   -> lit backend/.env pour recuperer DATABASE_URL
#   -> lit PostgreSQL ml.raw_matches + ml.import_batches
#   -> audite les cotes stockees dans ml.raw_matches.raw_data
#   -> genere reports/evidence/ml_training/74_1x2_market_odds_coverage_summary.txt
#   -> genere reports/evidence/ml_training/75_1x2_market_odds_coverage_by_season.csv
#   -> ne modifie pas PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modeles sauvegardes
