# Rôle du fichier :
# Ce script nettoie les matchs nationaux stockés dans ml_national.raw_matches
# et les insère dans ml_national.clean_matches avec une logique Team A / Team B.

from pathlib import Path
import argparse
import os
import sys
import unicodedata
from collections import Counter

import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"

DEFAULT_SOURCE_NAME = "kaggle-international-football-results"
DEFAULT_COMPETITION_CODES = ["WC", "WCQ"]


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
        description="Nettoyer les matchs nationaux bruts vers ml_national.clean_matches."
    )

    parser.add_argument(
        "--source-name",
        default=DEFAULT_SOURCE_NAME,
        help="Source à nettoyer. Par défaut : dataset Kaggle national.",
    )

    parser.add_argument(
        "--competition-codes",
        default=",".join(DEFAULT_COMPETITION_CODES),
        help="Codes compétition à nettoyer, séparés par des virgules. Par défaut : WC,WCQ.",
    )

    parser.add_argument(
        "--include-scheduled",
        action="store_true",
        help="Inclure les matchs sans score. Par défaut, seuls les matchs terminés sont nettoyés.",
    )

    return parser.parse_args()


# Normalise un nom pour comparer équipes et pays hôtes.
def normalize_name(value: str | None) -> str:
    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = normalized.lower().strip()

    replacements = {
        ".": "",
        ",": "",
        "-": " ",
        "_": " ",
        "'": "",
        "’": "",
    }

    for old_value, new_value in replacements.items():
        normalized = normalized.replace(old_value, new_value)

    normalized = " ".join(normalized.split())

    aliases = {
        "usa": "united states",
        "u s a": "united states",
        "united states of america": "united states",
        "korea republic": "south korea",
        "republic of korea": "south korea",
        "ir iran": "iran",
        "czech republic": "czechia",
        "turkiye": "turkey",
    }

    return aliases.get(normalized, normalized)


# Calcule le résultat dans une logique Team A / Team B, sans faux avantage domicile.
def build_team_a_b_result(home_score: int | None, away_score: int | None) -> str | None:
    if home_score is None or away_score is None:
        return None

    if home_score > away_score:
        return "TEAM_A_WIN"

    if home_score < away_score:
        return "TEAM_B_WIN"

    return "DRAW"


# Détermine si le match correspond à une phase de groupes.
def is_group_stage(stage: str | None, group_name: str | None) -> bool:
    stage_value = (stage or "").upper()

    return "GROUP" in stage_value or bool(group_name)


# Détermine si le match correspond à une phase à élimination directe.
def is_knockout_stage(stage: str | None) -> bool:
    stage_value = (stage or "").upper()

    knockout_markers = [
        "LAST_16",
        "ROUND_OF_16",
        "QUARTER",
        "SEMI",
        "FINAL",
        "THIRD",
        "PLAY_OFF",
    ]

    return any(marker in stage_value for marker in knockout_markers)


# Détermine si Team A ou Team B joue dans son pays hôte.
def build_host_context(match: dict) -> tuple[bool, bool, str]:
    raw_payload = match.get("raw_payload") or {}

    country = raw_payload.get("country")
    team_a = match.get("home_team_name")
    team_b = match.get("away_team_name")

    normalized_country = normalize_name(country)
    normalized_team_a = normalize_name(team_a)
    normalized_team_b = normalize_name(team_b)

    team_a_is_host = bool(normalized_country and normalized_country == normalized_team_a)
    team_b_is_host = bool(normalized_country and normalized_country == normalized_team_b)

    if team_a_is_host:
        return True, False, "TEAM_A"

    if team_b_is_host:
        return False, True, "TEAM_B"

    return False, False, "NONE"


# Récupère les matchs bruts exploitables selon la source et les compétitions ciblées.
def fetch_raw_matches(
    connection: psycopg.Connection,
    source_name: str,
    competition_codes: list[str],
    include_scheduled: bool,
) -> list[dict]:
    score_filter = ""

    if not include_scheduled:
        score_filter = """
            AND home_score IS NOT NULL
            AND away_score IS NOT NULL
            AND match_status = 'FINISHED'
        """

    query = f"""
        SELECT
            id,
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
        FROM ml_national.raw_matches
        WHERE source_name = %s
          AND competition_code = ANY(%s)
          AND match_date_utc IS NOT NULL
          AND home_team_name IS NOT NULL
          AND away_team_name IS NOT NULL
          {score_filter}
        ORDER BY match_date_utc ASC, id ASC
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (source_name, competition_codes))
        return list(cursor.fetchall())


# Supprime les anciennes lignes nettoyées correspondant aux matchs bruts sélectionnés.
def delete_existing_clean_matches(connection: psycopg.Connection, raw_match_ids: list[int]) -> int:
    if not raw_match_ids:
        return 0

    with connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM ml_national.clean_matches
            WHERE raw_match_id = ANY(%s)
            """,
            (raw_match_ids,),
        )

        return cursor.rowcount


# Insère les matchs nettoyés dans ml_national.clean_matches.
def insert_clean_matches(connection: psycopg.Connection, raw_matches: list[dict]) -> int:
    inserted_rows = 0

    with connection.cursor() as cursor:
        for match in raw_matches:
            team_a_is_host, team_b_is_host, host_advantage_side = build_host_context(match)
            result_1x2 = build_team_a_b_result(
                home_score=match.get("home_score"),
                away_score=match.get("away_score"),
            )

            cursor.execute(
                """
                INSERT INTO ml_national.clean_matches (
                    raw_match_id,
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
                    result_1x2,
                    is_neutral_venue,
                    team_a_is_host,
                    team_b_is_host,
                    host_advantage_side,
                    is_group_stage,
                    is_knockout_stage,
                    data_quality_status
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    match.get("id"),
                    match.get("competition_code"),
                    match.get("competition_name"),
                    match.get("season"),
                    match.get("match_date_utc"),
                    match.get("stage"),
                    match.get("group_name"),
                    match.get("home_team_name"),
                    match.get("away_team_name"),
                    match.get("home_score"),
                    match.get("away_score"),
                    result_1x2,
                    match.get("is_neutral_venue"),
                    team_a_is_host,
                    team_b_is_host,
                    host_advantage_side,
                    is_group_stage(match.get("stage"), match.get("group_name")),
                    is_knockout_stage(match.get("stage")),
                    "cleaned_finished" if result_1x2 else "cleaned_without_result",
                ),
            )

            inserted_rows += 1

    return inserted_rows


# Affiche un résumé clair du nettoyage effectué.
def print_cleaning_summary(raw_matches: list[dict], deleted_rows: int, inserted_rows: int) -> None:
    competition_counts = Counter(match.get("competition_code") for match in raw_matches)
    result_counts = Counter(
        build_team_a_b_result(match.get("home_score"), match.get("away_score"))
        for match in raw_matches
    )
    host_counts = Counter(build_host_context(match)[2] for match in raw_matches)

    print("Nettoyage national terminé avec succès.")
    print(f"Matchs bruts sélectionnés : {len(raw_matches)}")
    print(f"Anciennes lignes clean supprimées : {deleted_rows}")
    print(f"Nouvelles lignes clean insérées : {inserted_rows}")
    print("Table cible : ml_national.clean_matches")

    print("\nRépartition par compétition :")
    for competition_code, count in competition_counts.items():
        print(f"- {competition_code}: {count}")

    print("\nRépartition par résultat Team A / Team B :")
    for result, count in result_counts.items():
        print(f"- {result}: {count}")

    print("\nRépartition du contexte hôte :")
    for host_side, count in host_counts.items():
        print(f"- {host_side}: {count}")


# Exécute le nettoyage complet des matchs nationaux.
def main() -> None:
    try:
        args = parse_arguments()
        source_name = args.source_name
        competition_codes = [
            code.strip().upper()
            for code in args.competition_codes.split(",")
            if code.strip()
        ]

        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                raw_matches = fetch_raw_matches(
                    connection=connection,
                    source_name=source_name,
                    competition_codes=competition_codes,
                    include_scheduled=args.include_scheduled,
                )

                raw_match_ids = [match["id"] for match in raw_matches]
                deleted_rows = delete_existing_clean_matches(
                    connection=connection,
                    raw_match_ids=raw_match_ids,
                )
                inserted_rows = insert_clean_matches(
                    connection=connection,
                    raw_matches=raw_matches,
                )

        print_cleaning_summary(
            raw_matches=raw_matches,
            deleted_rows=deleted_rows,
            inserted_rows=inserted_rows,
        )

    except Exception as error:
        print("Erreur pendant le nettoyage national.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# ml_national.raw_matches
#        ↓
# backend/scripts/ml_national/clean_national_matches.py
#        ↓
# backend/.env
#        ↓
# PostgreSQL rubybets_db
#        ↓
# ml_national.clean_matches