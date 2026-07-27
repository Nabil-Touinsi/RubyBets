# Role du fichier :
# Cet adaptateur transforme une ligne de predictions nationales V18.3 en entree compatible
# avec le selecteur V18.3.3 strict reliability.

from __future__ import annotations

from typing import Any

from app.services.ml_national_v18_3_3_selector import select_market_with_v18_3_3


REQUIRED_V18_3_PREDICTION_COLUMNS = (
    "clean_match_id",
    "match_date_utc",
    "season",
    "competition_code",
    "competition_name",
    "team_a_name",
    "team_b_name",
    "1x2_prediction",
    "1x2_prob_TEAM_A_WIN",
    "1x2_prob_DRAW",
    "1x2_prob_TEAM_B_WIN",
    "1x2_max_probability",
    "over_1_5_prediction",
    "over_1_5_prob_YES",
    "over_1_5_max_probability",
    "over_2_5_prediction",
    "over_2_5_prob_YES",
    "over_2_5_prob_NO",
    "over_2_5_max_probability",
    "btts_prediction",
    "btts_prob_YES",
    "btts_prob_NO",
    "btts_max_probability",
)


# Recupere une valeur dans une ligne de prediction sans faire planter l'adaptateur.
def get_row_value(row: dict[str, Any], column: str, default: Any = None) -> Any:
    value = row.get(column, default)

    if value == "":
        return default

    return value


# Verifie quelles colonnes attendues sont absentes de la ligne fournie.
def get_missing_prediction_columns(row: dict[str, Any]) -> list[str]:
    return [
        column
        for column in REQUIRED_V18_3_PREDICTION_COLUMNS
        if column not in row
    ]


# Transforme une ligne V18.3 en features internes attendues par le selecteur V18.3.3.
def build_v18_3_3_selector_features_from_prediction_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "1x2_prediction": get_row_value(row, "1x2_prediction"),
        "1x2_prob_TEAM_A_WIN": get_row_value(row, "1x2_prob_TEAM_A_WIN"),
        "1x2_prob_DRAW": get_row_value(row, "1x2_prob_DRAW"),
        "1x2_prob_TEAM_B_WIN": get_row_value(row, "1x2_prob_TEAM_B_WIN"),
        "1x2_max_probability": get_row_value(row, "1x2_max_probability"),
        "over_1_5_prediction": get_row_value(row, "over_1_5_prediction"),
        "over_1_5_prob_YES": get_row_value(row, "over_1_5_prob_YES"),
        "over_1_5_max_probability": get_row_value(row, "over_1_5_max_probability"),
        "over_2_5_prediction": get_row_value(row, "over_2_5_prediction"),
        "over_2_5_prob_YES": get_row_value(row, "over_2_5_prob_YES"),
        "over_2_5_prob_NO": get_row_value(row, "over_2_5_prob_NO"),
        "over_2_5_max_probability": get_row_value(row, "over_2_5_max_probability"),
        "btts_prediction": get_row_value(row, "btts_prediction"),
        "btts_prob_YES": get_row_value(row, "btts_prob_YES"),
        "btts_prob_NO": get_row_value(row, "btts_prob_NO"),
        "btts_max_probability": get_row_value(row, "btts_max_probability"),
    }


# Recupere les metadonnees utiles du match pour enrichir la reponse backend.
def build_v18_3_3_match_metadata_from_prediction_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "clean_match_id": get_row_value(row, "clean_match_id"),
        "feature_id": get_row_value(row, "feature_id"),
        "feature_version": get_row_value(row, "feature_version"),
        "match_date_utc": get_row_value(row, "match_date_utc"),
        "season": get_row_value(row, "season"),
        "competition_code": get_row_value(row, "competition_code"),
        "competition_name": get_row_value(row, "competition_name"),
        "stage": get_row_value(row, "stage"),
        "group_name": get_row_value(row, "group_name"),
        "team_a_name": get_row_value(row, "team_a_name"),
        "team_b_name": get_row_value(row, "team_b_name"),
    }


# Applique le selecteur V18.3.3 a une ligne de predictions V18.3.
def select_v18_3_3_from_prediction_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    missing_columns = get_missing_prediction_columns(row)

    if missing_columns:
        return {
            "source": "rubybets_ml_national_v18_3_3_inference_adapter",
            "scope": "experimental_backend",
            "status": "INVALID_INPUT",
            "missing_columns": missing_columns,
            "responsible_note": (
                "Impossible d'appliquer le selecteur V18.3.3 : "
                "la ligne de prediction est incomplete."
            ),
        }

    features = build_v18_3_3_selector_features_from_prediction_row(row)
    metadata = build_v18_3_3_match_metadata_from_prediction_row(row)
    selector_result = select_market_with_v18_3_3(features)

    return {
        "source": "rubybets_ml_national_v18_3_3_inference_adapter",
        "scope": "experimental_backend",
        "status": "computed",
        "match": metadata,
        "selector_result": selector_result,
    }


# Schema de communication :
# ml_national_v18_3_3_inference_adapter.py
#   -> recoit une ligne issue du CSV 348 ou d'une future source interne de predictions
#   -> transforme les colonnes V18.3 en features compatibles V18.3.3
#   -> appelle ml_national_v18_3_3_selector.py
#   -> retourne le match + la recommandation ou l'abstention
