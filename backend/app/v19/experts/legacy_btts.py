# Rôle du fichier :
# Ce fichier encapsule les gates BTTS historiques V17.8 dans un candidat expert V19 standardisé.

from __future__ import annotations

from collections.abc import Mapping

from app.services.ml_v17_8_service import (
    BTTS_REQUIRED_FEATURES,
    BTTS_TYPE,
    BTTS_YES_VALUE,
    V17_8_SOURCE,
    build_confidence_level,
    build_risk_level,
    evaluate_btts_gates,
    get_v17_8_strategy_spec,
)
from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)
from app.v19.experts.base import (
    build_expert_candidate,
    freeze_entries,
    safe_float_or_none,
)


LEGACY_BTTS_EXPERT_ID = "legacy_v17_8_btts_yes"
LEGACY_BTTS_EXPERT_VERSION = "V17_8_USER_OBJECTIVE_BTTS_PRO_REVIEW"
LEGACY_BTTS_REQUIRED_FEATURES = tuple(BTTS_REQUIRED_FEATURES)


# Construit le candidat BTTS_YES en réutilisant exactement les gates du service V17.8.
def build_legacy_btts_candidate(
    features: Mapping[str, object],
) -> ExpertCandidateV1:
    strategy = get_v17_8_strategy_spec()
    feature_values = dict(features)
    gate_result = evaluate_btts_gates(feature_values, strategy)
    is_eligible = bool(gate_result["is_eligible"])
    raw_score = safe_float_or_none(feature_values.get("v17_6_score"))

    return build_expert_candidate(
        expert_id=LEGACY_BTTS_EXPERT_ID,
        expert_version=LEGACY_BTTS_EXPERT_VERSION,
        market_type=ExpertMarketType.BTTS,
        recommendation_value=BTTS_YES_VALUE if is_eligible else None,
        status=(
            ExpertCandidateStatus.ELIGIBLE
            if is_eligible
            else ExpertCandidateStatus.INELIGIBLE
        ),
        raw_score=raw_score,
        calibrated_probability=None,
        confidence_level=(build_confidence_level(BTTS_TYPE) if is_eligible else None),
        local_risk_level=(build_risk_level(BTTS_TYPE) if is_eligible else None),
        required_features=LEGACY_BTTS_REQUIRED_FEATURES,
        missing_features=tuple(gate_result["missing_features"]),
        positive_reasons=("BTTS_V17_8_GATES_PASSED",) if is_eligible else (),
        caution_reasons=tuple(gate_result["reasons"]),
        quality_requirements=freeze_entries(
            {
                "selection_mode": strategy.mode,
                "min_btts_score": strategy.min_btts_score,
                "min_history_count": strategy.min_history_count,
                "min_expected_team_goals": strategy.min_expected_team_goals,
                "min_expected_total_goals": strategy.min_expected_total_goals,
                "min_combined_btts_rate": strategy.min_combined_btts_rate,
                "min_combined_over_15_rate": strategy.min_combined_over_15_rate,
                "max_failed_to_score_rate": strategy.max_failed_to_score_rate,
            }
        ),
        metadata=freeze_entries(
            {
                "source_policy": V17_8_SOURCE,
                "strategy_name": strategy.name,
                "observed_min_history_count": feature_values.get(
                    "min_history_count_last_10"
                ),
                "observed_expected_home_goals": feature_values.get(
                    "expected_home_goals_proxy"
                ),
                "observed_expected_away_goals": feature_values.get(
                    "expected_away_goals_proxy"
                ),
                "observed_expected_total_goals": feature_values.get(
                    "expected_total_goals_proxy"
                ),
                "observed_combined_btts_rate": feature_values.get(
                    "combined_btts_rate_last_10"
                ),
                "observed_combined_over_15_rate": feature_values.get(
                    "combined_over_1_5_rate_last_10"
                ),
                "calibration_status": "NOT_CALIBRATED",
            }
        ),
    )


# Schéma de communication :
# legacy_btts.py
#   <- reçoit les features clubs préparées par legacy_adapters.py
#   <- réutilise evaluate_btts_gates() et la stratégie officielle de ml_v17_8_service.py
#   -> produit un ExpertCandidateV1 BTTS pour le futur orchestrateur V19
#   -> expose le mode replace_over15_or_fallback sans arbitrer lui-même les marchés
