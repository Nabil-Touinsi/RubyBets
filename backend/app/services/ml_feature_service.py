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


# Recupere une ligne de features ML depuis PostgreSQL a partir de son id.
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


# Prepare les features et les metadonnees necessaires pour une prediction ML 1X2.
def get_ml_1x2_features_by_id(feature_id: int) -> dict[str, Any]:
    row = fetch_ml_feature_row_by_id(feature_id)

    if row is None:
        raise LookupError(f"Aucune ligne ml.features trouvee pour id={feature_id}")

    return {
        "feature_id": row["id"],
        "clean_match_id": row["clean_match_id"],
        "target_result": row["target_result"],
        "features": build_features_from_database_row(row),
    }


# Schema de communication :
# ml_feature_service.py
#   -> lit PostgreSQL ml.features
#   -> extrait les 6 features ML attendues
#   -> prepare un dictionnaire exploitable par ml_1x2_prediction_service.py
#   -> sera appele par la route API experimentale ML