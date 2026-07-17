# Rôle du fichier :
# Ce service compose une sélection multi-matchs à partir des décisions officielles RubyBets V19.

from __future__ import annotations

import asyncio

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from math import ceil

from app.v19.application.v19_prediction_service import (
    build_v19_prediction_for_match,
)
from app.v19.domain.decision_contracts import DecisionResultV1
from app.v19.domain.decision_enums import DecisionStatus
from app.v19.domain.expert_enums import ExpertMarketType


V19_SELECTION_SERVICE_VERSION = "v19.selection.service.2"
V19_SELECTION_MAX_CONCURRENCY = 4

V19SelectionPredictor = Callable[..., Awaitable[DecisionResultV1]]


# Profils de sélectivité proposés par le générateur multi-matchs.
class V19SelectionProfile(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# États possibles d'une sélection V19 après analyse des matchs disponibles.
class V19SelectionStatus(str, Enum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"


# Motifs internes expliquant pourquoi un match n'a pas intégré la sélection.
class V19SelectionExclusionReason(str, Enum):
    ABSTAIN = "ABSTAIN"
    PROFILE_FILTERED = "PROFILE_FILTERED"
    PIPELINE_ERROR = "PIPELINE_ERROR"


# Associe une décision V19 retenue à son identifiant de match.
@dataclass(frozen=True)
class V19SelectedMatchV1:
    match_id: int
    result: DecisionResultV1


# Décrit un match évalué mais non intégré à la sélection finale.
@dataclass(frozen=True)
class V19ExcludedMatchV1:
    match_id: int
    reason: V19SelectionExclusionReason
    details: tuple[str, ...]


# Représente le résultat stable du service de sélection V19.
@dataclass(frozen=True)
class V19SelectionResultV1:
    status: V19SelectionStatus
    profile: V19SelectionProfile
    requested_count: int
    candidate_count: int
    evaluated_count: int
    abstain_count: int
    profile_filtered_count: int
    error_count: int
    selections: tuple[V19SelectedMatchV1, ...]
    excluded_matches: tuple[V19ExcludedMatchV1, ...]
    service_version: str


# Décrit les signaux internes utilisés pour classer un match sans score brut.
@dataclass(frozen=True)
class V19ProfiledCandidateV1:
    match_id: int
    result: DecisionResultV1
    input_position: int
    data_grade: str
    confidence_tier: str
    local_risk_tier: str
    caution_level: str


# Conserve le résultat d'un pipeline concurrent dans l'ordre du pool initial.
@dataclass(frozen=True)
class V19PredictionEvaluationV1:
    match_id: int
    input_position: int
    result: DecisionResultV1 | None
    error_details: tuple[str, ...]


# Convertit un profil reçu en valeur contrôlée et insensible à la casse.
def normalize_selection_profile(
    value: V19SelectionProfile | str,
) -> V19SelectionProfile:
    if isinstance(value, V19SelectionProfile):
        return value

    normalized_value = str(value).strip().upper()

    try:
        return V19SelectionProfile(normalized_value)
    except ValueError as exc:
        raise ValueError("selection_profile must be LOW, MEDIUM or HIGH") from exc


# Supprime les identifiants dupliqués tout en conservant leur ordre initial.
def deduplicate_match_ids(match_ids: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    unique_ids: list[int] = []
    seen_ids: set[int] = set()

    for raw_match_id in match_ids:
        match_id = int(raw_match_id)

        if match_id in seen_ids:
            continue

        seen_ids.add(match_id)
        unique_ids.append(match_id)

    return tuple(unique_ids)


# Transforme les métadonnées immuables de la décision en dictionnaire de lecture.
def decision_metadata(result: DecisionResultV1) -> dict[str, object]:
    return dict(result.metadata)


# Convertit la liste compacte des alertes Market en ensemble de codes stables.
def market_quality_flags(result: DecisionResultV1) -> set[str]:
    value = decision_metadata(result).get("market_quality_flags")

    if value in (None, ""):
        return set()

    return {
        item.strip()
        for item in str(value).split(",")
        if item.strip()
    }


# Normalise un niveau de confiance ou de risque en vocabulaire contrôlé.
def normalize_tier(value: str | None) -> str:
    normalized_value = str(value or "").strip().upper()

    if normalized_value in {"LOW", "MEDIUM", "HIGH"}:
        return normalized_value

    return "UNKNOWN"


# Classe les avertissements locaux sans interpréter leur contenu métier.
def build_caution_level(result: DecisionResultV1) -> str:
    candidate = result.selected_candidate

    if candidate is None or not candidate.caution_reasons:
        return "NONE"

    if len(candidate.caution_reasons) == 1:
        return "LIMITED"

    return "SIGNIFICANT"


# Évalue la qualité des données avec des catégories déterministes et sans probabilité.
def build_data_grade(result: DecisionResultV1) -> str:
    candidate = result.selected_candidate

    if candidate is None:
        return "C"

    metadata = decision_metadata(result)
    target_status = metadata.get("target_match_provider_status")
    market_status = metadata.get("market_module_status")
    history_status = metadata.get("history_data_status")
    quality_flags = market_quality_flags(result)

    explicitly_bad_target = target_status not in {
        None,
        "",
        "success",
        "available",
    }
    market_and_history_unavailable = (
        market_status == "UNAVAILABLE"
        and history_status != "available"
    )
    blocked_coverage = bool(
        quality_flags.intersection(
            {
                "LOW_BOOKMAKER_COVERAGE",
                "SINGLE_BOOKMAKER_ONLY",
            }
        )
    )

    if (
        candidate.missing_features
        or explicitly_bad_target
        or market_and_history_unavailable
        or blocked_coverage
    ):
        return "C"

    if (
        market_status == "READY"
        and history_status == "available"
        and not quality_flags
    ):
        return "A"

    return "B"


# Vérifie que le profil faible dispose des sources et garanties de qualité attendues.
def low_profile_rejection_reasons(
    result: DecisionResultV1,
) -> tuple[str, ...]:
    candidate = result.selected_candidate

    if candidate is None:
        return ("MISSING_SELECTED_CANDIDATE",)

    metadata = decision_metadata(result)
    reasons: list[str] = []

    if metadata.get("target_match_provider_status") != "success":
        reasons.append("TARGET_MATCH_SOURCE_NOT_READY")

    if metadata.get("market_module_status") != "READY":
        reasons.append("MARKET_MODULE_NOT_READY")

    if metadata.get("history_data_status") != "available":
        reasons.append("TEAM_HISTORY_NOT_AVAILABLE")

    if candidate.missing_features:
        reasons.append("SELECTED_CANDIDATE_HAS_MISSING_FEATURES")

    blocked_flags = {
        "LOW_BOOKMAKER_COVERAGE",
        "SINGLE_BOOKMAKER_ONLY",
    }
    if market_quality_flags(result).intersection(blocked_flags):
        reasons.append("MARKET_COVERAGE_TOO_LIMITED")

    if normalize_tier(candidate.local_risk_level) == "HIGH":
        reasons.append("SELECTED_CANDIDATE_RISK_TOO_HIGH_FOR_LOW_PROFILE")

    if normalize_tier(candidate.confidence_level) == "LOW":
        reasons.append("SELECTED_CANDIDATE_CONFIDENCE_TOO_LOW")

    return tuple(reasons)


# Vérifie que les données indispensables au marché retenu sont disponibles en profil moyen.
def medium_profile_rejection_reasons(
    result: DecisionResultV1,
) -> tuple[str, ...]:
    candidate = result.selected_candidate

    if candidate is None:
        return ("MISSING_SELECTED_CANDIDATE",)

    metadata = decision_metadata(result)
    reasons: list[str] = []

    if candidate.missing_features:
        reasons.append("SELECTED_CANDIDATE_HAS_MISSING_FEATURES")

    if build_data_grade(result) == "C":
        reasons.append("DATA_QUALITY_BELOW_MINIMUM")

    if candidate.market_type in {
        ExpertMarketType.STRICT_1X2,
        ExpertMarketType.DOUBLE_CHANCE,
    }:
        if metadata.get("market_module_status") not in {
            "READY",
            "DEGRADED",
        }:
            reasons.append("MARKET_DATA_NOT_AVAILABLE_FOR_SELECTED_MARKET")

    if candidate.market_type in {
        ExpertMarketType.OVER_1_5,
        ExpertMarketType.BTTS,
    }:
        if metadata.get("history_data_status") != "available":
            reasons.append("TEAM_HISTORY_NOT_AVAILABLE_FOR_SELECTED_MARKET")

    if normalize_tier(candidate.confidence_level) == "LOW":
        reasons.append("SELECTED_CANDIDATE_CONFIDENCE_TOO_LOW")

    return tuple(reasons)


# Vérifie le socle minimal de qualité conservé par le profil ouvert.
def high_profile_rejection_reasons(
    result: DecisionResultV1,
) -> tuple[str, ...]:
    candidate = result.selected_candidate

    if candidate is None:
        return ("MISSING_SELECTED_CANDIDATE",)

    reasons: list[str] = []

    if build_data_grade(result) == "C":
        reasons.append("DATA_QUALITY_BELOW_MINIMUM")

    if normalize_tier(candidate.confidence_level) == "LOW":
        reasons.append("SELECTED_CANDIDATE_CONFIDENCE_TOO_LOW")

    return tuple(reasons)


# Retourne les motifs empêchant une décision RECOMMEND d'intégrer le profil choisi.
def profile_rejection_reasons(
    result: DecisionResultV1,
    profile: V19SelectionProfile,
) -> tuple[str, ...]:
    if result.status is not DecisionStatus.RECOMMEND:
        return ("DECISION_IS_NOT_RECOMMEND",)

    if profile is V19SelectionProfile.LOW:
        return low_profile_rejection_reasons(result)

    if profile is V19SelectionProfile.MEDIUM:
        return medium_profile_rejection_reasons(result)

    return high_profile_rejection_reasons(result)


# Construit les signaux qualitatifs internes nécessaires au classement par profil.
def build_profiled_candidate(
    *,
    match_id: int,
    result: DecisionResultV1,
    input_position: int,
) -> V19ProfiledCandidateV1:
    candidate = result.selected_candidate

    if candidate is None:
        raise ValueError("profiled_candidate_requires_selected_candidate")

    return V19ProfiledCandidateV1(
        match_id=match_id,
        result=result,
        input_position=input_position,
        data_grade=build_data_grade(result),
        confidence_tier=normalize_tier(candidate.confidence_level),
        local_risk_tier=normalize_tier(candidate.local_risk_level),
        caution_level=build_caution_level(result),
    )


# Retourne la priorité du marché selon le profil de sélectivité demandé.
def market_preference_rank(
    market_type: ExpertMarketType,
    profile: V19SelectionProfile,
) -> int:
    preferences = {
        V19SelectionProfile.LOW: (
            ExpertMarketType.DOUBLE_CHANCE,
            ExpertMarketType.OVER_1_5,
            ExpertMarketType.STRICT_1X2,
            ExpertMarketType.BTTS,
        ),
        V19SelectionProfile.MEDIUM: (
            ExpertMarketType.OVER_1_5,
            ExpertMarketType.STRICT_1X2,
            ExpertMarketType.DOUBLE_CHANCE,
            ExpertMarketType.BTTS,
        ),
        V19SelectionProfile.HIGH: (
            ExpertMarketType.BTTS,
            ExpertMarketType.STRICT_1X2,
            ExpertMarketType.OVER_1_5,
            ExpertMarketType.DOUBLE_CHANCE,
        ),
    }
    return preferences[profile].index(market_type)


# Retourne la priorité du risque local selon le profil demandé.
def risk_preference_rank(
    risk_tier: str,
    profile: V19SelectionProfile,
) -> int:
    preferences = {
        V19SelectionProfile.LOW: {
            "LOW": 0,
            "MEDIUM": 1,
            "UNKNOWN": 2,
            "HIGH": 3,
        },
        V19SelectionProfile.MEDIUM: {
            "MEDIUM": 0,
            "LOW": 1,
            "HIGH": 2,
            "UNKNOWN": 3,
        },
        V19SelectionProfile.HIGH: {
            "HIGH": 0,
            "MEDIUM": 1,
            "LOW": 2,
            "UNKNOWN": 3,
        },
    }
    return preferences[profile][risk_tier]


# Construit une clé de classement qualitative sans score brut ni probabilité.
def candidate_sort_key(
    candidate: V19ProfiledCandidateV1,
    profile: V19SelectionProfile,
) -> tuple[int, int, int, int, int, int]:
    selected_candidate = candidate.result.selected_candidate

    if selected_candidate is None:
        raise ValueError("candidate_sort_requires_selected_candidate")

    data_rank = {"A": 0, "B": 1, "C": 2}[candidate.data_grade]
    confidence_rank = {
        "HIGH": 0,
        "MEDIUM": 1,
        "UNKNOWN": 2,
        "LOW": 3,
    }[candidate.confidence_tier]
    caution_rank = {
        "NONE": 0,
        "LIMITED": 1,
        "SIGNIFICANT": 2,
    }[candidate.caution_level]

    risk_rank = risk_preference_rank(
        candidate.local_risk_tier,
        profile,
    )
    market_rank = market_preference_rank(
        selected_candidate.market_type,
        profile,
    )

    if profile is V19SelectionProfile.MEDIUM:
        return (
            data_rank,
            market_rank,
            risk_rank,
            confidence_rank,
            caution_rank,
            candidate.input_position,
        )

    return (
        data_rank,
        risk_rank,
        confidence_rank,
        caution_rank,
        market_rank,
        candidate.input_position,
    )


# Limite les répétitions de marché pour diversifier les profils moyen et élevé.
def selection_market_limit(
    profile: V19SelectionProfile,
    match_count: int,
) -> int:
    if profile is V19SelectionProfile.LOW:
        return match_count

    return max(1, ceil(match_count / 2))


# Compose la sélection finale avec priorité qualitative et diversification contrôlée.
def compose_profile_selection(
    *,
    candidates: tuple[V19ProfiledCandidateV1, ...],
    match_count: int,
    profile: V19SelectionProfile,
) -> tuple[V19SelectedMatchV1, ...]:
    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: candidate_sort_key(candidate, profile),
    )
    market_limit = selection_market_limit(profile, match_count)

    selected: list[V19ProfiledCandidateV1] = []
    selected_ids: set[int] = set()
    market_counts: dict[ExpertMarketType, int] = {}

    for candidate in ranked_candidates:
        selected_candidate = candidate.result.selected_candidate

        if selected_candidate is None:
            continue

        market_type = selected_candidate.market_type
        if market_counts.get(market_type, 0) >= market_limit:
            continue

        selected.append(candidate)
        selected_ids.add(candidate.match_id)
        market_counts[market_type] = market_counts.get(market_type, 0) + 1

        if len(selected) >= match_count:
            break

    if len(selected) < match_count:
        for candidate in ranked_candidates:
            if candidate.match_id in selected_ids:
                continue

            selected.append(candidate)
            selected_ids.add(candidate.match_id)

            if len(selected) >= match_count:
                break

    return tuple(
        V19SelectedMatchV1(
            match_id=candidate.match_id,
            result=candidate.result,
        )
        for candidate in selected
    )


# Exécute un pipeline V19 sous sémaphore et transforme son erreur en résultat contrôlé.
async def evaluate_v19_match(
    *,
    match_id: int,
    input_position: int,
    request_id: str | None,
    predictor: V19SelectionPredictor,
    semaphore: asyncio.Semaphore,
) -> V19PredictionEvaluationV1:
    match_request_id = (
        f"{request_id}-{match_id}"
        if request_id
        else f"v19-selection-{match_id}"
    )

    async with semaphore:
        try:
            result = await predictor(
                match_id=match_id,
                request_id=match_request_id,
            )
        except Exception:
            return V19PredictionEvaluationV1(
                match_id=match_id,
                input_position=input_position,
                result=None,
                error_details=("V19_PREDICTION_UNAVAILABLE",),
            )

    return V19PredictionEvaluationV1(
        match_id=match_id,
        input_position=input_position,
        result=result,
        error_details=(),
    )


# Évalue tout le pool avec au plus quatre pipelines actifs simultanément.
async def evaluate_v19_match_pool(
    *,
    match_ids: tuple[int, ...],
    request_id: str | None,
    predictor: V19SelectionPredictor,
) -> tuple[V19PredictionEvaluationV1, ...]:
    semaphore = asyncio.Semaphore(V19_SELECTION_MAX_CONCURRENCY)
    evaluations = await asyncio.gather(
        *(
            evaluate_v19_match(
                match_id=match_id,
                input_position=input_position,
                request_id=request_id,
                predictor=predictor,
                semaphore=semaphore,
            )
            for input_position, match_id in enumerate(match_ids)
        )
    )
    return tuple(evaluations)


# Détermine si la sélection est complète, partielle ou vide.
def build_selection_status(
    *,
    selected_count: int,
    requested_count: int,
) -> V19SelectionStatus:
    if selected_count == 0:
        return V19SelectionStatus.EMPTY

    if selected_count >= requested_count:
        return V19SelectionStatus.READY

    return V19SelectionStatus.PARTIAL


# Construit une sélection après évaluation complète du pool, sans comparer les scores bruts.
async def build_v19_selection(
    *,
    match_ids: list[int] | tuple[int, ...],
    match_count: int,
    selection_profile: V19SelectionProfile | str,
    request_id: str | None = None,
    predictor: V19SelectionPredictor = build_v19_prediction_for_match,
) -> V19SelectionResultV1:
    if match_count < 1:
        raise ValueError("match_count must be greater than zero")

    normalized_profile = normalize_selection_profile(selection_profile)
    normalized_match_ids = deduplicate_match_ids(match_ids)

    if not normalized_match_ids:
        raise ValueError("match_ids must contain at least one match")

    profiled_candidates: list[V19ProfiledCandidateV1] = []
    excluded_matches: list[V19ExcludedMatchV1] = []

    evaluations = await evaluate_v19_match_pool(
        match_ids=normalized_match_ids,
        request_id=request_id,
        predictor=predictor,
    )

    evaluated_count = len(evaluations)
    abstain_count = 0
    profile_filtered_count = 0
    error_count = 0

    for evaluation in evaluations:
        match_id = evaluation.match_id
        result = evaluation.result

        if result is None:
            error_count += 1
            excluded_matches.append(
                V19ExcludedMatchV1(
                    match_id=match_id,
                    reason=V19SelectionExclusionReason.PIPELINE_ERROR,
                    details=evaluation.error_details,
                )
            )
            continue

        if result.status is DecisionStatus.ABSTAIN:
            abstain_count += 1
            excluded_matches.append(
                V19ExcludedMatchV1(
                    match_id=match_id,
                    reason=V19SelectionExclusionReason.ABSTAIN,
                    details=result.abstention_reasons,
                )
            )
            continue

        rejection_reasons = profile_rejection_reasons(
            result,
            normalized_profile,
        )

        if rejection_reasons:
            profile_filtered_count += 1
            excluded_matches.append(
                V19ExcludedMatchV1(
                    match_id=match_id,
                    reason=V19SelectionExclusionReason.PROFILE_FILTERED,
                    details=rejection_reasons,
                )
            )
            continue

        profiled_candidates.append(
            build_profiled_candidate(
                match_id=match_id,
                result=result,
                input_position=evaluation.input_position,
            )
        )

    selections = compose_profile_selection(
        candidates=tuple(profiled_candidates),
        match_count=match_count,
        profile=normalized_profile,
    )

    return V19SelectionResultV1(
        status=build_selection_status(
            selected_count=len(selections),
            requested_count=match_count,
        ),
        profile=normalized_profile,
        requested_count=match_count,
        candidate_count=len(normalized_match_ids),
        evaluated_count=evaluated_count,
        abstain_count=abstain_count,
        profile_filtered_count=profile_filtered_count,
        error_count=error_count,
        selections=selections,
        excluded_matches=tuple(excluded_matches),
        service_version=V19_SELECTION_SERVICE_VERSION,
    )


# Schéma de communication :
# liste de match_ids + profil utilisateur
#   -> v19_selection_service.py
#       -> appelle v19_prediction_service.py avec une concurrence maximale de quatre matchs
#       -> évalue tout le pool avant composition
#       -> classe par qualité, adéquation au profil et diversité de marché
#       -> ne compare jamais raw_score ou probabilité calibrée
#       -> ne transforme jamais une décision ABSTAIN
#   -> experimental_ml_v19.py expose ensuite la réponse publique stable