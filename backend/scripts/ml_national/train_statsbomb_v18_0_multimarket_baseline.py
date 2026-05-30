# Role du fichier :
# Ce script entraine une baseline experimentale V18.0 StatsBomb sur les marches OVER_1_5,
# OVER_2_5 et BTTS a partir des features rolling anti-fuite.

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

INPUT_CSV = EVIDENCE_DIR / "326_statsbomb_national_rolling_features.csv"

SUMMARY_FILE = EVIDENCE_DIR / "327_statsbomb_v18_0_multimarket_baseline_summary.txt"
COMPARISON_CSV = EVIDENCE_DIR / "328_statsbomb_v18_0_multimarket_model_comparison.csv"
PREDICTIONS_CSV = EVIDENCE_DIR / "329_statsbomb_v18_0_multimarket_predictions.csv"


TARGETS = [
    "target_over_1_5",
    "target_over_2_5",
    "target_btts",
]

FEATURE_COLUMNS = [
    "team_a_xg_for_last_5",
    "team_a_xg_against_last_5",
    "team_a_xg_diff_last_5",
    "team_a_shots_for_last_5",
    "team_a_shots_against_last_5",
    "team_a_shots_diff_last_5",
    "team_a_shots_on_target_for_last_5",
    "team_a_shots_on_target_against_last_5",
    "team_a_shots_on_target_diff_last_5",
    "team_a_goals_for_last_5",
    "team_a_goals_against_last_5",
    "team_a_goals_diff_last_5",
    "team_b_xg_for_last_5",
    "team_b_xg_against_last_5",
    "team_b_xg_diff_last_5",
    "team_b_shots_for_last_5",
    "team_b_shots_against_last_5",
    "team_b_shots_diff_last_5",
    "team_b_shots_on_target_for_last_5",
    "team_b_shots_on_target_against_last_5",
    "team_b_shots_on_target_diff_last_5",
    "team_b_goals_for_last_5",
    "team_b_goals_against_last_5",
    "team_b_goals_diff_last_5",
]

CONTEXT_COLUMNS = [
    "statsbomb_match_id",
    "competition_name",
    "season_name",
    "match_date",
    "team_a_name",
    "team_b_name",
    "team_a_score",
    "team_b_score",
    "total_goals",
]


# Cette fonction convertit une valeur en booleen.
def to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


# Cette fonction charge le dataset rolling StatsBomb.
def load_dataset() -> pd.DataFrame:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Fichier introuvable : {INPUT_CSV}")

    dataframe = pd.read_csv(INPUT_CSV)
    dataframe["match_date"] = pd.to_datetime(dataframe["match_date"], errors="coerce")

    for target in TARGETS:
        dataframe[target] = dataframe[target].apply(to_bool).astype(int)

    for column in FEATURE_COLUMNS:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce").fillna(0.0)

    dataframe["team_a_statsbomb_history_count"] = pd.to_numeric(
        dataframe["team_a_statsbomb_history_count"],
        errors="coerce",
    ).fillna(0).astype(int)

    dataframe["team_b_statsbomb_history_count"] = pd.to_numeric(
        dataframe["team_b_statsbomb_history_count"],
        errors="coerce",
    ).fillna(0).astype(int)

    dataframe["team_a_statsbomb_matches_used_last_5"] = pd.to_numeric(
        dataframe["team_a_statsbomb_matches_used_last_5"],
        errors="coerce",
    ).fillna(0).astype(int)

    dataframe["team_b_statsbomb_matches_used_last_5"] = pd.to_numeric(
        dataframe["team_b_statsbomb_matches_used_last_5"],
        errors="coerce",
    ).fillna(0).astype(int)

    dataframe = dataframe.sort_values(
        by=["match_date", "competition_name", "statsbomb_match_id"],
    ).reset_index(drop=True)

    return dataframe


# Cette fonction cree les scopes de test selon la quantite d'historique disponible.
def build_scopes(dataframe: pd.DataFrame) -> dict[str, pd.DataFrame]:
    history_any = dataframe[
        (dataframe["team_a_statsbomb_history_count"] > 0)
        & (dataframe["team_b_statsbomb_history_count"] > 0)
    ].copy()

    full_last_5 = dataframe[
        (dataframe["team_a_statsbomb_matches_used_last_5"] == 5)
        & (dataframe["team_b_statsbomb_matches_used_last_5"] == 5)
    ].copy()

    return {
        "history_any": history_any,
        "full_last_5": full_last_5,
    }


# Cette fonction cree un split chronologique train/test.
def chronological_split(dataframe: pd.DataFrame, train_ratio: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    dataframe = dataframe.sort_values(
        by=["match_date", "competition_name", "statsbomb_match_id"],
    ).reset_index(drop=True)

    split_index = int(len(dataframe) * train_ratio)

    train_df = dataframe.iloc[:split_index].copy()
    test_df = dataframe.iloc[split_index:].copy()

    return train_df, test_df


# Cette fonction construit les modeles binaires a comparer.
def build_models() -> dict[str, Any]:
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


# Cette fonction recupere une probabilite positive si le modele le permet.
def get_positive_probabilities(model: Any, x_test: pd.DataFrame) -> list[float]:
    if not hasattr(model, "predict_proba"):
        return [0.0 for _ in range(len(x_test))]

    probabilities = model.predict_proba(x_test)

    if probabilities.shape[1] == 1:
        return [float(probabilities[index][0]) for index in range(len(x_test))]

    return [float(probability[1]) for probability in probabilities]


# Cette fonction evalue un modele sur un target donne.
def evaluate_model(
    model_name: str,
    model: Any,
    target: str,
    scope_name: str,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    x_train = train_df[FEATURE_COLUMNS]
    y_train = train_df[target]

    x_test = test_df[FEATURE_COLUMNS]
    y_test = test_df[target]

    model.fit(x_train, y_train)

    y_pred = model.predict(x_test)
    positive_proba = get_positive_probabilities(model, x_test)

    accuracy = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)

    comparison_row = {
        "target": target,
        "scope": scope_name,
        "model_name": model_name,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "train_positive_rate": round(float(y_train.mean()), 4),
        "test_positive_rate": round(float(y_test.mean()), 4),
        "accuracy": round(float(accuracy), 4),
        "f1": round(float(f1), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
    }

    prediction_rows = []

    for index, (_, row) in enumerate(test_df.iterrows()):
        prediction_rows.append(
            {
                "target": target,
                "scope": scope_name,
                "model_name": model_name,
                "statsbomb_match_id": row["statsbomb_match_id"],
                "competition_name": row["competition_name"],
                "season_name": row["season_name"],
                "match_date": row["match_date"].date().isoformat(),
                "team_a_name": row["team_a_name"],
                "team_b_name": row["team_b_name"],
                "team_a_score": row["team_a_score"],
                "team_b_score": row["team_b_score"],
                "actual": int(y_test.iloc[index]),
                "predicted": int(y_pred[index]),
                "positive_probability": round(float(positive_proba[index]), 4),
                "is_correct": int(y_test.iloc[index]) == int(y_pred[index]),
            }
        )

    return comparison_row, prediction_rows


# Cette fonction verifie si un entrainement est possible pour le target.
def can_train_target(train_df: pd.DataFrame, test_df: pd.DataFrame, target: str) -> bool:
    if len(train_df) < 20 or len(test_df) < 10:
        return False

    if train_df[target].nunique() < 2:
        return False

    if test_df[target].nunique() < 2:
        return False

    return True


# Cette fonction lance tous les entrainements experimentaux.
def run_experiments(dataframe: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    comparison_rows = []
    prediction_rows = []
    skipped_experiments = []

    scopes = build_scopes(dataframe)

    for scope_name, scope_df in scopes.items():
        train_df, test_df = chronological_split(scope_df)

        for target in TARGETS:
            if not can_train_target(train_df, test_df, target):
                skipped_experiments.append(
                    f"{scope_name} | {target} | skipped because train/test split is too small or has one class"
                )
                continue

            models = build_models()

            for model_name, model in models.items():
                comparison_row, model_prediction_rows = evaluate_model(
                    model_name=model_name,
                    model=model,
                    target=target,
                    scope_name=scope_name,
                    train_df=train_df,
                    test_df=test_df,
                )

                comparison_rows.append(comparison_row)
                prediction_rows.extend(model_prediction_rows)

    return comparison_rows, prediction_rows, skipped_experiments


# Cette fonction sauvegarde le tableau de comparaison.
def save_comparison_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "target",
        "scope",
        "model_name",
        "train_rows",
        "test_rows",
        "train_positive_rate",
        "test_positive_rate",
        "accuracy",
        "f1",
        "precision",
        "recall",
    ]

    with COMPARISON_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction sauvegarde les predictions de test.
def save_predictions_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "target",
        "scope",
        "model_name",
        "statsbomb_match_id",
        "competition_name",
        "season_name",
        "match_date",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "actual",
        "predicted",
        "positive_probability",
        "is_correct",
    ]

    with PREDICTIONS_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction selectionne les meilleurs resultats par target et scope.
def get_best_rows(comparison_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_rows = []

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for row in comparison_rows:
        key = (str(row["target"]), str(row["scope"]))
        grouped.setdefault(key, []).append(row)

    for _, rows in grouped.items():
        best_row = sorted(
            rows,
            key=lambda row: (
                float(row["f1"]),
                float(row["accuracy"]),
                float(row["recall"]),
            ),
            reverse=True,
        )[0]

        best_rows.append(best_row)

    return best_rows


# Cette fonction sauvegarde la synthese texte.
def save_summary(
    dataframe: pd.DataFrame,
    comparison_rows: list[dict[str, Any]],
    skipped_experiments: list[str],
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    best_rows = get_best_rows(comparison_rows)

    lines = [
        "RubyBets - Baseline experimentale V18.0 StatsBomb multi-market",
        "",
        f"Source input : {INPUT_CSV}",
        f"Comparaison modeles : {COMPARISON_CSV}",
        f"Predictions test : {PREDICTIONS_CSV}",
        "",
        "Objectif :",
        "Tester si les features rolling StatsBomb peuvent ameliorer les marches OVER_1_5, OVER_2_5 et BTTS.",
        "",
        "Important :",
        "Cette experience est limitee au sous-ensemble StatsBomb.",
        "Elle ne remplace pas Kaggle + Elo, qui reste le socle principal national.",
        "Aucun modele n'est encore integre au backend ou au frontend.",
        "",
        "Dataset :",
        f"- Lignes totales : {len(dataframe)}",
        f"- Features utilisees : {len(FEATURE_COLUMNS)}",
        f"- Targets testees : {', '.join(TARGETS)}",
        "",
        "Scopes testes :",
        "- history_any : les deux equipes ont au moins un match StatsBomb precedent.",
        "- full_last_5 : les deux equipes ont cinq matchs StatsBomb precedents.",
        "",
        "Meilleurs resultats par target/scope :",
    ]

    if best_rows:
        for row in best_rows:
            lines.append(
                "- "
                f"{row['target']} | "
                f"{row['scope']} | "
                f"{row['model_name']} | "
                f"accuracy={row['accuracy']} | "
                f"f1={row['f1']} | "
                f"precision={row['precision']} | "
                f"recall={row['recall']} | "
                f"test_rows={row['test_rows']}"
            )
    else:
        lines.append("- Aucun entrainement exploitable.")

    lines.extend(
        [
            "",
            "Experiences ignorees :",
        ]
    )

    if skipped_experiments:
        lines.extend([f"- {item}" for item in skipped_experiments])
    else:
        lines.append("- Aucune.")

    lines.extend(
        [
            "",
            "Decision attendue apres lecture :",
            "- Si OVER_1_5 ou BTTS depasse clairement DummyClassifier, garder StatsBomb pour V18.0.",
            "- Si les gains sont faibles, conserver StatsBomb comme preuve d'enrichissement data mais ne pas complexifier le modele.",
            "- Ne pas integrer ces resultats directement dans le produit avant comparaison avec Kaggle + Elo.",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance l'experience complete V18.0 StatsBomb.
def main() -> None:
    dataframe = load_dataset()
    comparison_rows, prediction_rows, skipped_experiments = run_experiments(dataframe)

    save_comparison_csv(comparison_rows)
    save_predictions_csv(prediction_rows)
    save_summary(dataframe, comparison_rows, skipped_experiments)

    print("OK - Baseline V18.0 StatsBomb multi-market terminee.")
    print(f"Rows input: {len(dataframe)}")
    print(f"Experiments: {len(comparison_rows)}")
    print(f"Predictions rows: {len(prediction_rows)}")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"Comparison CSV saved: {COMPARISON_CSV}")
    print(f"Predictions CSV saved: {PREDICTIONS_CSV}")


if __name__ == "__main__":
    main()


# Schema de communication :
# train_statsbomb_v18_0_multimarket_baseline.py
#   -> lit reports/evidence/ml_training/326_statsbomb_national_rolling_features.csv
#   -> entraine Dummy, Logistic Regression et Random Forest sur OVER_1_5, OVER_2_5 et BTTS
#   -> produit reports/evidence/ml_training/327_statsbomb_v18_0_multimarket_baseline_summary.txt
#   -> produit reports/evidence/ml_training/328_statsbomb_v18_0_multimarket_model_comparison.csv
#   -> produit reports/evidence/ml_training/329_statsbomb_v18_0_multimarket_predictions.csv