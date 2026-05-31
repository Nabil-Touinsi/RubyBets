# Role du fichier :
# Cette route expose le selecteur national V18.3.3 strict reliability en API experimentale.
# Elle sert a tester le service backend sans l'integrer au frontend ni remplacer le scoring V1.

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.cache_service import build_cache_name, get_cached_football_data
from app.services.ml_national_v18_3_3_dynamic_inference_service import (
    get_match_last_updated,
    infer_v18_3_3_for_rubybets_match,
)
from app.services.ml_national_v18_3_3_inference_adapter import (
    select_v18_3_3_from_prediction_row,
)
from app.services.ml_national_v18_3_3_selector import (
    SELECTOR_PROFILE,
    SELECTOR_VARIANT,
    SELECTOR_VERSION,
    select_market_with_v18_3_3,
)


V18_3_TEST_PREDICTIONS_RELATIVE_PATH = Path(
    "reports/evidence/ml_training/348_v18_3_global_multimarket_test_predictions.csv"
)

MATCH_DETAIL_CACHE_TTL_MINUTES = 30

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


# Retourne les emplacements possibles du projet selon le dossier de lancement du backend.
def get_project_root_candidates() -> list[Path]:
    api_file_path = Path(__file__).resolve()

    candidates = [
        api_file_path.parents[3],
        Path.cwd(),
        Path.cwd().parent,
    ]

    unique_candidates: list[Path] = []
    for candidate in candidates:
        resolved_candidate = candidate.resolve()
        if resolved_candidate not in unique_candidates:
            unique_candidates.append(resolved_candidate)

    return unique_candidates


# Retrouve le fichier CSV 348 qui contient les predictions V18.3 globales de test.
def get_v18_3_predictions_csv_path() -> Path:
    for project_root in get_project_root_candidates():
        csv_path = project_root / V18_3_TEST_PREDICTIONS_RELATIVE_PATH
        if csv_path.exists():
            return csv_path

    return get_project_root_candidates()[0] / V18_3_TEST_PREDICTIONS_RELATIVE_PATH


# Charge la ligne CSV correspondant au clean_match_id demande.
def load_v18_3_prediction_row_by_clean_match_id(
    clean_match_id: str,
) -> dict[str, Any] | None:
    csv_path = get_v18_3_predictions_csv_path()

    if not csv_path.exists():
        raise HTTPException(
            status_code=503,
            detail={
                "status": "CSV_UNAVAILABLE",
                "message": (
                    "Le fichier de predictions V18.3 globales est introuvable. "
                    "La route experimentale ne peut pas calculer V18.3.3."
                ),
                "expected_file": str(V18_3_TEST_PREDICTIONS_RELATIVE_PATH),
            },
        )

    requested_id = str(clean_match_id).strip()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            row_match_id = str(row.get("clean_match_id", "")).strip()
            if row_match_id == requested_id:
                return row

    return None


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


# Applique le selecteur V18.3.3 a un match reel du CSV 348.
@router.get("/matches/{clean_match_id}")
async def get_v18_3_3_prediction_by_clean_match_id(
    clean_match_id: str,
) -> dict[str, Any]:
    prediction_row = load_v18_3_prediction_row_by_clean_match_id(clean_match_id)

    if prediction_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "MATCH_NOT_FOUND",
                "message": (
                    "Aucune ligne V18.3 globale ne correspond au clean_match_id fourni."
                ),
                "clean_match_id": clean_match_id,
                "data_source_file": V18_3_TEST_PREDICTIONS_RELATIVE_PATH.name,
            },
        )

    adapter_response = select_v18_3_3_from_prediction_row(prediction_row)

    if adapter_response.get("status") != "computed":
        raise HTTPException(
            status_code=422,
            detail={
                "status": "INVALID_PREDICTION_ROW",
                "message": (
                    "La ligne V18.3 existe, mais elle est incomplete ou incompatible "
                    "avec le selecteur V18.3.3."
                ),
                "clean_match_id": clean_match_id,
                "adapter_response": adapter_response,
            },
        )

    return {
        "source": "rubybets_ml_national_v18_3_3_api",
        "scope": "experimental_backend",
        "status": "computed",
        "data_source_file": V18_3_TEST_PREDICTIONS_RELATIVE_PATH.name,
        "match": adapter_response["match"],
        "selector_result": adapter_response["selector_result"],
        "responsible_note": (
            "Resultat experimental de laboratoire ML. Ne remplace pas les predictions "
            "officielles RubyBets et ne garantit aucun resultat sportif."
        ),
    }


# Applique V18.3.3 dynamiquement au match RubyBets selectionne dans le frontend.
@router.get("/rubybets-matches/{match_id}")
async def get_v18_3_3_dynamic_prediction_by_rubybets_match_id(
    match_id: int,
) -> dict[str, Any]:
    data, data_freshness = await get_cached_football_data(
        cache_name=build_cache_name("match", match_id),
        endpoint=f"/matches/{match_id}",
        ttl_minutes=MATCH_DETAIL_CACHE_TTL_MINUTES,
    )
    match = data.get("match", data)
    inference_response = infer_v18_3_3_for_rubybets_match(match)

    return {
        **inference_response,
        "rubybets_match_id": match_id,
        "data_freshness": {
            "match_cache": data_freshness,
            "match_last_updated": get_match_last_updated(match),
        },
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
#   -> expose /status, /demo, /select, /matches/{clean_match_id} et /rubybets-matches/{match_id}
#   -> lit le CSV reports/evidence/ml_training/348_v18_3_global_multimarket_test_predictions.csv
#   -> appelle backend/app/services/ml_national_v18_3_3_inference_adapter.py pour les tests CSV
#   -> appelle backend/app/services/ml_national_v18_3_3_dynamic_inference_service.py pour le match frontend
#   -> appelle indirectement backend/app/services/ml_national_v18_3_3_selector.py
#   -> retourne match + selector_result pour un lab experimental sans toucher aux routes officielles