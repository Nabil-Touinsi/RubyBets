# Rôle du fichier :
# Ce fichier définit les contrats immuables de rejet et de décision finale RubyBets V19.

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from app.v19.domain.decision_enums import (
    CandidateRejectionReason,
    DecisionStatus,
)
from app.v19.domain.expert_contracts import (
    ExpertCandidateV1,
    ExpertFeatureNames,
    ExpertMetadataEntries,
)
from app.v19.domain.expert_enums import ExpertCandidateStatus


DecisionReasonCodes: TypeAlias = tuple[str, ...]
DecisionExpertVersions: TypeAlias = tuple[tuple[str, str], ...]
DecisionFeatureVersions: TypeAlias = tuple[str, ...]


# Associe un candidat non retenu à un motif d'arbitrage stable et auditable.
@dataclass(frozen=True)
class RejectedExpertCandidateV1:
    candidate: ExpertCandidateV1
    reason: CandidateRejectionReason


# Représente l'unique résultat produit après arbitrage de tous les experts V19.
@dataclass(frozen=True)
class DecisionResultV1:
    match_id: str
    status: DecisionStatus
    selected_candidate: ExpertCandidateV1 | None
    evaluated_candidates: tuple[ExpertCandidateV1, ...]
    rejected_candidates: tuple[RejectedExpertCandidateV1, ...]
    missing_features: ExpertFeatureNames
    abstention_reasons: DecisionReasonCodes
    engine_version: str
    expert_versions: DecisionExpertVersions
    feature_versions: DecisionFeatureVersions
    metadata: ExpertMetadataEntries

    # Vérifie l'immuabilité profonde et la cohérence minimale du résultat final.
    def __post_init__(self) -> None:
        tuple_fields = (
            "evaluated_candidates",
            "rejected_candidates",
            "missing_features",
            "abstention_reasons",
            "expert_versions",
            "feature_versions",
            "metadata",
        )
        for field_name in tuple_fields:
            if not isinstance(getattr(self, field_name), tuple):
                raise TypeError(f"{field_name} must be a tuple")

        if self.status is DecisionStatus.RECOMMEND:
            if self.selected_candidate is None:
                raise ValueError("RECOMMEND requires a selected_candidate")
            if self.selected_candidate.status is not ExpertCandidateStatus.ELIGIBLE:
                raise ValueError("selected_candidate must be ELIGIBLE")
        elif self.selected_candidate is not None:
            raise ValueError("ABSTAIN cannot contain a selected_candidate")


# Schéma de communication :
# decision_contracts.py
#   <- utilise decision_enums.py et le contrat ExpertCandidateV1
#   <- reçoit les résultats produits par decision_orchestrator.py
#   -> fournira un contrat stable aux futures routes, Archives et écrans produit
#   -> reste indépendant de FastAPI, PostgreSQL et des fournisseurs externes
