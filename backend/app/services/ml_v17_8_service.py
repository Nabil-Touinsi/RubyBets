# Rôle du fichier :
# Ce module conserve uniquement les seuils et helpers V17.8 encore utilisés par les experts V19.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STRICT_TYPE = "STRICT_1X2"
DOUBLE_CHANCE_TYPE = "DOUBLE_CHANCE"
GOALS_OVER_15_TYPE = "GOALS_OVER_1_5"
BTTS_TYPE = "BTTS"

BTTS_YES_VALUE = "BTTS_YES"
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


# Schéma de communication :
# legacy_btts.py / legacy_over_15.py
#   -> importent les seuils, gates, niveaux de confiance et niveaux de risque
# ml_v17_8_service.py
#   -> expose uniquement les primitives historiques nécessaires à V19
# v19_prediction_service.py
#   -> orchestre la décision produit finale sans réactiver les routes V17/V18
