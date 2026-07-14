# Rôle du fichier :
# Ce service compose une sélection multi-matchs à partir des décisions officielles RubyBets V19.

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

from app.v19.application.v19_prediction_service import (
    build_v19_prediction_for_match,
)
from app.v19.domain.decision_contracts import DecisionResultV1
from app.v19.domain.decision_enums import DecisionStatus
from app.v19.domain.expert_enums import ExpertMarketType


V19_SELECTION_SERVICE_VERSION = "v19.selection.service.1"

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

    return ()


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


# Construit une sélection sans comparer les scores bruts et sans récupérer les abstentions.
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

    selections: list[V19SelectedMatchV1] = []
    excluded_matches: list[V19ExcludedMatchV1] = []

    evaluated_count = 0
    abstain_count = 0
    profile_filtered_count = 0
    error_count = 0

    for match_id in normalized_match_ids:
        if len(selections) >= match_count:
            break

        evaluated_count += 1
        match_request_id = (
            f"{request_id}-{match_id}"
            if request_id
            else f"v19-selection-{match_id}"
        )

        try:
            result = await predictor(
                match_id=match_id,
                request_id=match_request_id,
            )
        except Exception:
            error_count += 1
            excluded_matches.append(
                V19ExcludedMatchV1(
                    match_id=match_id,
                    reason=V19SelectionExclusionReason.PIPELINE_ERROR,
                    details=("V19_PREDICTION_UNAVAILABLE",),
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

        selections.append(
            V19SelectedMatchV1(
                match_id=match_id,
                result=result,
            )
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
        selections=tuple(selections),
        excluded_matches=tuple(excluded_matches),
        service_version=V19_SELECTION_SERVICE_VERSION,
    )


# Schéma de communication :
# liste de match_ids + profil utilisateur
#   -> v19_selection_service.py
#       -> appelle v19_prediction_service.py pour chaque match
#       -> conserve uniquement les décisions RECOMMEND compatibles avec le profil
#       -> ne compare jamais les raw_score et ne transforme jamais ABSTAIN
#   -> experimental_ml_v19.py exposera ensuite la réponse publique
