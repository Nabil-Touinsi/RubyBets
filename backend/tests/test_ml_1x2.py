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

# Vérifie que la route API peut produire une prédiction depuis un clean_match_id simulé.
def test_experimental_ml_1x2_api_from_clean_match_returns_valid_prediction(
    monkeypatch,
):
    def fake_get_ml_1x2_features_by_clean_match_id(clean_match_id: int) -> dict:
        assert clean_match_id == 10086
        return build_sample_database_feature_source()

    monkeypatch.setattr(
        ml_predictions,
        "get_ml_1x2_features_by_clean_match_id",
        fake_get_ml_1x2_features_by_clean_match_id,
    )

    response = client.post("/api/ml/1x2/predict/from-clean-match/10086")
    data = response.json()

    assert response.status_code == 200

    assert data["source"] == "rubybets_ml_baseline"
    assert data["scope"] == "experimental"
    assert "from clean match features" in data["message"]
    assert "does not replace the explainable V1 scoring engine" in data["message"]

    feature_source = data["feature_source"]

    assert feature_source["feature_id"] == 20
    assert feature_source["clean_match_id"] == 10086
    assert feature_source["target_result"] == "HOME_WIN"

    result = data["result"]

    assert result["status"] == "experimental_ml_baseline"
    assert result["model_name"] == "LogisticRegression_balanced"
    assert result["target"] == "1X2"
    assert result["predicted_class"] in ["HOME_WIN", "DRAW", "AWAY_WIN"]
    assert set(result["probabilities"].keys()) == {"HOME_WIN", "DRAW", "AWAY_WIN"}

    assert "model_path" not in result
    assert "C:\\dev_classe" not in str(result)
    assert "ne garantit aucun resultat sportif" in result["responsible_note"]


# Vérifie que la route API retourne une erreur 404 si le clean_match_id demandé n'existe pas.
def test_experimental_ml_1x2_api_from_clean_match_returns_404_when_missing(
    monkeypatch,
):
    def fake_get_ml_1x2_features_by_clean_match_id(clean_match_id: int) -> dict:
        raise LookupError(
            f"Aucune ligne ml.features trouvee pour clean_match_id={clean_match_id}"
        )

    monkeypatch.setattr(
        ml_predictions,
        "get_ml_1x2_features_by_clean_match_id",
        fake_get_ml_1x2_features_by_clean_match_id,
    )

    response = client.post("/api/ml/1x2/predict/from-clean-match/999999")
    data = response.json()

    assert response.status_code == 404
    assert "Aucune ligne ml.features trouvee pour clean_match_id=999999" in data["detail"]

    # Vérifie que la route API batch peut produire plusieurs prédictions depuis plusieurs clean_match_id simulés.
def test_experimental_ml_1x2_batch_api_from_clean_matches_returns_valid_predictions(
    monkeypatch,
):
    def fake_get_ml_1x2_features_by_clean_match_ids(clean_match_ids: list[int]) -> list[dict]:
        assert clean_match_ids == [10086, 10087]

        first_feature_source = build_sample_database_feature_source()

        second_feature_source = {
            "feature_id": 21,
            "clean_match_id": 10087,
            "target_result": "DRAW",
            "features": build_sample_1x2_features(),
        }

        return [first_feature_source, second_feature_source]

    monkeypatch.setattr(
        ml_predictions,
        "get_ml_1x2_features_by_clean_match_ids",
        fake_get_ml_1x2_features_by_clean_match_ids,
    )

    response = client.post(
        "/api/ml/1x2/predict/batch/from-clean-matches",
        json={"clean_match_ids": [10086, 10087]},
    )
    data = response.json()

    assert response.status_code == 200

    assert data["source"] == "rubybets_ml_baseline"
    assert data["scope"] == "experimental"
    assert "batch from clean match features" in data["message"]
    assert "does not replace the explainable V1 scoring engine" in data["message"]

    assert data["requested_count"] == 2
    assert data["returned_count"] == 2
    assert len(data["predictions"]) == 2

    for prediction in data["predictions"]:
        feature_source = prediction["feature_source"]
        result = prediction["result"]

        assert feature_source["clean_match_id"] in [10086, 10087]
        assert feature_source["target_result"] in ["HOME_WIN", "DRAW", "AWAY_WIN"]

        assert result["status"] == "experimental_ml_baseline"
        assert result["model_name"] == "LogisticRegression_balanced"
        assert result["target"] == "1X2"
        assert result["predicted_class"] in ["HOME_WIN", "DRAW", "AWAY_WIN"]
        assert set(result["probabilities"].keys()) == {"HOME_WIN", "DRAW", "AWAY_WIN"}

        assert "model_path" not in result
        assert "C:\\dev_classe" not in str(result)
        assert "ne garantit aucun resultat sportif" in result["responsible_note"]


# Vérifie que la route API batch retourne 400 si la liste clean_match_ids est vide.
def test_experimental_ml_1x2_batch_api_from_clean_matches_returns_400_when_empty():
    response = client.post(
        "/api/ml/1x2/predict/batch/from-clean-matches",
        json={"clean_match_ids": []},
    )
    data = response.json()

    assert response.status_code == 400
    assert "clean_match_ids ne doit pas etre vide" in data["detail"]


# Vérifie que la route API batch retourne 404 si au moins un clean_match_id est introuvable.
def test_experimental_ml_1x2_batch_api_from_clean_matches_returns_404_when_missing(
    monkeypatch,
):
    def fake_get_ml_1x2_features_by_clean_match_ids(clean_match_ids: list[int]) -> list[dict]:
        raise LookupError(
            f"Aucune ligne ml.features trouvee pour clean_match_id(s)={clean_match_ids}"
        )

    monkeypatch.setattr(
        ml_predictions,
        "get_ml_1x2_features_by_clean_match_ids",
        fake_get_ml_1x2_features_by_clean_match_ids,
    )

    response = client.post(
        "/api/ml/1x2/predict/batch/from-clean-matches",
        json={"clean_match_ids": [999999]},
    )
    data = response.json()

    assert response.status_code == 404
    assert "Aucune ligne ml.features trouvee pour clean_match_id(s)=[999999]" in data["detail"]

# Vérifie que la route de statut ML 1X2 expose correctement la disponibilité du modèle expérimental.
def test_experimental_ml_1x2_status_api_returns_model_status():
    response = client.get("/api/ml/1x2/status")
    data = response.json()

    assert response.status_code == 200

    assert data["source"] == "rubybets_ml_baseline"
    assert data["scope"] == "experimental"
    assert data["status"] == "available"
    assert data["model_name"] == "LogisticRegression_balanced"
    assert data["target"] == "1X2"

    assert data["model_artifact"] == "models/ml/1x2/best_1x2_model.joblib"

    assert data["features_expected"] == [
        "home_form_points_last_5",
        "away_form_points_last_5",
        "home_goals_scored_avg_last_5",
        "away_goals_scored_avg_last_5",
        "home_goals_conceded_avg_last_5",
        "away_goals_conceded_avg_last_5",
    ]

    assert "does not replace the explainable V1 scoring engine" in data["message"]
    assert "ne garantit aucun resultat sportif" in data["responsible_note"]

    assert "C:\\dev_classe" not in str(data)
    assert "model_path" not in data
# Schéma de communication :
# test_ml_1x2.py
#   -> teste app/services/ml_1x2_prediction_service.py
#   -> teste app/api/ml_predictions.py via POST /api/ml/1x2/predict
#   -> teste app/api/ml_predictions.py via POST /api/ml/1x2/predict/from-feature/{feature_id}
#   -> simule ml_feature_service.py pour éviter une dépendance directe à PostgreSQL dans pytest
#   -> passe par app/main.py
#   -> charge models/ml/1x2/best_1x2_model.joblib