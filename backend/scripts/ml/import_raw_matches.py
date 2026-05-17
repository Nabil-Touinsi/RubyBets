# Rôle du fichier :
# Ce script importe un dataset historique football au format CSV
# dans les tables Machine Learning ml.import_batches et ml.raw_matches.

from pathlib import Path
import argparse
import csv
import os
import sys

import psycopg
from psycopg.types.json import Jsonb


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"

DEFAULT_LEAGUE_CODE = "E0"
DEFAULT_SOURCE_NAME = "Football-Data.co.uk"


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
        description="Importer un CSV historique football dans ml.raw_matches."
    )

    parser.add_argument(
        "--csv",
        required=True,
        help="Chemin du fichier CSV à importer.",
    )

    parser.add_argument(
        "--season",
        required=True,
        help="Saison du dataset, exemple : 2022_2023.",
    )

    parser.add_argument(
        "--league-code",
        default=DEFAULT_LEAGUE_CODE,
        help="Code de la ligue. Exemple Premier League : E0.",
    )

    parser.add_argument(
        "--source-name",
        default=DEFAULT_SOURCE_NAME,
        help="Nom de la source du dataset.",
    )

    parser.add_argument(
        "--source-url",
        default=None,
        help="URL source du fichier CSV.",
    )

    return parser.parse_args()


# Résout le chemin du CSV, qu'il soit relatif ou absolu.
def resolve_csv_path(csv_path_argument: str) -> Path:
    csv_path = Path(csv_path_argument)

    if csv_path.is_absolute():
        return csv_path

    return PROJECT_ROOT / csv_path


# Lit le fichier CSV avec plusieurs encodages possibles et vérifie les colonnes nécessaires.
def read_csv_matches(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset introuvable : {csv_path}")

    supported_encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    last_error = None
    rows = []
    fieldnames = []

    for encoding in supported_encodings:
        try:
            with csv_path.open("r", encoding=encoding, newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                rows = list(reader)
                fieldnames = reader.fieldnames or []
            break
        except UnicodeDecodeError as error:
            last_error = error
            continue
    else:
        raise ValueError(
            f"Impossible de lire le CSV avec les encodages supportés : {csv_path}"
        ) from last_error

    required_columns = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
    missing_columns = required_columns - set(fieldnames)

    if missing_columns:
        raise ValueError(f"Colonnes manquantes dans le CSV : {missing_columns}")

    return rows


# Crée une ligne de suivi pour tracer l'import du fichier CSV.
def create_import_batch(
    connection: psycopg.Connection,
    league_code: str,
    season: str,
    source_name: str,
    source_file: str,
    source_url: str | None,
    row_count: int,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM ml.import_batches
            WHERE league_code = %s
              AND season = %s
              AND source_file = %s
              AND status IN ('imported', 'cleaned')
            """,
            (league_code, season, source_file),
        )

        existing_batch = cursor.fetchone()

        if existing_batch:
            raise RuntimeError(
                "Ce dataset a déjà été importé. "
                f"Batch existant id={existing_batch[0]}"
            )

        cursor.execute(
            """
            INSERT INTO ml.import_batches (
                league_code,
                season,
                source_name,
                source_file,
                source_url,
                row_count,
                status,
                notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'imported', %s)
            RETURNING id
            """,
            (
                league_code,
                season,
                source_name,
                source_file,
                source_url,
                row_count,
                "Import brut pour préparer le pipeline Machine Learning RubyBets.",
            ),
        )

        batch_id = cursor.fetchone()[0]
        return batch_id


# Insère chaque ligne brute du CSV dans la table ml.raw_matches.
def insert_raw_matches(
    connection: psycopg.Connection,
    import_batch_id: int,
    rows: list[dict],
) -> int:
    inserted_rows = 0

    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                INSERT INTO ml.raw_matches (
                    import_batch_id,
                    raw_date,
                    raw_home_team,
                    raw_away_team,
                    raw_home_goals,
                    raw_away_goals,
                    raw_result,
                    raw_data
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    import_batch_id,
                    row.get("Date"),
                    row.get("HomeTeam"),
                    row.get("AwayTeam"),
                    int(row["FTHG"]) if row.get("FTHG") not in (None, "") else None,
                    int(row["FTAG"]) if row.get("FTAG") not in (None, "") else None,
                    row.get("FTR"),
                    Jsonb(row),
                ),
            )

            inserted_rows += 1

    return inserted_rows


# Exécute l'import complet : lecture CSV, création du batch et insertion brute.
def main() -> None:
    try:
        args = parse_arguments()

        csv_path = resolve_csv_path(args.csv)
        source_file = csv_path.name

        database_url = get_database_url()
        rows = read_csv_matches(csv_path)

        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                import_batch_id = create_import_batch(
                    connection=connection,
                    league_code=args.league_code,
                    season=args.season,
                    source_name=args.source_name,
                    source_file=source_file,
                    source_url=args.source_url,
                    row_count=len(rows),
                )

                inserted_rows = insert_raw_matches(
                    connection=connection,
                    import_batch_id=import_batch_id,
                    rows=rows,
                )

        print("Import brut ML terminé avec succès.")
        print(f"Batch importé : {import_batch_id}")
        print(f"Ligue : {args.league_code}")
        print(f"Saison : {args.season}")
        print(f"Fichier source : {source_file}")
        print(f"Lignes CSV lues : {len(rows)}")
        print(f"Lignes insérées dans ml.raw_matches : {inserted_rows}")

    except Exception as error:
        print("Erreur pendant l'import brut ML.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# data/ml/raw/premier_league/*.csv
#        ↓
# backend/scripts/ml/import_raw_matches.py
#        ↓
# backend/.env
#        ↓
# PostgreSQL rubybets_db
#        ↓
# ml.import_batches + ml.raw_matches