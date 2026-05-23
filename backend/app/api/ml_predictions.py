# Rôle du fichier :
# Cette route expose la baseline ML 1X2 expérimentale sans remplacer le scoring explicable V1.

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ml_1x2_prediction_service import predict_1x2_result
from app.services.ml_feature_service import get_ml_1x2_features_by_id


router = APIRouter(prefix="/api/ml", tags=["Experimental ML"])


# Ce modèle décrit les 6 features attendues par la baseline ML 1X2.
class ML1X2PredictionRequest(BaseModel):
    home_form_points_last_5: float
    away_form_points_last_5: float
    home_goals_scored_avg_last_5: float
    away_goals_scored_avg_last_5: float
    home_goals_conceded_avg_last_5: float
    away_goals_conceded_avg_last_5: float


# Transforme la requête API en dictionnaire de features utilisable par le service ML.
def build_features_from_request(request: ML1X2PredictionRequest) -> dict[str, float]:
    return request.model_dump()


# Expose une prédiction ML 1X2 expérimentale à partir de features envoyées manuellement.
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


# Expose une prédiction ML 1X2 expérimentale à partir d'une ligne ml.features stockée en base.
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


# Schéma de communication :
# ml_predictions.py
#   -> reçoit soit 6 features numériques depuis une requête POST
#   -> soit récupère une ligne ml.features depuis PostgreSQL
#   -> appelle ml_feature_service.py si la prédiction part de la base
#   -> appelle ml_1x2_prediction_service.py pour charger le modèle ML
#   -> retourne une prédiction expérimentale 1X2
#   -> est enregistré dans app/main.py