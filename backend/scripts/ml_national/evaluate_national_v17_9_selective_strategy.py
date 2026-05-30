# Rôle du fichier :
# Ce script évalue des stratégies sélectives pour la baseline nationale V17.9.
# L'objectif est de garder les prédictions les plus fiables et d'abstenir les matchs trop incertains.

from pathlib import Path
import argparse
import csv
import os
import sys
from decimal import Decimal

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from sklearn.metrics import accuracy_score, f1_score


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"

EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

DEFAULT_FEATURE_VERSION = "national_v1_elo_form"
DEFAULT_PREDICTIONS_FILE = EVIDENCE_DIR / "306_national_v17_9_predictions.csv"

SUMMARY_FILENAME = "311_national_v17_9_selective_strategy_summary.txt"
RESULTS_FILENAME = "312_national_v17_9_selective_strategy_results.csv"
BEST_SELECTION_FILENAME = "313_national_v17_9_best_selective_predictions.csv"

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
        description="Évaluer des stratégies sélectives pour RubyBets V17.9 national."
    )

    parser.add_argument(
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help="Version des features utilisée pour l'évaluation.",
    )

    parser.add_argument(
        "--predictions-file",
        default=str(DEFAULT_PREDICTIONS_FILE),
        help="Chemin du CSV 306_national_v17_9_predictions.csv.",
    )

    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.20,
        help="Couverture minimale pour choisir une stratégie. Par défaut : 0.20.",
    )

    return parser.parse_args()


# Crée le dossier de preuves ML si nécessaire.
def ensure_evidence_directory() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# Convertit les valeurs PostgreSQL numériques en float.
def normalize_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)

    return value


# Charge les prédictions produites par la baseline V17.9.
def load_predictions(predictions_file: str) -> pd.DataFrame:
    predictions_path = Path(predictions_file)

    if not predictions_path.exists():
        raise FileNotFoundError(f"Fichier de prédictions introuvable : {predictions_path}")

    dataframe = pd.read_csv(predictions_path)

    required_columns = {
        "clean_match_id",
        "target_result",
        "predicted_result",
        "is_correct",
    }

    missing_columns = required_columns - set(dataframe.columns)

    if missing_columns:
        raise ValueError(f"Colonnes manquantes dans le CSV prédictions : {missing_columns}")

    dataframe["clean_match_id"] = dataframe["clean_match_id"].astype(int)
    dataframe["is_correct"] = dataframe["is_correct"].astype(str).str.lower().isin(
        ["true", "1", "yes"]
    )

    return dataframe


# Récupère le contexte des features nécessaire aux stratégies sélectives.
def fetch_feature_context(
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


# Fusionne les prédictions avec les features nécessaires à l'évaluation.
def build_evaluation_dataframe(
    predictions_dataframe: pd.DataFrame,
    feature_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    prediction_columns_to_drop = [
        "match_date_utc",
        "competition_code",
        "season",
        "team_a_name",
        "team_b_name",
    ]

    clean_predictions_dataframe = predictions_dataframe.drop(
        columns=prediction_columns_to_drop,
        errors="ignore",
    )

    evaluation_dataframe = clean_predictions_dataframe.merge(
        feature_dataframe.drop(columns=["target_result"], errors="ignore"),
        on="clean_match_id",
        how="left",
    )

    if "match_date_utc" not in evaluation_dataframe.columns:
        raise ValueError(
            "La colonne match_date_utc est absente après fusion des prédictions et des features."
        )

    evaluation_dataframe["match_date_utc"] = pd.to_datetime(
        evaluation_dataframe["match_date_utc"],
        utc=True,
    )

    evaluation_dataframe["elo_gap"] = pd.to_numeric(
        evaluation_dataframe["elo_gap"],
        errors="coerce",
    )

    evaluation_dataframe["abs_elo_gap"] = evaluation_dataframe["elo_gap"].abs()
    evaluation_dataframe["host_advantage_side"] = evaluation_dataframe[
        "host_advantage_side"
    ].fillna("NONE")

    boolean_columns = [
        "is_neutral_venue",
        "team_a_is_host",
        "team_b_is_host",
        "is_group_stage",
        "is_knockout_stage",
    ]

    for column in boolean_columns:
        evaluation_dataframe[column] = evaluation_dataframe[column].fillna(False)

    return evaluation_dataframe


# Construit les masques de sélection à tester.
def build_strategy_masks(dataframe: pd.DataFrame) -> dict[str, pd.Series]:
    masks = {
        "all_predictions": pd.Series(True, index=dataframe.index),
        "abs_elo_gap_50_plus": dataframe["abs_elo_gap"] >= 50,
        "abs_elo_gap_100_plus": dataframe["abs_elo_gap"] >= 100,
        "abs_elo_gap_150_plus": dataframe["abs_elo_gap"] >= 150,
        "abs_elo_gap_200_plus": dataframe["abs_elo_gap"] >= 200,
        "abs_elo_gap_300_plus": dataframe["abs_elo_gap"] >= 300,
        "abs_elo_gap_400_plus": dataframe["abs_elo_gap"] >= 400,
        "abs_elo_gap_100_plus_no_predicted_draw": (
            (dataframe["abs_elo_gap"] >= 100)
            & (dataframe["predicted_result"] != "DRAW")
        ),
        "abs_elo_gap_150_plus_no_predicted_draw": (
            (dataframe["abs_elo_gap"] >= 150)
            & (dataframe["predicted_result"] != "DRAW")
        ),
        "abs_elo_gap_200_plus_no_predicted_draw": (
            (dataframe["abs_elo_gap"] >= 200)
            & (dataframe["predicted_result"] != "DRAW")
        ),
        "wc_only_all_predictions": dataframe["competition_code"] == "WC",
        "wcq_only_all_predictions": dataframe["competition_code"] == "WCQ",
        "wc_abs_elo_gap_100_plus": (
            (dataframe["competition_code"] == "WC")
            & (dataframe["abs_elo_gap"] >= 100)
        ),
        "wcq_abs_elo_gap_100_plus": (
            (dataframe["competition_code"] == "WCQ")
            & (dataframe["abs_elo_gap"] >= 100)
        ),
        "neutral_abs_elo_gap_100_plus": (
            (dataframe["is_neutral_venue"] == True)
            & (dataframe["abs_elo_gap"] >= 100)
        ),
        "non_neutral_abs_elo_gap_100_plus": (
            (dataframe["is_neutral_venue"] == False)
            & (dataframe["abs_elo_gap"] >= 100)
        ),
    }

    return masks


# Évalue une stratégie de sélection donnée.
def evaluate_strategy(
    dataframe: pd.DataFrame,
    strategy_name: str,
    mask: pd.Series,
) -> dict[str, object]:
    total_rows = len(dataframe)
    selected_dataframe = dataframe[mask].copy()
    selected_rows = len(selected_dataframe)

    coverage = selected_rows / total_rows if total_rows else 0
    abstention_rate = 1 - coverage

    if selected_dataframe.empty:
        return {
            "strategy_name": strategy_name,
            "selected_rows": 0,
            "total_rows": total_rows,
            "coverage": 0,
            "abstention_rate": 1,
            "accuracy": None,
            "f1_macro": None,
            "f1_weighted": None,
            "team_a_win_rows": 0,
            "draw_rows": 0,
            "team_b_win_rows": 0,
            "draw_accuracy": None,
            "wc_rows": 0,
            "wc_accuracy": None,
            "wcq_rows": 0,
            "wcq_accuracy": None,
        }

    y_true = selected_dataframe["target_result"]
    y_pred = selected_dataframe["predicted_result"]

    draw_dataframe = selected_dataframe[selected_dataframe["target_result"] == "DRAW"]
    wc_dataframe = selected_dataframe[selected_dataframe["competition_code"] == "WC"]
    wcq_dataframe = selected_dataframe[selected_dataframe["competition_code"] == "WCQ"]

    draw_accuracy = None
    if not draw_dataframe.empty:
        draw_accuracy = accuracy_score(
            draw_dataframe["target_result"],
            draw_dataframe["predicted_result"],
        )

    wc_accuracy = None
    if not wc_dataframe.empty:
        wc_accuracy = accuracy_score(
            wc_dataframe["target_result"],
            wc_dataframe["predicted_result"],
        )

    wcq_accuracy = None
    if not wcq_dataframe.empty:
        wcq_accuracy = accuracy_score(
            wcq_dataframe["target_result"],
            wcq_dataframe["predicted_result"],
        )

    return {
        "strategy_name": strategy_name,
        "selected_rows": selected_rows,
        "total_rows": total_rows,
        "coverage": round(coverage, 4),
        "abstention_rate": round(abstention_rate, 4),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "f1_macro": round(
            f1_score(
                y_true,
                y_pred,
                average="macro",
                labels=TARGET_LABELS,
                zero_division=0,
            ),
            4,
        ),
        "f1_weighted": round(
            f1_score(
                y_true,
                y_pred,
                average="weighted",
                labels=TARGET_LABELS,
                zero_division=0,
            ),
            4,
        ),
        "team_a_win_rows": int((selected_dataframe["target_result"] == "TEAM_A_WIN").sum()),
        "draw_rows": int((selected_dataframe["target_result"] == "DRAW").sum()),
        "team_b_win_rows": int((selected_dataframe["target_result"] == "TEAM_B_WIN").sum()),
        "draw_accuracy": round(draw_accuracy, 4) if draw_accuracy is not None else None,
        "wc_rows": int(len(wc_dataframe)),
        "wc_accuracy": round(wc_accuracy, 4) if wc_accuracy is not None else None,
        "wcq_rows": int(len(wcq_dataframe)),
        "wcq_accuracy": round(wcq_accuracy, 4) if wcq_accuracy is not None else None,
    }


# Évalue toutes les stratégies.
def evaluate_all_strategies(dataframe: pd.DataFrame) -> list[dict[str, object]]:
    strategy_masks = build_strategy_masks(dataframe)

    results = []

    for strategy_name, mask in strategy_masks.items():
        results.append(
            evaluate_strategy(
                dataframe=dataframe,
                strategy_name=strategy_name,
                mask=mask,
            )
        )

    return results


# Choisit la meilleure stratégie selon accuracy, couverture minimale et prudence.
def select_best_strategy(
    strategy_results: list[dict[str, object]],
    min_coverage: float,
) -> dict[str, object]:
    eligible_results = [
        result
        for result in strategy_results
        if result["strategy_name"] != "all_predictions"
        and result["accuracy"] is not None
        and result["coverage"] >= min_coverage
    ]

    if not eligible_results:
        eligible_results = [
            result
            for result in strategy_results
            if result["accuracy"] is not None
        ]

    return max(
        eligible_results,
        key=lambda result: (
            result["accuracy"],
            result["f1_macro"] or 0,
            result["coverage"],
        ),
    )


# Exporte le tableau de comparaison des stratégies.
def export_results_csv(strategy_results: list[dict[str, object]]) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / RESULTS_FILENAME

    fieldnames = [
        "strategy_name",
        "selected_rows",
        "total_rows",
        "coverage",
        "abstention_rate",
        "accuracy",
        "f1_macro",
        "f1_weighted",
        "team_a_win_rows",
        "draw_rows",
        "team_b_win_rows",
        "draw_accuracy",
        "wc_rows",
        "wc_accuracy",
        "wcq_rows",
        "wcq_accuracy",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(strategy_results)

    return output_path


# Exporte les prédictions retenues par la meilleure stratégie.
def export_best_selection_csv(
    dataframe: pd.DataFrame,
    best_strategy: dict[str, object],
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / BEST_SELECTION_FILENAME

    strategy_masks = build_strategy_masks(dataframe)
    selected_dataframe = dataframe[
        strategy_masks[best_strategy["strategy_name"]]
    ].copy()

    export_columns = [
        "clean_match_id",
        "match_date_utc",
        "competition_code",
        "season",
        "team_a_name",
        "team_b_name",
        "target_result",
        "predicted_result",
        "is_correct",
        "elo_gap",
        "abs_elo_gap",
        "is_neutral_venue",
        "host_advantage_side",
    ]

    selected_dataframe[export_columns].to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )

    return output_path


# Exporte le résumé texte de la stratégie sélective.
def export_summary_txt(
    strategy_results: list[dict[str, object]],
    best_strategy: dict[str, object],
    results_path: Path,
    best_selection_path: Path,
    args: argparse.Namespace,
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / SUMMARY_FILENAME

    all_predictions = next(
        result for result in strategy_results if result["strategy_name"] == "all_predictions"
    )

    sorted_results = sorted(
        [
            result
            for result in strategy_results
            if result["accuracy"] is not None
        ],
        key=lambda result: (
            result["accuracy"],
            result["coverage"],
        ),
        reverse=True,
    )

    lines = [
        "OK - Évaluation stratégie sélective V17.9.1 terminée.",
        f"Feature version : {args.feature_version}",
        f"Fichier prédictions : {args.predictions_file}",
        f"Couverture minimale de sélection : {args.min_coverage}",
        "",
        "Référence sans abstention :",
        f"- strategy_name : {all_predictions['strategy_name']}",
        f"- accuracy : {all_predictions['accuracy']}",
        f"- f1_macro : {all_predictions['f1_macro']}",
        f"- coverage : {all_predictions['coverage']}",
        "",
        "Meilleure stratégie retenue :",
        f"- strategy_name : {best_strategy['strategy_name']}",
        f"- selected_rows : {best_strategy['selected_rows']}",
        f"- coverage : {best_strategy['coverage']}",
        f"- abstention_rate : {best_strategy['abstention_rate']}",
        f"- accuracy : {best_strategy['accuracy']}",
        f"- f1_macro : {best_strategy['f1_macro']}",
        f"- f1_weighted : {best_strategy['f1_weighted']}",
        f"- draw_rows : {best_strategy['draw_rows']}",
        f"- draw_accuracy : {best_strategy['draw_accuracy']}",
        f"- wc_rows : {best_strategy['wc_rows']}",
        f"- wc_accuracy : {best_strategy['wc_accuracy']}",
        f"- wcq_rows : {best_strategy['wcq_rows']}",
        f"- wcq_accuracy : {best_strategy['wcq_accuracy']}",
        "",
        "Top stratégies par accuracy :",
    ]

    for result in sorted_results[:10]:
        lines.append(
            f"- {result['strategy_name']} | "
            f"accuracy={result['accuracy']} | "
            f"coverage={result['coverage']} | "
            f"abstention={result['abstention_rate']} | "
            f"f1_macro={result['f1_macro']}"
        )

    lines.extend(
        [
            "",
            f"CSV comparaison stratégies : {results_path}",
            f"CSV meilleure sélection : {best_selection_path}",
            "",
            "Décision technique :",
            "- Une stratégie sélective est nécessaire avant toute intégration frontend.",
            "- Les matchs avec faible elo_gap doivent être considérés comme plus risqués.",
            "- La prédiction des DRAW reste fragile et doit être affichée avec prudence.",
            "- StatsBomb ne doit être envisagé qu'après validation de cette stratégie sélective.",
            "- Le modèle national V17.9 ne remplace pas le modèle club V17.8.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return output_path


# Affiche un résumé court dans le terminal.
def print_summary(
    all_predictions: dict[str, object],
    best_strategy: dict[str, object],
    summary_path: Path,
    results_path: Path,
) -> None:
    print("OK - Évaluation stratégie sélective V17.9.1 terminée.")
    print(
        f"Référence all_predictions : "
        f"accuracy={all_predictions['accuracy']} | "
        f"coverage={all_predictions['coverage']}"
    )
    print(f"Meilleure stratégie : {best_strategy['strategy_name']}")
    print(f"Accuracy : {best_strategy['accuracy']}")
    print(f"Coverage : {best_strategy['coverage']}")
    print(f"Abstention rate : {best_strategy['abstention_rate']}")
    print(f"F1 macro : {best_strategy['f1_macro']}")
    print(f"Résumé sauvegardé : {summary_path}")
    print(f"Résultats sauvegardés : {results_path}")


# Exécute l'évaluation complète des stratégies sélectives.
def main() -> None:
    try:
        args = parse_arguments()
        ensure_evidence_directory()

        predictions_dataframe = load_predictions(args.predictions_file)

        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            feature_dataframe = fetch_feature_context(
                connection=connection,
                feature_version=args.feature_version,
            )

        evaluation_dataframe = build_evaluation_dataframe(
            predictions_dataframe=predictions_dataframe,
            feature_dataframe=feature_dataframe,
        )

        strategy_results = evaluate_all_strategies(evaluation_dataframe)

        best_strategy = select_best_strategy(
            strategy_results=strategy_results,
            min_coverage=args.min_coverage,
        )

        results_path = export_results_csv(strategy_results)
        best_selection_path = export_best_selection_csv(
            dataframe=evaluation_dataframe,
            best_strategy=best_strategy,
        )

        summary_path = export_summary_txt(
            strategy_results=strategy_results,
            best_strategy=best_strategy,
            results_path=results_path,
            best_selection_path=best_selection_path,
            args=args,
        )

        all_predictions = next(
            result for result in strategy_results if result["strategy_name"] == "all_predictions"
        )

        print_summary(
            all_predictions=all_predictions,
            best_strategy=best_strategy,
            summary_path=summary_path,
            results_path=results_path,
        )

    except Exception as error:
        print("Erreur pendant l'évaluation stratégie sélective V17.9.1.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# 306_national_v17_9_predictions.csv
#        ↓
# ml_national.features + ml_national.clean_matches
#        ↓
# backend/scripts/ml_national/evaluate_national_v17_9_selective_strategy.py
#        ↓
# reports/evidence/ml_training/
#        ↓
# décision : intégration prudente, amélioration features ou StatsBomb post-baseline