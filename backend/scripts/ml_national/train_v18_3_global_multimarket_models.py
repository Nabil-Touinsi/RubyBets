# Role du fichier :
# Ce script entraine les premieres baselines V18.3 global multi-market RubyBets.
# Il utilise le dataset 345 pour comparer des modeles separes sur 1X2, OVER_1_5, OVER_2_5 et BTTS, sans utiliser StatsBomb.

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


CURRENT_FILE = Path(__file__).resolve()

if len(CURRENT_FILE.parents) >= 4 and CURRENT_FILE.parents[2].name == "backend":
    PROJECT_ROOT = CURRENT_FILE.parents[3]
else:
    PROJECT_ROOT = Path.cwd()

EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
MODEL_DIR = PROJECT_ROOT / "models" / "ml_national" / "v18_3_global_multimarket"

DEFAULT_DATASET_PATH = EVIDENCE_DIR / "345_v18_3_global_multimarket_dataset.csv"

SUMMARY_FILENAME = "346_v18_3_global_multimarket_models_summary.txt"
COMPARISON_FILENAME = "347_v18_3_global_multimarket_model_comparison.csv"
PREDICTIONS_FILENAME = "348_v18_3_global_multimarket_test_predictions.csv"

RANDOM_STATE = 42

MARKETS = {
    "1X2": {
        "target_column": "target_1x2",
        "labels": ["TEAM_A_WIN", "DRAW", "TEAM_B_WIN"],
    },
    "OVER_1_5": {
        "target_column": "target_over_1_5",
        "labels": ["YES", "NO"],
    },
    "OVER_2_5": {
        "target_column": "target_over_2_5",
        "labels": ["YES", "NO"],
    },
    "BTTS": {
        "target_column": "target_btts",
        "labels": ["YES", "NO"],
    },
}

BASE_FEATURE_COLUMNS = [
    "home_form_points_last_5",
    "away_form_points_last_5",
    "home_form_points_last_10",
    "away_form_points_last_10",
    "home_goals_scored_avg_last_10",
    "away_goals_scored_avg_last_10",
    "home_goals_conceded_avg_last_10",
    "away_goals_conceded_avg_last_10",
    "elo_gap",
    "is_neutral_venue",
    "team_a_is_host",
    "team_b_is_host",
    "host_side_team_a",
    "host_side_team_b",
    "is_group_stage",
    "is_knockout_stage",
]

EXCLUDED_FEATURES = {
    "ranking_gap": "exclue car 100% manquante dans le dataset 345",
}

PREDICTION_METADATA_COLUMNS = [
    "clean_match_id",
    "feature_id",
    "feature_version",
    "match_date_utc",
    "season",
    "competition_code",
    "competition_name",
    "stage",
    "group_name",
    "team_a_name",
    "team_b_name",
    "team_a_score",
    "team_b_score",
    "total_goals",
    "target_1x2",
    "target_over_1_5",
    "target_over_2_5",
    "target_btts",
    "split_role",
]


@dataclass
class TrainedMarketResult:
    market: str
    target_column: str
    labels: list[str]
    best_model_name: str
    best_model: Pipeline
    best_metrics: dict[str, Any]
    comparison_rows: list[dict[str, Any]]
    report_text: str
    model_artifact_path: Path


# Prepare les arguments utilisables en ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Entrainer les baselines V18.3 global multi-market RubyBets."
    )

    parser.add_argument(
        "--dataset-path",
        default=str(DEFAULT_DATASET_PATH),
        help="Chemin du CSV 345 genere a l'etape precedente.",
    )

    parser.add_argument(
        "--output-dir",
        default=str(EVIDENCE_DIR),
        help="Dossier de sortie des preuves 346, 347 et 348.",
    )

    parser.add_argument(
        "--model-dir",
        default=str(MODEL_DIR),
        help="Dossier de sauvegarde des modeles entraines V18.3.",
    )

    return parser.parse_args()


# Cree les dossiers de sortie si necessaire.
def ensure_output_directories(output_dir: Path, model_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)


# Charge le dataset global V18.3 depuis le CSV 345.
def load_dataset(dataset_path: Path) -> pd.DataFrame:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset introuvable : {dataset_path}")

    dataframe = pd.read_csv(dataset_path)

    if dataframe.empty:
        raise ValueError("Le dataset V18.3 est vide.")

    return dataframe


# Verifie que les colonnes obligatoires existent dans le dataset.
def validate_dataset_columns(dataframe: pd.DataFrame, feature_columns: list[str]) -> None:
    required_columns = set(feature_columns + ["split_role"])

    for market_config in MARKETS.values():
        required_columns.add(str(market_config["target_column"]))

    missing_columns = sorted(required_columns - set(dataframe.columns))

    if missing_columns:
        raise ValueError(
            "Colonnes obligatoires absentes du dataset V18.3 : "
            + ", ".join(missing_columns)
        )


# Construit la liste finale des features utilisables pour l'entrainement.
def get_training_feature_columns(dataframe: pd.DataFrame) -> list[str]:
    available_features = [
        column for column in BASE_FEATURE_COLUMNS if column in dataframe.columns
    ]

    if not available_features:
        raise ValueError("Aucune feature d'entrainement disponible dans le dataset.")

    return available_features


# Separe les lignes train et test selon split_role.
def split_train_test(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_df = dataframe[dataframe["split_role"] == "train"].copy()
    test_df = dataframe[dataframe["split_role"] == "test"].copy()

    if train_df.empty or test_df.empty:
        raise ValueError("Le dataset doit contenir des lignes train et test.")

    return train_df, test_df


# Cree les modeles candidats a comparer pour chaque marche.
def build_candidate_models() -> dict[str, Pipeline]:
    return {
        "dummy_most_frequent": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("model", DummyClassifier(strategy="most_frequent")),
            ]
        ),
        "logistic_regression_balanced": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=3000,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
        "random_forest_balanced": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=350,
                        max_depth=12,
                        min_samples_leaf=10,
                        class_weight="balanced",
                        random_state=RANDOM_STATE,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }


# Calcule les metriques principales d'un modele pour un marche donne.
def compute_metrics(
    y_true: pd.Series,
    y_pred: pd.Series,
    labels: list[str],
) -> dict[str, float]:
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "balanced_accuracy": round(balanced_accuracy_score(y_true, y_pred), 4),
        "f1_macro": round(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0), 4),
        "f1_weighted": round(f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0), 4),
        "precision_macro": round(precision_score(y_true, y_pred, labels=labels, average="macro", zero_division=0), 4),
        "recall_macro": round(recall_score(y_true, y_pred, labels=labels, average="macro", zero_division=0), 4),
    }


# Convertit un nom de marche en prefixe de colonne CSV lisible.
def market_to_column_prefix(market: str) -> str:
    return market.lower().replace(".", "_").replace("/", "_")


# Choisit le meilleur modele selon F1 macro, puis accuracy.
def select_best_model(comparison_rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid_rows = [row for row in comparison_rows if row.get("status") == "OK"]

    if not valid_rows:
        raise RuntimeError("Aucun modele candidat n'a pu etre entraine correctement.")

    non_dummy_rows = [
        row for row in valid_rows if not str(row["model_name"]).startswith("dummy_")
    ]
    ranking_pool = non_dummy_rows or valid_rows

    return sorted(
        ranking_pool,
        key=lambda row: (float(row["f1_macro"]), float(row["accuracy"])),
        reverse=True,
    )[0]


# Genere un rapport de classification et une matrice de confusion en texte.
def build_model_report_text(
    market: str,
    model_name: str,
    y_true: pd.Series,
    y_pred: pd.Series,
    labels: list[str],
) -> str:
    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        zero_division=0,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=labels)

    lines = [
        f"Marche : {market}",
        f"Modele retenu : {model_name}",
        "",
        "Classification report :",
        report,
        "Matrice de confusion :",
        "Labels : " + ", ".join(labels),
    ]

    for label, row_values in zip(labels, matrix):
        values = ", ".join(str(int(value)) for value in row_values)
        lines.append(f"- {label} : [{values}]")

    return "\n".join(lines)


# Entraine et compare les modeles candidats pour un marche donne.
def train_market_models(
    market: str,
    target_column: str,
    labels: list[str],
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    model_dir: Path,
) -> TrainedMarketResult:
    market_train_df = train_df.dropna(subset=[target_column]).copy()
    market_test_df = test_df.dropna(subset=[target_column]).copy()

    if market_train_df.empty or market_test_df.empty:
        raise ValueError(f"Train ou test vide pour le marche {market}.")

    x_train = market_train_df[feature_columns]
    y_train = market_train_df[target_column].astype(str)
    x_test = market_test_df[feature_columns]
    y_test = market_test_df[target_column].astype(str)

    candidate_models = build_candidate_models()
    comparison_rows: list[dict[str, Any]] = []
    trained_models: dict[str, Pipeline] = {}

    for model_name, model in candidate_models.items():
        try:
            model.fit(x_train, y_train)
            y_pred = model.predict(x_test)
            metrics = compute_metrics(y_test, y_pred, labels)

            row = {
                "market": market,
                "target_column": target_column,
                "model_name": model_name,
                "status": "OK",
                "train_rows": len(market_train_df),
                "test_rows": len(market_test_df),
                "feature_count": len(feature_columns),
                **metrics,
                "error": "",
            }

            trained_models[model_name] = model
            comparison_rows.append(row)

        except Exception as error:
            comparison_rows.append(
                {
                    "market": market,
                    "target_column": target_column,
                    "model_name": model_name,
                    "status": "ERROR",
                    "train_rows": len(market_train_df),
                    "test_rows": len(market_test_df),
                    "feature_count": len(feature_columns),
                    "accuracy": "",
                    "balanced_accuracy": "",
                    "f1_macro": "",
                    "f1_weighted": "",
                    "precision_macro": "",
                    "recall_macro": "",
                    "error": str(error),
                }
            )

    best_row = select_best_model(comparison_rows)
    best_model_name = str(best_row["model_name"])
    best_model = trained_models[best_model_name]

    best_predictions = best_model.predict(x_test)
    report_text = build_model_report_text(
        market=market,
        model_name=best_model_name,
        y_true=y_test,
        y_pred=pd.Series(best_predictions),
        labels=labels,
    )

    model_artifact_path = model_dir / f"{market_to_column_prefix(market)}_best_model.joblib"
    joblib.dump(
        {
            "market": market,
            "target_column": target_column,
            "labels": labels,
            "feature_columns": feature_columns,
            "model_name": best_model_name,
            "model": best_model,
            "metrics": best_row,
        },
        model_artifact_path,
    )

    for row in comparison_rows:
        row["best_model_for_market"] = best_model_name
        row["model_artifact"] = str(model_artifact_path) if row["model_name"] == best_model_name else ""

    return TrainedMarketResult(
        market=market,
        target_column=target_column,
        labels=labels,
        best_model_name=best_model_name,
        best_model=best_model,
        best_metrics=best_row,
        comparison_rows=comparison_rows,
        report_text=report_text,
        model_artifact_path=model_artifact_path,
    )


# Ajoute les predictions et probabilites du meilleur modele dans le CSV 348.
def add_market_predictions_to_output(
    output_df: pd.DataFrame,
    test_df: pd.DataFrame,
    result: TrainedMarketResult,
    feature_columns: list[str],
) -> pd.DataFrame:
    prefix = market_to_column_prefix(result.market)
    x_test = test_df[feature_columns]

    predictions = result.best_model.predict(x_test)
    output_df[f"{prefix}_model"] = result.best_model_name
    output_df[f"{prefix}_prediction"] = predictions

    if hasattr(result.best_model, "predict_proba"):
        probabilities = result.best_model.predict_proba(x_test)
        model_classes = list(result.best_model.classes_)

        for label in result.labels:
            column_name = f"{prefix}_prob_{label}"
            if label in model_classes:
                label_index = model_classes.index(label)
                output_df[column_name] = probabilities[:, label_index].round(6)
            else:
                output_df[column_name] = 0.0

        output_df[f"{prefix}_max_probability"] = probabilities.max(axis=1).round(6)
    else:
        output_df[f"{prefix}_max_probability"] = ""

    return output_df


# Exporte le tableau de comparaison des modeles candidats.
def export_comparison_csv(
    comparison_rows: list[dict[str, Any]],
    output_dir: Path,
) -> Path:
    output_path = output_dir / COMPARISON_FILENAME

    fieldnames = [
        "market",
        "target_column",
        "model_name",
        "status",
        "train_rows",
        "test_rows",
        "feature_count",
        "accuracy",
        "balanced_accuracy",
        "f1_macro",
        "f1_weighted",
        "precision_macro",
        "recall_macro",
        "best_model_for_market",
        "model_artifact",
        "error",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison_rows)

    return output_path


# Exporte les predictions test des meilleurs modeles pour preparer le futur selecteur.
def export_predictions_csv(
    test_df: pd.DataFrame,
    market_results: list[TrainedMarketResult],
    feature_columns: list[str],
    output_dir: Path,
) -> Path:
    output_path = output_dir / PREDICTIONS_FILENAME
    metadata_columns = [
        column for column in PREDICTION_METADATA_COLUMNS if column in test_df.columns
    ]
    output_df = test_df[metadata_columns].copy().reset_index(drop=True)
    clean_test_df = test_df.reset_index(drop=True)

    for result in market_results:
        output_df = add_market_predictions_to_output(
            output_df=output_df,
            test_df=clean_test_df,
            result=result,
            feature_columns=feature_columns,
        )

    output_df.to_csv(output_path, index=False, encoding="utf-8")
    return output_path


# Formate la distribution d'une colonne cible pour le rapport texte.
def format_value_distribution(dataframe: pd.DataFrame, column: str) -> list[str]:
    counts = dataframe[column].value_counts(dropna=False)
    total = len(dataframe)
    lines = []

    for value, count in counts.items():
        percentage = round((count / total) * 100, 2) if total else 0.0
        lines.append(f"- {value} : {count} ({percentage}%)")

    return lines


# Exporte la synthese texte de l'entrainement V18.3 global multi-market.
def export_summary_txt(
    dataset_path: Path,
    dataframe: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    market_results: list[TrainedMarketResult],
    comparison_path: Path,
    predictions_path: Path,
    output_dir: Path,
) -> Path:
    output_path = output_dir / SUMMARY_FILENAME

    lines = [
        "OK - Entrainement V18.3 global multi-market termine.",
        "",
        "Contexte :",
        "- Phase : V18.3 national global multi-market.",
        "- Objectif : entrainer des baselines separees pour 1X2, OVER_1_5, OVER_2_5 et BTTS.",
        "- StatsBomb : non utilise dans cet entrainement global.",
        "- DOUBLE_CHANCE : non entrainee comme target separee, elle sera derivee plus tard des probabilites 1X2.",
        "- ABSTAIN : non entraine comme target, il sera produit plus tard par le selecteur selon les seuils.",
        f"- Dataset utilise : {dataset_path}",
        "",
        "Volume :",
        f"- Lignes totales : {len(dataframe)}",
        f"- Train rows : {len(train_df)}",
        f"- Test rows : {len(test_df)}",
        f"- Features utilisees : {len(feature_columns)}",
        "",
        "Features utilisees :",
    ]

    for feature_name in feature_columns:
        missing_count = int(dataframe[feature_name].isna().sum())
        missing_pct = round((missing_count / len(dataframe)) * 100, 2) if len(dataframe) else 0.0
        lines.append(f"- {feature_name} | missing={missing_count} ({missing_pct}%)")

    lines.extend(["", "Features exclues :"])

    for feature_name, reason in EXCLUDED_FEATURES.items():
        lines.append(f"- {feature_name} : {reason}")

    lines.extend(["", "Distribution des targets sur le test :"])

    for market, config in MARKETS.items():
        target_column = str(config["target_column"])
        lines.append(f"\n{market} ({target_column}) :")
        lines.extend(format_value_distribution(test_df, target_column))

    lines.extend(["", "Meilleurs modeles retenus :"])

    for result in market_results:
        metrics = result.best_metrics
        lines.extend(
            [
                f"\n{result.market} :",
                f"- Best model : {result.best_model_name}",
                f"- Accuracy : {metrics['accuracy']}",
                f"- Balanced accuracy : {metrics['balanced_accuracy']}",
                f"- F1 macro : {metrics['f1_macro']}",
                f"- F1 weighted : {metrics['f1_weighted']}",
                f"- Precision macro : {metrics['precision_macro']}",
                f"- Recall macro : {metrics['recall_macro']}",
                f"- Model artifact : {result.model_artifact_path}",
            ]
        )

    lines.extend(["", "Rapports detailles des meilleurs modeles :", ""])

    for result in market_results:
        lines.append("=" * 80)
        lines.append(result.report_text)
        lines.append("")

    lines.extend(
        [
            "Fichiers generes :",
            f"- Synthese : {output_path}",
            f"- Comparaison modeles : {comparison_path}",
            f"- Predictions test : {predictions_path}",
            "",
            "Decision technique :",
            "- Cette etape produit une baseline globale pour chaque marche.",
            "- Le futur selecteur V18.3 devra comparer les probabilites et choisir entre STRICT_1X2, DOUBLE_CHANCE, OVER_1_5, OVER_2_5, BTTS ou ABSTAIN.",
            "- OVER_1_5 doit etre surveille car sa classe YES est tres majoritaire dans le dataset.",
            "- Les resultats restent experimentaux et ne promettent aucun resultat sportif.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# Affiche un resume court dans le terminal.
def print_terminal_summary(
    dataframe: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    market_results: list[TrainedMarketResult],
    summary_path: Path,
    comparison_path: Path,
    predictions_path: Path,
) -> None:
    print("OK - Entrainement V18.3 global multi-market termine.")
    print(f"Lignes totales : {len(dataframe)}")
    print(f"Train rows : {len(train_df)}")
    print(f"Test rows : {len(test_df)}")

    for result in market_results:
        metrics = result.best_metrics
        print(
            f"{result.market} best={result.best_model_name} "
            f"accuracy={metrics['accuracy']} f1_macro={metrics['f1_macro']}"
        )

    print(f"Summary saved: {summary_path}")
    print(f"Comparison CSV saved: {comparison_path}")
    print(f"Predictions CSV saved: {predictions_path}")


# Orchestre l'entrainement complet des baselines V18.3 globales.
def main() -> None:
    try:
        args = parse_arguments()
        dataset_path = Path(args.dataset_path)
        output_dir = Path(args.output_dir)
        model_dir = Path(args.model_dir)

        ensure_output_directories(output_dir=output_dir, model_dir=model_dir)

        dataframe = load_dataset(dataset_path=dataset_path)
        feature_columns = get_training_feature_columns(dataframe=dataframe)
        validate_dataset_columns(dataframe=dataframe, feature_columns=feature_columns)
        train_df, test_df = split_train_test(dataframe=dataframe)

        market_results: list[TrainedMarketResult] = []
        all_comparison_rows: list[dict[str, Any]] = []

        for market, config in MARKETS.items():
            result = train_market_models(
                market=market,
                target_column=str(config["target_column"]),
                labels=list(config["labels"]),
                train_df=train_df,
                test_df=test_df,
                feature_columns=feature_columns,
                model_dir=model_dir,
            )
            market_results.append(result)
            all_comparison_rows.extend(result.comparison_rows)

        comparison_path = export_comparison_csv(
            comparison_rows=all_comparison_rows,
            output_dir=output_dir,
        )
        predictions_path = export_predictions_csv(
            test_df=test_df,
            market_results=market_results,
            feature_columns=feature_columns,
            output_dir=output_dir,
        )
        summary_path = export_summary_txt(
            dataset_path=dataset_path,
            dataframe=dataframe,
            train_df=train_df,
            test_df=test_df,
            feature_columns=feature_columns,
            market_results=market_results,
            comparison_path=comparison_path,
            predictions_path=predictions_path,
            output_dir=output_dir,
        )

        print_terminal_summary(
            dataframe=dataframe,
            train_df=train_df,
            test_df=test_df,
            market_results=market_results,
            summary_path=summary_path,
            comparison_path=comparison_path,
            predictions_path=predictions_path,
        )

    except Exception as error:
        print("Erreur pendant l'entrainement V18.3 global multi-market.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schema de communication :
# reports/evidence/ml_training/345_v18_3_global_multimarket_dataset.csv
#     ↓
# train_v18_3_global_multimarket_models.py
#     ↓
# models/ml_national/v18_3_global_multimarket/*.joblib
# reports/evidence/ml_training/346_v18_3_global_multimarket_models_summary.txt
# reports/evidence/ml_training/347_v18_3_global_multimarket_model_comparison.csv
# reports/evidence/ml_training/348_v18_3_global_multimarket_test_predictions.csv
#     ↓
# futur diagnose_v18_3_global_multimarket_models.py
# futur evaluate_v18_3_global_selector.py
