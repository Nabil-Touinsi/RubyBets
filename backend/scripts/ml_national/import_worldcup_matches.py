# Rôle du fichier :
# Ce script importe les matchs de Coupe du Monde depuis Football-Data.org
# dans la table ml_national.raw_matches, sans modifier le pipeline ML club existant.

from pathlib import Path
import argparse
import os
import sys

import httpx
import psycopg
from psycopg.types.json import Jsonb


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"

DEFAULT_COMPETITION_CODE = "WC"
DEFAULT_STATUS = "SCHEDULED"
DEFAULT_SOURCE_NAME = "football-data.org"
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"


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


# Récupère la clé Football-Data depuis backend/.env.
def get_football_data_key() -> str:
    load_env_file()

    football_data_key = os.getenv("FOOTBALL_DATA_KEY")

    if not football_data_key:
        raise ValueError("FOOTBALL_DATA_KEY est absent du fichier backend/.env")

    return football_data_key


# Prépare les arguments utilisables en ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importer les matchs Coupe du Monde dans ml_national.raw_matches."
    )

    parser.add_argument(
        "--competition-code",
        default=DEFAULT_COMPETITION_CODE,
        help="Code compétition Football-Data. Par défaut : WC.",
    )

    parser.add_argument(
        "--status",
        default=DEFAULT_STATUS,
        help="Statut des matchs à importer. Par défaut : SCHEDULED.",
    )

    return parser.parse_args()


# Appelle Football-Data.org pour récupérer les matchs de la compétition demandée.
def fetch_competition_matches(
    competition_code: str,
    status: str | None,
) -> list[dict]:
    football_data_key = get_football_data_key()

    endpoint = f"{FOOTBALL_DATA_BASE_URL}/competitions/{competition_code}/matches"
    params = {}

    if status:
        params["status"] = status

    response = httpx.get(
        endpoint,
        headers={
            "X-Auth-Token": football_data_key,
            "Accept": "application/json",
        },
        params=params,
        timeout=30.0,
    )

    response.raise_for_status()
    payload = response.json()

    return payload.get("matches", [])


# Transforme une valeur en entier quand c'est possible.
def to_int(value: object) -> int | None:
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Extrait le score final depuis une réponse match Football-Data.
def extract_full_time_score(match: dict) -> tuple[int | None, int | None]:
    full_time_score = match.get("score", {}).get("fullTime", {})

    return (
        to_int(full_time_score.get("home")),
        to_int(full_time_score.get("away")),
    )


# Construit une saison lisible à partir des métadonnées Football-Data.
def build_season_label(match: dict) -> str | None:
    season = match.get("season", {})
    start_date = season.get("startDate")
    end_date = season.get("endDate")

    if start_date and end_date:
        start_year = start_date[:4]
        end_year = end_date[:4]

        if start_year == end_year:
            return start_year

        return f"{start_year}_{end_year}"

    return None


# Insère ou met à jour les matchs dans ml_national.raw_matches.
def upsert_raw_matches(
    connection: psycopg.Connection,
    matches: list[dict],
    source_name: str,
    fallback_competition_code: str,
) -> int:
    upserted_rows = 0

    with connection.cursor() as cursor:
        for match in matches:
            competition = match.get("competition", {})
            home_team = match.get("homeTeam", {})
            away_team = match.get("awayTeam", {})
            home_score, away_score = extract_full_time_score(match)

            source_match_id = str(match.get("id"))

            if not source_match_id or source_match_id == "None":
                continue

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
                    competition.get("code") or fallback_competition_code,
                    competition.get("name"),
                    build_season_label(match),
                    match.get("utcDate"),
                    match.get("stage"),
                    match.get("group"),
                    home_team.get("name"),
                    away_team.get("name"),
                    home_score,
                    away_score,
                    match.get("status"),
                    True,
                    Jsonb(match),
                    match.get("lastUpdated"),
                ),
            )

            upserted_rows += 1

    return upserted_rows


# Exécute l'import complet des matchs Coupe du Monde.
def main() -> None:
    try:
        args = parse_arguments()
        competition_code = args.competition_code.upper()
        status = args.status.upper() if args.status else None

        database_url = get_database_url()
        matches = fetch_competition_matches(
            competition_code=competition_code,
            status=status,
        )

        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                upserted_rows = upsert_raw_matches(
                    connection=connection,
                    matches=matches,
                    source_name=DEFAULT_SOURCE_NAME,
                    fallback_competition_code=competition_code,
                )

        print("Import Coupe du Monde terminé avec succès.")
        print(f"Compétition : {competition_code}")
        print(f"Statut demandé : {status or 'ALL'}")
        print(f"Matchs récupérés : {len(matches)}")
        print(f"Lignes insérées ou mises à jour : {upserted_rows}")
        print("Table cible : ml_national.raw_matches")

    except Exception as error:
        print("Erreur pendant l'import Coupe du Monde.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# Football-Data.org / compétitions WC
#        ↓
# backend/scripts/ml_national/import_worldcup_matches.py
#        ↓
# backend/.env
#        ↓
# PostgreSQL rubybets_db
#        ↓
# ml_national.raw_matches