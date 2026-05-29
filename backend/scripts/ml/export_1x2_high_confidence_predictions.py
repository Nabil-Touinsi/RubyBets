# Rôle du fichier : exporter les prédictions ML 1X2 à forte confiance pour voir concrètement les matchs où le modèle atteint environ 70% de fiabilité.

from pathlib import Path
import sys

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

OUTPUT_PATH = REPORT_DIR / "38_1x2_high_confidence_predictions.csv"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    FEATURE_SETS,
    TARGET_COLUMN,
    TEST_SEASONS,
    build_feature_dataframe,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)

FEATURE_SET_NAME = "balanced_candidate_last10_diff_abs_venue"
FEATURE_COLUMNS = FEATURE_SETS["v2_last10_diff_abs_venue_strength"]
CONFIDENCE_THRESHOLD = 0.60


# Crée le modèle expérimental retenu pour les prédictions à forte confiance.
def build_model() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=42,
                ),
            ),
        ]
    )


# Prépare les données train/test à partir du feature set sélectionné.
def prepare_train_test(
    feature_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame]:
    working_dataframe = feature_dataframe.dropna(
        subset=FEATURE_COLUMNS + [TARGET_COLUMN]
    ).copy()

    for column in FEATURE_COLUMNS:
        working_dataframe[column] = pd.to_numeric(
            working_dataframe[column],
            errors="coerce",
        )

    working_dataframe = working_dataframe.dropna(
        subset=FEATURE_COLUMNS + [TARGET_COLUMN]
    ).copy()

    train_dataframe = working_dataframe[
        ~working_dataframe["season"].isin(TEST_SEASONS)
    ].copy()

    test_dataframe = working_dataframe[
        working_dataframe["season"].isin(TEST_SEASONS)
    ].copy()

    x_train = train_dataframe[FEATURE_COLUMNS]
    y_train = train_dataframe[TARGET_COLUMN]

    x_test = test_dataframe[FEATURE_COLUMNS]
    y_test = test_dataframe[TARGET_COLUMN]

    return x_train, y_train, x_test, y_test, test_dataframe


# Récupère les classes du modèle entraîné dans le bon ordre de probabilité.
def get_model_classes(model: Pipeline) -> list[str]:
    classifier = model.named_steps["classifier"]

    return list(classifier.classes_)


# Construit le tableau complet des prédictions avec probabilités.
def build_predictions_dataframe(
    model: Pipeline,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    test_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)
    model_classes = get_model_classes(model)

    probability_dataframe = pd.DataFrame(
        probabilities,
        columns=[f"prob_{class_name.lower()}" for class_name in model_classes],
    )

    output_dataframe = test_dataframe[
        [
            "clean_match_id",
            "match_date",
            "league_code",
            "season",
            "home_team",
            "away_team",
        ]
    ].reset_index(drop=True)

    output_dataframe["match"] = (
        output_dataframe["home_team"] + " vs " + output_dataframe["away_team"]
    )

    output_dataframe["actual_result"] = y_test.reset_index(drop=True)
    output_dataframe["predicted_result"] = pd.Series(predictions)
    output_dataframe = pd.concat([output_dataframe, probability_dataframe], axis=1)

    probability_columns = [column for column in output_dataframe.columns if column.startswith("prob_")]

    output_dataframe["max_probability"] = output_dataframe[probability_columns].max(axis=1)
    output_dataframe["correct"] = (
        output_dataframe["actual_result"] == output_dataframe["predicted_result"]
    )

    return output_dataframe


# Filtre uniquement les prédictions dont la probabilité maximale atteint le seuil retenu.
def filter_high_confidence_predictions(predictions_dataframe: pd.DataFrame) -> pd.DataFrame:
    high_confidence = predictions_dataframe[
        predictions_dataframe["max_probability"] >= CONFIDENCE_THRESHOLD
    ].copy()

    high_confidence = high_confidence.sort_values(
        by="max_probability",
        ascending=False,
    )

    numeric_columns = [
        "prob_away_win",
        "prob_draw",
        "prob_home_win",
        "max_probability",
    ]

    for column in numeric_columns:
        if column in high_confidence.columns:
            high_confidence[column] = high_confidence[column].round(4)

    return high_confidence


# Sauvegarde le CSV des prédictions à forte confiance.
def save_high_confidence_predictions(high_confidence: pd.DataFrame) -> None:
    high_confidence.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )


# Orchestre l’export des matchs où le modèle est à forte confiance.
def main() -> None:
    ensure_report_dir()

    database_url = get_database_url()
    clean_matches = fetch_clean_matches(database_url)

    print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
    print("Construction des features candidates en memoire...", flush=True)

    feature_dataframe = build_feature_dataframe(clean_matches)

    x_train, y_train, x_test, y_test, test_dataframe = prepare_train_test(
        feature_dataframe
    )

    print(f"Train rows : {len(x_train)}", flush=True)
    print(f"Test rows : {len(x_test)}", flush=True)
    print("Entrainement du modele LogisticRegression_balanced...", flush=True)

    model = build_model()
    model.fit(x_train, y_train)

    predictions_dataframe = build_predictions_dataframe(
        model=model,
        x_test=x_test,
        y_test=y_test,
        test_dataframe=test_dataframe,
    )

    high_confidence = filter_high_confidence_predictions(predictions_dataframe)
    save_high_confidence_predictions(high_confidence)

    correct_predictions = int(high_confidence["correct"].sum())
    selected_rows = len(high_confidence)
    accuracy = correct_predictions / selected_rows if selected_rows else 0

    print("OK - Export des predictions forte confiance termine.")
    print(f"Feature set: {FEATURE_SET_NAME}")
    print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
    print(f"Selected rows: {selected_rows}")
    print(f"Correct predictions: {correct_predictions}")
    print(f"Accuracy: {accuracy:.4f}")
    print("CSV saved: reports/evidence/ml_training/38_1x2_high_confidence_predictions.csv")


if __name__ == "__main__":
    main()


# Schéma de communication :
# export_1x2_high_confidence_predictions.py
#   -> réutilise compare_1x2_feature_sets.py pour éviter la duplication
#   -> lit PostgreSQL : ml.clean_matches
#   -> reconstruit les features candidates en mémoire
#   -> entraîne LogisticRegression_balanced
#   -> filtre les prédictions avec max_probability >= 0.60
#   -> écrit reports/evidence/ml_training/38_1x2_high_confidence_predictions.csv