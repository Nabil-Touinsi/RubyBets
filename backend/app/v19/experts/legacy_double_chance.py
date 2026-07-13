# Rôle du fichier :
# Ce fichier encapsule la politique Double Chance V13.1 dans un candidat expert V19 standardisé.

from __future__ import annotations

from collections.abc import Mapping

from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import ExpertCandidateStatus, ExpertMarketType
from app.v19.experts.base import (
    build_expert_candidate,
    freeze_entries,
    get_missing_features,
    safe_float_or_none,
    safe_int_or_none,
)
from app.v19.experts.legacy_strict_1x2 import (
    LEGACY_STRICT_1X2_MARGIN_THRESHOLD,
    LEGACY_STRICT_1X2_PROBABILITY_THRESHOLD,
)


LEGACY_DOUBLE_CHANCE_EXPERT_ID = "legacy_v13_1_double_chance"
LEGACY_DOUBLE_CHANCE_EXPERT_VERSION = "v13_1_top2076_ent107_trip1_agr000_after_strict"
LEGACY_DOUBLE_CHANCE_TOP2_THRESHOLD = 0.76
LEGACY_DOUBLE_CHANCE_MAX_ENTROPY = 1.07
LEGACY_DOUBLE_CHANCE_MIN_TRIPLETS = 1
LEGACY_DOUBLE_CHANCE_MIN_AGREEMENT = 0.00
LEGACY_DOUBLE_CHANCE_ALLOWED_VALUES = {"1X", "X2", "12"}
LEGACY_DOUBLE_CHANCE_REQUIRED_FEATURES = (
    "market_top2_sum",
    "market_entropy",
    "market_available_triplets",
    "market_bookmaker_agreement_score",
    "v13_double_chance",
    "market_favorite_prob",
    "market_margin_top1_top2",
    "v13_strict_prediction",
)


# Vérifie si la politique stricte V13.1 possède la priorité historique sur Double Chance.
def is_legacy_strict_priority(features: Mapping[str, object]) -> bool:
    favorite_probability = safe_float_or_none(features.get("market_favorite_prob"))
    margin = safe_float_or_none(features.get("market_margin_top1_top2"))
    strict_prediction = str(features.get("v13_strict_prediction") or "").strip()

    return (
        favorite_probability is not None
        and favorite_probability >= LEGACY_STRICT_1X2_PROBABILITY_THRESHOLD
        and margin is not None
        and margin >= LEGACY_STRICT_1X2_MARGIN_THRESHOLD
        and strict_prediction != "DRAW"
    )


# Construit le candidat Double Chance après exclusion des cas retenus en 1X2 strict historique.
def build_legacy_double_chance_candidate(
    features: Mapping[str, object],
) -> ExpertCandidateV1:
    missing_features = list(
        get_missing_features(features, LEGACY_DOUBLE_CHANCE_REQUIRED_FEATURES)
    )
    top2_sum = safe_float_or_none(features.get("market_top2_sum"))
    entropy = safe_float_or_none(features.get("market_entropy"))
    triplet_count = safe_int_or_none(features.get("market_available_triplets"))
    agreement = safe_float_or_none(features.get("market_bookmaker_agreement_score"))
    recommendation = str(features.get("v13_double_chance") or "").strip()

    numeric_values = (
        ("market_top2_sum", top2_sum),
        ("market_entropy", entropy),
        ("market_available_triplets", triplet_count),
        ("market_bookmaker_agreement_score", agreement),
    )
    for feature_name, value in numeric_values:
        if value is None and feature_name not in missing_features:
            missing_features.append(feature_name)
    if not recommendation and "v13_double_chance" not in missing_features:
        missing_features.append("v13_double_chance")

    positive_reasons: list[str] = []
    caution_reasons: list[str] = []

    if missing_features:
        caution_reasons.append("MISSING_REQUIRED_FEATURES")
    else:
        if is_legacy_strict_priority(features):
            caution_reasons.append("STRICT_1X2_HAS_HISTORICAL_PRIORITY")

        if top2_sum is not None and top2_sum >= LEGACY_DOUBLE_CHANCE_TOP2_THRESHOLD:
            positive_reasons.append("TOP2_SUM_AT_OR_ABOVE_V13_1_THRESHOLD")
        else:
            caution_reasons.append("TOP2_SUM_BELOW_V13_1_THRESHOLD")

        if entropy is not None and entropy <= LEGACY_DOUBLE_CHANCE_MAX_ENTROPY:
            positive_reasons.append("ENTROPY_AT_OR_BELOW_V13_1_MAXIMUM")
        else:
            caution_reasons.append("ENTROPY_ABOVE_V13_1_MAXIMUM")

        if triplet_count is not None and triplet_count >= LEGACY_DOUBLE_CHANCE_MIN_TRIPLETS:
            positive_reasons.append("TRIPLET_COUNT_AT_OR_ABOVE_V13_1_MINIMUM")
        else:
            caution_reasons.append("TRIPLET_COUNT_BELOW_V13_1_MINIMUM")

        if agreement is not None and agreement >= LEGACY_DOUBLE_CHANCE_MIN_AGREEMENT:
            positive_reasons.append("BOOKMAKER_AGREEMENT_AT_OR_ABOVE_V13_1_MINIMUM")
        else:
            caution_reasons.append("BOOKMAKER_AGREEMENT_BELOW_V13_1_MINIMUM")

        if recommendation not in LEGACY_DOUBLE_CHANCE_ALLOWED_VALUES:
            caution_reasons.append("INVALID_DOUBLE_CHANCE_VALUE")

    is_eligible = not missing_features and not caution_reasons

    return build_expert_candidate(
        expert_id=LEGACY_DOUBLE_CHANCE_EXPERT_ID,
        expert_version=LEGACY_DOUBLE_CHANCE_EXPERT_VERSION,
        market_type=ExpertMarketType.DOUBLE_CHANCE,
        recommendation_value=recommendation if is_eligible else None,
        status=ExpertCandidateStatus.ELIGIBLE if is_eligible else ExpertCandidateStatus.INELIGIBLE,
        raw_score=top2_sum,
        calibrated_probability=None,
        confidence_level=None,
        local_risk_level=None,
        required_features=LEGACY_DOUBLE_CHANCE_REQUIRED_FEATURES,
        missing_features=tuple(missing_features),
        positive_reasons=tuple(positive_reasons),
        caution_reasons=tuple(caution_reasons),
        quality_requirements=freeze_entries(
            {
                "profile": "LEGACY_V13_1_PARITY",
                "min_top2_sum": LEGACY_DOUBLE_CHANCE_TOP2_THRESHOLD,
                "max_entropy": LEGACY_DOUBLE_CHANCE_MAX_ENTROPY,
                "min_available_triplets": LEGACY_DOUBLE_CHANCE_MIN_TRIPLETS,
                "min_bookmaker_agreement": LEGACY_DOUBLE_CHANCE_MIN_AGREEMENT,
                "strict_priority_applied": True,
            }
        ),
        metadata=freeze_entries(
            {
                "observed_top2_sum": top2_sum,
                "observed_entropy": entropy,
                "observed_available_triplets": triplet_count,
                "observed_bookmaker_agreement": agreement,
                "observed_recommendation": recommendation or None,
                "calibration_status": "NOT_CALIBRATED",
            }
        ),
    )


# Schéma de communication :
# market_feature_builder.py
#   -> fournit les features V13.1 et la valeur v13_double_chance
# legacy_strict_1x2.py
#   -> fournit les seuils de priorité historique stricte
# legacy_double_chance.py
#   -> produit un ExpertCandidateV1 DOUBLE_CHANCE seulement après le strict
# futur orchestrateur V19
#   -> reste seul responsable de la décision produit finale
