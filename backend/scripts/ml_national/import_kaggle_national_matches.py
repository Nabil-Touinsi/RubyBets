# Rôle du fichier :
# Ce script importe les matchs internationaux historiques du dataset Kaggle
# dans ml_national.raw_matches, afin de préparer la future baseline nationale V17.9.

from pathlib import Path
import argparse
import csv
import hashlib
import os
import sys
from collections import Counter

import psycopg
from psycopg.types.json import Jsonb


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "external" / "national_results" / "results.csv"

DEFAULT_SOURCE_NAME = "kaggle-international-football-results"
DEFAULT_COMPETITION_CODE = "INTL"

WORLD_CUP_TOURNAMENT = "FIFA World Cup"
WORLD_CUP_QUALIFICATION_TOURNAMENT = "FIFA World Cup qualification"


# Charge les variables du fichier backend/.env sans afficher de secret.
def load_env_file() -> None:
    if not ENV_PATH.exists():
        raise FileNotFoundError(f"Fichier .env introuvable : {ENV_PATH}")

    with ENV_PATH.open("r", encoding="utf-8") as env_file:
        for line in env_file:
            clean_line = line.strip()

            if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                continue

            key, value = clean_line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Récupère l'URL PostgreSQL depuis backend/.env.
def get_database_url() -> str:
    load_env_file()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL est absent du fichier backend/.env")

    return database_url


# Prépare les arguments utilisables en ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importer les matchs nationaux historiques Kaggle dans ml_national.raw_matches."
    )

    parser.add_argument(
        "--dataset-path",
        default=str(DEFAULT_DATASET_PATH),
        help="Chemin vers results.csv du dataset Kaggle.",
    )

    parser.add_argument(
        "--scope",
        choices=["worldcup", "qualifiers", "worldcup_and_qualifiers", "all"],
        default="worldcup_and_qualifiers",
        help="Périmètre à importer. Par défaut : Coupe du Monde + qualifications.",
    )

    parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Inclure aussi les matchs sans score. Par défaut, seuls les matchs terminés sont importés.",
    )

    return parser.parse_args()


# Vérifie si une valeur de score est réellement exploitable.
def has_score(value: str | None) -> bool:
    if value is None:
        return False

    clean_value = value.strip().lower()

    if clean_value in {"", "na", "nan", "none", "null"}:
        return False

    return clean_value.isdigit()


# Convertit une valeur de score en entier.
def to_int(value: str | None) -> int | None:
    if not has_score(value):
        return None

    try:
        return int(value)
    except ValueError:
        return None


# Convertit le champ neutral du CSV en booléen.
def to_bool(value: str | None) -> bool:
    if value is None:
        return False

    return value.strip().lower() in {"true", "1", "yes", "y"}


# Détermine si le tournoi correspond au périmètre demandé.
def is_row_in_scope(row: dict, scope: str) -> bool:
    tournament = row.get("tournament", "")

    if scope == "all":
        return True

    if scope == "worldcup":
        return tournament == WORLD_CUP_TOURNAMENT

    if scope == "qualifiers":
        return tournament == WORLD_CUP_QUALIFICATION_TOURNAMENT

    return tournament in {
        WORLD_CUP_TOURNAMENT,
        WORLD_CUP_QUALIFICATION_TOURNAMENT,
    }


# Crée un identifiant stable pour éviter les doublons à l'import.
def build_source_match_id(row: dict) -> str:
    raw_identifier = "|".join(
        [
            row.get("date", ""),
            row.get("home_team", ""),
            row.get("away_team", ""),
            row.get("tournament", ""),
            row.get("home_score", ""),
            row.get("away_score", ""),
        ]
    )

    return hashlib.sha256(raw_identifier.encode("utf-8")).hexdigest()


# Détermine le statut du match selon la présence des scores.
def build_match_status(row: dict) -> str:
    if has_score(row.get("home_score")) and has_score(row.get("away_score")):
        return "FINISHED"

    return "SCHEDULED"


# Détermine un code compétition interne simple selon le tournoi.
def build_competition_code(row: dict) -> str:
    tournament = row.get("tournament", "")

    if tournament == WORLD_CUP_TOURNAMENT:
        return "WC"

    if tournament == WORLD_CUP_QUALIFICATION_TOURNAMENT:
        return "WCQ"

    return DEFAULT_COMPETITION_CODE


# Charge et filtre les lignes du fichier results.csv.
def load_kaggle_rows(dataset_path: Path, scope: str, include_unfinished: bool) -> list[dict]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Fichier CSV introuvable : {dataset_path}")

    selected_rows = []

    with dataset_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            if not is_row_in_scope(row, scope):
                continue

            match_status = build_match_status(row)

            if not include_unfinished and match_status != "FINISHED":
                continue

            selected_rows.append(row)

    return selected_rows


# Insère ou met à jour les lignes Kaggle dans ml_national.raw_matches.
def upsert_kaggle_matches(
    connection: psycopg.Connection,
    rows: list[dict],
    source_name: str,
) -> int:
    upserted_rows = 0

    with connection.cursor() as cursor:
        for row in rows:
            source_match_id = build_source_match_id(row)
            match_status = build_match_status(row)

            cursor.execute(
                """
                INSERT INTO ml_national.raw_matches (
                    source_name,
                    source_match_id,
                    competition_code,
                    competition_name,
                    season,
                    match_date_utc,
                    stage,
                    group_name,
                    home_team_name,
                    away_team_name,
                    home_score,
                    away_score,
                    match_status,
                    is_neutral_venue,
                    raw_payload,
                    source_updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (source_name, source_match_id)
                DO UPDATE SET
                    competition_code = EXCLUDED.competition_code,
                    competition_name = EXCLUDED.competition_name,
                    season = EXCLUDED.season,
                    match_date_utc = EXCLUDED.match_date_utc,
                    stage = EXCLUDED.stage,
                    group_name = EXCLUDED.group_name,
                    home_team_name = EXCLUDED.home_team_name,
                    away_team_name = EXCLUDED.away_team_name,
                    home_score = EXCLUDED.home_score,
                    away_score = EXCLUDED.away_score,
                    match_status = EXCLUDED.match_status,
                    is_neutral_venue = EXCLUDED.is_neutral_venue,
                    raw_payload = EXCLUDED.raw_payload,
                    source_updated_at = EXCLUDED.source_updated_at,
                    imported_at = NOW()
                """,
                (
                    source_name,
                    source_match_id,
                    build_competition_code(row),
                    row.get("tournament"),
                    row.get("date", "")[:4] or None,
                    row.get("date"),
                    None,
                    None,
                    row.get("home_team"),
                    row.get("away_team"),
                    to_int(row.get("home_score")),
                    to_int(row.get("away_score")),
                    match_status,
                    to_bool(row.get("neutral")),
                    Jsonb(row),
                    None,
                ),
            )

            upserted_rows += 1

    return upserted_rows


# Affiche un résumé simple de l'import effectué.
def print_import_summary(rows: list[dict], upserted_rows: int, scope: str) -> None:
    tournament_counts = Counter(row.get("tournament", "UNKNOWN") for row in rows)
    status_counts = Counter(build_match_status(row) for row in rows)

    print("Import Kaggle national terminé avec succès.")
    print(f"Scope demandé : {scope}")
    print(f"Lignes sélectionnées : {len(rows)}")
    print(f"Lignes insérées ou mises à jour : {upserted_rows}")
    print("Table cible : ml_national.raw_matches")

    print("\nRépartition par statut :")
    for status, count in status_counts.items():
        print(f"- {status}: {count}")

    print("\nRépartition par tournoi :")
    for tournament, count in tournament_counts.items():
        print(f"- {tournament}: {count}")


# Exécute l'import complet du dataset Kaggle.
def main() -> None:
    try:
        args = parse_arguments()
        dataset_path = Path(args.dataset_path)

        database_url = get_database_url()
        rows = load_kaggle_rows(
            dataset_path=dataset_path,
            scope=args.scope,
            include_unfinished=args.include_unfinished,
        )

        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                upserted_rows = upsert_kaggle_matches(
                    connection=connection,
                    rows=rows,
                    source_name=DEFAULT_SOURCE_NAME,
                )

        print_import_summary(
            rows=rows,
            upserted_rows=upserted_rows,
            scope=args.scope,
        )

    except Exception as error:
        print("Erreur pendant l'import Kaggle national.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# data/external/national_results/results.csv
#        ↓
# backend/scripts/ml_national/import_kaggle_national_matches.py
#        ↓
# backend/.env
#        ↓
# PostgreSQL rubybets_db
#        ↓
# ml_national.raw_matches