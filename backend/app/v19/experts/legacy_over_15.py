# Rôle du fichier :
# Ce fichier encapsule la politique Over 1.5 historique V15 dans un candidat expert V19 standardisé.

from __future__ import annotations

from collections.abc import Mapping

from app.services.ml_v17_8_service import (
    GOALS_OVER_15_TYPE,
    build_confidence_level,
    build_risk_level,
)
from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)
from app.v19.experts.base import (
    build_expert_candidate,
    freeze_entries,
    get_missing_features,
    safe_float_or_none,
    safe_int_or_none,
)


LEGACY_OVER_15_EXPERT_ID = "legacy_v15_over_1_5"
LEGACY_OVER_15_EXPERT_VERSION = "v15_ou15_labels_ot080_ut050_mh10_ognone_ugnone"
LEGACY_OVER_15_RECOMMENDATION = "OVER_1_5"
LEGACY_OVER_15_RATE_THRESHOLD = 0.80
LEGACY_OVER_15_MIN_HISTORY_COUNT = 10
LEGACY_OVER_15_REQUIRED_FEATURES = (
    "combined_over_15_rate_last10",
    "min_history_count_last10",
)


# Construit le candidat Over 1.5 V15 à partir des deux features décisionnelles historiques.
def build_legacy_over_15_candidate(
    features: Mapping[str, object],
) -> ExpertCandidateV1:
    missing_features = list(
        get_missing_features(features, LEGACY_OVER_15_REQUIRED_FEATURES)
    )
    combined_over_rate = safe_float_or_none(
        features.get("combined_over_15_rate_last10")
    )
    min_history_count = safe_int_or_none(
        features.get("min_history_count_last10")
    )

    if combined_over_rate is None and "combined_over_15_rate_last10" not in missing_features:
        missing_features.append("combined_over_15_rate_last10")
    if min_history_count is None and "min_history_count_last10" not in missing_features:
        missing_features.append("min_history_count_last10")

    positive_reasons: list[str] = []
    caution_reasons: list[str] = []

    if missing_features:
        caution_reasons.append("MISSING_REQUIRED_FEATURES")
    else:
        if combined_over_rate is not None and combined_over_rate >= LEGACY_OVER_15_RATE_THRESHOLD:
            positive_reasons.append("OVER_15_RATE_AT_OR_ABOVE_V15_THRESHOLD")
        else:
            caution_reasons.append("OVER_15_RATE_BELOW_V15_THRESHOLD")

        if min_history_count is not None and min_history_count >= LEGACY_OVER_15_MIN_HISTORY_COUNT:
            positive_reasons.append("HISTORY_DEPTH_AT_OR_ABOVE_V15_MINIMUM")
        else:
            caution_reasons.append("HISTORY_DEPTH_BELOW_V15_MINIMUM")

    is_eligible = not missing_features and not caution_reasons

    return build_expert_candidate(
        expert_id=LEGACY_OVER_15_EXPERT_ID,
        expert_version=LEGACY_OVER_15_EXPERT_VERSION,
        market_type=ExpertMarketType.OVER_1_5,
        recommendation_value=(
            LEGACY_OVER_15_RECOMMENDATION if is_eligible else None
        ),
        status=(
            ExpertCandidateStatus.ELIGIBLE
            if is_eligible
            else ExpertCandidateStatus.INELIGIBLE
        ),
        raw_score=combined_over_rate,
        calibrated_probability=None,
        confidence_level=(
            build_confidence_level(GOALS_OVER_15_TYPE) if is_eligible else None
        ),
        local_risk_level=(
            build_risk_level(GOALS_OVER_15_TYPE) if is_eligible else None
        ),
        required_features=LEGACY_OVER_15_REQUIRED_FEATURES,
        missing_features=tuple(missing_features),
        positive_reasons=tuple(positive_reasons),
        caution_reasons=tuple(caution_reasons),
        quality_requirements=freeze_entries(
            {
                "profile": "LEGACY_V15_PARITY",
                "replay_mode": "LIVE_FORMULA_PARITY",
                "min_combined_over_15_rate": LEGACY_OVER_15_RATE_THRESHOLD,
                "min_history_count": LEGACY_OVER_15_MIN_HISTORY_COUNT,
            }
        ),
        metadata=freeze_entries(
            {
                "source_policy": "V15_OVER_1_5_ONLY",
                "observed_combined_over_15_rate": combined_over_rate,
                "observed_min_history_count": min_history_count,
                "calibration_status": "NOT_CALIBRATED",
            }
        ),
    )


# Schéma de communication :
# legacy_over_15.py
#   <- reçoit les aliases V15 préparés par legacy_adapters.py
#   <- réutilise les niveaux confiance/risque du service historique V17.8
#   -> produit un ExpertCandidateV1 OVER_1_5 pour le futur orchestrateur
#   -> ne prend jamais la décision finale et n'utilise pas le H2H
