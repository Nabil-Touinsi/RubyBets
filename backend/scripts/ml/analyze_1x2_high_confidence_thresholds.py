# Rôle du fichier : analyser les seuils de confiance du modèle ML 1X2 expérimental sans modifier la baseline validée.

from pathlib import Path
import sys

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "36_1x2_high_confidence_thresholds.txt"
CSV_PATH = REPORT_DIR / "37_1x2_high_confidence_thresholds.csv"

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

THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]


# Crée le modèle retenu pour analyser les seuils de confiance.
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
def prepare_train_test(feature_dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
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

    return x_train, y_train, x_test, y_test


# Calcule la précision d’une classe prédite dans un sous-ensemble filtré.
def calculate_predicted_class_accuracy(dataframe: pd.DataFrame, class_name: str) -> float | None:
    selected = dataframe[dataframe["predicted_result"] == class_name]

    if selected.empty:
        return None

    return round(float(selected["correct"].mean()), 4)


# Compte les lignes d’une classe dans une colonne donnée.
def count_class_rows(dataframe: pd.DataFrame, column_name: str, class_name: str) -> int:
    return int((dataframe[column_name] == class_name).sum())


# Analyse un seuil de probabilité donné.
def analyze_threshold(prediction_dataframe: pd.DataFrame, threshold: float) -> dict:
    selected = prediction_dataframe[
        prediction_dataframe["max_probability"] >= threshold
    ].copy()

    selected_rows = len(selected)
    total_rows = len(prediction_dataframe)

    if selected_rows == 0:
        return {
            "threshold": threshold,
            "selected_rows": 0,
            "coverage": 0.0,
            "correct_predictions": 0,
            "accuracy": None,
            "predicted_home_win_rows": 0,
            "predicted_draw_rows": 0,
            "predicted_away_win_rows": 0,
            "home_win_accuracy_when_predicted": None,
            "draw_accuracy_when_predicted": None,
            "away_win_accuracy_when_predicted": None,
            "actual_home_win_rows": 0,
            "actual_draw_rows": 0,
            "actual_away_win_rows": 0,
        }

    correct_predictions = int(selected["correct"].sum())

    return {
        "threshold": threshold,
        "selected_rows": selected_rows,
        "coverage": round(selected_rows / total_rows, 4),
        "correct_predictions": correct_predictions,
        "accuracy": round(accuracy_score(selected["actual_result"], selected["predicted_result"]), 4),
        "predicted_home_win_rows": count_class_rows(selected, "predicted_result", "HOME_WIN"),
        "predicted_draw_rows": count_class_rows(selected, "predicted_result", "DRAW"),
        "predicted_away_win_rows": count_class_rows(selected, "predicted_result", "AWAY_WIN"),
        "home_win_accuracy_when_predicted": calculate_predicted_class_accuracy(selected, "HOME_WIN"),
        "draw_accuracy_when_predicted": calculate_predicted_class_accuracy(selected, "DRAW"),
        "away_win_accuracy_when_predicted": calculate_predicted_class_accuracy(selected, "AWAY_WIN"),
        "actual_home_win_rows": count_class_rows(selected, "actual_result", "HOME_WIN"),
        "actual_draw_rows": count_class_rows(selected, "actual_result", "DRAW"),
        "actual_away_win_rows": count_class_rows(selected, "actual_result", "AWAY_WIN"),
    }


# Construit le tableau complet des prédictions avec probabilité maximale.
def build_prediction_dataframe(model: Pipeline, x_test: pd.DataFrame, y_test: pd.Series) -> pd.DataFrame:
    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)
    max_probabilities = probabilities.max(axis=1)

    return pd.DataFrame(
        {
            "actual_result": y_test.reset_index(drop=True),
            "predicted_result": pd.Series(predictions),
            "max_probability": max_probabilities,
            "correct": pd.Series(predictions) == y_test.reset_index(drop=True),
        }
    )


# Construit la synthèse texte lisible pour décider si le ML peut être utilisé en forte confiance.
def build_summary(thresholds_dataframe: pd.DataFrame, total_test_rows: int) -> str:
    eligible = thresholds_dataframe[
        thresholds_dataframe["accuracy"].fillna(0) >= 0.70
    ].copy()

    if eligible.empty:
        decision = "Aucun seuil ne permet d'atteindre 70% d'accuracy."
    else:
        best_coverage_row = eligible.sort_values(
            by=["coverage", "accuracy"],
            ascending=False,
        ).iloc[0]

        decision = (
            f"Seuil exploitable possible : {best_coverage_row['threshold']} "
            f"avec accuracy {best_coverage_row['accuracy']} "
            f"et coverage {best_coverage_row['coverage']}."
        )

    lines = [
        "RubyBets - ML 1X2 high confidence thresholds analysis",
        "36 - Analyse des seuils de confiance du modele experimental",
        "",
        "Positionnement :",
        "Cette analyse ne remplace pas la baseline ML sauvegardee.",
        "Elle sert a verifier si le ML devient utile uniquement sur les matchs ou il est tres confiant.",
        "",
        "Feature set et modele analyses :",
        f"- Feature set : {FEATURE_SET_NAME}",
        "- Modele : LogisticRegression_balanced",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        f"- Test rows : {total_test_rows}",
        "",
        "Objectif :",
        "- Identifier un seuil de probabilite permettant d'approcher ou depasser 70% d'accuracy.",
        "- Mesurer en meme temps le coverage, c'est-a-dire la part de matchs sur lesquels le modele parle.",
        "",
        "Decision automatique :",
        decision,
        "",
        "Threshold comparison:",
        thresholds_dataframe.to_string(index=False),
        "",
        "Lecture metier :",
        "- Si accuracy >= 0.70 mais coverage faible, le ML ne peut pas predire tous les matchs.",
        "- Il peut seulement devenir un signal complementaire sur quelques matchs tres confiants.",
        "- Si les predictions fortes concernent surtout HOME_WIN ou AWAY_WIN, le modele reste faible sur DRAW.",
        "- Le scoring explicable V1 reste donc le socle produit tant que le ML global ne s'ameliore pas.",
        "",
        "Generated files:",
        str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
        str(CSV_PATH.relative_to(PROJECT_ROOT)),
        "",
    ]

    return "\n".join(lines)


# Sauvegarde les fichiers de preuve.
def save_reports(thresholds_dataframe: pd.DataFrame, summary: str) -> None:
    thresholds_dataframe.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")


# Orchestre l’analyse complète des seuils de confiance.
def main() -> None:
    ensure_report_dir()

    database_url = get_database_url()
    clean_matches = fetch_clean_matches(database_url)

    print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
    print("Construction des features candidates en memoire...", flush=True)

    feature_dataframe = build_feature_dataframe(clean_matches)

    x_train, y_train, x_test, y_test = prepare_train_test(feature_dataframe)

    print(f"Train rows : {len(x_train)}", flush=True)
    print(f"Test rows : {len(x_test)}", flush=True)
    print("Entrainement du modele LogisticRegression_balanced...", flush=True)

    model = build_model()
    model.fit(x_train, y_train)

    prediction_dataframe = build_prediction_dataframe(model, x_test, y_test)

    print("Analyse des seuils de confiance...", flush=True)

    threshold_rows = [
        analyze_threshold(prediction_dataframe, threshold)
        for threshold in THRESHOLDS
    ]

    thresholds_dataframe = pd.DataFrame(threshold_rows)
    summary = build_summary(thresholds_dataframe, len(x_test))

    save_reports(thresholds_dataframe, summary)

    print("OK - Analyse des seuils de confiance terminee.")
    print("Summary saved: reports/evidence/ml_training/36_1x2_high_confidence_thresholds.txt")
    print("CSV saved: reports/evidence/ml_training/37_1x2_high_confidence_thresholds.csv")


if __name__ == "__main__":
    main()


# Schéma de communication :
# analyze_1x2_high_confidence_thresholds.py
#   -> réutilise compare_1x2_feature_sets.py pour éviter la duplication
#   -> lit PostgreSQL : ml.clean_matches
#   -> reconstruit les features candidates en mémoire
#   -> entraîne LogisticRegression_balanced sur le meilleur set métier
#   -> analyse les seuils 0.50 à 0.80
#   -> mesure accuracy, coverage et classes prédites
#   -> écrit reports/evidence/ml_training/36_1x2_high_confidence_thresholds.txt
#   -> écrit reports/evidence/ml_training/37_1x2_high_confidence_thresholds.csv