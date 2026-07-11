# Rôle du fichier :
# Ce service acquiert les confrontations FlashScore et assemble le contrat H2HModuleInputV1.

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.services.rapidapi_flashscore_client import get_flashscore_head_to_head
from app.v19.acquisition.flashscore_h2h_adapter import (
    adapt_flashscore_h2h_match,
    normalize_cache_state,
)
from app.v19.domain.h2h_contracts import (
    H2HAcquisitionContextV1,
    H2HModuleInputV1,
    H2HProcessingPolicyV1,
    TargetMatchRefV1,
    TargetTeamsV1,
)
from app.v19.domain.h2h_enums import (
    H2HCacheState,
    H2HDomainProfile,
    H2HEntityType,
    H2HProvider,
    H2HProviderResultStatus,
)


H2H_INPUT_CONTRACT_VERSION = "H2HModuleInputV1"
H2H_ACQUISITION_CANDIDATE_LIMIT = 8
H2H_PROCESSING_POLICY_VERSION = "v19.h2h.processing-policy.1"

H2HProviderClient = Callable[
    [str | None, str, str, int],
    tuple[list[dict[str, Any]], dict[str, Any]],
]
H2HClock = Callable[[], datetime]


# Retourne l'instant courant sous forme de datetime UTC conscient du fuseau.
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Normalise un datetime technique en UTC pour éviter les comparaisons naïves.
def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


# Recherche l'identifiant FlashScore du match cible dans le contrat de domaine.
def get_target_flashscore_match_id(
    target_match: TargetMatchRefV1,
) -> str | None:
    for provider, provider_match_id in target_match.provider_match_ids:
        if provider == H2HProvider.FLASHSCORE:
            normalized_id = str(provider_match_id).strip()
            return normalized_id or None

    return None


# Sélectionne le profil H2H officiel selon le domaine club ou sélection nationale.
def get_h2h_domain_profile(
    entity_type: H2HEntityType,
) -> H2HDomainProfile:
    if entity_type == H2HEntityType.NATIONAL_TEAM:
        return H2HDomainProfile.NATIONAL_TEAM_H2H_V1

    return H2HDomainProfile.CLUB_H2H_V1


# Construit la politique versionnée transportée avec chaque entrée du module H2H.
def build_h2h_processing_policy(
    entity_type: H2HEntityType,
) -> H2HProcessingPolicyV1:
    domain_profile = get_h2h_domain_profile(entity_type)

    return H2HProcessingPolicyV1(
        policy_version=H2H_PROCESSING_POLICY_VERSION,
        domain_profile=domain_profile,
        temporal_policy=(
            ("cutoff_operator", "kickoff_utc < cutoff_utc"),
            ("timezone", "UTC"),
            ("require_kickoff_utc", True),
            ("exclude_target_match", True),
        ),
        exclusion_policy=(
            ("require_target_team_pair", True),
            ("club_friendlies", "EXCLUDE"),
            ("national_official_priority", True),
            ("national_friendly_supplement_years", 6),
        ),
        deduplication_policy=(
            ("primary_key", "provider_match_id"),
            ("secondary_key", "kickoff_utc+team_pair"),
            ("provider_priority", "FLASHSCORE"),
            ("preserve_all_provenance", True),
        ),
        identity_policy=(
            ("provider_id_priority", True),
            ("normalized_name_fallback", True),
            ("ambiguous_identity", "KEEP_AS_DIAGNOSTIC"),
        ),
    )


# Convertit le statut historique du client FlashScore vers le vocabulaire V19.
def map_flashscore_provider_status(
    metadata: dict[str, Any],
) -> H2HProviderResultStatus:
    status = str(metadata.get("status") or "").strip().lower()

    if status in {"success", "empty"}:
        return H2HProviderResultStatus.AVAILABLE

    if status in {"missing_match_id", "unavailable"}:
        return H2HProviderResultStatus.UNAVAILABLE

    if status in {"error", "unexpected_response"}:
        return H2HProviderResultStatus.ERROR

    return H2HProviderResultStatus.PARTIAL


# Détermine si les données assemblées déclarent explicitement provenir du cache.
def is_assembled_from_cache(metadata: dict[str, Any]) -> bool:
    cache_state = normalize_cache_state(metadata.get("cache_state"))
    return cache_state in {
        H2HCacheState.HIT_FRESH,
        H2HCacheState.HIT_STALE_ALLOWED,
    } or metadata.get("cache_hit") is True


# Construit des avertissements techniques structurés sans exposer le contenu du payload.
def build_acquisition_warnings(
    metadata: dict[str, Any],
    provider_status: H2HProviderResultStatus,
) -> tuple[str, ...]:
    warnings: list[str] = []
    message = metadata.get("message")

    if provider_status in {
        H2HProviderResultStatus.UNAVAILABLE,
        H2HProviderResultStatus.ERROR,
        H2HProviderResultStatus.PARTIAL,
    }:
        status = str(metadata.get("status") or "unknown")
        warnings.append(f"flashscore_h2h_status:{status}")

    if message:
        warnings.append("flashscore_h2h_message_available")

    return tuple(warnings)


# Appelle le client injecté en garantissant le plafond commun de huit candidats.
def call_flashscore_h2h_client(
    client: H2HProviderClient,
    flashscore_match_id: str | None,
    home_team_name: str,
    away_team_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        return client(
            flashscore_match_id,
            home_team_name,
            away_team_name,
            H2H_ACQUISITION_CANDIDATE_LIMIT,
        )
    except Exception as exc:
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "error",
            "endpoint": "/matches/h2h",
            "message": type(exc).__name__,
            "results": 0,
        }


# Assemble les confrontations candidates sans appliquer de feature ni de recommandation.
def acquire_h2h_module_input(
    request_id: str,
    target_match: TargetMatchRefV1,
    target_teams: TargetTeamsV1,
    client: H2HProviderClient = get_flashscore_head_to_head,
    clock: H2HClock = utc_now,
    processing_policy: H2HProcessingPolicyV1 | None = None,
) -> H2HModuleInputV1:
    assembled_at_utc = ensure_utc_datetime(clock())
    flashscore_match_id = get_target_flashscore_match_id(target_match)
    raw_meetings, metadata = call_flashscore_h2h_client(
        client=client,
        flashscore_match_id=flashscore_match_id,
        home_team_name=target_teams.home_team.display_name,
        away_team_name=target_teams.away_team.display_name,
    )
    retrieved_at_utc = ensure_utc_datetime(clock())
    cache_state = normalize_cache_state(metadata.get("cache_state"))
    provider_status = map_flashscore_provider_status(metadata)

    candidate_meetings = tuple(
        adapt_flashscore_h2h_match(
            match_data=meeting,
            target_teams=target_teams,
            entity_type=target_match.domain,
            retrieved_at_utc=retrieved_at_utc,
            cache_state=cache_state,
        )
        for meeting in raw_meetings[:H2H_ACQUISITION_CANDIDATE_LIMIT]
        if isinstance(meeting, dict)
    )
    retrieval_bounds = (
        retrieved_at_utc if candidate_meetings else None
    )

    acquisition_context = H2HAcquisitionContextV1(
        primary_provider=H2HProvider.FLASHSCORE,
        providers_attempted=(H2HProvider.FLASHSCORE,),
        provider_results=((H2HProvider.FLASHSCORE, provider_status),),
        fallback_used=False,
        assembled_from_cache=is_assembled_from_cache(metadata),
        earliest_retrieved_at_utc=retrieval_bounds,
        latest_retrieved_at_utc=retrieval_bounds,
        warnings=build_acquisition_warnings(
            metadata=metadata,
            provider_status=provider_status,
        ),
    )

    return H2HModuleInputV1(
        contract_version=H2H_INPUT_CONTRACT_VERSION,
        request_id=request_id,
        assembled_at_utc=assembled_at_utc,
        target_match=target_match,
        target_teams=target_teams,
        candidate_meetings=candidate_meetings,
        acquisition_context=acquisition_context,
        processing_policy=(
            processing_policy
            if processing_policy is not None
            else build_h2h_processing_policy(target_match.domain)
        ),
    )


# Schéma de communication :
# rapidapi_flashscore_client.py
#   -> fournit get_flashscore_head_to_head avec une limite explicite de huit candidats
# flashscore_h2h_adapter.py
#   -> transforme chaque dictionnaire normalisé en H2HMeetingV1
# h2h_acquisition_service.py
#   -> assemble H2HAcquisitionContextV1, H2HProcessingPolicyV1 et H2HModuleInputV1
# backend/tests/test_v19.py
#   -> teste succès, indisponibilité, orientation, provenance et données manquantes
#   -> aucune feature ni recommandation sportive n'est calculée ici
