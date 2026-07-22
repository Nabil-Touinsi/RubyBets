# Rôle du fichier :
# Cette route expose le pipeline produit V19 expérimental pour les matchs clubs RubyBets.

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.services.archives_service import archive_v19_decision

from app.v19.application.v19_selection_service import (
    V19ExcludedMatchV1,
    V19SelectedMatchV1,
    V19SelectionProfile,
    V19SelectionResultV1,
    V19SelectionStatus,
    build_v19_selection,
)

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
SELECTION_API_SCOPE = "experimental_v19_multimatch_selection"
V19_SELECTION_CONTRACT_VERSION = "v19.selection.public.1"

RESPONSIBLE_NOTE = (
    "Décision analytique expérimentale avant-match. "
    "RubyBets ne garantit aucun résultat sportif et ne permet aucune prise de pari."
)

router = APIRouter(
    prefix="/api/experimental/ml-v19",
    tags=["Experimental ML V19 Product"],
)


# Décrit les paramètres publics autorisés pour composer une sélection V19.
class V19SelectionRequest(BaseModel):
    match_ids: list[int]
    match_count: int = Field(default=3, ge=2, le=5)
    selection_profile: V19SelectionProfile = V19SelectionProfile.MEDIUM


# Produit un identifiant unique pour relier la sélection à ses décisions.
def build_selection_request_id() -> str:
    return f"v19-selection-{uuid4().hex}"


# Retourne le libellé public du profil de sélectivité demandé.
def build_selection_profile_label(
    profile: V19SelectionProfile,
) -> str:
    labels = {
        V19SelectionProfile.LOW: "Prudence renforcée",
        V19SelectionProfile.MEDIUM: "Équilibre",
        V19SelectionProfile.HIGH: "Ouverture contrôlée",
    }
    return labels[profile]


# Explique le profil sans le présenter comme un risque sportif.
def build_selection_profile_description(
    profile: V19SelectionProfile,
) -> str:
    descriptions = {
        V19SelectionProfile.LOW: (
            "Priorise les décisions robustes, peu variables "
            "et appuyées par des données complètes."
        ),
        V19SelectionProfile.MEDIUM: (
            "Recherche un équilibre entre robustesse, diversité "
            "des marchés et variabilité maîtrisée."
        ),
        V19SelectionProfile.HIGH: (
            "Priorise les décisions officielles plus variables "
            "tout en maintenant un socle minimal de qualité."
        ),
    }
    return descriptions[profile]


# Construit un match public retenu sans exposer son score brut.
def build_public_selection_item(
    item: V19SelectedMatchV1,
) -> dict[str, Any]:
    result = item.result
    candidate = result.selected_candidate

    if candidate is None:
        raise ValueError("selected_match_without_candidate")

    metadata = dict(result.metadata)

    return {
        "match_id": item.match_id,
        "status": result.status.value,
        "recommendation": {
            "market_type": candidate.market_type.value,
            "value": candidate.recommendation_value,
        },
        "explanation": build_public_explanation(
            result=result,
            responsible_note=RESPONSIBLE_NOTE,
        ),
        "data_quality": {
            "target_match_provider_status": metadata.get(
                "target_match_provider_status"
            ),
            "market_provider_status": metadata.get(
                "market_provider_status"
            ),
            "market_module_status": metadata.get(
                "market_module_status"
            ),
            "market_quality_flags": metadata.get(
                "market_quality_flags"
            ),
            "history_provider_status": metadata.get(
                "history_provider_status"
            ),
            "history_data_status": metadata.get(
                "history_data_status"
            ),
            "history_source_used": metadata.get(
                "history_source_used"
            ),
        },
        "versions": {
            "engine": result.engine_version,
            "experts": dict(result.expert_versions),
            "features": list(result.feature_versions),
            "product_service": metadata.get(
                "product_service_version"
            ),
            "explanation": EXPLANATION_CONTRACT_VERSION,
        },
    }


# Traduit une exclusion sans exposer ses codes techniques détaillés.
def build_public_excluded_match(
    item: V19ExcludedMatchV1,
) -> dict[str, Any]:
    messages = {
        "ABSTAIN": (
            "Le moteur V19 s'abstient sur ce match et ne produit "
            "aucune recommandation artificielle."
        ),
        "PROFILE_FILTERED": (
            "La décision ne satisfait pas le niveau de sélectivité "
            "demandé pour cette sélection."
        ),
        "PIPELINE_ERROR": (
            "L'analyse V19 de ce match est temporairement indisponible."
        ),
    }

    return {
        "match_id": item.match_id,
        "status": item.reason.value,
        "summary": messages[item.reason.value],
    }


# Construit le titre public associé à l'état de la sélection.
def build_selection_headline(
    status: V19SelectionStatus,
) -> str:
    headlines = {
        V19SelectionStatus.READY: "Sélection V19 constituée",
        V19SelectionStatus.PARTIAL: "Sélection V19 partielle",
        V19SelectionStatus.EMPTY: "Aucune sélection V19 disponible",
    }
    return headlines[status]


# Construit un résumé factuel du nombre de matchs retenus.
def build_selection_summary(
    result: V19SelectionResultV1,
) -> str:
    selected_count = len(result.selections)

    if result.status is V19SelectionStatus.READY:
        return (
            f"{selected_count} match(s) ont été retenus après "
            "évaluation complète du pool et application "
            "du profil de sélectivité demandé."
        )

    if result.status is V19SelectionStatus.PARTIAL:
        return (
            f"{selected_count} match(s) ont été retenus sur "
            f"{result.requested_count} demandé(s) après "
            "évaluation complète du pool. RubyBets ne complète "
            "jamais une sélection avec une abstention ou une "
            "donnée de qualité insuffisante."
        )

    return (
        "Aucun match ne satisfait actuellement les décisions V19 "
        "et le profil de sélectivité demandés."
    )


# Transforme le résultat du service en contrat public stable.
def build_v19_selection_api_response(
    *,
    request_id: str,
    result: V19SelectionResultV1,
) -> dict[str, Any]:
    return {
        "source": API_SOURCE,
        "scope": SELECTION_API_SCOPE,
        "contract_version": V19_SELECTION_CONTRACT_VERSION,
        "request_id": request_id,
        "status": result.status.value,
        "profile": {
            "value": result.profile.value,
            "label": build_selection_profile_label(
                result.profile
            ),
            "description": build_selection_profile_description(
                result.profile
            ),
        },
        "requested_count": result.requested_count,
        "candidate_count": result.candidate_count,
        "evaluated_count": result.evaluated_count,
        "selected_count": len(result.selections),
        "abstain_count": result.abstain_count,
        "profile_filtered_count": result.profile_filtered_count,
        "error_count": result.error_count,
        "selections": [
            build_public_selection_item(item)
            for item in result.selections
        ],
        "excluded_matches": [
            build_public_excluded_match(item)
            for item in result.excluded_matches
        ],
        "selection_explanation": {
            "headline": build_selection_headline(result.status),
            "summary": build_selection_summary(result),
        },
        "versions": {
            "selection_service": result.service_version,
            "selection_contract": V19_SELECTION_CONTRACT_VERSION,
            "explanation": EXPLANATION_CONTRACT_VERSION,
        },
        "responsible_note": RESPONSIBLE_NOTE,
    }


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
async def get_v19_rubybets_match_prediction(
    match_id: int,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
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

    background_tasks.add_task(archive_v19_decision, result)

    return build_v19_product_api_response(
        match_id=match_id,
        request_id=request_id,
        result=result,
    )


# Compose une sélection à partir des décisions officielles V19.
@router.post("/selection")
async def create_v19_selection(
    request: V19SelectionRequest,
) -> dict[str, Any]:
    if not request.match_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "V19_SELECTION_MATCH_IDS_REQUIRED",
                "message": (
                    "La sélection nécessite au moins "
                    "un identifiant de match."
                ),
            },
        )

    request_id = build_selection_request_id()

    try:
        result = await build_v19_selection(
            match_ids=request.match_ids,
            match_count=request.match_count,
            selection_profile=request.selection_profile,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "V19_SELECTION_INVALID_REQUEST",
                "message": (
                    "La demande de sélection V19 est invalide."
                ),
                "reason": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "V19_SELECTION_UNEXPECTED_ERROR",
                "message": (
                    "Erreur inattendue pendant la composition "
                    "de la sélection V19."
                ),
            },
        ) from exc

    return build_v19_selection_api_response(
        request_id=request_id,
        result=result,
    )


# Schéma de communication :
# experimental_ml_v19.py
#   -> appelle v19_prediction_service.py pour une décision individuelle
#   -> appelle v19_selection_service.py pour la composition multi-matchs
#   -> appelle explanation_builder.py pour les projections publiques
#   -> programme archives_service.py après une décision individuelle
#   -> projette uniquement le contrat public sans diagnostics internes
#   -> est enregistré dans backend/app/main.py
#   -> n'expose jamais score brut, odds, bookmaker ou payload fournisseur
