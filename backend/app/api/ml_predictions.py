# Role du fichier :
# Cette route expose la baseline ML 1X2 experimentale sans remplacer le scoring explicable V1.

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ml_1x2_prediction_service import predict_1x2_result
from app.services.ml_feature_service import (
    get_ml_1x2_features_by_clean_match_id,
    get_ml_1x2_features_by_clean_match_ids,
    get_ml_1x2_features_by_id,
)


router = APIRouter(prefix="/api/ml", tags=["Experimental ML"])


ML_1X2_MODEL_NAME = "LogisticRegression_balanced"
ML_1X2_MODEL_ARTIFACT = "models/ml/1x2/best_1x2_model.joblib"
ML_1X2_EXPECTED_FEATURES = [
    "home_form_points_last_5",
    "away_form_points_last_5",
    "home_goals_scored_avg_last_5",
    "away_goals_scored_avg_last_5",
    "home_goals_conceded_avg_last_5",
    "away_goals_conceded_avg_last_5",
]


# Ce modele decrit les 6 features attendues par la baseline ML 1X2.
class ML1X2PredictionRequest(BaseModel):
    home_form_points_last_5: float
    away_form_points_last_5: float
    home_goals_scored_avg_last_5: float
    away_goals_scored_avg_last_5: float
    home_goals_conceded_avg_last_5: float
    away_goals_conceded_avg_last_5: float


# Ce modele decrit une requete batch basee sur plusieurs clean_match_id.
class ML1X2BatchCleanMatchRequest(BaseModel):
    clean_match_ids: list[int]


# Transforme la requete API en dictionnaire de features utilisable par le service ML.
def build_features_from_request(request: ML1X2PredictionRequest) -> dict[str, float]:
    return request.model_dump()


# Expose le statut technique de la baseline ML 1X2 experimentale.
@router.get("/1x2/status")
async def get_ml_1x2_status() -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[3]
    model_path = project_root / ML_1X2_MODEL_ARTIFACT

    return {
        "source": "rubybets_ml_baseline",
        "scope": "experimental",
        "status": "available" if model_path.exists() else "missing_model_artifact",
        "model_name": ML_1X2_MODEL_NAME,
        "target": "1X2",
        "model_artifact": ML_1X2_MODEL_ARTIFACT,
        "features_expected": ML_1X2_EXPECTED_FEATURES,
        "message": "Experimental ML baseline status. This endpoint does not replace the explainable V1 scoring engine.",
        "responsible_note": "Baseline ML experimentale. Ne remplace pas le scoring explicable V1 et ne garantit aucun resultat sportif.",
    }


# Expose une prediction ML 1X2 experimentale a partir de features envoyees manuellement.
@router.post("/1x2/predict")
async def predict_1x2_from_features(
    request: ML1X2PredictionRequest,
) -> dict[str, Any]:
    prediction_result = predict_1x2_result(
        build_features_from_request(request)
    )

    return {
        "source": "rubybets_ml_baseline",
        "scope": "experimental",
        "message": "Experimental ML baseline. This endpoint does not replace the explainable V1 scoring engine.",
        "result": prediction_result,
    }


# Expose une prediction ML 1X2 experimentale a partir d'une ligne ml.features stockee en base.
@router.post("/1x2/predict/from-feature/{feature_id}")
async def predict_1x2_from_database_feature(feature_id: int) -> dict[str, Any]:
    try:
        feature_source = get_ml_1x2_features_by_id(feature_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    prediction_result = predict_1x2_result(feature_source["features"])

    return {
        "source": "rubybets_ml_baseline",
        "scope": "experimental",
        "message": "Experimental ML baseline from database features. This endpoint does not replace the explainable V1 scoring engine.",
        "feature_source": feature_source,
        "result": prediction_result,
    }


# Expose une prediction ML 1X2 experimentale a partir du clean_match_id d'un match nettoye.
@router.post("/1x2/predict/from-clean-match/{clean_match_id}")
async def predict_1x2_from_clean_match(clean_match_id: int) -> dict[str, Any]:
    try:
        feature_source = get_ml_1x2_features_by_clean_match_id(clean_match_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    prediction_result = predict_1x2_result(feature_source["features"])

    return {
        "source": "rubybets_ml_baseline",
        "scope": "experimental",
        "message": "Experimental ML baseline from clean match features. This endpoint does not replace the explainable V1 scoring engine.",
        "feature_source": feature_source,
        "result": prediction_result,
    }


# Expose plusieurs predictions ML 1X2 experimentales a partir de plusieurs clean_match_id.
@router.post("/1x2/predict/batch/from-clean-matches")
async def predict_1x2_batch_from_clean_matches(
    request: ML1X2BatchCleanMatchRequest,
) -> dict[str, Any]:
    try:
        feature_sources = get_ml_1x2_features_by_clean_match_ids(
            request.clean_match_ids
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    predictions = [
        {
            "feature_source": feature_source,
            "result": predict_1x2_result(feature_source["features"]),
        }
        for feature_source in feature_sources
    ]

    return {
        "source": "rubybets_ml_baseline",
        "scope": "experimental",
        "message": "Experimental ML baseline batch from clean match features. This endpoint does not replace the explainable V1 scoring engine.",
        "requested_count": len(request.clean_match_ids),
        "returned_count": len(predictions),
        "predictions": predictions,
    }


# Schema de communication :
# ml_predictions.py
#   -> expose le statut technique du modele ML 1X2 experimental
#   -> recoit soit 6 features numeriques depuis une requete POST
#   -> soit recupere une ligne ml.features depuis PostgreSQL par feature_id
#   -> soit recupere une ligne ml.features depuis PostgreSQL par clean_match_id
#   -> soit recupere plusieurs lignes ml.features depuis PostgreSQL par liste de clean_match_id
#   -> appelle ml_feature_service.py si la prediction part de la base
#   -> appelle ml_1x2_prediction_service.py pour charger le modele ML
#   -> retourne une ou plusieurs predictions experimentales 1X2
#   -> est enregistre dans app/main.py