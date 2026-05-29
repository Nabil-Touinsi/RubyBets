# Rôle du fichier : exporter les prédictions ML 1X2 à forte confiance avec les features de force d’équipe, sans modifier la base ni remplacer le modèle sauvegardé.

from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

CSV_OUTPUT_PATH = REPORT_DIR / "43_1x2_team_strength_high_confidence_predictions.csv"
SUMMARY_OUTPUT_PATH = REPORT_DIR / "44_1x2_team_strength_high_confidence_predictions_summary.txt"

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
    SELECTED_FEATURE_SETS,
    build_candidate_models,
    build_experiment_dataframe,
)

warnings.filterwarnings("ignore", category=UserWarning)

FEATURE_SET_NAME = "last10_diff_plus_team_strength"
MODEL_NAME = "LogisticRegression_balanced"
CONFIDENCE_THRESHOLD = 0.61
PREVIOUS_HIGH_CONFIDENCE_ACCURACY = 0.7076
PREVIOUS_HIGH_CONFIDENCE_COVERAGE = 0.0920

EXPORT_COLUMNS = [
    "clean_match_id",
    "match_date",
    "league_code",
    "season",
    "home_team",
    "away_team",
    "match",
    "actual_result",
    "predicted_result",
    "prob_away_win",
    "prob_draw",
    "prob_home_win",
    "max_probability",
    "correct",
    "home_form_points_last_10",
    "away_form_points_last_10",
    "form_points_diff",
    "home_goals_scored_avg_last_10",
    "away_goals_scored_avg_last_10",
    "goals_scored_diff",
    "home_goals_conceded_avg_last_10",
    "away_goals_conceded_avg_last_10",
    "goals_conceded_diff",
    "home_team_strength_before",
    "away_team_strength_before",
    "team_strength_diff",
    "abs_team_strength_diff",
    "home_team_strength_recent_delta",
    "away_team_strength_recent_delta",
]


# Vérifie que le feature set retenu et le modèle retenu existent dans les scripts précédents.
def validate_configuration() -> None:
    if FEATURE_SET_NAME not in SELECTED_FEATURE_SETS:
        raise RuntimeError(f"Feature set introuvable : {FEATURE_SET_NAME}")

    candidate_models = build_candidate_models()

    if MODEL_NAME not in candidate_models:
        raise RuntimeError(f"Modele introuvable : {MODEL_NAME}")


# Prépare le train/test chronologique en gardant aussi les métadonnées des matchs test.
def prepare_train_test_export(
    feature_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, list[str]]:
    feature_columns = SELECTED_FEATURE_SETS[FEATURE_SET_NAME]
    working_dataframe = feature_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError("Train ou test vide apres preparation des donnees.")

    x_train = train_dataframe[feature_columns]
    y_train = train_dataframe[TARGET_COLUMN]
    x_test = test_dataframe[feature_columns]
    y_test = test_dataframe[TARGET_COLUMN]

    return x_train, y_train, x_test, y_test, test_dataframe, feature_columns


# Entraîne le modèle expérimental retenu uniquement en mémoire.
def train_selected_model(x_train: pd.DataFrame, y_train: pd.Series):
    candidate_models = build_candidate_models()
    model = clone(candidate_models[MODEL_NAME])
    model.fit(x_train, y_train)

    return model


# Récupère les classes du modèle dans le bon ordre pour nommer les colonnes de probabilité.
def get_model_classes(model) -> list[str]:
    if hasattr(model, "classes_"):
        return list(model.classes_)

    if hasattr(model, "named_steps") and "classifier" in model.named_steps:
        return list(model.named_steps["classifier"].classes_)

    raise RuntimeError("Impossible de recuperer les classes du modele entraine.")


# Construit le tableau complet des prédictions test avec probabilités et variables utiles.
def build_predictions_dataframe(
    model,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    test_dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> pd.DataFrame:
    predictions = pd.Series(model.predict(x_test)).reset_index(drop=True)
    probabilities = model.predict_proba(x_test)
    model_classes = get_model_classes(model)

    probability_dataframe = pd.DataFrame(
        probabilities,
        columns=[f"prob_{class_name.lower()}" for class_name in model_classes],
    )

    metadata_columns = [
        "clean_match_id",
        "match_date",
        "league_code",
        "season",
        "home_team",
        "away_team",
    ]

    output_dataframe = test_dataframe[metadata_columns + feature_columns].reset_index(drop=True)
    output_dataframe["match"] = output_dataframe["home_team"] + " vs " + output_dataframe["away_team"]
    output_dataframe["actual_result"] = y_test.reset_index(drop=True)
    output_dataframe["predicted_result"] = predictions
    output_dataframe = pd.concat([output_dataframe, probability_dataframe], axis=1)

    probability_columns = [column for column in output_dataframe.columns if column.startswith("prob_")]
    output_dataframe["max_probability"] = output_dataframe[probability_columns].max(axis=1)
    output_dataframe["correct"] = output_dataframe["actual_result"] == output_dataframe["predicted_result"]

    return output_dataframe


# Filtre les lignes dont la probabilité maximale atteint le seuil de forte confiance retenu.
def filter_high_confidence_predictions(predictions_dataframe: pd.DataFrame) -> pd.DataFrame:
    high_confidence = predictions_dataframe[
        predictions_dataframe["max_probability"] >= CONFIDENCE_THRESHOLD
    ].copy()

    high_confidence = high_confidence.sort_values(
        by=["max_probability", "match_date"],
        ascending=[False, True],
    )

    numeric_columns = [
        column
        for column in high_confidence.columns
        if column.startswith("prob_")
        or column.endswith("_diff")
        or column.endswith("_before")
        or column.endswith("_delta")
        or column.endswith("_last_10")
        or column == "max_probability"
    ]

    for column in numeric_columns:
        if column in high_confidence.columns:
            high_confidence[column] = pd.to_numeric(high_confidence[column], errors="coerce").round(4)

    available_export_columns = [column for column in EXPORT_COLUMNS if column in high_confidence.columns]

    return high_confidence[available_export_columns]


# Calcule une distribution simple des résultats ou prédictions sélectionnés.
def calculate_distribution(values: pd.Series) -> dict[str, int]:
    value_counts = values.value_counts().to_dict()

    return {
        "HOME_WIN": int(value_counts.get("HOME_WIN", 0)),
        "DRAW": int(value_counts.get("DRAW", 0)),
        "AWAY_WIN": int(value_counts.get("AWAY_WIN", 0)),
    }


# Construit le texte de synthèse de l’export forte confiance.
def build_summary(
    clean_matches: list[dict],
    feature_dataframe: pd.DataFrame,
    high_confidence: pd.DataFrame,
    test_rows: int,
    train_rows: int,
    feature_columns: list[str],
) -> str:
    selected_rows = len(high_confidence)
    correct_predictions = int(high_confidence["correct"].sum()) if selected_rows else 0
    accuracy = accuracy_score(high_confidence["actual_result"], high_confidence["predicted_result"]) if selected_rows else 0
    coverage = selected_rows / test_rows if test_rows else 0
    predicted_distribution = calculate_distribution(high_confidence["predicted_result"]) if selected_rows else {}
    actual_distribution = calculate_distribution(high_confidence["actual_result"]) if selected_rows else {}

    lines = [
        "RubyBets - ML 1X2 team strength high-confidence predictions export",
        "44 - Export des predictions forte confiance avec force d'equipe avant-match",
        "",
        "Positionnement :",
        "Cet export ne remplace pas le scoring explicable V1.",
        "Il ne modifie pas PostgreSQL, ne remplace pas le modele sauvegarde et ne touche pas au frontend.",
        "Il documente uniquement les matchs ou le signal ML experimental est le plus confiant.",
        "",
        "Configuration retenue :",
        f"- Feature set : {FEATURE_SET_NAME}",
        f"- Model : {MODEL_NAME}",
        f"- Confidence threshold : {CONFIDENCE_THRESHOLD}",
        "- Signal attendu : principalement HOME_WIN / AWAY_WIN, car DRAW reste absent en forte confiance.",
        "",
        "Baseline officielle actuelle :",
        f"- Accuracy officielle : {OFFICIAL_BASELINE_ACCURACY:.4f}",
        f"- F1 macro officiel : {OFFICIAL_BASELINE_F1_MACRO:.4f}",
        "",
        "Reference forte confiance precedente :",
        f"- Accuracy : {PREVIOUS_HIGH_CONFIDENCE_ACCURACY:.4f}",
        f"- Coverage : {PREVIOUS_HIGH_CONFIDENCE_COVERAGE:.4f}",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features construites : {len(feature_dataframe)}",
        f"- Train rows : {train_rows}",
        f"- Test rows : {test_rows}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Resultat export forte confiance :",
        f"- Selected rows : {selected_rows}",
        f"- Coverage : {coverage:.4f}",
        f"- Correct predictions : {correct_predictions}",
        f"- Accuracy : {accuracy:.4f}",
        f"- Predicted HOME_WIN rows : {predicted_distribution.get('HOME_WIN', 0)}",
        f"- Predicted DRAW rows : {predicted_distribution.get('DRAW', 0)}",
        f"- Predicted AWAY_WIN rows : {predicted_distribution.get('AWAY_WIN', 0)}",
        f"- Actual HOME_WIN rows : {actual_distribution.get('HOME_WIN', 0)}",
        f"- Actual DRAW rows : {actual_distribution.get('DRAW', 0)}",
        f"- Actual AWAY_WIN rows : {actual_distribution.get('AWAY_WIN', 0)}",
        "",
        "Features utilisees :",
        *[f"- {column}" for column in feature_columns],
        "",
        "Lecture metier :",
        "- Le seuil 0.61 depasse environ 70% d'accuracy avec une couverture plus large que l'ancien signal forte confiance.",
        "- Le signal reste experimental et ne doit pas etre presente comme un predicteur general 1X2.",
        "- L'absence de predictions DRAW en forte confiance reste la limite principale.",
        "- Le scoring explicable V1 reste le socle produit tant qu'une V2 ML n'est pas validee globalement.",
        "",
        "Generated files:",
        str(CSV_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        str(SUMMARY_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        "",
    ]

    return "\n".join(lines)


# Sauvegarde le CSV détaillé et la synthèse TXT.
def save_reports(high_confidence: pd.DataFrame, summary: str) -> None:
    high_confidence.to_csv(CSV_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    SUMMARY_OUTPUT_PATH.write_text(summary, encoding="utf-8")


# Orchestre l’export des prédictions forte confiance avec team_strength_rating.
def main() -> None:
    try:
        ensure_report_dir()
        validate_configuration()

        database_url = get_database_url()
        clean_matches = fetch_clean_matches(database_url)

        print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
        print("Construction des features last10 + force d'equipe en memoire...", flush=True)

        feature_dataframe = build_experiment_dataframe(clean_matches)

        x_train, y_train, x_test, y_test, test_dataframe, feature_columns = prepare_train_test_export(
            feature_dataframe=feature_dataframe,
        )

        print(f"Train rows : {len(x_train)}", flush=True)
        print(f"Test rows : {len(x_test)}", flush=True)
        print(f"Entrainement du modele {MODEL_NAME}...", flush=True)

        model = train_selected_model(x_train=x_train, y_train=y_train)

        predictions_dataframe = build_predictions_dataframe(
            model=model,
            x_test=x_test,
            y_test=y_test,
            test_dataframe=test_dataframe,
            feature_columns=feature_columns,
        )

        high_confidence = filter_high_confidence_predictions(predictions_dataframe)
        summary = build_summary(
            clean_matches=clean_matches,
            feature_dataframe=feature_dataframe,
            high_confidence=high_confidence,
            test_rows=len(x_test),
            train_rows=len(x_train),
            feature_columns=feature_columns,
        )

        save_reports(high_confidence=high_confidence, summary=summary)

        selected_rows = len(high_confidence)
        correct_predictions = int(high_confidence["correct"].sum()) if selected_rows else 0
        accuracy = correct_predictions / selected_rows if selected_rows else 0
        coverage = selected_rows / len(x_test) if len(x_test) else 0
        predicted_draw_rows = int((high_confidence["predicted_result"] == "DRAW").sum()) if selected_rows else 0

        print("OK - Export des predictions forte confiance team_strength_rating termine.")
        print(f"Feature set: {FEATURE_SET_NAME}")
        print(f"Model: {MODEL_NAME}")
        print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
        print(f"Selected rows: {selected_rows}")
        print(f"Coverage: {coverage:.4f}")
        print(f"Correct predictions: {correct_predictions}")
        print(f"Accuracy: {accuracy:.4f}")
        print(f"Predicted DRAW rows: {predicted_draw_rows}")
        print("CSV saved: reports/evidence/ml_training/43_1x2_team_strength_high_confidence_predictions.csv")
        print("Summary saved: reports/evidence/ml_training/44_1x2_team_strength_high_confidence_predictions_summary.txt")

    except Exception as error:
        print("Erreur pendant l'export forte confiance team_strength_rating.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# export_1x2_team_strength_high_confidence_predictions.py
#   -> réutilise experiment_team_strength_features_1x2.py pour reconstruire les features team_strength_rating
#   -> réutilise compare_1x2_feature_sets.py pour lire PostgreSQL et les constantes ML
#   -> lit backend/.env pour DATABASE_URL sans afficher de secret
#   -> lit PostgreSQL : ml.clean_matches
#   -> entraîne LogisticRegression_balanced en mémoire
#   -> filtre les prédictions avec max_probability >= 0.61
#   -> ne modifie pas ml.features
#   -> ne remplace pas models/ml/1x2/best_1x2_model.joblib
#   -> écrit reports/evidence/ml_training/43_1x2_team_strength_high_confidence_predictions.csv
#   -> écrit reports/evidence/ml_training/44_1x2_team_strength_high_confidence_predictions_summary.txt
