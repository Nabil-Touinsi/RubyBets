# Rôle du fichier :
# Ce fichier arbitre les candidats experts V19 selon la parité historique V13/V15/V17/V17.8.

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.v19.domain.decision_contracts import (
    DecisionResultV1,
    RejectedExpertCandidateV1,
)
from app.v19.domain.decision_enums import (
    CandidateRejectionReason,
    DecisionAbstentionReason,
    DecisionStatus,
)
from app.v19.domain.expert_contracts import (
    ExpertCandidateV1,
    ExpertMetadataEntries,
)
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


LEGACY_DECISION_ENGINE_VERSION = "v19.orchestrator.legacy_parity.1"
LEGACY_MARKET_PRIORITY = (
    ExpertMarketType.STRICT_1X2,
    ExpertMarketType.DOUBLE_CHANCE,
    ExpertMarketType.OVER_1_5,
    ExpertMarketType.BTTS,
)


# Retourne les valeurs uniques dans leur ordre d'apparition pour stabiliser la traçabilité.
def unique_in_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


# Indexe le premier candidat de chaque marché afin d'appliquer une politique déterministe.
def index_candidates_by_market(
    candidates: tuple[ExpertCandidateV1, ...],
) -> dict[ExpertMarketType, ExpertCandidateV1]:
    indexed: dict[ExpertMarketType, ExpertCandidateV1] = {}
    for candidate in candidates:
        indexed.setdefault(candidate.market_type, candidate)
    return indexed


# Indique si un candidat peut participer à la décision finale.
def is_eligible(candidate: ExpertCandidateV1 | None) -> bool:
    return candidate is not None and candidate.status is ExpertCandidateStatus.ELIGIBLE


# Sélectionne le candidat final selon la chaîne historique stricte, DC, Over 1.5 puis BTTS.
def select_legacy_candidate(
    candidates_by_market: Mapping[ExpertMarketType, ExpertCandidateV1],
) -> ExpertCandidateV1 | None:
    strict_candidate = candidates_by_market.get(ExpertMarketType.STRICT_1X2)
    if is_eligible(strict_candidate):
        return strict_candidate

    double_chance_candidate = candidates_by_market.get(
        ExpertMarketType.DOUBLE_CHANCE
    )
    if is_eligible(double_chance_candidate):
        return double_chance_candidate

    over_15_candidate = candidates_by_market.get(ExpertMarketType.OVER_1_5)
    btts_candidate = candidates_by_market.get(ExpertMarketType.BTTS)

    if is_eligible(btts_candidate):
        return btts_candidate
    if is_eligible(over_15_candidate):
        return over_15_candidate
    return None


# Détermine le motif expliquant le rejet de chaque candidat non sélectionné.
def build_rejection_reason(
    candidate: ExpertCandidateV1,
    selected_candidate: ExpertCandidateV1 | None,
) -> CandidateRejectionReason:
    if candidate.status is ExpertCandidateStatus.ERROR:
        return CandidateRejectionReason.CANDIDATE_ERROR
    if candidate.status is ExpertCandidateStatus.INELIGIBLE:
        return CandidateRejectionReason.CANDIDATE_INELIGIBLE
    if (
        selected_candidate is not None
        and selected_candidate.market_type is ExpertMarketType.BTTS
        and candidate.market_type is ExpertMarketType.OVER_1_5
    ):
        return CandidateRejectionReason.REPLACED_BY_BTTS_POLICY
    return CandidateRejectionReason.HIGHER_PRIORITY_CANDIDATE_SELECTED


# Construit la liste exhaustive et immuable des candidats non retenus.
def build_rejected_candidates(
    candidates: tuple[ExpertCandidateV1, ...],
    selected_candidate: ExpertCandidateV1 | None,
) -> tuple[RejectedExpertCandidateV1, ...]:
    return tuple(
        RejectedExpertCandidateV1(
            candidate=candidate,
            reason=build_rejection_reason(candidate, selected_candidate),
        )
        for candidate in candidates
        if candidate is not selected_candidate
    )


# Agrège toutes les features manquantes déclarées par les experts évalués.
def collect_missing_features(
    candidates: tuple[ExpertCandidateV1, ...],
) -> tuple[str, ...]:
    return unique_in_order(
        feature_name
        for candidate in candidates
        for feature_name in candidate.missing_features
    )


# Agrège les versions des experts évalués sans dupliquer un même expert.
def collect_expert_versions(
    candidates: tuple[ExpertCandidateV1, ...],
) -> tuple[tuple[str, str], ...]:
    seen: set[str] = set()
    versions: list[tuple[str, str]] = []
    for candidate in candidates:
        if candidate.expert_id not in seen:
            seen.add(candidate.expert_id)
            versions.append((candidate.expert_id, candidate.expert_version))
    return tuple(versions)


# Construit les motifs d'abstention à partir des diagnostics locaux des experts.
def build_abstention_reasons(
    candidates: tuple[ExpertCandidateV1, ...],
) -> tuple[str, ...]:
    local_reasons = (
        reason
        for candidate in candidates
        for reason in candidate.caution_reasons
    )
    return unique_in_order(
        (
            DecisionAbstentionReason.NO_ELIGIBLE_CANDIDATE.value,
            *local_reasons,
        )
    )


# Produit la décision finale V19 en conservant tous les candidats et diagnostics évalués.
def orchestrate_legacy_decision(
    *,
    match_id: str | int,
    candidates: Iterable[ExpertCandidateV1],
    feature_versions: Iterable[str] = (),
    metadata: ExpertMetadataEntries = (),
) -> DecisionResultV1:
    evaluated_candidates = tuple(candidates)
    candidates_by_market = index_candidates_by_market(evaluated_candidates)
    selected_candidate = select_legacy_candidate(candidates_by_market)
    status = (
        DecisionStatus.RECOMMEND
        if selected_candidate is not None
        else DecisionStatus.ABSTAIN
    )

    return DecisionResultV1(
        match_id=str(match_id),
        status=status,
        selected_candidate=selected_candidate,
        evaluated_candidates=evaluated_candidates,
        rejected_candidates=build_rejected_candidates(
            evaluated_candidates,
            selected_candidate,
        ),
        missing_features=collect_missing_features(evaluated_candidates),
        abstention_reasons=(
            ()
            if selected_candidate is not None
            else build_abstention_reasons(evaluated_candidates)
        ),
        engine_version=LEGACY_DECISION_ENGINE_VERSION,
        expert_versions=collect_expert_versions(evaluated_candidates),
        feature_versions=tuple(feature_versions),
        metadata=tuple(metadata),
    )


# Schéma de communication :
# experts legacy_strict_1x2 / legacy_double_chance / legacy_over_15 / legacy_btts
#   -> produisent les ExpertCandidateV1 évalués ici
# decision_orchestrator.py
#   -> applique la parité V13.1 -> V15 -> V17 -> V17.8
#   -> produit DecisionResultV1 avec sélection, rejets, manque et versions
# futures routes / Archives / frontend
#   <- consommeront le résultat sans recalculer la décision métier
