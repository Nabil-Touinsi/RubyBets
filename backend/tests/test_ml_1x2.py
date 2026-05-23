# Rôle du fichier :
# Ces tests vérifient la baseline ML 1X2 au niveau service interne et au niveau route API expérimentale.

from fastapi.testclient import TestClient

from app.api import ml_predictions
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


# Fournit une ligne simulée issue de ml.features pour tester la route API sans dépendre de PostgreSQL.
def build_sample_database_feature_source() -> dict:
    return {
        "feature_id": 20,
        "clean_match_id": 10086,
        "target_result": "HOME_WIN",
        "features": build_sample_1x2_features(),
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


# Vérifie que la route API expérimentale expose correctement la baseline ML 1X2 avec features manuelles.
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


# Vérifie que la route API peut produire une prédiction depuis une ligne ml.features simulée.
def test_experimental_ml_1x2_api_from_database_feature_returns_valid_prediction(
    monkeypatch,
):
    def fake_get_ml_1x2_features_by_id(feature_id: int) -> dict:
        assert feature_id == 20
        return build_sample_database_feature_source()

    monkeypatch.setattr(
        ml_predictions,
        "get_ml_1x2_features_by_id",
        fake_get_ml_1x2_features_by_id,
    )

    response = client.post("/api/ml/1x2/predict/from-feature/20")
    data = response.json()

    assert response.status_code == 200

    assert data["source"] == "rubybets_ml_baseline"
    assert data["scope"] == "experimental"
    assert "from database features" in data["message"]
    assert "does not replace the explainable V1 scoring engine" in data["message"]

    feature_source = data["feature_source"]

    assert feature_source["feature_id"] == 20
    assert feature_source["clean_match_id"] == 10086
    assert feature_source["target_result"] == "HOME_WIN"
    assert set(feature_source["features"].keys()) == set(build_sample_1x2_features().keys())

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


# Vérifie que la route API retourne une erreur 404 si la ligne ml.features demandée n'existe pas.
def test_experimental_ml_1x2_api_from_database_feature_returns_404_when_missing(
    monkeypatch,
):
    def fake_get_ml_1x2_features_by_id(feature_id: int) -> dict:
        raise LookupError(f"Aucune ligne ml.features trouvee pour id={feature_id}")

    monkeypatch.setattr(
        ml_predictions,
        "get_ml_1x2_features_by_id",
        fake_get_ml_1x2_features_by_id,
    )

    response = client.post("/api/ml/1x2/predict/from-feature/999999")
    data = response.json()

    assert response.status_code == 404
    assert "Aucune ligne ml.features trouvee pour id=999999" in data["detail"]


# Schéma de communication :
# test_ml_1x2.py
#   -> teste app/services/ml_1x2_prediction_service.py
#   -> teste app/api/ml_predictions.py via POST /api/ml/1x2/predict
#   -> teste app/api/ml_predictions.py via POST /api/ml/1x2/predict/from-feature/{feature_id}
#   -> simule ml_feature_service.py pour éviter une dépendance directe à PostgreSQL dans pytest
#   -> passe par app/main.py
#   -> charge models/ml/1x2/best_1x2_model.joblib