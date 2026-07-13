# Rôle du fichier :
# Ce fichier encapsule la politique 1X2 stricte V13.1 dans un candidat expert V19 standardisé.

from __future__ import annotations

from collections.abc import Mapping

from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import ExpertCandidateStatus, ExpertMarketType
from app.v19.experts.base import (
    build_expert_candidate,
    freeze_entries,
    get_missing_features,
    safe_float_or_none,
)


LEGACY_STRICT_1X2_EXPERT_ID = "legacy_v13_1_strict_1x2"
LEGACY_STRICT_1X2_EXPERT_VERSION = "v13_1_sp080_sm010_no_draw"
LEGACY_STRICT_1X2_PROBABILITY_THRESHOLD = 0.80
LEGACY_STRICT_1X2_MARGIN_THRESHOLD = 0.10
LEGACY_STRICT_1X2_REQUIRED_FEATURES = (
    "market_favorite_prob",
    "market_margin_top1_top2",
    "v13_strict_prediction",
)
LEGACY_STRICT_1X2_ALLOWED_VALUES = {"HOME_WIN", "AWAY_WIN"}


# Construit le candidat 1X2 strict en reproduisant exactement les gates V13.1 retenues.
def build_legacy_strict_1x2_candidate(
    features: Mapping[str, object],
) -> ExpertCandidateV1:
    missing_features = list(
        get_missing_features(features, LEGACY_STRICT_1X2_REQUIRED_FEATURES)
    )
    favorite_probability = safe_float_or_none(features.get("market_favorite_prob"))
    margin = safe_float_or_none(features.get("market_margin_top1_top2"))
    prediction = str(features.get("v13_strict_prediction") or "").strip()

    if favorite_probability is None and "market_favorite_prob" not in missing_features:
        missing_features.append("market_favorite_prob")
    if margin is None and "market_margin_top1_top2" not in missing_features:
        missing_features.append("market_margin_top1_top2")
    if not prediction and "v13_strict_prediction" not in missing_features:
        missing_features.append("v13_strict_prediction")

    positive_reasons: list[str] = []
    caution_reasons: list[str] = []

    if missing_features:
        caution_reasons.append("MISSING_REQUIRED_FEATURES")
    else:
        if favorite_probability is not None and favorite_probability >= LEGACY_STRICT_1X2_PROBABILITY_THRESHOLD:
            positive_reasons.append("FAVORITE_PROBABILITY_AT_OR_ABOVE_V13_1_THRESHOLD")
        else:
            caution_reasons.append("FAVORITE_PROBABILITY_BELOW_V13_1_THRESHOLD")

        if margin is not None and margin >= LEGACY_STRICT_1X2_MARGIN_THRESHOLD:
            positive_reasons.append("TOP1_TOP2_MARGIN_AT_OR_ABOVE_V13_1_THRESHOLD")
        else:
            caution_reasons.append("TOP1_TOP2_MARGIN_BELOW_V13_1_THRESHOLD")

        if prediction in LEGACY_STRICT_1X2_ALLOWED_VALUES:
            positive_reasons.append("STRICT_PREDICTION_IS_NOT_DRAW")
        elif prediction == "DRAW":
            caution_reasons.append("DRAW_NOT_ALLOWED_BY_V13_1_STRICT_POLICY")
        else:
            caution_reasons.append("INVALID_STRICT_1X2_VALUE")

    is_eligible = not missing_features and not caution_reasons

    return build_expert_candidate(
        expert_id=LEGACY_STRICT_1X2_EXPERT_ID,
        expert_version=LEGACY_STRICT_1X2_EXPERT_VERSION,
        market_type=ExpertMarketType.STRICT_1X2,
        recommendation_value=prediction if is_eligible else None,
        status=ExpertCandidateStatus.ELIGIBLE if is_eligible else ExpertCandidateStatus.INELIGIBLE,
        raw_score=favorite_probability,
        calibrated_probability=None,
        confidence_level=None,
        local_risk_level=None,
        required_features=LEGACY_STRICT_1X2_REQUIRED_FEATURES,
        missing_features=tuple(missing_features),
        positive_reasons=tuple(positive_reasons),
        caution_reasons=tuple(caution_reasons),
        quality_requirements=freeze_entries(
            {
                "profile": "LEGACY_V13_1_PARITY",
                "min_favorite_probability": LEGACY_STRICT_1X2_PROBABILITY_THRESHOLD,
                "min_top1_top2_margin": LEGACY_STRICT_1X2_MARGIN_THRESHOLD,
                "draw_allowed": False,
            }
        ),
        metadata=freeze_entries(
            {
                "observed_favorite_probability": favorite_probability,
                "observed_top1_top2_margin": margin,
                "observed_prediction": prediction or None,
                "calibration_status": "NOT_CALIBRATED",
            }
        ),
    )


# Schéma de communication :
# market_feature_builder.py
#   -> fournit market_favorite_prob, market_margin_top1_top2 et v13_strict_prediction
# legacy_strict_1x2.py
#   -> produit un ExpertCandidateV1 STRICT_1X2 selon la parité V13.1
# futur orchestrateur V19
#   -> reçoit le candidat mais reste seul responsable de la décision produit finale
