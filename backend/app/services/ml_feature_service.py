# Role du fichier :
# Ce service recupere les features ML stockees dans PostgreSQL
# pour alimenter la baseline experimentale 1X2.

from decimal import Decimal
from typing import Any

from app.services.database_service import get_database_connection
from app.services.ml_1x2_prediction_service import FEATURE_COLUMNS


SELECTED_COLUMNS = [
    "id",
    "clean_match_id",
    *FEATURE_COLUMNS,
    "target_result",
]


# Convertit une valeur numerique PostgreSQL en float utilisable par le modele ML.
def convert_numeric_value(value: Any) -> float:
    if value is None:
        raise ValueError("Une feature ML attendue est vide.")

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


# Transforme une ligne ml.features en dictionnaire de features dans le bon format.
def build_features_from_database_row(row: dict[str, Any]) -> dict[str, float]:
    return {
        column: convert_numeric_value(row[column])
        for column in FEATURE_COLUMNS
    }


# Recupere une ligne de features ML depuis PostgreSQL a partir de son id technique.
def fetch_ml_feature_row_by_id(feature_id: int) -> dict[str, Any] | None:
    query = """
        SELECT
            id,
            clean_match_id,
            home_form_points_last_5,
            away_form_points_last_5,
            home_goals_scored_avg_last_5,
            away_goals_scored_avg_last_5,
            home_goals_conceded_avg_last_5,
            away_goals_conceded_avg_last_5,
            target_result
        FROM ml.features
        WHERE id = %s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (feature_id,))
            row = cursor.fetchone()

            if row is None:
                return None

            column_names = [column.name for column in cursor.description]
            return dict(zip(column_names, row))


# Recupere une ligne de features ML depuis PostgreSQL a partir du clean_match_id.
def fetch_ml_feature_row_by_clean_match_id(clean_match_id: int) -> dict[str, Any] | None:
    query = """
        SELECT
            id,
            clean_match_id,
            home_form_points_last_5,
            away_form_points_last_5,
            home_goals_scored_avg_last_5,
            away_goals_scored_avg_last_5,
            home_goals_conceded_avg_last_5,
            away_goals_conceded_avg_last_5,
            target_result
        FROM ml.features
        WHERE clean_match_id = %s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (clean_match_id,))
            row = cursor.fetchone()

            if row is None:
                return None

            column_names = [column.name for column in cursor.description]
            return dict(zip(column_names, row))

# Recupere plusieurs lignes de features ML depuis PostgreSQL a partir de plusieurs clean_match_id.
def fetch_ml_feature_rows_by_clean_match_ids(
    clean_match_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not clean_match_ids:
        return {}

    placeholders = ", ".join(["%s"] * len(clean_match_ids))

    query = f"""
        SELECT
            id,
            clean_match_id,
            home_form_points_last_5,
            away_form_points_last_5,
            home_goals_scored_avg_last_5,
            away_goals_scored_avg_last_5,
            home_goals_conceded_avg_last_5,
            away_goals_conceded_avg_last_5,
            target_result
        FROM ml.features
        WHERE clean_match_id IN ({placeholders})
        ORDER BY clean_match_id;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(clean_match_ids))
            rows = cursor.fetchall()

            column_names = [column.name for column in cursor.description]

            return {
                dict(zip(column_names, row))["clean_match_id"]: dict(zip(column_names, row))
                for row in rows
            }


# Prepare plusieurs payloads de features ML 1X2 depuis une liste de clean_match_id.
def get_ml_1x2_features_by_clean_match_ids(
    clean_match_ids: list[int],
) -> list[dict[str, Any]]:
    ordered_clean_match_ids = list(dict.fromkeys(clean_match_ids))

    if not ordered_clean_match_ids:
        raise ValueError("La liste clean_match_ids ne doit pas etre vide.")

    rows_by_clean_match_id = fetch_ml_feature_rows_by_clean_match_ids(
        ordered_clean_match_ids
    )

    missing_clean_match_ids = [
        clean_match_id
        for clean_match_id in ordered_clean_match_ids
        if clean_match_id not in rows_by_clean_match_id
    ]

    if missing_clean_match_ids:
        raise LookupError(
            f"Aucune ligne ml.features trouvee pour clean_match_id(s)={missing_clean_match_ids}"
        )

    return [
        build_ml_1x2_feature_payload(rows_by_clean_match_id[clean_match_id])
        for clean_match_id in ordered_clean_match_ids
    ]

# Prepare les features et les metadonnees necessaires pour une prediction ML 1X2.
def build_ml_1x2_feature_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": row["id"],
        "clean_match_id": row["clean_match_id"],
        "target_result": row["target_result"],
        "features": build_features_from_database_row(row),
    }


# Prepare les features ML 1X2 depuis l'id technique de la table ml.features.
def get_ml_1x2_features_by_id(feature_id: int) -> dict[str, Any]:
    row = fetch_ml_feature_row_by_id(feature_id)

    if row is None:
        raise LookupError(f"Aucune ligne ml.features trouvee pour id={feature_id}")

    return build_ml_1x2_feature_payload(row)


# Prepare les features ML 1X2 depuis le clean_match_id du match nettoye.
def get_ml_1x2_features_by_clean_match_id(clean_match_id: int) -> dict[str, Any]:
    row = fetch_ml_feature_row_by_clean_match_id(clean_match_id)

    if row is None:
        raise LookupError(
            f"Aucune ligne ml.features trouvee pour clean_match_id={clean_match_id}"
        )

    return build_ml_1x2_feature_payload(row)


# Schema de communication :
# ml_feature_service.py
#   -> lit PostgreSQL ml.features
#   -> recupere les features par id ou par clean_match_id
#   -> extrait les 6 features ML attendues
#   -> prepare un dictionnaire exploitable par ml_1x2_prediction_service.py
#   -> sera appele par la route API experimentale ML