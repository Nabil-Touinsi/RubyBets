# Role du fichier :
# Ce script entraine et compare une experience V18.1 WC enriched.
# Il compare Kaggle + Elo seul contre Kaggle + Elo + StatsBomb rolling features
# sur 1X2, OVER_1_5, OVER_2_5 et BTTS.

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT_DIR = Path(__file__).resolve().parents[3]

EVIDENCE_DIR = ROOT_DIR / "reports" / "evidence" / "ml_training"

INPUT_CSV = EVIDENCE_DIR / "333_v18_1_wc_enriched_dataset.csv"

SUMMARY_FILE = EVIDENCE_DIR / "334_v18_1_wc_enriched_multimarket_summary.txt"
COMPARISON_CSV = EVIDENCE_DIR / "335_v18_1_wc_enriched_model_comparison.csv"
PREDICTIONS_CSV = EVIDENCE_DIR / "336_v18_1_wc_enriched_predictions.csv"


TARGETS = [
    "target_1x2",
    "target_over_1_5",
    "target_over_2_5",
    "target_btts",
]

CONTEXT_COLUMNS = [
    "clean_match_id",
    "feature_id",
    "statsbomb_match_id",
    "match_date",
    "statsbomb_season_name",
    "team_a_name",
    "team_b_name",
    "team_a_score",
    "team_b_score",
]


# Cette fonction convertit une valeur CSV en booleen numerique.
def to_binary(value: Any) -> int:
    return 1 if str(value).strip().lower() in {"true", "1", "yes"} else 0


# Cette fonction charge le dataset V18.1 enrichi.
def load_dataset() -> pd.DataFrame:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Fichier introuvable : {INPUT_CSV}")

    dataframe = pd.read_csv(INPUT_CSV)
    dataframe["match_date"] = pd.to_datetime(dataframe["match_date"], errors="coerce")

    dataframe["target_1x2"] = dataframe["target_1x2"].astype(str)

    for target in ["target_over_1_5", "target_over_2_5", "target_btts"]:
        dataframe[target] = dataframe[target].apply(to_binary).astype(int)

    dataframe = dataframe.sort_values(
        by=["match_date", "statsbomb_match_id"],
    ).reset_index(drop=True)

    return dataframe


# Cette fonction verifie si une colonne est numerique et exploitable comme feature.
def is_numeric_feature(dataframe: pd.DataFrame, column: str) -> bool:
    numeric_series = pd.to_numeric(dataframe[column], errors="coerce")

    valid_count = numeric_series.notna().sum()
    unique_count = numeric_series.nunique(dropna=True)

    return valid_count > 0 and unique_count > 1


# Cette fonction prepare les colonnes de features Kaggle/Elo et StatsBomb.
def infer_feature_sets(dataframe: pd.DataFrame) -> dict[str, list[str]]:
    excluded_keywords = [
        "id",
        "target",
        "score",
        "date",
        "version",
        "name",
        "competition",
        "season",
        "status",
        "reason",
        "alignment",
    ]

    kaggle_candidates = [
        column
        for column in dataframe.columns
        if column.startswith("f_")
        and not any(keyword in column.lower() for keyword in excluded_keywords)
    ]

    statsbomb_candidates = [
        column
        for column in dataframe.columns
        if column.startswith("sb_team_")
        and not any(keyword in column.lower() for keyword in excluded_keywords)
    ]

    kaggle_features = [
        column
        for column in kaggle_candidates
        if is_numeric_feature(dataframe, column)
    ]

    statsbomb_features = [
        column
        for column in statsbomb_candidates
        if is_numeric_feature(dataframe, column)
    ]

    for column in kaggle_features + statsbomb_features:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce").fillna(0.0)

    if not kaggle_features:
        raise RuntimeError("Aucune feature Kaggle/Elo numerique exploitable detectee.")

    if not statsbomb_features:
        raise RuntimeError("Aucune feature StatsBomb rolling numerique exploitable detectee.")

    return {
        "kaggle_elo_only": kaggle_features,
        "kaggle_elo_statsbomb": kaggle_features + statsbomb_features,
    }


# Cette fonction cree un split Coupe du Monde 2018 -> 2022.
def wc_2018_2022_split(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_df = dataframe[dataframe["statsbomb_season_name"].astype(str) == "2018"].copy()
    test_df = dataframe[dataframe["statsbomb_season_name"].astype(str) == "2022"].copy()

    if len(train_df) == 0 or len(test_df) == 0:
        split_index = int(len(dataframe) * 0.5)
        train_df = dataframe.iloc[:split_index].copy()
        test_df = dataframe.iloc[split_index:].copy()

    return train_df, test_df


# Cette fonction construit les modeles a comparer.
def build_models(target: str) -> dict[str, Any]:
    if target == "target_1x2":
        return {
            "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
            "logistic_regression_balanced": Pipeline(
                steps=[
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            class_weight="balanced",
                            max_iter=1000,
                            random_state=42,
                        ),
                    ),
                ]
            ),
            "random_forest_balanced": RandomForestClassifier(
                n_estimators=300,
                class_weight="balanced",
                random_state=42,
                min_samples_leaf=3,
            ),
        }

    return {
        "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
        "logistic_regression_balanced": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=1000,
                        random_state=42,
                    ),
                ),
            ]
        ),
        "random_forest_balanced": RandomForestClassifier(
            n_estimators=300,
            class_weight="balanced",
            random_state=42,
            min_samples_leaf=3,
        ),
    }


# Cette fonction verifie si l'entrainement est possible.
def can_train_target(train_df: pd.DataFrame, test_df: pd.DataFrame, target: str) -> bool:
    if len(train_df) < 20 or len(test_df) < 20:
        return False

    if train_df[target].nunique() < 2:
        return False

    if test_df[target].nunique() < 2:
        return False

    return True


# Cette fonction extrait les probabilites du modele.
def get_prediction_confidences(model: Any, x_test: pd.DataFrame, y_pred: Any) -> tuple[list[float], list[float]]:
    if not hasattr(model, "predict_proba"):
        return [0.0 for _ in range(len(x_test))], [0.0 for _ in range(len(x_test))]

    probabilities = model.predict_proba(x_test)
    classes = list(model.classes_)

    predicted_confidences = []
    positive_probabilities = []

    for index, predicted_value in enumerate(y_pred):
        predicted_class_index = classes.index(predicted_value)
        predicted_confidences.append(float(probabilities[index][predicted_class_index]))

        if 1 in classes:
            positive_class_index = classes.index(1)
            positive_probabilities.append(float(probabilities[index][positive_class_index]))
        else:
            positive_probabilities.append(0.0)

    return predicted_confidences, positive_probabilities


# Cette fonction calcule les metriques selon le type de target.
def compute_metrics(y_test: pd.Series, y_pred: Any, target: str) -> dict[str, float]:
    accuracy = accuracy_score(y_test, y_pred)

    if target == "target_1x2":
        f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)
        precision = precision_score(y_test, y_pred, average="macro", zero_division=0)
        recall = recall_score(y_test, y_pred, average="macro", zero_division=0)
    else:
        f1 = f1_score(y_test, y_pred, zero_division=0)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)

    return {
        "accuracy": round(float(accuracy), 4),
        "f1": round(float(f1), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
    }


# Cette fonction evalue un modele.
def evaluate_model(
    dataframe: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target: str,
    feature_set_name: str,
    feature_columns: list[str],
    model_name: str,
    model: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    x_train = train_df[feature_columns]
    y_train = train_df[target]

    x_test = test_df[feature_columns]
    y_test = test_df[target]

    model.fit(x_train, y_train)

    y_pred = model.predict(x_test)
    predicted_confidences, positive_probabilities = get_prediction_confidences(
        model,
        x_test,
        y_pred,
    )

    metrics = compute_metrics(y_test, y_pred, target)

    comparison_row = {
        "target": target,
        "feature_set": feature_set_name,
        "model_name": model_name,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "feature_count": len(feature_columns),
        "train_distribution": dict(y_train.value_counts().sort_index()),
        "test_distribution": dict(y_test.value_counts().sort_index()),
        "accuracy": metrics["accuracy"],
        "f1": metrics["f1"],
        "precision": metrics["precision"],
        "recall": metrics["recall"],
    }

    prediction_rows = []

    for index, (_, row) in enumerate(test_df.iterrows()):
        prediction_rows.append(
            {
                "target": target,
                "feature_set": feature_set_name,
                "model_name": model_name,
                "clean_match_id": row.get("clean_match_id"),
                "statsbomb_match_id": row.get("statsbomb_match_id"),
                "match_date": row.get("match_date").date().isoformat(),
                "season": row.get("statsbomb_season_name"),
                "team_a_name": row.get("team_a_name"),
                "team_b_name": row.get("team_b_name"),
                "team_a_score": row.get("team_a_score"),
                "team_b_score": row.get("team_b_score"),
                "actual": y_test.iloc[index],
                "predicted": y_pred[index],
                "predicted_confidence": round(float(predicted_confidences[index]), 4),
                "positive_probability": round(float(positive_probabilities[index]), 4),
                "is_correct": int(y_test.iloc[index] == y_pred[index]),
            }
        )

    return comparison_row, prediction_rows


# Cette fonction lance toutes les experiences V18.1.
def run_experiments(
    dataframe: pd.DataFrame,
    feature_sets: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    train_df, test_df = wc_2018_2022_split(dataframe)

    comparison_rows = []
    prediction_rows = []
    skipped = []

    for target in TARGETS:
        if not can_train_target(train_df, test_df, target):
            skipped.append(f"{target} skipped: train/test too small or one-class target.")
            continue

        for feature_set_name, feature_columns in feature_sets.items():
            models = build_models(target)

            for model_name, model in models.items():
                comparison_row, model_prediction_rows = evaluate_model(
                    dataframe=dataframe,
                    train_df=train_df,
                    test_df=test_df,
                    target=target,
                    feature_set_name=feature_set_name,
                    feature_columns=feature_columns,
                    model_name=model_name,
                    model=model,
                )

                comparison_rows.append(comparison_row)
                prediction_rows.extend(model_prediction_rows)

    return comparison_rows, prediction_rows, skipped


# Cette fonction sauvegarde la comparaison des modeles.
def save_comparison_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "target",
        "feature_set",
        "model_name",
        "train_rows",
        "test_rows",
        "feature_count",
        "train_distribution",
        "test_distribution",
        "accuracy",
        "f1",
        "precision",
        "recall",
    ]

    with COMPARISON_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction sauvegarde les predictions.
def save_predictions_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "target",
        "feature_set",
        "model_name",
        "clean_match_id",
        "statsbomb_match_id",
        "match_date",
        "season",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "actual",
        "predicted",
        "predicted_confidence",
        "positive_probability",
        "is_correct",
    ]

    with PREDICTIONS_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction selectionne les meilleurs resultats par target et feature set.
def get_best_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for row in rows:
        key = (str(row["target"]), str(row["feature_set"]))
        grouped.setdefault(key, []).append(row)

    best_rows = []

    for _, group_rows in grouped.items():
        best_row = sorted(
            group_rows,
            key=lambda row: (
                float(row["f1"]),
                float(row["accuracy"]),
                float(row["precision"]),
            ),
            reverse=True,
        )[0]

        best_rows.append(best_row)

    return best_rows


# Cette fonction compare Kaggle/Elo seul contre Kaggle/Elo + StatsBomb.
def build_feature_set_comparison(rows: list[dict[str, Any]]) -> list[str]:
    lines = []

    grouped_by_target: dict[str, list[dict[str, Any]]] = {}

    for row in get_best_rows(rows):
        grouped_by_target.setdefault(str(row["target"]), []).append(row)

    for target, target_rows in grouped_by_target.items():
        base_rows = [row for row in target_rows if row["feature_set"] == "kaggle_elo_only"]
        enriched_rows = [row for row in target_rows if row["feature_set"] == "kaggle_elo_statsbomb"]

        if not base_rows or not enriched_rows:
            continue

        base = base_rows[0]
        enriched = enriched_rows[0]

        delta_f1 = round(float(enriched["f1"]) - float(base["f1"]), 4)
        delta_accuracy = round(float(enriched["accuracy"]) - float(base["accuracy"]), 4)

        lines.append(
            "- "
            f"{target} | "
            f"base={base['model_name']} f1={base['f1']} acc={base['accuracy']} | "
            f"enriched={enriched['model_name']} f1={enriched['f1']} acc={enriched['accuracy']} | "
            f"delta_f1={delta_f1} | delta_accuracy={delta_accuracy}"
        )

    return lines


# Cette fonction sauvegarde la synthese texte.
def save_summary(
    dataframe: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    comparison_rows: list[dict[str, Any]],
    skipped: list[str],
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    train_df, test_df = wc_2018_2022_split(dataframe)
    best_rows = get_best_rows(comparison_rows)
    feature_set_comparison = build_feature_set_comparison(comparison_rows)

    lines = [
        "RubyBets - Experience V18.1 WC enriched multi-market",
        "",
        f"Source input : {INPUT_CSV}",
        f"Comparaison modeles : {COMPARISON_CSV}",
        f"Predictions test : {PREDICTIONS_CSV}",
        "",
        "Objectif :",
        "Comparer Kaggle + Elo seul contre Kaggle + Elo + StatsBomb rolling features.",
        "Les marches testes sont : 1X2, OVER_1_5, OVER_2_5 et BTTS.",
        "",
        "Perimetre :",
        "- Train : Coupe du Monde 2018",
        "- Test : Coupe du Monde 2022",
        "- Dataset : 128 matchs Coupe du Monde enrichis",
        "",
        "Important :",
        "Cette experience reste limitee au perimetre WC 2018/2022.",
        "Elle ne remplace pas encore V17.9.2 nationale globale.",
        "Aucun modele n'est integre au backend ou au frontend a cette etape.",
        "",
        "Dataset :",
        f"- Lignes totales : {len(dataframe)}",
        f"- Train rows : {len(train_df)}",
        f"- Test rows : {len(test_df)}",
        f"- Features Kaggle/Elo : {len(feature_sets['kaggle_elo_only'])}",
        f"- Features Kaggle/Elo + StatsBomb : {len(feature_sets['kaggle_elo_statsbomb'])}",
        "",
        "Meilleurs resultats par target et feature set :",
    ]

    if best_rows:
        for row in best_rows:
            lines.append(
                "- "
                f"{row['target']} | "
                f"{row['feature_set']} | "
                f"{row['model_name']} | "
                f"accuracy={row['accuracy']} | "
                f"f1={row['f1']} | "
                f"precision={row['precision']} | "
                f"recall={row['recall']} | "
                f"features={row['feature_count']}"
            )
    else:
        lines.append("- Aucun resultat exploitable.")

    lines.extend(
        [
            "",
            "Comparaison base vs enrichi :",
        ]
    )

    if feature_set_comparison:
        lines.extend(feature_set_comparison)
    else:
        lines.append("- Comparaison indisponible.")

    lines.extend(
        [
            "",
            "Experiences ignorees :",
        ]
    )

    if skipped:
        lines.extend([f"- {item}" for item in skipped])
    else:
        lines.append("- Aucune.")

    lines.extend(
        [
            "",
            "Decision attendue apres lecture :",
            "- Si l'enrichissement StatsBomb ameliore clairement OVER_1_5 ou BTTS, il pourra etre conserve pour V18.2.",
            "- Si le gain est faible, StatsBomb restera une preuve d'enrichissement data, sans complexifier le modele produit.",
            "- La double chance devra etre derivee plus tard des probabilites 1X2, pas entrainee comme target separee.",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance l'experience V18.1 complete.
def main() -> None:
    dataframe = load_dataset()
    feature_sets = infer_feature_sets(dataframe)

    comparison_rows, prediction_rows, skipped = run_experiments(dataframe, feature_sets)

    save_comparison_csv(comparison_rows)
    save_predictions_csv(prediction_rows)
    save_summary(dataframe, feature_sets, comparison_rows, skipped)

    print("OK - Experience V18.1 WC enriched multi-market terminee.")
    print(f"Rows input: {len(dataframe)}")
    print(f"Experiments: {len(comparison_rows)}")
    print(f"Predictions rows: {len(prediction_rows)}")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"Comparison CSV saved: {COMPARISON_CSV}")
    print(f"Predictions CSV saved: {PREDICTIONS_CSV}")


if __name__ == "__main__":
    main()


# Schema de communication :
# train_v18_1_wc_enriched_multimarket.py
#   -> lit reports/evidence/ml_training/333_v18_1_wc_enriched_dataset.csv
#   -> compare Kaggle + Elo seul vs Kaggle + Elo + StatsBomb rolling features
#   -> teste 1X2, OVER_1_5, OVER_2_5 et BTTS
#   -> produit reports/evidence/ml_training/334_v18_1_wc_enriched_multimarket_summary.txt
#   -> produit reports/evidence/ml_training/335_v18_1_wc_enriched_model_comparison.csv
#   -> produit reports/evidence/ml_training/336_v18_1_wc_enriched_predictions.csv