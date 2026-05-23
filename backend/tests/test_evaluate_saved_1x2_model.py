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