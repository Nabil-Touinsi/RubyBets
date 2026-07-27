# Ce fichier regroupe les tests backend du domaine ml 1x2.
# Les sections sources restent identifiables pour préserver la traçabilité et faciliter la maintenance.


# ============================================================================
# Section issue de : backend/tests/test_ml_1x2.py
# ============================================================================

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

# ============================================================================
# Section issue de : backend/tests/test_evaluate_saved_1x2_model.py
# ============================================================================

# Rôle du fichier : tester le script d’évaluation reproductible du modèle ML 1X2 sauvegardé sans interroger PostgreSQL.

from pathlib import Path
import importlib.util

import pandas as pd


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "ml"
    / "evaluate_saved_1x2_model.py"
)


# Charge le script d’évaluation comme module Python pour tester ses fonctions.
def load_evaluation_module():
    spec = importlib.util.spec_from_file_location(
        "evaluate_saved_1x2_model",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


# Vérifie que la liste officielle des features ML reste stable.
def test_feature_columns_are_the_expected_baseline_features():
    module = load_evaluation_module()

    assert module.FEATURE_COLUMNS == [
        "home_form_points_last_5",
        "away_form_points_last_5",
        "home_goals_scored_avg_last_5",
        "away_goals_scored_avg_last_5",
        "home_goals_conceded_avg_last_5",
        "away_goals_conceded_avg_last_5",
    ]


# Vérifie que le nettoyage supprime les lignes avec features manquantes.
def test_prepare_dataset_removes_rows_with_missing_features():
    module = load_evaluation_module()

    dataset = pd.DataFrame(
        [
            {
                "home_form_points_last_5": 10,
                "away_form_points_last_5": 7,
                "home_goals_scored_avg_last_5": 2.0,
                "away_goals_scored_avg_last_5": 1.2,
                "home_goals_conceded_avg_last_5": 0.8,
                "away_goals_conceded_avg_last_5": 1.5,
                "target_result": "HOME_WIN",
                "season": "2024_2025",
            },
            {
                "home_form_points_last_5": None,
                "away_form_points_last_5": 6,
                "home_goals_scored_avg_last_5": 1.4,
                "away_goals_scored_avg_last_5": 1.1,
                "home_goals_conceded_avg_last_5": 1.0,
                "away_goals_conceded_avg_last_5": 1.3,
                "target_result": "DRAW",
                "season": "2024_2025",
            },
        ]
    )

    prepared_dataset, rows_removed = module.prepare_dataset(dataset)

    assert rows_removed == 1
    assert len(prepared_dataset) == 1
    assert prepared_dataset.iloc[0]["target_result"] == "HOME_WIN"


# Vérifie que seules les saisons de test officielles sont conservées.
def test_filter_test_dataset_keeps_only_expected_test_seasons():
    module = load_evaluation_module()

    dataset = pd.DataFrame(
        [
            {"season": "2021_2022", "target_result": "HOME_WIN"},
            {"season": "2022_2023", "target_result": "DRAW"},
            {"season": "2023_2024", "target_result": "AWAY_WIN"},
            {"season": "2024_2025", "target_result": "HOME_WIN"},
        ]
    )

    test_dataset = module.filter_test_dataset(dataset)

    assert list(test_dataset["season"]) == [
        "2022_2023",
        "2023_2024",
        "2024_2025",
    ]


# Vérifie que les chemins du modèle et de la preuve restent cohérents.
def test_model_and_report_paths_are_expected():
    module = load_evaluation_module()

    assert str(module.MODEL_PATH).endswith(
        "models\\ml\\1x2\\best_1x2_model.joblib"
    ) or str(module.MODEL_PATH).endswith(
        "models/ml/1x2/best_1x2_model.joblib"
    )

    assert str(module.REPORT_PATH).endswith(
        "reports\\evidence\\ml_training\\28_saved_1x2_model_evaluation.txt"
    ) or str(module.REPORT_PATH).endswith(
        "reports/evidence/ml_training/28_saved_1x2_model_evaluation.txt"
    )


# Vérifie que le rapport généré contient les informations attendues pour la preuve.
def test_build_evaluation_report_contains_key_sections():
    module = load_evaluation_module()

    dataset = pd.DataFrame(
        [
            {
                "league_code": "E0",
                "season": "2024_2025",
                "target_result": "HOME_WIN",
            }
        ]
    )
    prepared_dataset = dataset.copy()
    test_dataset = dataset.copy()

    evaluation = {
        "accuracy": 0.4669,
        "f1_macro": 0.4266,
        "f1_weighted": 0.4525,
        "confusion_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "classification_report": "classification report content",
    }

    report = module.build_evaluation_report(
        dataset=dataset,
        prepared_dataset=prepared_dataset,
        rows_removed=0,
        test_dataset=test_dataset,
        evaluation=evaluation,
    )

    assert "RubyBets - Saved ML 1X2 model evaluation" in report
    assert "Cette évaluation concerne la baseline ML 1X2 expérimentale." in report
    assert "Accuracy: 0.4669" in report
    assert "F1 macro: 0.4266" in report
    assert "F1 weighted: 0.4525" in report
    assert "Classification report:" in report

# Schéma de communication du fichier :
# backend/tests/test_ml_1x2.py
#   ├── importe les routes, services et contrats du domaine testé
#   ├── utilise les fixtures partagées de backend/tests/conftest.py
#   └── est collecté par pytest dans la suite backend complète
