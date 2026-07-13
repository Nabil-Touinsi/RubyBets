# Rôle du fichier :
# Cette route expose le pipeline produit V19 expérimental pour les matchs clubs RubyBets.

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from app.v19.application.v19_prediction_service import (
    V19ProductMatchInvalidError,
    V19ProductMatchNotFoundError,
    V19ProductMatchProviderError,
    build_v19_prediction_for_match,
)
from app.v19.domain.decision_contracts import DecisionResultV1
from app.v19.explainability.explanation_builder import (
    EXPLANATION_CONTRACT_VERSION,
    build_public_explanation,
)


API_SOURCE = "rubybets_v19_product_api"
API_SCOPE = "experimental_clubs_product_pipeline"
RESPONSIBLE_NOTE = (
    "Décision analytique expérimentale avant-match. "
    "RubyBets ne garantit aucun résultat sportif et ne permet aucune prise de pari."
)

router = APIRouter(
    prefix="/api/experimental/ml-v19",
    tags=["Experimental ML V19 Product"],
)


# Produit un identifiant unique pour relier la requête API, les logs et la décision V19.
def build_request_id(match_id: int) -> str:
    return f"v19-product-{match_id}-{uuid4().hex}"


# Convertit le candidat retenu en résumé produit sans recalculer la décision métier.
def build_recommendation_summary(result: DecisionResultV1) -> dict[str, Any] | None:
    candidate = result.selected_candidate
    if candidate is None:
        return None

    return {
        "market_type": candidate.market_type.value,
        "value": candidate.recommendation_value,
        "score": candidate.raw_score,
        "confidence_level": candidate.confidence_level,
        "risk_level": candidate.local_risk_level,
    }


# Transforme DecisionResultV1 en réponse API stable sans exposer les odds ou payloads fournisseurs.
def build_v19_product_api_response(
    *,
    match_id: int,
    request_id: str,
    result: DecisionResultV1,
) -> dict[str, Any]:
    metadata = dict(result.metadata)

    return {
        "source": API_SOURCE,
        "scope": API_SCOPE,
        "match_id": match_id,
        "request_id": request_id,
        "status": result.status.value,
        "recommendation": build_recommendation_summary(result),
        "decision": jsonable_encoder(result),
        "explanation": build_public_explanation(
            result=result,
            responsible_note=RESPONSIBLE_NOTE,
        ),
        "data_quality": {
            "target_match_provider_status": metadata.get("target_match_provider_status"),
            "market_provider_status": metadata.get("market_provider_status"),
            "market_module_status": metadata.get("market_module_status"),
            "market_quality_flags": metadata.get("market_quality_flags"),
            "history_provider_status": metadata.get("history_provider_status"),
            "history_data_status": metadata.get("history_data_status"),
            "history_source_used": metadata.get("history_source_used"),
        },
        "versions": {
            "engine": result.engine_version,
            "experts": dict(result.expert_versions),
            "features": list(result.feature_versions),
            "product_service": metadata.get("product_service_version"),
            "explanation": EXPLANATION_CONTRACT_VERSION,
        },
        "responsible_note": RESPONSIBLE_NOTE,
    }


# Retourne la décision produit V19 d'un match réel tout en conservant l'abstention comme sortie HTTP normale.
@router.get("/rubybets-matches/{match_id}")
async def get_v19_rubybets_match_prediction(match_id: int) -> dict[str, Any]:
    request_id = build_request_id(match_id)

    try:
        result = await build_v19_prediction_for_match(
            match_id=match_id,
            request_id=request_id,
        )
    except V19ProductMatchNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "V19_PRODUCT_TARGET_MATCH_NOT_FOUND",
                "message": "Le match cible demandé est introuvable.",
                "match_id": match_id,
            },
        ) from exc
    except V19ProductMatchInvalidError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "V19_PRODUCT_TARGET_MATCH_INVALID",
                "message": "Le match cible ne respecte pas le contrat minimal du pipeline V19.",
                "match_id": match_id,
                "reason": str(exc),
            },
        ) from exc
    except V19ProductMatchProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "V19_PRODUCT_TARGET_PROVIDER_UNAVAILABLE",
                "message": "Le fournisseur du match cible est temporairement indisponible.",
                "match_id": match_id,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "V19_PRODUCT_UNEXPECTED_ERROR",
                "message": "Erreur inattendue pendant le pipeline produit V19.",
                "match_id": match_id,
            },
        ) from exc

    return build_v19_product_api_response(
        match_id=match_id,
        request_id=request_id,
        result=result,
    )


# Schéma de communication :
# experimental_ml_v19.py
#   -> appelle v19_prediction_service.py sans contenir de règle sportive
#   -> appelle explanation_builder.py pour la projection publique déterministe
#   -> sérialise DecisionResultV1 et les diagnostics de qualité
#   -> est enregistré dans backend/app/main.py
#   -> n'expose jamais les odds, les bookmakers ou le payload brut FlashScore
