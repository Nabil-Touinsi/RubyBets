# Rôle du fichier : comparer plusieurs modèles ML 1X2 sur les meilleurs feature sets identifiés, sans modifier la baseline validée.

from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "34_1x2_models_on_best_features_comparison.txt"
CSV_PATH = REPORT_DIR / "35_1x2_models_on_best_features_comparison.csv"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    FEATURE_SETS,
    OFFICIAL_BASELINE_ACCURACY,
    OFFICIAL_BASELINE_F1_MACRO,
    TARGET_COLUMN,
    TEST_SEASONS,
    build_feature_dataframe,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)

warnings.filterwarnings("ignore", category=UserWarning)

SELECTED_FEATURE_SETS = {
    "accuracy_candidate_last10_diff": FEATURE_SETS["v2_last10_overall_with_diff"],
    "balanced_candidate_last10_diff_abs_venue": FEATURE_SETS["v2_last10_diff_abs_venue_strength"],
}


# Crée les modèles candidats à comparer sur les mêmes données.
def build_candidate_models() -> dict:
    models = {
        "LogisticRegression_balanced": Pipeline(
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
        ),
        "RandomForest_balanced": RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
            min_samples_leaf=5,
        ),
        "GradientBoosting": GradientBoostingClassifier(
            random_state=42,
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            random_state=42,
            max_iter=200,
            learning_rate=0.06,
        ),
    }

    try:
        from xgboost import XGBClassifier

        models["XGBoost"] = XGBClassifier(
            objective="multi:softprob",
            eval_metric="mlogloss",
            random_state=42,
            n_estimators=250,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
        )
    except Exception:
        print("Info - XGBoost non disponible, comparaison continue sans XGBoost.")

    return models


# Prépare les labels pour XGBoost si nécessaire.
def encode_target_for_xgboost(y_train: pd.Series, y_test: pd.Series) -> tuple[pd.Series, pd.Series, dict]:
    label_mapping = {
        "AWAY_WIN": 0,
        "DRAW": 1,
        "HOME_WIN": 2,
    }

    return y_train.map(label_mapping), y_test.map(label_mapping), label_mapping


# Reconvertit les prédictions numériques XGBoost vers les labels métier.
def decode_xgboost_predictions(predictions, label_mapping: dict) -> list[str]:
    reverse_mapping = {value: key for key, value in label_mapping.items()}

    return [reverse_mapping[int(prediction)] for prediction in predictions]


# Calcule l’accuracy sur les prédictions de forte confiance si le modèle expose des probabilités.
def calculate_high_confidence_metrics(model, x_test: pd.DataFrame, y_test: pd.Series, predictions) -> dict:
    if not hasattr(model, "predict_proba"):
        return {
            "high_confidence_threshold": None,
            "high_confidence_rows": 0,
            "high_confidence_coverage": 0.0,
            "high_confidence_accuracy": None,
        }

    probabilities = model.predict_proba(x_test)
    max_probabilities = probabilities.max(axis=1)

    threshold = 0.60
    selected_mask = max_probabilities >= threshold
    selected_count = int(selected_mask.sum())

    if selected_count == 0:
        return {
            "high_confidence_threshold": threshold,
            "high_confidence_rows": 0,
            "high_confidence_coverage": 0.0,
            "high_confidence_accuracy": None,
        }

    selected_predictions = pd.Series(predictions).reset_index(drop=True)[selected_mask]
    selected_truth = y_test.reset_index(drop=True)[selected_mask]

    return {
        "high_confidence_threshold": threshold,
        "high_confidence_rows": selected_count,
        "high_confidence_coverage": round(selected_count / len(y_test), 4),
        "high_confidence_accuracy": round(accuracy_score(selected_truth, selected_predictions), 4),
    }


# Évalue un modèle sur un feature set donné.
def evaluate_model_on_feature_set(
    feature_dataframe: pd.DataFrame,
    feature_set_name: str,
    feature_columns: list[str],
    model_name: str,
    model,
) -> dict:
    working_dataframe = feature_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    x_train = train_dataframe[feature_columns]
    y_train = train_dataframe[TARGET_COLUMN]

    x_test = test_dataframe[feature_columns]
    y_test = test_dataframe[TARGET_COLUMN]

    if model_name == "XGBoost":
        y_train_encoded, _, label_mapping = encode_target_for_xgboost(y_train, y_test)
        model.fit(x_train, y_train_encoded)
        raw_predictions = model.predict(x_test)
        predictions = decode_xgboost_predictions(raw_predictions, label_mapping)
    else:
        model.fit(x_train, y_train)
        predictions = model.predict(x_test)

    report = classification_report(
        y_test,
        predictions,
        labels=["HOME_WIN", "DRAW", "AWAY_WIN"],
        output_dict=True,
        zero_division=0,
    )

    high_confidence = calculate_high_confidence_metrics(
        model=model,
        x_test=x_test,
        y_test=y_test,
        predictions=predictions,
    )

    return {
        "feature_set": feature_set_name,
        "model": model_name,
        "feature_count": len(feature_columns),
        "train_rows": len(train_dataframe),
        "test_rows": len(test_dataframe),
        "accuracy": round(accuracy_score(y_test, predictions), 4),
        "f1_macro": round(f1_score(y_test, predictions, average="macro"), 4),
        "f1_weighted": round(f1_score(y_test, predictions, average="weighted"), 4),
        "home_win_precision": round(report["HOME_WIN"]["precision"], 4),
        "home_win_recall": round(report["HOME_WIN"]["recall"], 4),
        "draw_precision": round(report["DRAW"]["precision"], 4),
        "draw_recall": round(report["DRAW"]["recall"], 4),
        "away_win_precision": round(report["AWAY_WIN"]["precision"], 4),
        "away_win_recall": round(report["AWAY_WIN"]["recall"], 4),
        **high_confidence,
    }


# Compare tous les modèles sur les deux meilleurs feature sets.
def compare_models(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    results = []

    for feature_set_name, feature_columns in SELECTED_FEATURE_SETS.items():
        candidate_models = build_candidate_models()

        for model_name, model in candidate_models.items():
            print(f"Evaluation : {model_name} sur {feature_set_name}", flush=True)

            result = evaluate_model_on_feature_set(
                feature_dataframe=feature_dataframe,
                feature_set_name=feature_set_name,
                feature_columns=feature_columns,
                model_name=model_name,
                model=model,
            )

            results.append(result)

    comparison = pd.DataFrame(results)

    return comparison.sort_values(
        by=["accuracy", "f1_macro"],
        ascending=False,
    )


# Construit la synthèse lisible de comparaison.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, comparison: pd.DataFrame) -> str:
    best_row = comparison.iloc[0]

    lines = [
        "RubyBets - ML 1X2 models comparison on best feature sets",
        "34 - Comparaison modeles apres selection des features candidates",
        "",
        "Positionnement :",
        "Cette experimentation compare plusieurs modeles sur les meilleurs feature sets identifies.",
        "Elle ne remplace pas encore la baseline sauvegardee et ne modifie pas l'API.",
        "",
        "Objectif utilisateur :",
        "- Verifier si un modele peut se rapprocher d'une accuracy globale utile.",
        "- Objectif souhaite : accuracy proche de 0.70.",
        "- Si le score reste loin de 0.70, le ML reste experimental.",
        "",
        "Baseline officielle actuelle :",
        f"- Accuracy officielle : {OFFICIAL_BASELINE_ACCURACY:.4f}",
        f"- F1 macro officiel : {OFFICIAL_BASELINE_F1_MACRO:.4f}",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features candidates construites : {len(feature_dataframe)}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Best experimental model:",
        f"- Feature set : {best_row['feature_set']}",
        f"- Model : {best_row['model']}",
        f"- Accuracy : {best_row['accuracy']}",
        f"- F1 macro : {best_row['f1_macro']}",
        f"- F1 weighted : {best_row['f1_weighted']}",
        f"- DRAW precision : {best_row['draw_precision']}",
        f"- DRAW recall : {best_row['draw_recall']}",
        f"- High confidence accuracy at threshold 0.60 : {best_row['high_confidence_accuracy']}",
        f"- High confidence coverage : {best_row['high_confidence_coverage']}",
        "",
        "Comparison table:",
        comparison[
            [
                "feature_set",
                "model",
                "accuracy",
                "f1_macro",
                "f1_weighted",
                "home_win_recall",
                "draw_recall",
                "away_win_recall",
                "high_confidence_accuracy",
                "high_confidence_coverage",
            ]
        ].to_string(index=False),
        "",
        "Decision rules:",
        "- Si aucun modele ne depasse clairement la baseline, on ne remplace pas le modele sauvegarde.",
        "- Si un modele ameliore fortement accuracy et F1 macro, il pourra devenir une V2 separee.",
        "- Si l'accuracy globale reste loin de 0.70, ne pas presenter le modele comme fiable produit.",
        "- Si seule l'accuracy forte confiance atteint environ 0.70, le modele pourra etre utilise comme signal limite aux cas confiants.",
        "",
        "Generated files:",
        str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
        str(CSV_PATH.relative_to(PROJECT_ROOT)),
        "",
    ]

    return "\n".join(lines)


# Sauvegarde les rapports de comparaison.
def save_reports(comparison: pd.DataFrame, summary: str) -> None:
    comparison.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")


# Orchestre la comparaison complète des modèles.
def main() -> None:
    ensure_report_dir()

    database_url = get_database_url()
    clean_matches = fetch_clean_matches(database_url)

    print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
    print("Construction des features candidates en memoire...", flush=True)

    feature_dataframe = build_feature_dataframe(clean_matches)

    print(f"Lignes de features candidates : {len(feature_dataframe)}", flush=True)
    print("Comparaison des modeles sur les meilleurs feature sets...", flush=True)

    comparison = compare_models(feature_dataframe)
    summary = build_summary(clean_matches, feature_dataframe, comparison)

    save_reports(comparison, summary)

    best_row = comparison.iloc[0]

    print("OK - Comparaison des modeles terminee.")
    print(f"Best feature set: {best_row['feature_set']}")
    print(f"Best model: {best_row['model']}")
    print(f"Accuracy: {best_row['accuracy']}")
    print(f"F1 macro: {best_row['f1_macro']}")
    print(f"DRAW recall: {best_row['draw_recall']}")
    print(f"High confidence accuracy: {best_row['high_confidence_accuracy']}")
    print("Summary saved: reports/evidence/ml_training/34_1x2_models_on_best_features_comparison.txt")
    print("CSV saved: reports/evidence/ml_training/35_1x2_models_on_best_features_comparison.csv")


if __name__ == "__main__":
    main()


# Schéma de communication :
# compare_1x2_models_on_best_features.py
#   -> réutilise compare_1x2_feature_sets.py pour éviter de dupliquer le calcul des features
#   -> lit PostgreSQL : ml.clean_matches
#   -> reconstruit les features candidates en mémoire
#   -> compare plusieurs modèles sur les deux meilleurs feature sets
#   -> mesure accuracy, F1 macro, rappel par classe et fiabilité forte confiance
#   -> écrit reports/evidence/ml_training/34_1x2_models_on_best_features_comparison.txt
#   -> écrit reports/evidence/ml_training/35_1x2_models_on_best_features_comparison.csv