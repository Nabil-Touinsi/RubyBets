# Rôle du fichier :
# Ce service orchestre le flux match cible -> acquisition H2H -> features H2H V19.

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.services.rapidapi_flashscore_client import (
    get_flashscore_head_to_head,
    get_normalized_flashscore_match_details,
)
from app.v19.acquisition.h2h_acquisition_service import (
    H2HClock,
    H2HProviderClient,
    acquire_h2h_module_input,
    utc_now,
)
from app.v19.acquisition.target_match_adapter import (
    TargetMatchAdapterError,
    adapt_normalized_target_match,
)
from app.v19.domain.h2h_contracts import H2HModuleResultV1
from app.v19.domain.h2h_enums import H2HEntityType
from app.v19.features.h2h_feature_builder import build_h2h_module_result


H2HTargetMatchLoader = Callable[
    [int | str | None],
    tuple[dict[str, Any] | None, dict[str, Any]],
]


# Signale une erreur applicative contrôlée du flux H2H V19.
class H2HApplicationError(RuntimeError):
    pass


# Signale qu'aucun match cible exploitable ne correspond à l'identifiant demandé.
class H2HTargetMatchNotFoundError(H2HApplicationError):
    pass


# Signale que le fournisseur du match cible n'a pas pu répondre correctement.
class H2HTargetMatchProviderError(H2HApplicationError):
    pass


# Signale que le match cible reçu ne respecte pas le contrat minimal H2H V19.
class H2HTargetMatchInvalidError(H2HApplicationError):
    pass


# Détermine si les métadonnées du chargeur décrivent une absence plutôt qu'une panne fournisseur.
def is_target_match_not_found(metadata: dict[str, Any]) -> bool:
    status = str(metadata.get("status") or "").strip().lower()
    return status in {
        "not_flashscore_match_id",
        "not_found",
        "missing_match_id",
        "empty",
    }


# Charge le match cible avec une gestion stable des absences et erreurs fournisseur.
def load_target_match(
    match_id: int | str,
    loader: H2HTargetMatchLoader,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        match_data, metadata = loader(match_id)
    except Exception as exc:
        raise H2HTargetMatchProviderError(
            f"target_match_provider_error:{type(exc).__name__}"
        ) from exc

    normalized_metadata = metadata if isinstance(metadata, dict) else {}
    if isinstance(match_data, dict) and match_data:
        return match_data, normalized_metadata

    if is_target_match_not_found(normalized_metadata):
        raise H2HTargetMatchNotFoundError("target_match_not_found")

    status = str(normalized_metadata.get("status") or "unknown")
    raise H2HTargetMatchProviderError(
        f"target_match_provider_unavailable:{status}"
    )


# Exécute la chaîne H2H complète sans exposer de route ni produire de recommandation sportive.
def build_h2h_result_for_match(
    match_id: int | str,
    request_id: str,
    cutoff_utc: datetime,
    entity_type: H2HEntityType,
    match_loader: H2HTargetMatchLoader = get_normalized_flashscore_match_details,
    h2h_client: H2HProviderClient = get_flashscore_head_to_head,
    clock: H2HClock = utc_now,
) -> H2HModuleResultV1:
    match_data, _metadata = load_target_match(
        match_id=match_id,
        loader=match_loader,
    )

    try:
        target_match, target_teams = adapt_normalized_target_match(
            match_data=match_data,
            cutoff_utc=cutoff_utc,
            entity_type=entity_type,
        )
    except TargetMatchAdapterError as exc:
        raise H2HTargetMatchInvalidError(str(exc)) from exc

    module_input = acquire_h2h_module_input(
        request_id=request_id,
        target_match=target_match,
        target_teams=target_teams,
        client=h2h_client,
        clock=clock,
    )

    return build_h2h_module_result(
        module_input=module_input,
        clock=clock,
    )


# Schéma de communication :
# rapidapi_flashscore_client.py
#   -> charge le match cible et les confrontations FlashScore
# target_match_adapter.py
#   -> produit TargetMatchRefV1 et TargetTeamsV1
# h2h_acquisition_service.py
#   -> produit H2HModuleInputV1
# h2h_feature_builder.py
#   -> produit H2HModuleResultV1
# future route FastAPI V19
#   -> appellera ce service sans contenir la logique métier
# backend/tests/test_v19.py
#   -> injecte chargeurs, clients et horloges contrôlés sans réseau réel
