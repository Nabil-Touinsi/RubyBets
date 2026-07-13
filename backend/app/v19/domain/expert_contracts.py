# Rôle du fichier :
# Ce fichier définit le contrat immuable commun aux candidats experts RubyBets V19.

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


ExpertFeatureNames: TypeAlias = tuple[str, ...]

ExpertReasonCodes: TypeAlias = tuple[str, ...]

ExpertScalar: TypeAlias = str | int | float | bool | None

ExpertQualityRequirements: TypeAlias = tuple[
    tuple[str, ExpertScalar],
    ...,
]

ExpertMetadataEntries: TypeAlias = tuple[
    tuple[str, ExpertScalar],
    ...,
]


# Décrit la proposition locale d'un expert sans prendre la décision produit finale.
@dataclass(frozen=True)
class ExpertCandidateV1:
    expert_id: str
    expert_version: str
    market_type: ExpertMarketType
    recommendation_value: str | None
    status: ExpertCandidateStatus
    raw_score: float | None
    calibrated_probability: float | None
    confidence_level: str | None
    local_risk_level: str | None
    required_features: ExpertFeatureNames
    missing_features: ExpertFeatureNames
    positive_reasons: ExpertReasonCodes
    caution_reasons: ExpertReasonCodes
    quality_requirements: ExpertQualityRequirements
    metadata: ExpertMetadataEntries

    # Vérifie que les collections du contrat restent profondément immuables.
    def __post_init__(self) -> None:
        tuple_fields = (
            "required_features",
            "missing_features",
            "positive_reasons",
            "caution_reasons",
            "quality_requirements",
            "metadata",
        )

        for field_name in tuple_fields:
            if not isinstance(getattr(self, field_name), tuple):
                raise TypeError(f"{field_name} must be a tuple")


# Schéma de communication :
# expert_contracts.py
#   <- utilise le vocabulaire de expert_enums.py
#   <- recevra les propositions des futurs experts 1X2, DC, Over 1.5 et BTTS
#   -> fournira des candidats standardisés au futur orchestrateur V19
#   -> restera indépendant de FastAPI, des Archives et de l'interface utilisateur
#   -> ne sélectionne jamais lui-même la recommandation finale
