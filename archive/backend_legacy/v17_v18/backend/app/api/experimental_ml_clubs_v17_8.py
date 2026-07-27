# Role du fichier :
# Cette route expose une vraie prediction experimentale clubs V17.8 a partir de matchs RubyBets reels.
# Elle ne branche pas les routes de demo V17.8 et ne modifie pas les Archives nationales.

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.ml_clubs_v17_8_feature_builder import (
    build_clubs_v17_8_prepared_match_data,
)
from app.services.ml_v17_8_feature_adapter import adapt_and_recommend_with_v17_8
from app.services.team_history_service import build_team_history_response


API_SOURCE = "rubybets_ml_clubs_v17_8_api"
API_SCOPE = "experimental_clubs_product_route"


router = APIRouter(
    prefix="/api/experimental/ml-clubs/v17-8",
    tags=["Experimental ML Clubs V17.8"],
)


# Construit une reponse produit stable et future-compatible avec les Archives clubs.
def build_clubs_v17_8_product_response(
    match_id: int,
    team_history_response: dict[str, Any],
    prepared_match_data: dict[str, Any],
    adapter_response: dict[str, Any],
) -> dict[str, Any]:
    result = adapter_response.get("result", {}) or {}
    feature_metadata = prepared_match_data.get("feature_metadata", {}) or {}

    return {
        "source": API_SOURCE,
        "scope": API_SCOPE,
        "match_id": match_id,
        "status": result.get("status", "ABSTAIN"),
        "engine_version": result.get("model_status"),
        "strategy": result.get("strategy"),
        "recommendation_type": result.get("recommendation_type"),
        "recommendation_value": result.get("recommendation_value"),
        "recommendation_source": result.get("recommendation_source"),
        "confidence_level": result.get("confidence_level"),
        "risk_level": result.get("risk_level"),
        "accuracy_reference": result.get("accuracy_reference"),
        "coverage_reference": result.get("coverage_reference"),
        "is_btts": result.get("is_btts", False),
        "is_added_btts": result.get("is_added_btts", False),
        "is_replaced_over15": result.get("is_replaced_over15", False),
        "btts_score": result.get("btts_score"),
        "btts_gate_result": result.get("btts_gate_result"),
        "abstention_reasons": result.get("reasons", []),
        "missing_features": result.get("missing_features", []),
        "data_status": team_history_response.get("data_status"),
        "source_used": team_history_response.get("source_used"),
        "teams": {
            "home": feature_metadata.get("home_team"),
            "away": feature_metadata.get("away_team"),
        },
        "features": prepared_match_data.get("btts_signals"),
        "features_debug": prepared_match_data.get("clubs_features_debug"),
        "feature_metadata": feature_metadata,
        "adapter_metadata": adapter_response.get("adapter_metadata"),
        "archive_status": {
            "is_archivable": True,
            "is_persisted": False,
            "archive_scope": "clubs_v17_8",
            "message": "Prediction clubs structurée pour archivage futur, mais non persistée dans cette route.",
        },
        "responsible_note": result.get(
            "responsible_note",
            "Recommandation experimentale sans garantie de resultat sportif.",
        ),
    }


# Retourne une prediction clubs V17.8 construite depuis un vrai match RubyBets.
@router.get("/rubybets-matches/{match_id}")
async def get_clubs_v17_8_rubybets_match_prediction(
    match_id: int,
) -> dict[str, Any]:
    try:
        team_history_response = await build_team_history_response(match_id)
        prepared_match_data = build_clubs_v17_8_prepared_match_data(
            team_history_response
        )
        adapter_response = adapt_and_recommend_with_v17_8(prepared_match_data)

        return build_clubs_v17_8_product_response(
            match_id=match_id,
            team_history_response=team_history_response,
            prepared_match_data=prepared_match_data,
            adapter_response=adapter_response,
        )

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Erreur pendant la generation de la prediction clubs V17.8.",
                "match_id": match_id,
                "error": str(error),
            },
        ) from error


# Schema de communication :
# experimental_ml_clubs_v17_8.py
#   -> appelle build_team_history_response(match_id)
#   -> appelle ml_clubs_v17_8_feature_builder.py
#   -> appelle ml_v17_8_feature_adapter.py
#   -> retourne une reponse produit clubs future-compatible Archives
#   -> reste separe de experimental_ml_v17_8.py, du moteur national et des Archives actuelles