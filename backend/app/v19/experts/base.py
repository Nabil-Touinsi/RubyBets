# Rôle du fichier :
# Ce fichier fournit les helpers communs pour construire des candidats experts V19 immuables et traçables.

from __future__ import annotations

from collections.abc import Mapping

from app.v19.domain.expert_contracts import (
    ExpertCandidateV1,
    ExpertFeatureNames,
    ExpertMetadataEntries,
    ExpertQualityRequirements,
    ExpertReasonCodes,
    ExpertScalar,
)
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


# Transforme un mapping de scalaires en tuple immuable compatible avec les contrats V19.
def freeze_entries(values: Mapping[str, ExpertScalar]) -> tuple[tuple[str, ExpertScalar], ...]:
    return tuple(values.items())


# Liste les features absentes ou explicitement nulles dans un dictionnaire de signaux.
def get_missing_features(
    features: Mapping[str, object],
    required_features: ExpertFeatureNames,
) -> ExpertFeatureNames:
    return tuple(
        feature_name
        for feature_name in required_features
        if feature_name not in features or features[feature_name] is None
    )


# Convertit une valeur en float tout en conservant None lorsque la valeur est inexploitable.
def safe_float_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# Convertit une valeur en int tout en conservant None lorsque la valeur est inexploitable.
def safe_int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


# Construit un ExpertCandidateV1 sans laisser de collections mutables dans le contrat.
def build_expert_candidate(
    *,
    expert_id: str,
    expert_version: str,
    market_type: ExpertMarketType,
    recommendation_value: str | None,
    status: ExpertCandidateStatus,
    raw_score: float | None,
    calibrated_probability: float | None,
    confidence_level: str | None,
    local_risk_level: str | None,
    required_features: ExpertFeatureNames,
    missing_features: ExpertFeatureNames = (),
    positive_reasons: ExpertReasonCodes = (),
    caution_reasons: ExpertReasonCodes = (),
    quality_requirements: ExpertQualityRequirements = (),
    metadata: ExpertMetadataEntries = (),
) -> ExpertCandidateV1:
    return ExpertCandidateV1(
        expert_id=expert_id,
        expert_version=expert_version,
        market_type=market_type,
        recommendation_value=recommendation_value,
        status=status,
        raw_score=raw_score,
        calibrated_probability=calibrated_probability,
        confidence_level=confidence_level,
        local_risk_level=local_risk_level,
        required_features=tuple(required_features),
        missing_features=tuple(missing_features),
        positive_reasons=tuple(positive_reasons),
        caution_reasons=tuple(caution_reasons),
        quality_requirements=tuple(quality_requirements),
        metadata=tuple(metadata),
    )


# Schéma de communication :
# base.py
#   <- utilise expert_contracts.py et expert_enums.py
#   -> fournit des helpers aux experts legacy_over_15.py et legacy_btts.py
#   -> garantit des collections immuables pour le futur orchestrateur V19
#   -> ne contient aucune règle sportive ni aucun seuil métier
