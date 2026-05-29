# Rôle du fichier : analyser les seuils de forte confiance du modèle ML 1X2 avec les features de force d’équipe, sans modifier la base ni remplacer le modèle sauvegardé.

from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "41_1x2_team_strength_high_confidence_thresholds.txt"
CSV_PATH = REPORT_DIR / "42_1x2_team_strength_high_confidence_thresholds.csv"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    OFFICIAL_BASELINE_ACCURACY,
    OFFICIAL_BASELINE_F1_MACRO,
    TARGET_COLUMN,
    TEST_SEASONS,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)
from experiment_team_strength_features_1x2 import (  # noqa: E402
    CLASS_LABELS,
    SELECTED_FEATURE_SETS,
    build_candidate_models,
    build_experiment_dataframe,
    prepare_train_test,
)

warnings.filterwarnings("ignore", category=UserWarning)

MODEL_NAME = "LogisticRegression_balanced"
FEATURE_SETS_TO_ANALYZE = [
    "last10_diff_plus_team_strength",
    "balanced_last10_diff_abs_venue_plus_team_strength",
]

THRESHOLDS = [round(value / 100, 2) for value in range(50, 81)]
PREVIOUS_HIGH_CONFIDENCE_ACCURACY = 0.7076
PREVIOUS_HIGH_CONFIDENCE_COVERAGE = 0.0920
MIN_PRACTICAL_ROWS = 500
MIN_PRACTICAL_COVERAGE = 0.10


# Vérifie que les feature sets demandés existent bien dans le script d’expérimentation précédent.
def validate_feature_sets() -> None:
    missing_feature_sets = [
        feature_set_name
        for feature_set_name in FEATURE_SETS_TO_ANALYZE
        if feature_set_name not in SELECTED_FEATURE_SETS
    ]

    if missing_feature_sets:
        raise RuntimeError(
            "Feature set introuvable dans experiment_team_strength_features_1x2.py : "
            + ", ".join(missing_feature_sets)
        )


# Entraîne LogisticRegression_balanced sur un feature set donné puis retourne les prédictions et probabilités du test.
def train_model_for_feature_set(
    feature_dataframe: pd.DataFrame,
    feature_set_name: str,
) -> tuple[pd.DataFrame, pd.Series, list[str], pd.Series]:
    feature_columns = SELECTED_FEATURE_SETS[feature_set_name]
    x_train, y_train, x_test, y_test, _ = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    candidate_models = build_candidate_models()

    if MODEL_NAME not in candidate_models:
        raise RuntimeError(f"Modele introuvable : {MODEL_NAME}")

    model = clone(candidate_models[MODEL_NAME])
    model.fit(x_train, y_train)

    predictions = list(model.predict(x_test))
    probabilities = model.predict_proba(x_test)
    max_probabilities = pd.Series(probabilities.max(axis=1)).reset_index(drop=True)

    return x_test, y_test.reset_index(drop=True), predictions, max_probabilities


# Calcule la distribution des classes prédites ou réelles sur les lignes sélectionnées.
def calculate_distribution(values: pd.Series) -> dict[str, int]:
    value_counts = values.value_counts().to_dict()

    return {
        "home_win_rows": int(value_counts.get("HOME_WIN", 0)),
        "draw_rows": int(value_counts.get("DRAW", 0)),
        "away_win_rows": int(value_counts.get("AWAY_WIN", 0)),
    }


# Calcule les métriques de forte confiance pour un seuil donné.
def calculate_threshold_metrics(
    feature_set_name: str,
    threshold: float,
    y_test: pd.Series,
    predictions: list[str],
    max_probabilities: pd.Series,
) -> dict:
    predictions_series = pd.Series(predictions).reset_index(drop=True)
    selected_mask = max_probabilities >= threshold
    selected_rows = int(selected_mask.sum())

    base_result = {
        "feature_set": feature_set_name,
        "model": MODEL_NAME,
        "threshold": threshold,
        "test_rows": len(y_test),
        "selected_rows": selected_rows,
        "coverage": round(selected_rows / len(y_test), 4) if len(y_test) else 0.0,
    }

    if selected_rows == 0:
        return {
            **base_result,
            "correct_predictions": 0,
            "accuracy": None,
            "predicted_home_win_rows": 0,
            "predicted_draw_rows": 0,
            "predicted_away_win_rows": 0,
            "actual_home_win_rows": 0,
            "actual_draw_rows": 0,
            "actual_away_win_rows": 0,
            "average_confidence": None,
            "min_confidence": None,
            "max_confidence": None,
        }

    selected_predictions = predictions_series[selected_mask]
    selected_truth = y_test[selected_mask]
    selected_probabilities = max_probabilities[selected_mask]

    predicted_distribution = calculate_distribution(selected_predictions)
    actual_distribution = calculate_distribution(selected_truth)
    correct_predictions = int((selected_predictions.reset_index(drop=True) == selected_truth.reset_index(drop=True)).sum())

    return {
        **base_result,
        "correct_predictions": correct_predictions,
        "accuracy": round(accuracy_score(selected_truth, selected_predictions), 4),
        "predicted_home_win_rows": predicted_distribution["home_win_rows"],
        "predicted_draw_rows": predicted_distribution["draw_rows"],
        "predicted_away_win_rows": predicted_distribution["away_win_rows"],
        "actual_home_win_rows": actual_distribution["home_win_rows"],
        "actual_draw_rows": actual_distribution["draw_rows"],
        "actual_away_win_rows": actual_distribution["away_win_rows"],
        "average_confidence": round(float(selected_probabilities.mean()), 4),
        "min_confidence": round(float(selected_probabilities.min()), 4),
        "max_confidence": round(float(selected_probabilities.max()), 4),
    }


# Analyse tous les seuils retenus pour les feature sets sélectionnés.
def analyze_thresholds(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for feature_set_name in FEATURE_SETS_TO_ANALYZE:
        print(f"Entrainement du modele {MODEL_NAME} sur {feature_set_name}...", flush=True)
        _, y_test, predictions, max_probabilities = train_model_for_feature_set(
            feature_dataframe=feature_dataframe,
            feature_set_name=feature_set_name,
        )

        for threshold in THRESHOLDS:
            rows.append(
                calculate_threshold_metrics(
                    feature_set_name=feature_set_name,
                    threshold=threshold,
                    y_test=y_test,
                    predictions=predictions,
                    max_probabilities=max_probabilities,
                )
            )

    results = pd.DataFrame(rows)

    return results.sort_values(
        by=["feature_set", "threshold"],
        ascending=[True, True],
    )


# Retourne la meilleure ligne selon un filtre et un tri, ou None si aucune ligne n’existe.
def select_best_row(
    results: pd.DataFrame,
    query: str | None,
    sort_columns: list[str],
    ascending: list[bool],
) -> pd.Series | None:
    candidate_results = results.dropna(subset=["accuracy"]).copy()

    if query:
        candidate_results = candidate_results.query(query).copy()

    if candidate_results.empty:
        return None

    return candidate_results.sort_values(by=sort_columns, ascending=ascending).iloc[0]


# Formate une ligne de résultat pour le rapport texte.
def format_row(row: pd.Series | None) -> list[str]:
    if row is None:
        return ["- Aucun seuil ne respecte ce critere."]

    return [
        f"- Feature set : {row['feature_set']}",
        f"- Model : {row['model']}",
        f"- Threshold : {row['threshold']}",
        f"- Selected rows : {int(row['selected_rows'])}",
        f"- Coverage : {row['coverage']}",
        f"- Correct predictions : {int(row['correct_predictions'])}",
        f"- Accuracy : {row['accuracy']}",
        f"- Predicted DRAW rows : {int(row['predicted_draw_rows'])}",
        f"- Actual DRAW rows in selected rows : {int(row['actual_draw_rows'])}",
        f"- Average confidence : {row['average_confidence']}",
    ]


# Construit le rapport texte lisible pour les preuves RNCP.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, results: pd.DataFrame) -> str:
    best_accuracy_row = select_best_row(
        results=results,
        query="selected_rows > 0",
        sort_columns=["accuracy", "coverage"],
        ascending=[False, False],
    )
    best_practical_row = select_best_row(
        results=results,
        query=f"selected_rows >= {MIN_PRACTICAL_ROWS}",
        sort_columns=["accuracy", "coverage"],
        ascending=[False, False],
    )
    best_over_70_row = select_best_row(
        results=results,
        query="accuracy >= 0.70",
        sort_columns=["coverage", "accuracy"],
        ascending=[False, False],
    )
    best_over_70_and_previous_coverage_row = select_best_row(
        results=results,
        query=f"accuracy >= 0.70 and coverage >= {PREVIOUS_HIGH_CONFIDENCE_COVERAGE}",
        sort_columns=["coverage", "accuracy"],
        ascending=[False, False],
    )
    best_practical_coverage_row = select_best_row(
        results=results,
        query=f"accuracy >= 0.70 and coverage >= {MIN_PRACTICAL_COVERAGE}",
        sort_columns=["coverage", "accuracy"],
        ascending=[False, False],
    )

    lines = [
        "RubyBets - ML 1X2 team strength high-confidence thresholds",
        "41 - Analyse des seuils de forte confiance avec force d'equipe avant-match",
        "",
        "Positionnement :",
        "Cette analyse ne remplace pas le scoring explicable V1.",
        "Elle ne modifie pas PostgreSQL, ne remplace pas le modele sauvegarde et ne touche pas au frontend.",
        "Elle sert uniquement a identifier si le signal ML forte confiance devient plus exploitable avec team_strength_rating.",
        "",
        "Modele analyse :",
        f"- {MODEL_NAME}",
        "",
        "Feature sets analyses :",
        *[f"- {feature_set_name}" for feature_set_name in FEATURE_SETS_TO_ANALYZE],
        "",
        "Seuils testes :",
        f"- De {THRESHOLDS[0]} a {THRESHOLDS[-1]} par pas de 0.01",
        "",
        "Baseline officielle actuelle :",
        f"- Accuracy officielle : {OFFICIAL_BASELINE_ACCURACY:.4f}",
        f"- F1 macro officiel : {OFFICIAL_BASELINE_F1_MACRO:.4f}",
        "",
        "Reference forte confiance precedente :",
        f"- Accuracy : {PREVIOUS_HIGH_CONFIDENCE_ACCURACY}",
        f"- Coverage : {PREVIOUS_HIGH_CONFIDENCE_COVERAGE}",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features construites : {len(feature_dataframe)}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Best accuracy, sans filtre pratique :",
        *format_row(best_accuracy_row),
        "",
        f"Best practical threshold avec au moins {MIN_PRACTICAL_ROWS} lignes selectionnees :",
        *format_row(best_practical_row),
        "",
        "Meilleur seuil atteignant au moins 70% d'accuracy, couverture maximale :",
        *format_row(best_over_70_row),
        "",
        "Meilleur seuil atteignant au moins 70% d'accuracy et au moins la couverture precedente de 9.2% :",
        *format_row(best_over_70_and_previous_coverage_row),
        "",
        f"Meilleur seuil atteignant au moins 70% d'accuracy et au moins {MIN_PRACTICAL_COVERAGE:.0%} de couverture :",
        *format_row(best_practical_coverage_row),
        "",
        "Tableau complet :",
        results.to_string(index=False),
        "",
        "Lecture metier :",
        "- Un seuil plus haut augmente generalement la precision mais reduit la couverture.",
        "- Si les predictions DRAW restent absentes en forte confiance, le signal doit etre presente comme limite a HOME_WIN / AWAY_WIN.",
        "- Si 70% n'est atteint qu'avec une couverture faible, le ML reste un signal experimental et non un predicteur general.",
        "- Le scoring explicable V1 reste le socle produit tant qu'une V2 ML n'est pas validee globalement.",
        "",
        "Generated files:",
        str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
        str(CSV_PATH.relative_to(PROJECT_ROOT)),
        "",
    ]

    return "\n".join(lines)


# Sauvegarde les rapports CSV et TXT de l’analyse des seuils.
def save_reports(results: pd.DataFrame, summary: str) -> None:
    results.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")


# Orchestre l’analyse des seuils de forte confiance avec team_strength_rating.
def main() -> None:
    try:
        ensure_report_dir()
        validate_feature_sets()

        database_url = get_database_url()
        clean_matches = fetch_clean_matches(database_url)

        print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
        print("Construction des features last10 + force d'equipe en memoire...", flush=True)

        feature_dataframe = build_experiment_dataframe(clean_matches)

        print(f"Lignes de features construites : {len(feature_dataframe)}", flush=True)
        print("Analyse des seuils de forte confiance team_strength_rating...", flush=True)

        results = analyze_thresholds(feature_dataframe)
        summary = build_summary(clean_matches, feature_dataframe, results)

        save_reports(results, summary)

        best_over_70_row = select_best_row(
            results=results,
            query="accuracy >= 0.70",
            sort_columns=["coverage", "accuracy"],
            ascending=[False, False],
        )

        print("OK - Analyse des seuils team_strength_rating terminee.")

        if best_over_70_row is not None:
            print(f"Best >= 70% feature set: {best_over_70_row['feature_set']}")
            print(f"Threshold: {best_over_70_row['threshold']}")
            print(f"Selected rows: {int(best_over_70_row['selected_rows'])}")
            print(f"Coverage: {best_over_70_row['coverage']}")
            print(f"Accuracy: {best_over_70_row['accuracy']}")
            print(f"Predicted DRAW rows: {int(best_over_70_row['predicted_draw_rows'])}")
        else:
            print("Aucun seuil teste n'atteint 70% d'accuracy.")

        print("Summary saved: reports/evidence/ml_training/41_1x2_team_strength_high_confidence_thresholds.txt")
        print("CSV saved: reports/evidence/ml_training/42_1x2_team_strength_high_confidence_thresholds.csv")

    except Exception as error:
        print("Erreur pendant l'analyse des seuils team_strength_rating.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# analyze_1x2_team_strength_high_confidence_thresholds.py
#   -> réutilise experiment_team_strength_features_1x2.py pour reconstruire les features team_strength_rating
#   -> réutilise compare_1x2_feature_sets.py pour lire PostgreSQL et les constantes ML
#   -> lit backend/.env pour DATABASE_URL sans afficher de secret
#   -> lit PostgreSQL : ml.clean_matches
#   -> entraîne LogisticRegression_balanced en mémoire
#   -> analyse les seuils de forte confiance sans modifier ml.features
#   -> ne remplace pas models/ml/1x2/best_1x2_model.joblib
#   -> écrit reports/evidence/ml_training/41_1x2_team_strength_high_confidence_thresholds.txt
#   -> écrit reports/evidence/ml_training/42_1x2_team_strength_high_confidence_thresholds.csv
