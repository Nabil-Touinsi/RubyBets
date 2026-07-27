# Role du fichier :
# Cet adaptateur prepare des donnees de match au format attendu par le service experimental V17.8,
# sans modifier PostgreSQL, ml.features, le frontend ou le scoring explicable V1.

from typing import Any

from app.services.ml_v17_8_service import (
    ABSTAIN_STATUS,
    ABSTAIN_VALUE,
    BTTS_REQUIRED_FEATURES,
    recommend_with_v17_8,
)


ADAPTER_SOURCE = "rubybets_ml_v17_8_feature_adapter"
ADAPTER_SCOPE = "experimental"
DEFAULT_BASE_SOURCE = "V17_REFERENCE_ADAPTER_UNAVAILABLE"


BTTS_SIGNAL_PATHS = {
    "v17_6_score": [
        "btts_signals.v17_6_score",
        "features.v17_6_score",
        "v17_6_score",
    ],
    "min_history_count_last_10": [
        "btts_signals.min_history_count_last_10",
        "features.min_history_count_last_10",
        "min_history_count_last_10",
    ],
    "expected_home_goals_proxy": [
        "btts_signals.expected_home_goals_proxy",
        "features.expected_home_goals_proxy",
        "expected_home_goals_proxy",
    ],
    "expected_away_goals_proxy": [
        "btts_signals.expected_away_goals_proxy",
        "features.expected_away_goals_proxy",
        "expected_away_goals_proxy",
    ],
    "expected_total_goals_proxy": [
        "btts_signals.expected_total_goals_proxy",
        "features.expected_total_goals_proxy",
        "expected_total_goals_proxy",
    ],
    "combined_btts_rate_last_10": [
        "btts_signals.combined_btts_rate_last_10",
        "features.combined_btts_rate_last_10",
        "combined_btts_rate_last_10",
    ],
    "combined_over_1_5_rate_last_10": [
        "btts_signals.combined_over_1_5_rate_last_10",
        "features.combined_over_1_5_rate_last_10",
        "combined_over_1_5_rate_last_10",
    ],
    "home_failed_to_score_rate_last_10": [
        "btts_signals.home_failed_to_score_rate_last_10",
        "features.home_failed_to_score_rate_last_10",
        "home_failed_to_score_rate_last_10",
    ],
    "away_failed_to_score_rate_last_10": [
        "btts_signals.away_failed_to_score_rate_last_10",
        "features.away_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
    ],
}


BASE_RECOMMENDATION_PATHS = {
    "v17_recommendation_status": [
        "v17_reference.status",
        "base_recommendation.status",
        "v17_recommendation_status",
    ],
    "v17_recommendation_type": [
        "v17_reference.type",
        "base_recommendation.type",
        "v17_recommendation_type",
    ],
    "v17_recommendation_value": [
        "v17_reference.value",
        "base_recommendation.value",
        "v17_recommendation_value",
    ],
    "v17_source": [
        "v17_reference.source",
        "base_recommendation.source",
        "v17_source",
    ],
}


# Recupere une valeur imbriquee dans un dictionnaire a partir d'un chemin de type "a.b.c".
def get_nested_value(payload: dict[str, Any], path: str) -> Any | None:
    current_value: Any = payload

    for path_part in path.split("."):
        if not isinstance(current_value, dict):
            return None

        if path_part not in current_value:
            return None

        current_value = current_value[path_part]

    return current_value


# Retourne la premiere valeur disponible parmi plusieurs chemins possibles.
def get_first_available_value(
    payload: dict[str, Any],
    paths: list[str],
    default: Any = None,
) -> Any:
    for path in paths:
        value = get_nested_value(payload, path)

        if value is not None:
            return value

    return default


# Extrait les signaux BTTS disponibles depuis des donnees deja preparees.
def build_btts_feature_values(prepared_match_data: dict[str, Any]) -> dict[str, Any]:
    return {
        feature_name: get_first_available_value(
            prepared_match_data,
            BTTS_SIGNAL_PATHS[feature_name],
        )
        for feature_name in BTTS_REQUIRED_FEATURES
    }


# Extrait la recommandation prudente V17/V17.0 si elle est fournie par une couche precedente.
def build_base_recommendation_values(
    prepared_match_data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "v17_recommendation_status": get_first_available_value(
            prepared_match_data,
            BASE_RECOMMENDATION_PATHS["v17_recommendation_status"],
            ABSTAIN_STATUS,
        ),
        "v17_recommendation_type": get_first_available_value(
            prepared_match_data,
            BASE_RECOMMENDATION_PATHS["v17_recommendation_type"],
            ABSTAIN_VALUE,
        ),
        "v17_recommendation_value": get_first_available_value(
            prepared_match_data,
            BASE_RECOMMENDATION_PATHS["v17_recommendation_value"],
            ABSTAIN_VALUE,
        ),
        "v17_source": get_first_available_value(
            prepared_match_data,
            BASE_RECOMMENDATION_PATHS["v17_source"],
            DEFAULT_BASE_SOURCE,
        ),
    }


# Construit le dictionnaire final de features compatible avec ml_v17_8_service.py.
def build_v17_8_features_from_prepared_match_data(
    prepared_match_data: dict[str, Any],
) -> dict[str, Any]:
    features = {}

    features.update(build_btts_feature_values(prepared_match_data))
    features.update(build_base_recommendation_values(prepared_match_data))

    return features


# Liste les features BTTS manquantes apres adaptation.
def get_adapter_missing_features(features: dict[str, Any]) -> list[str]:
    return [
        feature_name
        for feature_name in BTTS_REQUIRED_FEATURES
        if features.get(feature_name) is None
    ]


# Retourne le statut qualite des features adaptees.
def build_adapter_feature_status(features: dict[str, Any]) -> str:
    missing_features = get_adapter_missing_features(features)

    if missing_features:
        return "partial"

    return "complete"


# Construit les metadonnees de l'adaptation pour garder une trace claire de ce qui a ete prepare.
def build_adapter_metadata(
    prepared_match_data: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    match_id = get_first_available_value(
        prepared_match_data,
        ["match.id", "match_id", "id"],
    )

    competition_code = get_first_available_value(
        prepared_match_data,
        ["match.competition.code", "competition.code", "competition_code"],
    )

    return {
        "adapter_source": ADAPTER_SOURCE,
        "features_status": build_adapter_feature_status(features),
        "missing_features": get_adapter_missing_features(features),
        "match_id": match_id,
        "competition_code": competition_code,
        "base_recommendation_status": features.get("v17_recommendation_status"),
        "base_recommendation_type": features.get("v17_recommendation_type"),
        "message": "Adaptation experimentale. Les features doivent etre preparees en amont avant tout branchement sur des matchs reels.",
    }


# Adapte des donnees deja preparees puis appelle le service experimental V17.8.
def adapt_and_recommend_with_v17_8(
    prepared_match_data: dict[str, Any],
) -> dict[str, Any]:
    features = build_v17_8_features_from_prepared_match_data(prepared_match_data)
    recommendation = recommend_with_v17_8(features)

    return {
        "source": ADAPTER_SOURCE,
        "scope": ADAPTER_SCOPE,
        "status": "adapted",
        "message": "Adaptation V17.8 experimentale. Ne remplace pas le scoring explicable V1.",
        "adapter_metadata": build_adapter_metadata(prepared_match_data, features),
        "features": features,
        "result": recommendation,
    }


# Schema de communication :
# ml_v17_8_feature_adapter.py
#   -> recoit des donnees de match deja preparees par une future couche d'integration
#   -> extrait les signaux BTTS et la recommandation prudente V17/V17.0 si disponibles
#   -> construit un dictionnaire compatible avec ml_v17_8_service.py
#   -> appelle recommend_with_v17_8()
#   -> retourne une recommandation experimentale ou une abstention documentee
#   -> reste separe de PostgreSQL, ml.features, du frontend et du scoring explicable V1