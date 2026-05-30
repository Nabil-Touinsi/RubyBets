# Role du fichier :
# Cette route expose le selecteur national V18.3.3 strict reliability en API experimentale.
# Elle sert a tester le service backend sans l'integrer au frontend ni remplacer le scoring V1.

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ml_national_v18_3_3_selector import (
    SELECTOR_PROFILE,
    SELECTOR_VARIANT,
    SELECTOR_VERSION,
    select_market_with_v18_3_3,
)


router = APIRouter(
    prefix="/api/experimental/ml-national/v18-3-3",
    tags=["Experimental ML National V18.3.3"],
)


# Ce modele decrit les signaux multi-marches attendus par le selecteur V18.3.3.
class V1833SelectorRequest(BaseModel):
    one_x_two_prediction: str | None = None
    one_x_two_max_probability: float | None = None
    one_x_two_prob_team_a_win: float | None = None
    one_x_two_prob_draw: float | None = None
    one_x_two_prob_team_b_win: float | None = None
    over_1_5_prediction: str | None = None
    over_1_5_prob_yes: float | None = None
    over_2_5_prediction: str | None = None
    over_2_5_max_probability: float | None = None
    btts_prediction: str | None = None
    btts_prob_no: float | None = None


# Transforme le format API lisible en format interne attendu par le service.
def build_selector_features_from_request(
    request: V1833SelectorRequest,
) -> dict[str, Any]:
    return {
        "1x2_prediction": request.one_x_two_prediction,
        "1x2_max_probability": request.one_x_two_max_probability,
        "1x2_prob_TEAM_A_WIN": request.one_x_two_prob_team_a_win,
        "1x2_prob_DRAW": request.one_x_two_prob_draw,
        "1x2_prob_TEAM_B_WIN": request.one_x_two_prob_team_b_win,
        "over_1_5_prediction": request.over_1_5_prediction,
        "over_1_5_prob_YES": request.over_1_5_prob_yes,
        "over_2_5_prediction": request.over_2_5_prediction,
        "over_2_5_max_probability": request.over_2_5_max_probability,
        "btts_prediction": request.btts_prediction,
        "btts_prob_NO": request.btts_prob_no,
    }


# Construit un exemple controle pour verifier rapidement le fonctionnement de l'API.
def build_v18_3_3_demo_features() -> dict[str, Any]:
    return {
        "1x2_prediction": "TEAM_A_WIN",
        "1x2_max_probability": 0.81,
        "1x2_prob_TEAM_A_WIN": 0.81,
        "1x2_prob_DRAW": 0.11,
        "1x2_prob_TEAM_B_WIN": 0.08,
        "over_1_5_prediction": "YES",
        "over_1_5_prob_YES": 0.79,
        "over_2_5_prediction": "OVER",
        "over_2_5_max_probability": 0.71,
        "btts_prediction": "NO",
        "btts_prob_NO": 0.76,
    }


# Expose le statut technique du profil V18.3.3 strict reliability.
@router.get("/status")
async def get_v18_3_3_selector_status() -> dict[str, Any]:
    return {
        "source": "rubybets_ml_national_v18_3_3_api",
        "scope": "experimental_backend",
        "status": "available",
        "selector_version": SELECTOR_VERSION,
        "selector_profile": SELECTOR_PROFILE,
        "selector_variant": SELECTOR_VARIANT,
        "message": (
            "Selecteur national V18.3.3 strict reliability disponible en API "
            "experimentale. Non integre au frontend."
        ),
        "responsible_note": (
            "Profil analytique experimental sans garantie de resultat sportif."
        ),
    }


# Expose une demonstration controlee du selecteur V18.3.3.
@router.get("/demo")
async def get_v18_3_3_selector_demo() -> dict[str, Any]:
    demo_features = build_v18_3_3_demo_features()
    result = select_market_with_v18_3_3(demo_features)

    return {
        "source": "rubybets_ml_national_v18_3_3_api",
        "scope": "experimental_backend",
        "status": "demo_only",
        "demo_features_profile": "controlled_strict_1x2_case",
        "result": result,
    }


# Applique le selecteur V18.3.3 a des features envoyees manuellement.
@router.post("/select")
async def select_with_v18_3_3(
    request: V1833SelectorRequest,
) -> dict[str, Any]:
    features = build_selector_features_from_request(request)
    result = select_market_with_v18_3_3(features)

    return {
        "source": "rubybets_ml_national_v18_3_3_api",
        "scope": "experimental_backend",
        "status": "computed",
        "result": result,
    }


# Schema de communication :
# experimental_ml_national_v18_3_3.py
#   -> recoit des features multi-marches via /select ou construit une demo via /demo
#   -> appelle backend/app/services/ml_national_v18_3_3_selector.py
#   -> retourne une recommandation experimentale ou une abstention
#   -> reste separe du frontend et des routes officielles tant que l'inference n'est pas stabilisee
