# Rôle du fichier :
# Ce service prépare l'utilisation expérimentale du sélecteur V17.8 sans modifier le scoring explicable V1.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

STRICT_TYPE = "STRICT_1X2"
DOUBLE_CHANCE_TYPE = "DOUBLE_CHANCE"
GOALS_OVER_15_TYPE = "GOALS_OVER_1_5"
BTTS_TYPE = "BTTS"

BTTS_YES_VALUE = "BTTS_YES"
ABSTAIN_VALUE = "ABSTAIN"

V17_8_STATUS = "V17_8_USER_OBJECTIVE_BTTS_PRO_REVIEW"
V17_8_SOURCE = "V17_8_BTTS_YES_USER_OBJECTIVE"
V17_8_STRATEGY_NAME = (
    "v17_8_user_objective_btts_replace_over15_or_fallback_"
    "s520_mh8_eg0900_tot1800_bt550_ov500_fail450_limitall"
)

BTTS_REQUIRED_FEATURES = [
    "v17_6_score",
    "min_history_count_last_10",
    "expected_home_goals_proxy",
    "expected_away_goals_proxy",
    "expected_total_goals_proxy",
    "combined_btts_rate_last_10",
    "combined_over_1_5_rate_last_10",
    "home_failed_to_score_rate_last_10",
    "away_failed_to_score_rate_last_10",
]

MARKET_ACCURACY_REFERENCES = {
    STRICT_TYPE: 0.8707,
    DOUBLE_CHANCE_TYPE: 0.8565,
    GOALS_OVER_15_TYPE: 0.7694,
    BTTS_TYPE: 0.6058,
}

V17_8_GLOBAL_REFERENCES = {
    "accuracy": 0.8000,
    "coverage": 0.7946,
    "abstention_rate": 0.2054,
    "selected_rows": 4235,
}


@dataclass(frozen=True)
class V178StrategySpec:
    name: str
    mode: str
    min_btts_score: float
    min_history_count: int
    min_expected_team_goals: float
    min_expected_total_goals: float
    min_combined_btts_rate: float
    min_combined_over_15_rate: float
    max_failed_to_score_rate: float


# Retourne la stratégie V17.8 retenue dans les preuves ML.
def get_v17_8_strategy_spec() -> V178StrategySpec:
    return V178StrategySpec(
        name=V17_8_STRATEGY_NAME,
        mode="replace_over15_or_fallback",
        min_btts_score=0.52,
        min_history_count=8,
        min_expected_team_goals=0.90,
        min_expected_total_goals=1.80,
        min_combined_btts_rate=0.55,
        min_combined_over_15_rate=0.50,
        max_failed_to_score_rate=0.45,
    )


# Convertit une valeur numérique en float sans faire planter le service expérimental.
def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


# Convertit une valeur numérique en int sans faire planter le service expérimental.
def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


# Repère les features manquantes pour évaluer le signal BTTS V17.8.
def get_missing_btts_features(features: dict[str, Any]) -> list[str]:
    return [
        feature_name
        for feature_name in BTTS_REQUIRED_FEATURES
        if feature_name not in features or features[feature_name] is None
    ]


# Indique si une recommandation de base V17/V17.0 existe déjà.
def is_base_recommendation_selected(features: dict[str, Any]) -> bool:
    if features.get("v17_recommendation_status") == RECOMMEND_STATUS:
        return True

    recommendation_type = str(features.get("v17_recommendation_type", ""))
    return recommendation_type in {STRICT_TYPE, DOUBLE_CHANCE_TYPE, GOALS_OVER_15_TYPE}


# Indique si la recommandation de base est un Over 1.5 remplaçable par BTTS.
def is_base_recommendation_over_15(features: dict[str, Any]) -> bool:
    return str(features.get("v17_recommendation_type", "")) == GOALS_OVER_15_TYPE


# Évalue les gates BTTS de V17.8 et retourne les raisons bloquantes si le signal est refusé.
def evaluate_btts_gates(
    features: dict[str, Any],
    strategy: V178StrategySpec | None = None,
) -> dict[str, Any]:
    strategy = strategy or get_v17_8_strategy_spec()
    missing_features = get_missing_btts_features(features)

    if missing_features:
        return {
            "is_eligible": False,
            "reasons": ["MISSING_BTTS_FEATURES"],
            "missing_features": missing_features,
        }

    failed_reasons: list[str] = []

    if safe_float(features.get("v17_6_score")) < strategy.min_btts_score:
        failed_reasons.append("BTTS_SCORE_TOO_LOW")

    if safe_int(features.get("min_history_count_last_10")) < strategy.min_history_count:
        failed_reasons.append("HISTORY_TOO_LOW")

    if safe_float(features.get("expected_home_goals_proxy")) < strategy.min_expected_team_goals:
        failed_reasons.append("HOME_EXPECTED_GOALS_TOO_LOW")

    if safe_float(features.get("expected_away_goals_proxy")) < strategy.min_expected_team_goals:
        failed_reasons.append("AWAY_EXPECTED_GOALS_TOO_LOW")

    if safe_float(features.get("expected_total_goals_proxy")) < strategy.min_expected_total_goals:
        failed_reasons.append("TOTAL_EXPECTED_GOALS_TOO_LOW")

    if safe_float(features.get("combined_btts_rate_last_10")) < strategy.min_combined_btts_rate:
        failed_reasons.append("BTTS_RATE_TOO_LOW")

    if safe_float(features.get("combined_over_1_5_rate_last_10")) < strategy.min_combined_over_15_rate:
        failed_reasons.append("OVER_15_RATE_TOO_LOW")

    if safe_float(features.get("home_failed_to_score_rate_last_10")) > strategy.max_failed_to_score_rate:
        failed_reasons.append("HOME_FAILED_TO_SCORE_RATE_TOO_HIGH")

    if safe_float(features.get("away_failed_to_score_rate_last_10")) > strategy.max_failed_to_score_rate:
        failed_reasons.append("AWAY_FAILED_TO_SCORE_RATE_TOO_HIGH")

    return {
        "is_eligible": not failed_reasons,
        "reasons": failed_reasons,
        "missing_features": [],
    }


# Vérifie si BTTS peut remplacer Over 1.5 ou compléter une abstention selon la stratégie V17.8.
def can_use_btts_in_v17_8(features: dict[str, Any]) -> bool:
    base_selected = is_base_recommendation_selected(features)
    base_is_over_15 = is_base_recommendation_over_15(features)

    return (not base_selected) or base_is_over_15


# Déduit un niveau de confiance simple à partir du marché et de sa performance de référence.
def build_confidence_level(recommendation_type: str) -> str:
    accuracy_reference = MARKET_ACCURACY_REFERENCES.get(recommendation_type, 0.0)

    if recommendation_type == BTTS_TYPE:
        return "medium"
    if accuracy_reference >= 0.85:
        return "high"
    if accuracy_reference >= 0.75:
        return "medium"
    return "low"


# Déduit un niveau de risque simple à partir du marché et de sa performance de référence.
def build_risk_level(recommendation_type: str) -> str:
    accuracy_reference = MARKET_ACCURACY_REFERENCES.get(recommendation_type, 0.0)

    if recommendation_type == BTTS_TYPE:
        return "high"
    if accuracy_reference >= 0.85:
        return "low"
    if accuracy_reference >= 0.75:
        return "medium"
    return "high"


# Construit une réponse d'abstention lorsque V17.8 ne peut pas recommander proprement.
def build_abstention_response(
    reasons: list[str],
    missing_features: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source": "rubybets_ml_v17_8",
        "scope": "experimental",
        "status": ABSTAIN_STATUS,
        "model_status": V17_8_STATUS,
        "strategy": V17_8_STRATEGY_NAME,
        "recommendation_type": ABSTAIN_VALUE,
        "recommendation_value": ABSTAIN_VALUE,
        "confidence_level": "low",
        "risk_level": "high",
        "accuracy_reference": V17_8_GLOBAL_REFERENCES["accuracy"],
        "coverage_reference": V17_8_GLOBAL_REFERENCES["coverage"],
        "reasons": reasons,
        "missing_features": missing_features or [],
        "responsible_note": "Recommandation ML experimentale sans garantie de resultat sportif. Ne remplace pas le scoring explicable V1.",
    }


# Construit une réponse basée sur la recommandation prudente V17/V17.0 existante.
def build_base_recommendation_response(features: dict[str, Any]) -> dict[str, Any]:
    recommendation_type = str(features.get("v17_recommendation_type", ABSTAIN_VALUE))
    recommendation_value = str(features.get("v17_recommendation_value", ABSTAIN_VALUE))
    accuracy_reference = MARKET_ACCURACY_REFERENCES.get(
        recommendation_type,
        V17_8_GLOBAL_REFERENCES["accuracy"],
    )

    return {
        "source": "rubybets_ml_v17_8",
        "scope": "experimental",
        "status": RECOMMEND_STATUS,
        "model_status": V17_8_STATUS,
        "strategy": V17_8_STRATEGY_NAME,
        "recommendation_type": recommendation_type,
        "recommendation_value": recommendation_value,
        "recommendation_source": str(features.get("v17_source", "V17_REFERENCE_BASE")),
        "confidence_level": build_confidence_level(recommendation_type),
        "risk_level": build_risk_level(recommendation_type),
        "accuracy_reference": accuracy_reference,
        "coverage_reference": V17_8_GLOBAL_REFERENCES["coverage"],
        "is_btts": False,
        "is_added_btts": False,
        "is_replaced_over15": False,
        "responsible_note": "Recommandation ML experimentale sans garantie de resultat sportif. Ne remplace pas le scoring explicable V1.",
    }


# Construit une réponse BTTS_YES lorsque les gates V17.8 sont validés.
def build_btts_recommendation_response(features: dict[str, Any]) -> dict[str, Any]:
    base_selected = is_base_recommendation_selected(features)
    base_is_over_15 = is_base_recommendation_over_15(features)

    return {
        "source": "rubybets_ml_v17_8",
        "scope": "experimental",
        "status": RECOMMEND_STATUS,
        "model_status": V17_8_STATUS,
        "strategy": V17_8_STRATEGY_NAME,
        "recommendation_type": BTTS_TYPE,
        "recommendation_value": BTTS_YES_VALUE,
        "recommendation_source": V17_8_SOURCE,
        "confidence_level": build_confidence_level(BTTS_TYPE),
        "risk_level": build_risk_level(BTTS_TYPE),
        "accuracy_reference": MARKET_ACCURACY_REFERENCES[BTTS_TYPE],
        "coverage_reference": V17_8_GLOBAL_REFERENCES["coverage"],
        "btts_score": round(safe_float(features.get("v17_6_score")), 4),
        "is_btts": True,
        "is_added_btts": not base_selected,
        "is_replaced_over15": base_is_over_15,
        "responsible_note": "Signal BTTS_YES experimental. Il reste moins stable que 1X2 et double chance et ne garantit aucun resultat sportif.",
    }


# Produit une recommandation V17.8 à partir d'un dictionnaire de signaux déjà préparés.
def recommend_with_v17_8(features: dict[str, Any]) -> dict[str, Any]:
    strategy = get_v17_8_strategy_spec()
    btts_gate_result = evaluate_btts_gates(features, strategy)

    if btts_gate_result["is_eligible"] and can_use_btts_in_v17_8(features):
        return build_btts_recommendation_response(features)

    if is_base_recommendation_selected(features):
        base_response = build_base_recommendation_response(features)
        base_response["btts_gate_result"] = btts_gate_result
        return base_response

    return build_abstention_response(
        reasons=btts_gate_result["reasons"] or ["NO_SELECTED_SIGNAL"],
        missing_features=btts_gate_result["missing_features"],
    )


# Schéma de communication :
# ml_v17_8_service.py
#   -> reçoit un dictionnaire de signaux préparés par un futur adaptateur de features
#   -> applique les seuils V17.8 retenus dans reports/evidence/ml_training/280 et 281
#   -> conserve la base V17/V17.0 si elle existe
#   -> remplace uniquement OVER_1_5 ou une abstention par BTTS_YES si les gates sont validés
#   -> retourne une recommandation expérimentale ou une abstention
#   -> sera appelé plus tard par une route API expérimentale séparée du scoring explicable V1