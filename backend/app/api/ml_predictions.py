# Rôle du fichier :
# Cette route expose la baseline ML 1X2 expérimentale sans remplacer le scoring explicable V1.

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ml_1x2_prediction_service import predict_1x2_result


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


# Schéma de communication :
# ml_predictions.py
#   -> reçoit 6 features numériques depuis une requête POST
#   -> appelle ml_1x2_prediction_service.py
#   -> charge models/ml/1x2/best_1x2_model.joblib
#   -> retourne une prédiction expérimentale 1X2
#   -> est enregistré dans app/main.py