# Rôle du fichier :
# Ce script entraîne une première baseline ML nationale V17.9
# à partir des features ml_national.features, sans modifier le modèle club V17.8.

from pathlib import Path
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from decimal import Decimal

import joblib
import pandas as pd
import psycopg
from psycopg.rows import dict_row

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"

EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
MODEL_DIR = PROJECT_ROOT / "models" / "ml" / "national"

DEFAULT_FEATURE_VERSION = "national_v1_elo_form"
DEFAULT_MODEL_VERSION = "v17_9_national_baseline"
DEFAULT_TEST_RATIO = 0.20
DEFAULT_RANDOM_STATE = 42

SUMMARY_FILENAME = "303_national_v17_9_baseline_summary.txt"
COMPARISON_FILENAME = "304_national_v17_9_model_comparison.csv"
BEST_REPORT_FILENAME = "305_national_v17_9_best_model_report.txt"
PREDICTIONS_FILENAME = "306_national_v17_9_predictions.csv"

MODEL_FILENAME = "v17_9_national_baseline.joblib"
METADATA_FILENAME = "v17_9_national_baseline_metadata.json"

TARGET_COLUMN = "target_result"

BASE_FEATURE_COLUMNS = [
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
    "is_group_stage",
    "is_knockout_stage",
    "host_side_team_a",
    "host_side_team_b",
]

TARGET_LABELS = [
    "TEAM_A_WIN",
    "DRAW",
    "TEAM_B_WIN",
]


# Charge les variables du fichier backend/.env sans afficher de secret.
def load_env_file() -> None:
    if not ENV_PATH.exists():
        raise FileNotFoundError(f"Fichier .env introuvable : {ENV_PATH}")

    with ENV_PATH.open("r", encoding="utf-8") as env_file:
        for line in env_file:
            clean_line = line.strip()

            if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                continue

            key, value = clean_line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Récupère l'URL PostgreSQL depuis backend/.env.
def get_database_url() -> str:
    load_env_file()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL est absent du fichier backend/.env")

    return database_url


# Prépare les arguments utilisables en ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Entraîner la baseline nationale RubyBets V17.9."
    )

    parser.add_argument(
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help="Version des features à charger depuis ml_national.features.",
    )

    parser.add_argument(
        "--model-version",
        default=DEFAULT_MODEL_VERSION,
        help="Nom/version du modèle sauvegardé.",
    )

    parser.add_argument(
        "--test-ratio",
        type=float,
        default=DEFAULT_TEST_RATIO,
        help="Part chronologique réservée au test. Par défaut : 0.20.",
    )

    parser.add_argument(
        "--random-state",
        type=int,
        default=DEFAULT_RANDOM_STATE,
        help="Seed pour les modèles reproductibles.",
    )

    return parser.parse_args()


# Crée les dossiers nécessaires aux preuves et aux modèles.
def ensure_output_directories() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


# Convertit une valeur PostgreSQL en valeur compatible pandas/json.
def normalize_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        return value.isoformat()

    return value


# Charge les features nationales depuis PostgreSQL.
def fetch_national_features(
    connection: psycopg.Connection,
    feature_version: str,
) -> pd.DataFrame:
    query = """
        SELECT
            f.clean_match_id,
            f.feature_version,
            cm.match_date_utc,
            cm.competition_code,
            cm.season,
            cm.home_team_name AS team_a_name,
            cm.away_team_name AS team_b_name,

            f.home_form_points_last_10,
            f.away_form_points_last_10,
            f.home_goals_scored_avg_last_10,
            f.away_goals_scored_avg_last_10,
            f.home_goals_conceded_avg_last_10,
            f.away_goals_conceded_avg_last_10,
            f.elo_gap,
            f.is_neutral_venue,
            f.team_a_is_host,
            f.team_b_is_host,
            f.host_advantage_side,
            f.is_group_stage,
            f.is_knockout_stage,
            f.target_result

        FROM ml_national.features f
        JOIN ml_national.clean_matches cm
            ON cm.id = f.clean_match_id
        WHERE f.feature_version = %s
          AND f.target_result IN ('TEAM_A_WIN', 'DRAW', 'TEAM_B_WIN')
        ORDER BY cm.match_date_utc ASC, f.clean_match_id ASC
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (feature_version,))
        rows = cursor.fetchall()

    normalized_rows = [
        {key: normalize_value(value) for key, value in row.items()}
        for row in rows
    ]

    return pd.DataFrame(normalized_rows)


# Prépare les colonnes numériques et les indicateurs exploitables par scikit-learn.
def prepare_dataframe(raw_dataframe: pd.DataFrame) -> pd.DataFrame:
    if raw_dataframe.empty:
        raise ValueError("Aucune feature nationale trouvée pour cette version.")

    dataframe = raw_dataframe.copy()

    dataframe["match_date_utc"] = pd.to_datetime(
    dataframe["match_date_utc"],
    utc=True,
    )

    dataframe["host_side_team_a"] = (
        dataframe["host_advantage_side"].fillna("NONE") == "TEAM_A"
    ).astype(int)

    dataframe["host_side_team_b"] = (
        dataframe["host_advantage_side"].fillna("NONE") == "TEAM_B"
    ).astype(int)

    boolean_columns = [
        "is_neutral_venue",
        "team_a_is_host",
        "team_b_is_host",
        "is_group_stage",
        "is_knockout_stage",
    ]

    for column in boolean_columns:
        dataframe[column] = dataframe[column].fillna(False).astype(int)

    numeric_columns = [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "elo_gap",
        "host_side_team_a",
        "host_side_team_b",
    ] + boolean_columns

    for column in numeric_columns:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    dataframe = dataframe.sort_values(
        by=["match_date_utc", "clean_match_id"]
    ).reset_index(drop=True)

    return dataframe


# Découpe les données en train/test avec une logique chronologique.
def split_train_test(
    dataframe: pd.DataFrame,
    test_ratio: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0 < test_ratio < 0.5:
        raise ValueError("test_ratio doit être compris entre 0 et 0.5.")

    split_index = int(len(dataframe) * (1 - test_ratio))

    if split_index <= 0 or split_index >= len(dataframe):
        raise ValueError("Split chronologique impossible avec ce volume de données.")

    train_dataframe = dataframe.iloc[:split_index].copy()
    test_dataframe = dataframe.iloc[split_index:].copy()

    return train_dataframe, test_dataframe


# Construit les modèles baseline à comparer.
def build_models(random_state: int) -> dict[str, object]:
    return {
        "dummy_most_frequent": DummyClassifier(
            strategy="most_frequent"
        ),
        "logistic_regression_balanced": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ]
        ),
        "random_forest_balanced": Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=300,
                        max_depth=12,
                        min_samples_leaf=5,
                        class_weight="balanced",
                        random_state=random_state,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }


# Calcule les métriques principales d'un modèle.
def evaluate_model(
    model_name: str,
    model: object,
    train_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
) -> dict[str, object]:
    x_train = train_dataframe[BASE_FEATURE_COLUMNS]
    y_train = train_dataframe[TARGET_COLUMN]

    x_test = test_dataframe[BASE_FEATURE_COLUMNS]
    y_test = test_dataframe[TARGET_COLUMN]

    model.fit(x_train, y_train)
    predictions = model.predict(x_test)

    accuracy = accuracy_score(y_test, predictions)
    f1_macro = f1_score(y_test, predictions, average="macro")
    f1_weighted = f1_score(y_test, predictions, average="weighted")

    report = classification_report(
        y_test,
        predictions,
        labels=TARGET_LABELS,
        zero_division=0,
        output_dict=True,
    )

    matrix = confusion_matrix(
        y_test,
        predictions,
        labels=TARGET_LABELS,
    )

    return {
        "model_name": model_name,
        "model": model,
        "accuracy": accuracy,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted,
        "classification_report": report,
        "confusion_matrix": matrix,
        "predictions": predictions,
    }


# Entraîne et évalue tous les modèles candidats.
def train_and_evaluate_models(
    train_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
    random_state: int,
) -> list[dict[str, object]]:
    models = build_models(random_state=random_state)
    results = []

    for model_name, model in models.items():
        print(f"Entraînement du modèle national : {model_name}")

        result = evaluate_model(
            model_name=model_name,
            model=model,
            train_dataframe=train_dataframe,
            test_dataframe=test_dataframe,
        )

        results.append(result)

    return results


# Sélectionne le meilleur modèle selon F1 macro, puis accuracy en cas d'égalité.
def select_best_model(results: list[dict[str, object]]) -> dict[str, object]:
    candidate_results = [
        result
        for result in results
        if result["model_name"] != "dummy_most_frequent"
    ]

    if not candidate_results:
        candidate_results = results

    return max(
        candidate_results,
        key=lambda result: (result["f1_macro"], result["accuracy"]),
    )


# Exporte le tableau comparatif des modèles.
def export_model_comparison(results: list[dict[str, object]]) -> Path:
    ensure_output_directories()
    output_path = EVIDENCE_DIR / COMPARISON_FILENAME

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)

        writer.writerow(
            [
                "model_name",
                "accuracy",
                "f1_macro",
                "f1_weighted",
                "draw_precision",
                "draw_recall",
                "draw_f1",
            ]
        )

        for result in results:
            draw_metrics = result["classification_report"].get("DRAW", {})

            writer.writerow(
                [
                    result["model_name"],
                    round(result["accuracy"], 4),
                    round(result["f1_macro"], 4),
                    round(result["f1_weighted"], 4),
                    round(draw_metrics.get("precision", 0), 4),
                    round(draw_metrics.get("recall", 0), 4),
                    round(draw_metrics.get("f1-score", 0), 4),
                ]
            )

    return output_path


# Exporte les prédictions du meilleur modèle sur le test set.
def export_best_predictions(
    test_dataframe: pd.DataFrame,
    best_result: dict[str, object],
) -> Path:
    ensure_output_directories()
    output_path = EVIDENCE_DIR / PREDICTIONS_FILENAME

    predictions = best_result["predictions"]

    export_dataframe = test_dataframe[
        [
            "clean_match_id",
            "match_date_utc",
            "competition_code",
            "season",
            "team_a_name",
            "team_b_name",
            TARGET_COLUMN,
        ]
    ].copy()

    export_dataframe["predicted_result"] = predictions
    export_dataframe["is_correct"] = (
        export_dataframe[TARGET_COLUMN] == export_dataframe["predicted_result"]
    )

    export_dataframe.to_csv(output_path, index=False, encoding="utf-8")

    return output_path


# Exporte le rapport détaillé du meilleur modèle.
def export_best_model_report(
    best_result: dict[str, object],
) -> Path:
    ensure_output_directories()
    output_path = EVIDENCE_DIR / BEST_REPORT_FILENAME

    report_dict = best_result["classification_report"]
    confusion = best_result["confusion_matrix"]

    lines = [
        "Rapport détaillé - meilleur modèle national V17.9 baseline",
        "",
        f"Meilleur modèle : {best_result['model_name']}",
        f"Accuracy test : {round(best_result['accuracy'], 4)}",
        f"F1 macro test : {round(best_result['f1_macro'], 4)}",
        f"F1 weighted test : {round(best_result['f1_weighted'], 4)}",
        "",
        "Classification report :",
    ]

    for label in TARGET_LABELS:
        metrics = report_dict.get(label, {})

        lines.extend(
            [
                f"- {label}",
                f"  precision : {round(metrics.get('precision', 0), 4)}",
                f"  recall    : {round(metrics.get('recall', 0), 4)}",
                f"  f1-score  : {round(metrics.get('f1-score', 0), 4)}",
                f"  support   : {int(metrics.get('support', 0))}",
            ]
        )

    lines.extend(
        [
            "",
            "Confusion matrix :",
            "Labels : TEAM_A_WIN, DRAW, TEAM_B_WIN",
        ]
    )

    for row in confusion.tolist():
        lines.append(str(row))

    lines.extend(
        [
            "",
            "Note méthodologique :",
            "- Le split est chronologique pour simuler un usage réel avant-match.",
            "- Le modèle V17.9 national ne remplace pas V17.8 club.",
            "- Les colonnes home_* / away_* représentent Team A / Team B dans ce pipeline national.",
            "- Les scores ne constituent pas une promesse de résultat sportif.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return output_path


# Sauvegarde le meilleur modèle et ses métadonnées.
def save_best_model(
    best_result: dict[str, object],
    train_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[Path, Path]:
    ensure_output_directories()

    model_path = MODEL_DIR / MODEL_FILENAME
    metadata_path = MODEL_DIR / METADATA_FILENAME

    joblib.dump(best_result["model"], model_path)

    metadata = {
        "source": "rubybets_ml_national",
        "scope": "experimental",
        "status": "baseline_review",
        "model_version": args.model_version,
        "model_name": best_result["model_name"],
        "feature_version": args.feature_version,
        "target": TARGET_COLUMN,
        "target_classes": TARGET_LABELS,
        "features_used": BASE_FEATURE_COLUMNS,
        "split_strategy": "chronological",
        "test_ratio": args.test_ratio,
        "train_rows": int(len(train_dataframe)),
        "test_rows": int(len(test_dataframe)),
        "train_start_date": train_dataframe["match_date_utc"].min().isoformat(),
        "train_end_date": train_dataframe["match_date_utc"].max().isoformat(),
        "test_start_date": test_dataframe["match_date_utc"].min().isoformat(),
        "test_end_date": test_dataframe["match_date_utc"].max().isoformat(),
        "evaluation_results": {
            "accuracy": round(best_result["accuracy"], 4),
            "f1_macro": round(best_result["f1_macro"], 4),
            "f1_weighted": round(best_result["f1_weighted"], 4),
        },
        "model_artifact": str(model_path.relative_to(PROJECT_ROOT)),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "important_note": (
            "Baseline nationale expérimentale. Ne remplace pas le modèle club V17.8 "
            "et ne garantit aucun résultat sportif."
        ),
    }

    metadata_path.write_text(
        json.dumps(metadata, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )

    return model_path, metadata_path


# Exporte un résumé global de l'entraînement.
def export_summary_txt(
    dataframe: pd.DataFrame,
    train_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
    results: list[dict[str, object]],
    best_result: dict[str, object],
    comparison_path: Path,
    report_path: Path,
    predictions_path: Path,
    model_path: Path,
    metadata_path: Path,
    args: argparse.Namespace,
) -> Path:
    ensure_output_directories()
    output_path = EVIDENCE_DIR / SUMMARY_FILENAME

    target_distribution = dataframe[TARGET_COLUMN].value_counts().to_dict()
    train_distribution = train_dataframe[TARGET_COLUMN].value_counts().to_dict()
    test_distribution = test_dataframe[TARGET_COLUMN].value_counts().to_dict()

    lines = [
        "OK - Entraînement V17.9 national baseline terminé.",
        f"Feature version : {args.feature_version}",
        f"Features chargées : {len(dataframe)}",
        f"Train rows : {len(train_dataframe)}",
        f"Test rows : {len(test_dataframe)}",
        f"Train période : {train_dataframe['match_date_utc'].min().date()} -> {train_dataframe['match_date_utc'].max().date()}",
        f"Test période : {test_dataframe['match_date_utc'].min().date()} -> {test_dataframe['match_date_utc'].max().date()}",
        "",
        "Features utilisées :",
    ]

    for feature_name in BASE_FEATURE_COLUMNS:
        lines.append(f"- {feature_name}")

    lines.extend(
        [
            "",
            "Distribution target globale :",
        ]
    )

    for label, count in target_distribution.items():
        lines.append(f"- {label}: {count}")

    lines.extend(
        [
            "",
            "Distribution target train :",
        ]
    )

    for label, count in train_distribution.items():
        lines.append(f"- {label}: {count}")

    lines.extend(
        [
            "",
            "Distribution target test :",
        ]
    )

    for label, count in test_distribution.items():
        lines.append(f"- {label}: {count}")

    lines.extend(
        [
            "",
            "Comparaison modèles :",
        ]
    )

    for result in results:
        lines.append(
            f"- {result['model_name']} | "
            f"accuracy={round(result['accuracy'], 4)} | "
            f"f1_macro={round(result['f1_macro'], 4)} | "
            f"f1_weighted={round(result['f1_weighted'], 4)}"
        )

    lines.extend(
        [
            "",
            f"Meilleur modèle : {best_result['model_name']}",
            f"Accuracy test : {round(best_result['accuracy'], 4)}",
            f"F1 macro test : {round(best_result['f1_macro'], 4)}",
            f"F1 weighted test : {round(best_result['f1_weighted'], 4)}",
            "",
            f"Comparaison sauvegardée : {comparison_path}",
            f"Rapport meilleur modèle : {report_path}",
            f"Prédictions test : {predictions_path}",
            f"Modèle sauvegardé : {model_path}",
            f"Métadonnées sauvegardées : {metadata_path}",
            "",
            "Décision technique :",
            "- Ce modèle est une baseline nationale expérimentale.",
            "- Il sert à mesurer le potentiel Kaggle + Elo avant enrichissement StatsBomb.",
            "- Il ne remplace pas le modèle club V17.8.",
            "- Il ne doit pas être présenté comme une garantie de résultat sportif.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return output_path


# Affiche un résumé court dans le terminal.
def print_summary(
    dataframe: pd.DataFrame,
    train_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
    best_result: dict[str, object],
    summary_path: Path,
    model_path: Path,
) -> None:
    print("OK - Entraînement V17.9 national baseline terminé.")
    print(f"Features chargées : {len(dataframe)}")
    print(f"Train rows : {len(train_dataframe)}")
    print(f"Test rows : {len(test_dataframe)}")
    print(f"Meilleur modèle : {best_result['model_name']}")
    print(f"Accuracy test : {round(best_result['accuracy'], 4)}")
    print(f"F1 macro test : {round(best_result['f1_macro'], 4)}")
    print(f"F1 weighted test : {round(best_result['f1_weighted'], 4)}")
    print(f"Rapport sauvegardé : {summary_path}")
    print(f"Modèle sauvegardé : {model_path}")


# Exécute l'entraînement complet de la baseline nationale V17.9.
def main() -> None:
    try:
        args = parse_arguments()
        ensure_output_directories()

        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            raw_dataframe = fetch_national_features(
                connection=connection,
                feature_version=args.feature_version,
            )

        dataframe = prepare_dataframe(raw_dataframe)

        train_dataframe, test_dataframe = split_train_test(
            dataframe=dataframe,
            test_ratio=args.test_ratio,
        )

        print(f"Features nationales chargées : {len(dataframe)}")
        print(f"Train rows : {len(train_dataframe)}")
        print(f"Test rows : {len(test_dataframe)}")

        results = train_and_evaluate_models(
            train_dataframe=train_dataframe,
            test_dataframe=test_dataframe,
            random_state=args.random_state,
        )

        best_result = select_best_model(results)

        comparison_path = export_model_comparison(results)
        predictions_path = export_best_predictions(test_dataframe, best_result)
        report_path = export_best_model_report(best_result)

        model_path, metadata_path = save_best_model(
            best_result=best_result,
            train_dataframe=train_dataframe,
            test_dataframe=test_dataframe,
            args=args,
        )

        summary_path = export_summary_txt(
            dataframe=dataframe,
            train_dataframe=train_dataframe,
            test_dataframe=test_dataframe,
            results=results,
            best_result=best_result,
            comparison_path=comparison_path,
            report_path=report_path,
            predictions_path=predictions_path,
            model_path=model_path,
            metadata_path=metadata_path,
            args=args,
        )

        print_summary(
            dataframe=dataframe,
            train_dataframe=train_dataframe,
            test_dataframe=test_dataframe,
            best_result=best_result,
            summary_path=summary_path,
            model_path=model_path,
        )

    except Exception as error:
        print("Erreur pendant l'entraînement V17.9 national baseline.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# ml_national.features
#        ↓
# backend/scripts/ml_national/train_national_v17_9_baseline.py
#        ↓
# reports/evidence/ml_training/
#        ↓
# models/ml/national/
#        ↓
# futur diagnostic V17.9 + décision enrichissement StatsBomb