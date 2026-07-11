# Rôle du fichier :
# Cette route expose le module H2H V19 en API expérimentale sans produire de recommandation sportive.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool

from app.v19.application.h2h_service import (
    H2HTargetMatchInvalidError,
    H2HTargetMatchNotFoundError,
    H2HTargetMatchProviderError,
    build_h2h_result_for_match,
)
from app.v19.domain.h2h_contracts import H2HModuleResultV1
from app.v19.domain.h2h_enums import H2HEntityType


API_SOURCE = "rubybets_v19_h2h_api"
API_SCOPE = "experimental_h2h_module"
RESPONSIBLE_NOTE = (
    "Analyse H2H expérimentale utilisée comme signal secondaire. "
    "Elle ne constitue pas une recommandation sportive et ne garantit aucun résultat."
)

router = APIRouter(
    prefix="/api/experimental/ml-v19/h2h",
    tags=["Experimental ML V19 H2H"],
)


# Retourne l'instant courant sous forme de datetime UTC conscient du fuseau.
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Normalise le cutoff fourni par l'appelant ou utilise l'instant courant de la requête.
def resolve_cutoff_utc(cutoff_utc: datetime | None) -> datetime:
    if cutoff_utc is None:
        return utc_now()

    if cutoff_utc.tzinfo is None:
        return cutoff_utc.replace(tzinfo=timezone.utc)

    return cutoff_utc.astimezone(timezone.utc)


# Produit un identifiant de requête unique pour relier logs, résultat et futur archivage.
def build_request_id(match_id: int) -> str:
    return f"v19-h2h-{match_id}-{uuid4().hex}"


# Transforme le contrat de domaine en réponse JSON stable pour l'API et le futur frontend.
def build_v19_h2h_api_response(
    match_id: int,
    entity_type: H2HEntityType,
    result: H2HModuleResultV1,
) -> dict[str, Any]:
    encoded_result = jsonable_encoder(result)

    return {
        "source": API_SOURCE,
        "scope": API_SCOPE,
        "match_id": match_id,
        "entity_type": entity_type.value,
        "request_id": result.request_id,
        "module_status": result.module_status.value,
        "module_outcome": result.module_outcome.value,
        "feature_set_version": result.feature_set_version,
        "result": encoded_result,
        "responsible_note": RESPONSIBLE_NOTE,
    }


# Retourne l'analyse H2H V19 d'un match RubyBets réel sans décision sportive finale.
@router.get("/rubybets-matches/{match_id}")
async def get_v19_h2h_rubybets_match(
    match_id: int,
    entity_type: H2HEntityType = Query(default=H2HEntityType.CLUB),
    cutoff_utc: datetime | None = Query(default=None),
) -> dict[str, Any]:
    resolved_cutoff = resolve_cutoff_utc(cutoff_utc)
    request_id = build_request_id(match_id)

    try:
        result = await run_in_threadpool(
            build_h2h_result_for_match,
            match_id=match_id,
            request_id=request_id,
            cutoff_utc=resolved_cutoff,
            entity_type=entity_type,
        )
    except H2HTargetMatchNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "V19_H2H_TARGET_MATCH_NOT_FOUND",
                "message": "Le match cible demandé est introuvable.",
                "match_id": match_id,
            },
        ) from exc
    except H2HTargetMatchInvalidError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "V19_H2H_TARGET_MATCH_INVALID",
                "message": "Le match cible ne respecte pas le contrat minimal H2H V19.",
                "match_id": match_id,
                "reason": str(exc),
            },
        ) from exc
    except H2HTargetMatchProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "V19_H2H_TARGET_PROVIDER_UNAVAILABLE",
                "message": "Le fournisseur du match cible est temporairement indisponible.",
                "match_id": match_id,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "V19_H2H_UNEXPECTED_ERROR",
                "message": "Erreur inattendue pendant l'analyse H2H V19.",
                "match_id": match_id,
            },
        ) from exc

    return build_v19_h2h_api_response(
        match_id=match_id,
        entity_type=entity_type,
        result=result,
    )


# Schéma de communication :
# experimental_ml_v19_h2h.py
#   -> appelle backend/app/v19/application/h2h_service.py
#   -> sérialise H2HModuleResultV1 sans modifier ses règles métier
#   -> est enregistré dans backend/app/main.py
#   -> sera consommé par le futur bloc frontend V19 H2H
#   -> est testé dans backend/tests/test_v19.py sans appel réseau réel
