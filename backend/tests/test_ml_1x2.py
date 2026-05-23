# Rôle du fichier :
# Ces tests vérifient la baseline ML 1X2 au niveau service interne et au niveau route API expérimentale.

from fastapi.testclient import TestClient

from app.main import app
from app.services.ml_1x2_prediction_service import predict_1x2_result


client = TestClient(app)


# Fournit un jeu de features stable pour tester la baseline ML 1X2.
def build_sample_1x2_features() -> dict[str, float]:
    return {
        "home_form_points_last_5": 10.0,
        "away_form_points_last_5": 6.0,
        "home_goals_scored_avg_last_5": 1.8,
        "away_goals_scored_avg_last_5": 1.2,
        "home_goals_conceded_avg_last_5": 0.8,
        "away_goals_conceded_avg_last_5": 1.4,
    }


# Vérifie que le service ML interne charge le modèle et retourne une prédiction 1X2 exploitable.
def test_ml_1x2_service_returns_valid_prediction():
    result = predict_1x2_result(build_sample_1x2_features())

    assert result["status"] == "experimental_ml_baseline"
    assert result["model_name"] == "LogisticRegression_balanced"
    assert result["target"] == "1X2"
    assert result["predicted_class"] in ["HOME_WIN", "DRAW", "AWAY_WIN"]

    assert set(result["probabilities"].keys()) == {"HOME_WIN", "DRAW", "AWAY_WIN"}
    assert result["model_artifact"] == "models/ml/1x2/best_1x2_model.joblib"

    assert "model_path" not in result
    assert "C:\\dev_classe" not in str(result)
    assert "ne garantit aucun resultat sportif" in result["responsible_note"]


# Vérifie que la route API expérimentale expose correctement la baseline ML 1X2.
def test_experimental_ml_1x2_api_returns_valid_prediction():
    response = client.post(
        "/api/ml/1x2/predict",
        json=build_sample_1x2_features(),
    )

    data = response.json()

    assert response.status_code == 200

    assert data["source"] == "rubybets_ml_baseline"
    assert data["scope"] == "experimental"
    assert "does not replace the explainable V1 scoring engine" in data["message"]

    result = data["result"]

    assert result["status"] == "experimental_ml_baseline"
    assert result["model_name"] == "LogisticRegression_balanced"
    assert result["target"] == "1X2"
    assert result["predicted_class"] in ["HOME_WIN", "DRAW", "AWAY_WIN"]

    assert set(result["probabilities"].keys()) == {"HOME_WIN", "DRAW", "AWAY_WIN"}
    assert result["model_artifact"] == "models/ml/1x2/best_1x2_model.joblib"

    assert "model_path" not in result
    assert "C:\\dev_classe" not in str(result)
    assert "ne garantit aucun resultat sportif" in result["responsible_note"]


# Schéma de communication :
# test_ml_1x2.py
#   -> teste app/services/ml_1x2_prediction_service.py
#   -> teste app/api/ml_predictions.py via POST /api/ml/1x2/predict
#   -> passe par app/main.py
#   -> charge models/ml/1x2/best_1x2_model.joblib