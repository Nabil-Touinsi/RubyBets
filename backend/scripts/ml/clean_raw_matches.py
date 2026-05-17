# Rôle du fichier :
# Ce script nettoie les matchs bruts importés depuis Football-Data.co.uk
# et les insère dans la table ml.clean_matches pour préparer le dataset ML.

from datetime import datetime
import argparse
import os
import sys
from pathlib import Path

import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"


# Charge les variables du fichier .env local sans afficher de secret.
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


# Récupère l'URL de connexion PostgreSQL depuis les variables d'environnement.
def get_database_url() -> str:
    load_env_file()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL est absent du fichier backend/.env")

    return database_url


# Prépare les arguments utilisables en ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nettoyer un batch importé dans ml.raw_matches vers ml.clean_matches."
    )

    parser.add_argument(
        "--source-file",
        required=True,
        help="Nom du fichier source déjà importé, exemple : E0_2022_2023.csv.",
    )

    return parser.parse_args()


# Convertit une date brute du CSV au format date PostgreSQL.
def parse_match_date(raw_date: str):
    supported_formats = ["%d/%m/%Y", "%d/%m/%y"]

    for date_format in supported_formats:
        try:
            return datetime.strptime(raw_date.strip(), date_format).date()
        except ValueError:
            continue

    raise ValueError(f"Format de date non reconnu dans le CSV : {raw_date}")


# Convertit le résultat Football-Data.co.uk vers le format métier RubyBets.
def map_result(raw_result: str) -> str:
    clean_raw_result = str(raw_result).strip()

    result_mapping = {
        "H": "HOME_WIN",
        "D": "DRAW",
        "A": "AWAY_WIN",
    }

    if clean_raw_result not in result_mapping:
        raise ValueError(f"Résultat inconnu dans le CSV : {raw_result}")

    return result_mapping[clean_raw_result]


# Récupère le batch importé et ses matchs bruts associés.
def fetch_raw_matches(
    connection: psycopg.Connection,
    source_file: str,
) -> tuple[int, str, str, list[dict]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, league_code, season
            FROM ml.import_batches
            WHERE source_file = %s
              AND status = 'imported'
            ORDER BY imported_at DESC
            LIMIT 1
            """,
            (source_file,),
        )

        batch = cursor.fetchone()

        if not batch:
            raise RuntimeError(
                "Aucun batch importé à nettoyer pour ce fichier "
                f"ou batch déjà nettoyé : {source_file}"
            )

        batch_id, league_code, season = batch

        cursor.execute(
            """
            SELECT
                id,
                raw_date,
                raw_home_team,
                raw_away_team,
                raw_home_goals,
                raw_away_goals,
                raw_result
            FROM ml.raw_matches
            WHERE import_batch_id = %s
            ORDER BY id
            """,
            (batch_id,),
        )

        rows = cursor.fetchall()

    raw_matches = [
        {
            "id": row[0],
            "raw_date": row[1],
            "raw_home_team": row[2],
            "raw_away_team": row[3],
            "raw_home_goals": row[4],
            "raw_away_goals": row[5],
            "raw_result": row[6],
        }
        for row in rows
    ]

    return batch_id, league_code, season, raw_matches


# Vérifie que le batch n'a pas déjà produit des matchs nettoyés.
def ensure_batch_is_not_already_cleaned(
    connection: psycopg.Connection,
    batch_id: int,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ml.clean_matches clean
            JOIN ml.raw_matches raw ON raw.id = clean.raw_match_id
            WHERE raw.import_batch_id = %s
            """,
            (batch_id,),
        )

        existing_clean_rows = cursor.fetchone()[0]

    if existing_clean_rows > 0:
        raise RuntimeError(
            "Ce batch possède déjà des matchs nettoyés "
            f"({existing_clean_rows} lignes)."
        )
    
# Vérifie qu'une ligne brute contient bien les informations minimales d'un match.
def is_complete_match_row(raw_match: dict) -> bool:
    text_fields = [
        "raw_date",
        "raw_home_team",
        "raw_away_team",
        "raw_result",
    ]

    numeric_fields = [
        "raw_home_goals",
        "raw_away_goals",
    ]

    has_required_text = all(
        str(raw_match.get(field) or "").strip()
        for field in text_fields
    )

    has_required_scores = all(
        raw_match.get(field) is not None
        for field in numeric_fields
    )

    return has_required_text and has_required_scores

# Insère les matchs nettoyés dans ml.clean_matches.
def insert_clean_matches(
    connection: psycopg.Connection,
    league_code: str,
    season: str,
    raw_matches: list[dict],
) -> int:
    inserted_rows = 0

    with connection.cursor() as cursor:
        for raw_match in raw_matches:
            if not is_complete_match_row(raw_match):
                continue

            clean_result = map_result(raw_match["raw_result"])
            match_date = parse_match_date(raw_match["raw_date"])

            cursor.execute(
                """
                INSERT INTO ml.clean_matches (
                    raw_match_id,
                    match_date,
                    league_code,
                    season,
                    home_team,
                    away_team,
                    home_goals,
                    away_goals,
                    result,
                    is_valid
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                """,
                (
                    raw_match["id"],
                    match_date,
                    league_code,
                    season,
                    raw_match["raw_home_team"],
                    raw_match["raw_away_team"],
                    raw_match["raw_home_goals"],
                    raw_match["raw_away_goals"],
                    clean_result,
                ),
            )

            inserted_rows += 1

    return inserted_rows


# Met à jour le statut du batch pour indiquer que le nettoyage est terminé.
def mark_batch_as_cleaned(connection: psycopg.Connection, batch_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ml.import_batches
            SET status = 'cleaned',
                notes = COALESCE(notes, '') || ' Nettoyage terminé vers ml.clean_matches.'
            WHERE id = %s
            """,
            (batch_id,),
        )


# Exécute le nettoyage complet des données brutes vers les données propres.
def main() -> None:
    try:
        args = parse_arguments()
        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                batch_id, league_code, season, raw_matches = fetch_raw_matches(
                    connection=connection,
                    source_file=args.source_file,
                )

                ensure_batch_is_not_already_cleaned(connection, batch_id)

                inserted_rows = insert_clean_matches(
                    connection=connection,
                    league_code=league_code,
                    season=season,
                    raw_matches=raw_matches,
                )

                mark_batch_as_cleaned(connection, batch_id)

        print("Nettoyage ML terminé avec succès.")
        print(f"Batch nettoyé : {batch_id}")
        print(f"Fichier source : {args.source_file}")
        print(f"Ligue : {league_code}")
        print(f"Saison : {season}")
        print(f"Lignes brutes lues : {len(raw_matches)}")
        print(f"Lignes insérées dans ml.clean_matches : {inserted_rows}")

    except Exception as error:
        print("Erreur pendant le nettoyage ML.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# ml.import_batches + ml.raw_matches
#        ↓
# backend/scripts/ml/clean_raw_matches.py
#        ↓
# PostgreSQL rubybets_db
#        ↓
# ml.clean_matches