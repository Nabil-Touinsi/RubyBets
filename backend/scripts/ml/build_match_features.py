# Role du fichier :
# Ce script construit les premieres features Machine Learning de RubyBets
# a partir des matchs nettoyes stockes dans ml.clean_matches.

import os
import sys
from collections import defaultdict
from itertools import groupby
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"
LAST_MATCHES_LIMIT = 5
PROGRESS_STEP = 500


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


# Recupere l'URL de connexion PostgreSQL depuis les variables d'environnement.
def get_database_url() -> str:
    load_env_file()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL est absent du fichier backend/.env")

    return database_url


# Recupere tous les matchs nettoyes dans l'ordre chronologique.
def fetch_clean_matches(connection: psycopg.Connection) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
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
            ORDER BY match_date ASC, id ASC
            """
        )

        return list(cursor.fetchall())


# Supprime les anciennes features pour reconstruire un dataset coherent.
def delete_existing_features(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM ml.features")
        return cursor.rowcount


# Calcule les points obtenus par une equipe selon son role dans un match passe.
def calculate_team_points(match: dict, venue: str) -> int:
    if match["result"] == "DRAW":
        return 1

    if venue == "home" and match["result"] == "HOME_WIN":
        return 3

    if venue == "away" and match["result"] == "AWAY_WIN":
        return 3

    return 0


# Recupere les buts marques et encaisses par une equipe selon son role.
def get_goals_for_team(match: dict, venue: str) -> tuple[int, int]:
    if venue == "home":
        return match["home_goals"], match["away_goals"]

    return match["away_goals"], match["home_goals"]


# Calcule les statistiques recentes d'une equipe sur ses derniers matchs disponibles.
def calculate_recent_stats(
    matches: list[dict],
    venue: str,
) -> tuple[float | None, float | None, float | None]:
    if not matches:
        return None, None, None

    points = []
    goals_scored = []
    goals_conceded = []

    for match in matches:
        team_points = calculate_team_points(match, venue)
        scored, conceded = get_goals_for_team(match, venue)

        points.append(team_points)
        goals_scored.append(scored)
        goals_conceded.append(conceded)

    form_points = float(sum(points))
    goals_scored_avg = round(sum(goals_scored) / len(goals_scored), 2)
    goals_conceded_avg = round(sum(goals_conceded) / len(goals_conceded), 2)

    return form_points, goals_scored_avg, goals_conceded_avg


# Construit les features d'un match avec uniquement l'historique deja disponible.
def build_features_for_match(
    match: dict,
    team_history: dict[tuple[str, str, str], list[dict]],
) -> dict:
    league_code = match["league_code"]

    home_previous_matches = team_history[
        (league_code, match["home_team"], "home")
    ][-LAST_MATCHES_LIMIT:]

    away_previous_matches = team_history[
        (league_code, match["away_team"], "away")
    ][-LAST_MATCHES_LIMIT:]

    (
        home_form_points,
        home_goals_scored_avg,
        home_goals_conceded_avg,
    ) = calculate_recent_stats(home_previous_matches, venue="home")

    (
        away_form_points,
        away_goals_scored_avg,
        away_goals_conceded_avg,
    ) = calculate_recent_stats(away_previous_matches, venue="away")

    return {
        "clean_match_id": match["id"],
        "home_form_points_last_5": home_form_points,
        "away_form_points_last_5": away_form_points,
        "home_goals_scored_avg_last_5": home_goals_scored_avg,
        "away_goals_scored_avg_last_5": away_goals_scored_avg,
        "home_goals_conceded_avg_last_5": home_goals_conceded_avg,
        "away_goals_conceded_avg_last_5": away_goals_conceded_avg,
        "home_advantage": 1,
        "target_result": match["result"],
        "home_history_count": len(home_previous_matches),
        "away_history_count": len(away_previous_matches),
    }


# Ajoute les matchs d'une meme date a l'historique apres calcul des features.
def update_team_history(
    matches_for_date: list[dict],
    team_history: dict[tuple[str, str, str], list[dict]],
) -> None:
    for match in matches_for_date:
        league_code = match["league_code"]

        team_history[(league_code, match["home_team"], "home")].append(match)
        team_history[(league_code, match["away_team"], "away")].append(match)


# Construit toutes les features sans utiliser les matchs du meme jour.
def build_all_features(clean_matches: list[dict]) -> list[dict]:
    features = []
    team_history = defaultdict(list)
    processed_matches = 0
    total_matches = len(clean_matches)

    for match_date, matches_group in groupby(clean_matches, key=lambda row: row["match_date"]):
        matches_for_date = list(matches_group)

        for match in matches_for_date:
            feature = build_features_for_match(
                match=match,
                team_history=team_history,
            )

            features.append(feature)
            processed_matches += 1

            if processed_matches % PROGRESS_STEP == 0 or processed_matches == total_matches:
                print(
                    f"Progression features : {processed_matches}/{total_matches} matchs traites",
                    flush=True,
                )

        update_team_history(
            matches_for_date=matches_for_date,
            team_history=team_history,
        )

    return features


# Insere les features calculees dans ml.features.
def insert_features(connection: psycopg.Connection, features: list[dict]) -> int:
    values = [
        (
            feature["clean_match_id"],
            feature["home_form_points_last_5"],
            feature["away_form_points_last_5"],
            feature["home_goals_scored_avg_last_5"],
            feature["away_goals_scored_avg_last_5"],
            feature["home_goals_conceded_avg_last_5"],
            feature["away_goals_conceded_avg_last_5"],
            feature["home_advantage"],
            feature["target_result"],
        )
        for feature in features
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO ml.features (
                clean_match_id,
                home_form_points_last_5,
                away_form_points_last_5,
                home_goals_scored_avg_last_5,
                away_goals_scored_avg_last_5,
                home_goals_conceded_avg_last_5,
                away_goals_conceded_avg_last_5,
                home_advantage,
                target_result
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            values,
        )

    return len(features)


# Execute la construction complete des features ML.
def main() -> None:
    try:
        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                clean_matches = fetch_clean_matches(connection)

                print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)

                deleted_rows = delete_existing_features(connection)

                print(f"Anciennes features supprimees : {deleted_rows}", flush=True)
                print("Construction des features en cours...", flush=True)

                features = build_all_features(clean_matches)

                print("Insertion des features dans PostgreSQL...", flush=True)

                inserted_rows = insert_features(connection, features)

        matches_without_home_history = sum(
            1 for feature in features if feature["home_history_count"] == 0
        )
        matches_without_away_history = sum(
            1 for feature in features if feature["away_history_count"] == 0
        )

        print("Construction des features ML terminee avec succes.")
        print(f"Matchs nettoyes lus : {len(clean_matches)}")
        print(f"Anciennes features supprimees : {deleted_rows}")
        print(f"Features inserees dans ml.features : {inserted_rows}")
        print(f"Matchs sans historique domicile : {matches_without_home_history}")
        print(f"Matchs sans historique exterieur : {matches_without_away_history}")
        print("Regle anti-fuite respectee : seules les rencontres anterieures sont utilisees.")

    except Exception as error:
        print("Erreur pendant la construction des features ML.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schema de communication :
# ml.clean_matches
#        |
#        v
# backend/scripts/ml/build_match_features.py
#        |
#        v
# PostgreSQL rubybets_db
#        |
#        v
# ml.features