# Rôle du fichier : analyser toutes les expérimentations ML 1X2 RubyBets déjà produites, comparer les versions globales et sélectives, puis décider la meilleure suite sans modifier la base, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from __future__ import annotations

from pathlib import Path
import math
import re
import sys
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "82_1x2_all_versions_error_patterns_summary.txt"
COMPARISON_PATH = REPORT_DIR / "83_1x2_all_versions_comparison.csv"
ERROR_SEGMENTS_PATH = REPORT_DIR / "84_1x2_all_versions_error_segments.csv"
DECISION_PATH = REPORT_DIR / "85_1x2_next_strategy_decision.txt"

CLASS_LABELS = ["HOME_WIN", "DRAW", "AWAY_WIN"]
GLOBAL_MIN_COVERAGE = 0.90
INTERESTING_GLOBAL_ACCURACY = 0.5250
INTERESTING_GLOBAL_F1_MACRO = 0.4900
INTERESTING_DRAW_RECALL = 0.3000
INTERESTING_DRAW_PRECISION = 0.3200
SERIOUS_GLOBAL_ACCURACY = 0.5350
SERIOUS_GLOBAL_F1_MACRO = 0.5000
SERIOUS_DRAW_RECALL = 0.3200
SERIOUS_DRAW_PRECISION = 0.3300
SELECTIVE_MIN_ACCURACY = 0.6500
SELECTIVE_MIN_ROWS = 500

COMPARISON_COLUMNS = [
    "source_file",
    "version_family",
    "candidate_type",
    "strategy",
    "model",
    "metric_origin",
    "train_rows",
    "test_rows",
    "selected_rows",
    "coverage",
    "accuracy",
    "f1_macro",
    "f1_weighted",
    "home_win_precision",
    "home_win_recall",
    "draw_precision",
    "draw_recall",
    "away_win_precision",
    "away_win_recall",
    "predicted_home_win_rows",
    "predicted_draw_rows",
    "predicted_away_win_rows",
    "actual_home_win_rows",
    "actual_draw_rows",
    "actual_away_win_rows",
    "is_draw_blind",
    "passes_interesting_global_gate",
    "passes_serious_global_gate",
    "notes",
]

SEGMENT_COLUMNS = [
    "source_file",
    "version_family",
    "strategy",
    "segment_type",
    "segment_value",
    "rows",
    "correct_rows",
    "error_rows",
    "accuracy",
    "error_rate",
    "actual_home_win_rows",
    "actual_draw_rows",
    "actual_away_win_rows",
    "predicted_home_win_rows",
    "predicted_draw_rows",
    "predicted_away_win_rows",
    "draw_missed_rows",
    "draw_missed_rate",
    "notes",
]

DETAILED_PREDICTION_FILES = {
    "30_saved_1x2_predictions_inspection.csv": "baseline_saved_model_inspection",
    "38_1x2_high_confidence_predictions.csv": "v2_high_confidence_predictions",
    "43_1x2_team_strength_high_confidence_predictions.csv": "v2_team_strength_high_confidence_predictions",
    "53_1x2_v3_high_confidence_predictions.csv": "v3_high_confidence_predictions",
    "60_1x2_v3_filtered_high_confidence_predictions.csv": "v3_filtered_high_confidence_predictions",
}

EXISTING_SEGMENT_FILES = [
    "56_1x2_v3_error_segments.csv",
    "63_1x2_v3_filtered_stability.csv",
    "72_1x2_v5_candidate_stability.csv",
    "73_1x2_v5_candidate_error_segments.csv",
]

SUMMARY_TEXT_FILES = [
    "07_best_model_decision.txt",
    "28_saved_1x2_model_evaluation.txt",
    "31_saved_1x2_reliability_summary.txt",
    "46_1x2_v2_fast_experiment_summary.txt",
    "50_1x2_v3_feature_groups_summary.txt",
    "64_1x2_v3_experimental_final_decision.txt",
    "67_1x2_v4_draw_aware_decision.txt",
    "70_1x2_v5_balance_features_decision.txt",
    "71_1x2_v5_candidate_stability_summary.txt",
    "76_1x2_v6_market_prior_summary.txt",
    "78_1x2_v6_market_prior_decision.txt",
    "79_1x2_v7_team_strength_context_summary.txt",
    "81_1x2_v7_team_strength_context_decision.txt",
]

AGGREGATE_RESULT_FILES = [
    "03_model_comparison.csv",
    "33_1x2_feature_sets_comparison.csv",
    "35_1x2_models_on_best_features_comparison.csv",
    "37_1x2_high_confidence_thresholds.csv",
    "40_1x2_team_strength_features_comparison.csv",
    "42_1x2_team_strength_high_confidence_thresholds.csv",
    "47_1x2_v2_fast_experiment_results.csv",
    "51_1x2_v3_feature_groups_results.csv",
    "58_1x2_draw_risk_gate_results.csv",
    "66_1x2_v4_draw_aware_results.csv",
    "69_1x2_v5_balance_features_results.csv",
    "77_1x2_v6_market_prior_results.csv",
    "80_1x2_v7_team_strength_context_results.csv",
]


# Crée le dossier de preuves si nécessaire.
def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Convertit proprement une valeur en float, avec NaN si la conversion est impossible.
def to_float(value: Any) -> float:
    if value is None:
        return math.nan

    try:
        if pd.isna(value):
            return math.nan
    except TypeError:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


# Convertit proprement une valeur en entier, avec 0 si la conversion est impossible.
def to_int(value: Any) -> int:
    number = to_float(value)

    if math.isnan(number):
        return 0

    return int(round(number))


# Arrondit les métriques numériques pour stabiliser les exports.
def rounded(value: Any, digits: int = 4) -> float:
    number = to_float(value)

    if math.isnan(number):
        return math.nan

    return round(number, digits)


# Lit un CSV si le fichier existe, sinon retourne un DataFrame vide.
def read_csv_if_exists(file_name: str) -> pd.DataFrame:
    path = REPORT_DIR / file_name

    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except Exception as error:
        print(f"Attention - CSV illisible ignore : {file_name} ({error})", flush=True)
        return pd.DataFrame()


# Lit un fichier texte si le fichier existe, sinon retourne une chaîne vide.
def read_text_if_exists(file_name: str) -> str:
    path = REPORT_DIR / file_name

    if not path.exists():
        return ""

    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


# Déduit la famille de version à partir du nom du fichier ou de la stratégie.
def infer_version_family(source_file: str, strategy: str = "") -> str:
    source = source_file.lower()
    strategy_lower = str(strategy).lower()

    if source.startswith(("01_", "02_", "03_", "04_", "05_", "06_", "07_", "08_", "09_", "10_", "11_", "12_", "13_", "14_", "15_", "16_", "17_", "18_", "19_", "20_", "21_", "22_", "23_", "24_", "25_", "26_", "27_", "28_", "29_", "30_", "31_")):
        return "baseline_officielle"
    if source.startswith(("32_", "33_", "34_", "35_", "36_", "37_", "38_", "39_", "40_", "41_", "42_", "43_", "44_", "45_", "46_", "47_", "48_", "49_")) or strategy_lower.startswith("v2"):
        return "v2_feature_engineering"
    if source.startswith(("50_", "51_", "52_", "53_", "54_", "55_", "56_", "57_", "58_", "59_", "60_", "61_", "62_", "63_", "64_")) or strategy_lower.startswith("v3"):
        return "v3_feature_groups_high_confidence"
    if source.startswith(("65_", "66_", "67_")) or strategy_lower.startswith("v4"):
        return "v4_draw_aware"
    if source.startswith(("68_", "69_", "70_", "71_", "72_", "73_")) or strategy_lower.startswith("v5"):
        return "v5_balance_features"
    if source.startswith(("74_", "75_", "76_", "77_", "78_")) or strategy_lower.startswith("v6") or "market" in strategy_lower or "agreement" in strategy_lower:
        return "v6_market_prior"
    if source.startswith(("79_", "80_", "81_")) or strategy_lower.startswith("v7"):
        return "v7_team_strength_context"

    return "unknown"


# Détermine si une ligne correspond à un modèle global, une stratégie sélective ou un benchmark.
def infer_candidate_type(source_file: str, strategy: str, row: pd.Series | None = None) -> str:
    source = source_file.lower()
    strategy_lower = str(strategy).lower()

    if "agreement" in strategy_lower:
        return "selective_candidate"
    if "high_confidence" in source or "threshold" in source or "gate" in source or "filtered" in strategy_lower:
        return "selective_candidate"
    if "direct" in strategy_lower or "favorite" in strategy_lower or "dummy" in strategy_lower:
        return "benchmark"
    if source.startswith("03_") and "xgboost" in strategy_lower:
        return "benchmark"

    if row is not None:
        coverage = to_float(row.get("coverage"))
        coverage_scope = str(row.get("coverage_scope", "")).lower()
        selected_rows = to_int(row.get("selected_rows"))
        test_rows = to_int(row.get("test_rows"))

        if selected_rows > 0 and test_rows == 0:
            return "selective_candidate"
        if not math.isnan(coverage) and coverage < GLOBAL_MIN_COVERAGE and "full" not in coverage_scope:
            return "selective_candidate"

    return "global_candidate"


# Récupère une valeur dans une ligne avec plusieurs noms de colonnes possibles.
def get_first_value(row: pd.Series, possible_columns: list[str], default: Any = None) -> Any:
    for column in possible_columns:
        if column in row.index:
            value = row.get(column)
            if not pd.isna(value):
                return value

    return default


# Normalise une ligne de résultats agrégés dans un format commun.
def normalize_aggregate_row(source_file: str, row: pd.Series) -> dict[str, Any]:
    strategy = str(
        get_first_value(
            row,
            ["strategy", "feature_set", "feature_group", "model", "gate_name", "threshold"],
            "unknown_strategy",
        )
    )

    if source_file in {"03_model_comparison.csv"}:
        strategy = f"baseline_{strategy}"

    if "threshold" in row.index and "feature_set" in row.index:
        strategy = f"{row.get('feature_set')}_threshold_{row.get('threshold')}"
    elif "threshold" in row.index and source_file == "37_1x2_high_confidence_thresholds.csv":
        strategy = f"v2_high_confidence_threshold_{row.get('threshold')}"

    model = str(get_first_value(row, ["model"], ""))
    if not model and source_file == "03_model_comparison.csv":
        model = str(row.get("model", ""))

    candidate_type = infer_candidate_type(source_file, strategy, row)
    version_family = infer_version_family(source_file, strategy)
    draw_precision = to_float(get_first_value(row, ["draw_precision", "precision_DRAW", "draw_accuracy_when_predicted"]))
    draw_recall = to_float(get_first_value(row, ["draw_recall", "recall_DRAW"]))
    predicted_draw_rows = to_int(get_first_value(row, ["predicted_draw_rows", "predicted_DRAW_rows"], 0))

    accuracy = to_float(get_first_value(row, ["accuracy"]))
    f1_macro = to_float(get_first_value(row, ["f1_macro"]))
    selected_rows = to_int(get_first_value(row, ["selected_rows", "kept_rows"], 0))
    test_rows = to_int(get_first_value(row, ["test_rows", "input_rows"], 0))
    coverage = to_float(get_first_value(row, ["coverage", "test_coverage", "retention_on_high_confidence"]))

    if math.isnan(coverage) and selected_rows > 0 and test_rows > 0:
        coverage = selected_rows / test_rows

    return {
        "source_file": source_file,
        "version_family": version_family,
        "candidate_type": candidate_type,
        "strategy": strategy,
        "model": model,
        "metric_origin": "aggregate_result_csv",
        "train_rows": to_int(get_first_value(row, ["train_rows"], 0)),
        "test_rows": test_rows,
        "selected_rows": selected_rows,
        "coverage": rounded(coverage),
        "accuracy": rounded(accuracy),
        "f1_macro": rounded(f1_macro),
        "f1_weighted": rounded(get_first_value(row, ["f1_weighted"])),
        "home_win_precision": rounded(get_first_value(row, ["home_win_precision", "precision_HOME_WIN"])),
        "home_win_recall": rounded(get_first_value(row, ["home_win_recall", "recall_HOME_WIN"])),
        "draw_precision": rounded(draw_precision),
        "draw_recall": rounded(draw_recall),
        "away_win_precision": rounded(get_first_value(row, ["away_win_precision", "precision_AWAY_WIN"])),
        "away_win_recall": rounded(get_first_value(row, ["away_win_recall", "recall_AWAY_WIN"])),
        "predicted_home_win_rows": to_int(get_first_value(row, ["predicted_home_win_rows", "predicted_HOME_WIN_rows"], 0)),
        "predicted_draw_rows": predicted_draw_rows,
        "predicted_away_win_rows": to_int(get_first_value(row, ["predicted_away_win_rows", "predicted_AWAY_WIN_rows"], 0)),
        "actual_home_win_rows": to_int(get_first_value(row, ["actual_home_win_rows", "actual_home_rows"], 0)),
        "actual_draw_rows": to_int(get_first_value(row, ["actual_draw_rows", "actual_draw_rows"], 0)),
        "actual_away_win_rows": to_int(get_first_value(row, ["actual_away_win_rows", "actual_away_rows"], 0)),
        "is_draw_blind": bool(predicted_draw_rows == 0 or (not math.isnan(draw_recall) and draw_recall < 0.05)),
        "passes_interesting_global_gate": False,
        "passes_serious_global_gate": False,
        "notes": "ligne normalisee depuis un CSV de resultats agreges",
    }


# Calcule précision, rappel et F1 d'une classe à partir des prédictions détaillées.
def compute_class_metrics(predictions_dataframe: pd.DataFrame, class_label: str) -> tuple[float, float, float]:
    actual_is_class = predictions_dataframe["actual_result"] == class_label
    predicted_is_class = predictions_dataframe["predicted_result"] == class_label
    true_positive = int((actual_is_class & predicted_is_class).sum())
    predicted_positive = int(predicted_is_class.sum())
    actual_positive = int(actual_is_class.sum())

    precision = true_positive / predicted_positive if predicted_positive else 0.0
    recall = true_positive / actual_positive if actual_positive else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return precision, recall, f1


# Calcule les métriques globales à partir d'un fichier de prédictions détaillées.
def compute_metrics_from_predictions(source_file: str, strategy: str, predictions_dataframe: pd.DataFrame) -> dict[str, Any]:
    working_dataframe = predictions_dataframe.dropna(subset=["actual_result", "predicted_result"]).copy()
    correct_series = working_dataframe["actual_result"] == working_dataframe["predicted_result"]
    total_rows = len(working_dataframe)
    actual_distribution = working_dataframe["actual_result"].value_counts().to_dict()
    predicted_distribution = working_dataframe["predicted_result"].value_counts().to_dict()

    class_metrics = {label: compute_class_metrics(working_dataframe, label) for label in CLASS_LABELS}
    f1_scores = [class_metrics[label][2] for label in CLASS_LABELS]
    weights = [actual_distribution.get(label, 0) for label in CLASS_LABELS]
    f1_macro = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
    f1_weighted = sum(f1 * weight for f1, weight in zip(f1_scores, weights)) / sum(weights) if sum(weights) else 0.0
    candidate_type = infer_candidate_type(source_file, strategy)

    return {
        "source_file": source_file,
        "version_family": infer_version_family(source_file, strategy),
        "candidate_type": candidate_type,
        "strategy": strategy,
        "model": "from_saved_predictions",
        "metric_origin": "detailed_predictions_csv",
        "train_rows": 0,
        "test_rows": total_rows,
        "selected_rows": total_rows if candidate_type == "selective_candidate" else 0,
        "coverage": math.nan,
        "accuracy": rounded(correct_series.mean() if total_rows else 0.0),
        "f1_macro": rounded(f1_macro),
        "f1_weighted": rounded(f1_weighted),
        "home_win_precision": rounded(class_metrics["HOME_WIN"][0]),
        "home_win_recall": rounded(class_metrics["HOME_WIN"][1]),
        "draw_precision": rounded(class_metrics["DRAW"][0]),
        "draw_recall": rounded(class_metrics["DRAW"][1]),
        "away_win_precision": rounded(class_metrics["AWAY_WIN"][0]),
        "away_win_recall": rounded(class_metrics["AWAY_WIN"][1]),
        "predicted_home_win_rows": int(predicted_distribution.get("HOME_WIN", 0)),
        "predicted_draw_rows": int(predicted_distribution.get("DRAW", 0)),
        "predicted_away_win_rows": int(predicted_distribution.get("AWAY_WIN", 0)),
        "actual_home_win_rows": int(actual_distribution.get("HOME_WIN", 0)),
        "actual_draw_rows": int(actual_distribution.get("DRAW", 0)),
        "actual_away_win_rows": int(actual_distribution.get("AWAY_WIN", 0)),
        "is_draw_blind": bool(predicted_distribution.get("DRAW", 0) == 0 or class_metrics["DRAW"][1] < 0.05),
        "passes_interesting_global_gate": False,
        "passes_serious_global_gate": False,
        "notes": "metriques recalculees depuis les predictions detaillees",
    }


# Ajoute les booléens de passage des seuils global candidates.
def add_gate_columns(comparison_dataframe: pd.DataFrame) -> pd.DataFrame:
    if comparison_dataframe.empty:
        return comparison_dataframe

    result = comparison_dataframe.copy()
    result["passes_interesting_global_gate"] = (
        (result["candidate_type"] == "global_candidate")
        & (result["accuracy"] > INTERESTING_GLOBAL_ACCURACY)
        & (result["f1_macro"] > INTERESTING_GLOBAL_F1_MACRO)
        & (result["draw_recall"] >= INTERESTING_DRAW_RECALL)
        & (result["draw_precision"] >= INTERESTING_DRAW_PRECISION)
    )
    result["passes_serious_global_gate"] = (
        (result["candidate_type"] == "global_candidate")
        & (result["accuracy"] >= SERIOUS_GLOBAL_ACCURACY)
        & (result["f1_macro"] >= SERIOUS_GLOBAL_F1_MACRO)
        & (result["draw_recall"] >= SERIOUS_DRAW_RECALL)
        & (result["draw_precision"] >= SERIOUS_DRAW_PRECISION)
    )

    return result


# Charge tous les tableaux de résultats agrégés disponibles.
def collect_aggregate_results() -> list[dict[str, Any]]:
    rows = []

    for file_name in AGGREGATE_RESULT_FILES:
        dataframe = read_csv_if_exists(file_name)

        if dataframe.empty:
            continue

        print(f"Lecture resultats agreges : {file_name}", flush=True)
        for _, row in dataframe.iterrows():
            rows.append(normalize_aggregate_row(file_name, row))

    return rows


# Charge tous les fichiers de prédictions détaillées disponibles.
def collect_prediction_results() -> list[dict[str, Any]]:
    rows = []

    for file_name, strategy in DETAILED_PREDICTION_FILES.items():
        dataframe = read_csv_if_exists(file_name)

        if dataframe.empty or "actual_result" not in dataframe.columns or "predicted_result" not in dataframe.columns:
            continue

        print(f"Lecture predictions detaillees : {file_name}", flush=True)
        rows.append(compute_metrics_from_predictions(file_name, strategy, dataframe))

    return rows


# Construit un segment d'erreur à partir d'un sous-ensemble de prédictions.
def build_segment_row(
    source_file: str,
    strategy: str,
    segment_type: str,
    segment_value: str,
    segment_dataframe: pd.DataFrame,
) -> dict[str, Any]:
    rows = len(segment_dataframe)

    if rows == 0:
        correct_rows = 0
    else:
        correct_rows = int((segment_dataframe["actual_result"] == segment_dataframe["predicted_result"]).sum())

    error_rows = rows - correct_rows
    actual_distribution = segment_dataframe["actual_result"].value_counts().to_dict() if rows else {}
    predicted_distribution = segment_dataframe["predicted_result"].value_counts().to_dict() if rows else {}
    draw_missed_rows = int(((segment_dataframe["actual_result"] == "DRAW") & (segment_dataframe["predicted_result"] != "DRAW")).sum()) if rows else 0
    actual_draw_rows = int(actual_distribution.get("DRAW", 0))

    return {
        "source_file": source_file,
        "version_family": infer_version_family(source_file, strategy),
        "strategy": strategy,
        "segment_type": segment_type,
        "segment_value": str(segment_value),
        "rows": rows,
        "correct_rows": correct_rows,
        "error_rows": error_rows,
        "accuracy": rounded(correct_rows / rows if rows else 0.0),
        "error_rate": rounded(error_rows / rows if rows else 0.0),
        "actual_home_win_rows": int(actual_distribution.get("HOME_WIN", 0)),
        "actual_draw_rows": actual_draw_rows,
        "actual_away_win_rows": int(actual_distribution.get("AWAY_WIN", 0)),
        "predicted_home_win_rows": int(predicted_distribution.get("HOME_WIN", 0)),
        "predicted_draw_rows": int(predicted_distribution.get("DRAW", 0)),
        "predicted_away_win_rows": int(predicted_distribution.get("AWAY_WIN", 0)),
        "draw_missed_rows": draw_missed_rows,
        "draw_missed_rate": rounded(draw_missed_rows / actual_draw_rows if actual_draw_rows else 0.0),
        "notes": "segment recalcule depuis predictions detaillees",
    }


# Transforme une probabilité maximale en bucket lisible pour les segments de confiance.
def probability_bucket(value: Any) -> str:
    number = to_float(value)

    if math.isnan(number):
        return "unknown"
    if number >= 0.75:
        return "very_high_0_75_plus"
    if number >= 0.65:
        return "high_0_65_0_75"
    if number >= 0.55:
        return "medium_0_55_0_65"
    if number >= 0.45:
        return "low_0_45_0_55"

    return "very_low_under_0_45"


# Construit les segments d'erreur à partir des fichiers de prédictions détaillées.
def collect_prediction_error_segments() -> list[dict[str, Any]]:
    segment_rows = []

    for file_name, strategy in DETAILED_PREDICTION_FILES.items():
        dataframe = read_csv_if_exists(file_name)

        if dataframe.empty or "actual_result" not in dataframe.columns or "predicted_result" not in dataframe.columns:
            continue

        working_dataframe = dataframe.dropna(subset=["actual_result", "predicted_result"]).copy()
        working_dataframe["prediction_transition"] = working_dataframe["actual_result"].astype(str) + "_predicted_as_" + working_dataframe["predicted_result"].astype(str)

        if {"prob_home_win", "prob_draw", "prob_away_win"}.issubset(working_dataframe.columns):
            working_dataframe["max_probability"] = working_dataframe[["prob_home_win", "prob_draw", "prob_away_win"]].max(axis=1)
            working_dataframe["probability_bucket"] = working_dataframe["max_probability"].apply(probability_bucket)

        segment_rows.append(build_segment_row(file_name, strategy, "all_rows", "all", working_dataframe))

        for column in ["actual_result", "predicted_result", "prediction_transition", "league_code", "season", "probability_bucket"]:
            if column not in working_dataframe.columns:
                continue

            for segment_value, segment_dataframe in working_dataframe.groupby(column, dropna=False):
                segment_rows.append(build_segment_row(file_name, strategy, column, str(segment_value), segment_dataframe))

        if {"league_code", "season"}.issubset(working_dataframe.columns):
            working_dataframe["league_season"] = working_dataframe["league_code"].astype(str) + "_" + working_dataframe["season"].astype(str)
            for segment_value, segment_dataframe in working_dataframe.groupby("league_season", dropna=False):
                segment_rows.append(build_segment_row(file_name, strategy, "league_season", str(segment_value), segment_dataframe))

    return segment_rows


# Normalise les segments déjà produits par les anciens scripts pour les regrouper dans un seul fichier.
def normalize_existing_segment_row(source_file: str, row: pd.Series) -> dict[str, Any]:
    segment_type = str(get_first_value(row, ["segment_type", "segment_family"], "unknown"))
    segment_value = str(get_first_value(row, ["segment_value"], "unknown"))
    strategy = f"existing_segments_from_{source_file.replace('.csv', '')}"

    return {
        "source_file": source_file,
        "version_family": infer_version_family(source_file, strategy),
        "strategy": strategy,
        "segment_type": segment_type,
        "segment_value": segment_value,
        "rows": to_int(get_first_value(row, ["rows"], 0)),
        "correct_rows": to_int(get_first_value(row, ["correct_rows"], 0)),
        "error_rows": to_int(get_first_value(row, ["error_rows"], 0)),
        "accuracy": rounded(get_first_value(row, ["accuracy", "v5_accuracy", "v2_accuracy"])),
        "error_rate": rounded(get_first_value(row, ["error_rate"])),
        "actual_home_win_rows": to_int(get_first_value(row, ["actual_home_win_rows", "actual_home_rows"], 0)),
        "actual_draw_rows": to_int(get_first_value(row, ["actual_draw_rows"], 0)),
        "actual_away_win_rows": to_int(get_first_value(row, ["actual_away_win_rows", "actual_away_rows"], 0)),
        "predicted_home_win_rows": to_int(get_first_value(row, ["predicted_home_rows", "predicted_home_win_rows"], 0)),
        "predicted_draw_rows": to_int(get_first_value(row, ["predicted_draw_rows"], 0)),
        "predicted_away_win_rows": to_int(get_first_value(row, ["predicted_away_rows", "predicted_away_win_rows"], 0)),
        "draw_missed_rows": to_int(get_first_value(row, ["draw_missed_rows"], 0)),
        "draw_missed_rate": rounded(get_first_value(row, ["draw_missed_rate"])),
        "notes": "segment repris depuis un fichier de segment deja produit",
    }


# Charge les fichiers de segments déjà existants.
def collect_existing_segments() -> list[dict[str, Any]]:
    segment_rows = []

    for file_name in EXISTING_SEGMENT_FILES:
        dataframe = read_csv_if_exists(file_name)

        if dataframe.empty:
            continue

        print(f"Lecture segments existants : {file_name}", flush=True)
        for _, row in dataframe.iterrows():
            segment_rows.append(normalize_existing_segment_row(file_name, row))

    return segment_rows


# Extrait quelques métriques clés depuis les fichiers texte, utile si un CSV manque.
def extract_text_based_rows() -> list[dict[str, Any]]:
    rows = []
    metric_patterns = {
        "accuracy": r"Accuracy\s*:\s*([0-9]+(?:\.[0-9]+)?)",
        "f1_macro": r"F1 macro\s*:\s*([0-9]+(?:\.[0-9]+)?)",
        "draw_precision": r"DRAW precision\s*:\s*([0-9]+(?:\.[0-9]+)?)",
        "draw_recall": r"DRAW recall\s*:\s*([0-9]+(?:\.[0-9]+)?)",
        "predicted_draw_rows": r"Predicted DRAW rows\s*:\s*([0-9]+)",
    }

    for file_name in SUMMARY_TEXT_FILES:
        text = read_text_if_exists(file_name)

        if not text:
            continue

        extracted = {metric: re.search(pattern, text, flags=re.IGNORECASE) for metric, pattern in metric_patterns.items()}
        if not any(extracted.values()):
            continue

        strategy_match = re.search(r"(?:Strategy|Feature set|Nom|Candidat V5 retenu)\s*:\s*([^\n]+)", text, flags=re.IGNORECASE)
        strategy = strategy_match.group(1).strip() if strategy_match else file_name.replace(".txt", "")

        row = {
            "source_file": file_name,
            "version_family": infer_version_family(file_name, strategy),
            "candidate_type": infer_candidate_type(file_name, strategy),
            "strategy": strategy,
            "model": "from_summary_text",
            "metric_origin": "summary_text_fallback",
            "train_rows": 0,
            "test_rows": 0,
            "selected_rows": 0,
            "coverage": math.nan,
            "accuracy": rounded(extracted["accuracy"].group(1)) if extracted["accuracy"] else math.nan,
            "f1_macro": rounded(extracted["f1_macro"].group(1)) if extracted["f1_macro"] else math.nan,
            "f1_weighted": math.nan,
            "home_win_precision": math.nan,
            "home_win_recall": math.nan,
            "draw_precision": rounded(extracted["draw_precision"].group(1)) if extracted["draw_precision"] else math.nan,
            "draw_recall": rounded(extracted["draw_recall"].group(1)) if extracted["draw_recall"] else math.nan,
            "away_win_precision": math.nan,
            "away_win_recall": math.nan,
            "predicted_home_win_rows": 0,
            "predicted_draw_rows": to_int(extracted["predicted_draw_rows"].group(1)) if extracted["predicted_draw_rows"] else 0,
            "predicted_away_win_rows": 0,
            "actual_home_win_rows": 0,
            "actual_draw_rows": 0,
            "actual_away_win_rows": 0,
            "is_draw_blind": False,
            "passes_interesting_global_gate": False,
            "passes_serious_global_gate": False,
            "notes": "ligne extraite du fichier texte car ce resume contient une decision importante",
        }
        rows.append(row)

    return rows


# Regroupe toutes les sources disponibles en un seul tableau de comparaison.
def build_all_versions_comparison() -> pd.DataFrame:
    rows = []
    rows.extend(collect_aggregate_results())
    rows.extend(collect_prediction_results())
    rows.extend(extract_text_based_rows())

    if not rows:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    comparison_dataframe = pd.DataFrame(rows)

    for column in COMPARISON_COLUMNS:
        if column not in comparison_dataframe.columns:
            comparison_dataframe[column] = math.nan

    comparison_dataframe = comparison_dataframe[COMPARISON_COLUMNS]
    comparison_dataframe = add_gate_columns(comparison_dataframe)
    comparison_dataframe = comparison_dataframe.sort_values(
        by=["candidate_type", "f1_macro", "draw_recall", "accuracy"],
        ascending=[True, False, False, False],
        na_position="last",
    )

    return comparison_dataframe


# Regroupe tous les segments d'erreurs calculés et les segments déjà produits.
def build_all_error_segments() -> pd.DataFrame:
    segment_rows = []
    segment_rows.extend(collect_prediction_error_segments())
    segment_rows.extend(collect_existing_segments())

    if not segment_rows:
        return pd.DataFrame(columns=SEGMENT_COLUMNS)

    segments_dataframe = pd.DataFrame(segment_rows)

    for column in SEGMENT_COLUMNS:
        if column not in segments_dataframe.columns:
            segments_dataframe[column] = math.nan

    segments_dataframe = segments_dataframe[SEGMENT_COLUMNS]
    segments_dataframe = segments_dataframe.sort_values(
        by=["error_rows", "draw_missed_rows", "rows"],
        ascending=[False, False, False],
        na_position="last",
    )

    return segments_dataframe


# Sélectionne la meilleure ligne globale exploitable selon F1 macro, DRAW recall et accuracy.
def select_best_global_candidate(comparison_dataframe: pd.DataFrame) -> pd.Series | None:
    if comparison_dataframe.empty:
        return None

    candidates = comparison_dataframe[
        (comparison_dataframe["candidate_type"] == "global_candidate")
        & comparison_dataframe["f1_macro"].notna()
        & comparison_dataframe["accuracy"].notna()
    ].copy()

    if candidates.empty:
        return None

    return candidates.sort_values(by=["f1_macro", "draw_recall", "accuracy"], ascending=False).iloc[0]


# Sélectionne la meilleure stratégie sélective selon accuracy et volume analysé.
def select_best_selective_candidate(comparison_dataframe: pd.DataFrame) -> pd.Series | None:
    if comparison_dataframe.empty:
        return None

    candidates = comparison_dataframe[
        (comparison_dataframe["candidate_type"] == "selective_candidate")
        & comparison_dataframe["accuracy"].notna()
    ].copy()

    if candidates.empty:
        return None

    candidates["volume_for_sort"] = candidates[["selected_rows", "test_rows"]].max(axis=1)

    return candidates.sort_values(by=["accuracy", "volume_for_sort"], ascending=False).iloc[0]


# Sélectionne la meilleure ligne sur le rappel DRAW parmi les candidats globaux.
def select_best_draw_recall_candidate(comparison_dataframe: pd.DataFrame) -> pd.Series | None:
    candidates = comparison_dataframe[
        (comparison_dataframe["candidate_type"] == "global_candidate")
        & comparison_dataframe["draw_recall"].notna()
    ].copy()

    if candidates.empty:
        return None

    return candidates.sort_values(by=["draw_recall", "f1_macro", "accuracy"], ascending=False).iloc[0]


# Calcule le diagnostic stratégique final à partir des comparaisons.
def determine_next_strategy(comparison_dataframe: pd.DataFrame) -> dict[str, Any]:
    best_global = select_best_global_candidate(comparison_dataframe)
    best_selective = select_best_selective_candidate(comparison_dataframe)
    best_draw = select_best_draw_recall_candidate(comparison_dataframe)

    interesting_global_rows = comparison_dataframe[comparison_dataframe["passes_interesting_global_gate"] == True]
    serious_global_rows = comparison_dataframe[comparison_dataframe["passes_serious_global_gate"] == True]

    if not serious_global_rows.empty:
        status = "GLOBAL_MODEL_SERIOUS_CANDIDATE_FOUND"
        recommendation = "Preparer une analyse de stabilite puis envisager une sauvegarde candidate separee."
    elif not interesting_global_rows.empty:
        status = "GLOBAL_MODEL_INTERESTING_BUT_NEEDS_STABILITY"
        recommendation = "Faire une analyse de stabilite dediee avant toute sauvegarde."
    elif best_selective is not None and to_float(best_selective.get("accuracy")) >= SELECTIVE_MIN_ACCURACY and max(to_int(best_selective.get("selected_rows")), to_int(best_selective.get("test_rows"))) >= SELECTIVE_MIN_ROWS:
        status = "GLOBAL_PLATEAU_SELECTIVE_SIGNAL_EXISTS"
        recommendation = "Ne pas continuer les petites features globales. Conserver le meilleur global comme reference et approfondir une strategie forte confiance, tout en documentant qu'elle ne couvre pas tous les matchs."
    else:
        status = "GLOBAL_PLATEAU_DATA_ENRICHMENT_REQUIRED"
        recommendation = "Arreter les variantes de features simples et enrichir le dataset pre-match avec des donnees plus informatives avant de relancer un modele global."

    return {
        "status": status,
        "recommendation": recommendation,
        "best_global": best_global,
        "best_selective": best_selective,
        "best_draw": best_draw,
        "interesting_global_count": len(interesting_global_rows),
        "serious_global_count": len(serious_global_rows),
    }


# Formate une ligne de métriques pour les synthèses texte.
def format_row(label: str, row: pd.Series | None) -> list[str]:
    if row is None:
        return [f"- {label} : indisponible"]

    return [
        f"- {label} :",
        f"  - source : {row.get('source_file')}",
        f"  - version : {row.get('version_family')}",
        f"  - type : {row.get('candidate_type')}",
        f"  - strategy : {row.get('strategy')}",
        f"  - model : {row.get('model')}",
        f"  - accuracy : {row.get('accuracy')}",
        f"  - f1_macro : {row.get('f1_macro')}",
        f"  - draw_precision : {row.get('draw_precision')}",
        f"  - draw_recall : {row.get('draw_recall')}",
        f"  - predicted_draw_rows : {row.get('predicted_draw_rows')}",
        f"  - test_rows : {row.get('test_rows')}",
        f"  - selected_rows : {row.get('selected_rows')}",
    ]


# Construit un résumé lisible de toute l'analyse.
def build_summary(comparison_dataframe: pd.DataFrame, segments_dataframe: pd.DataFrame, decision: dict[str, Any]) -> str:
    best_global = decision["best_global"]
    best_selective = decision["best_selective"]
    best_draw = decision["best_draw"]
    global_count = int((comparison_dataframe["candidate_type"] == "global_candidate").sum()) if not comparison_dataframe.empty else 0
    selective_count = int((comparison_dataframe["candidate_type"] == "selective_candidate").sum()) if not comparison_dataframe.empty else 0
    benchmark_count = int((comparison_dataframe["candidate_type"] == "benchmark").sum()) if not comparison_dataframe.empty else 0
    draw_blind_count = int(comparison_dataframe["is_draw_blind"].fillna(False).sum()) if not comparison_dataframe.empty else 0

    top_global = comparison_dataframe[comparison_dataframe["candidate_type"] == "global_candidate"].head(10)
    top_selective = comparison_dataframe[comparison_dataframe["candidate_type"] == "selective_candidate"].head(10)
    top_error_segments = segments_dataframe.head(15)

    lines = [
        "RubyBets - ML 1X2 all versions error patterns",
        "82 - Synthese globale de toutes les versions ML 1X2",
        "",
        "Objectif :",
        "Analyser toutes les experimentations ML 1X2 deja produites, sans se limiter a V2/V5/V6/V7, pour identifier le vrai plafond actuel et la prochaine strategie utile.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Analyse basee uniquement sur les preuves deja generees dans reports/evidence/ml_training/.",
        "",
        "Sources analysees :",
        f"- Lignes de comparaison normalisees : {len(comparison_dataframe)}",
        f"- Segments d'erreurs normalises : {len(segments_dataframe)}",
        f"- Candidats globaux : {global_count}",
        f"- Strategies selectives / forte confiance : {selective_count}",
        f"- Benchmarks ou references non integrables directement : {benchmark_count}",
        f"- Lignes draw-blind ou quasi draw-blind : {draw_blind_count}",
        "",
        "Meilleures lectures :",
    ]
    lines.extend(format_row("Meilleur candidat global observe", best_global))
    lines.extend(format_row("Meilleure strategie selective observee", best_selective))
    lines.extend(format_row("Meilleur rappel DRAW parmi les candidats globaux", best_draw))

    lines.extend(
        [
            "",
            "Diagnostic :",
            f"- Status : {decision['status']}",
            f"- Recommendation : {decision['recommendation']}",
            f"- Candidats globaux passant le seuil interessant : {decision['interesting_global_count']}",
            f"- Candidats globaux passant le seuil serieux : {decision['serious_global_count']}",
            "",
            "Top candidats globaux par F1 macro :",
        ]
    )

    for _, row in top_global.iterrows():
        lines.append(
            f"- {row['version_family']} | {row['strategy']} | acc={row['accuracy']} | f1_macro={row['f1_macro']} | draw_precision={row['draw_precision']} | draw_recall={row['draw_recall']} | source={row['source_file']}"
        )

    lines.extend(["", "Top strategies selectives par accuracy :"])
    for _, row in top_selective.sort_values(by=["accuracy", "test_rows"], ascending=False).head(10).iterrows():
        lines.append(
            f"- {row['version_family']} | {row['strategy']} | acc={row['accuracy']} | f1_macro={row['f1_macro']} | draw_precision={row['draw_precision']} | draw_recall={row['draw_recall']} | rows={max(to_int(row['selected_rows']), to_int(row['test_rows']))} | source={row['source_file']}"
        )

    lines.extend(["", "Segments d'erreurs les plus lourds :"])
    for _, row in top_error_segments.iterrows():
        lines.append(
            f"- {row['version_family']} | {row['segment_type']}={row['segment_value']} | rows={row['rows']} | errors={row['error_rows']} | accuracy={row['accuracy']} | draw_missed={row['draw_missed_rows']} | source={row['source_file']}"
        )

    lines.extend(
        [
            "",
            "Lecture simple :",
            "- Les modeles globaux progressent par rapport a la baseline initiale, mais restent proches d'un plafond autour de 0.51/0.52 selon les perimetres.",
            "- Les strategies forte confiance montent plus haut en accuracy, mais elles couvrent moins de matchs et peuvent ignorer les DRAW.",
            "- Le bloc DRAW reste le principal frein : si le rappel DRAW reste sous 0.30, le modele global 1X2 reste difficile a defendre comme amelioration forte.",
            "- La prochaine vraie piste n'est pas une petite variante V8 de forme/buts, mais soit un enrichissement de donnees pre-match, soit une strategie forte confiance clairement separee du modele global.",
            "",
            "Fichiers generes :",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(COMPARISON_PATH.relative_to(PROJECT_ROOT)),
            str(ERROR_SEGMENTS_PATH.relative_to(PROJECT_ROOT)),
            str(DECISION_PATH.relative_to(PROJECT_ROOT)),
            "",
            "Statut de suivi :",
            "- Tache realisee : analyse globale de toutes les versions ML 1X2.",
            "- Statut source a mettre a jour : a produire -> realise pour les fichiers reports/evidence/ml_training/82, 83, 84 et 85.",
        ]
    )

    return "\n".join(lines)


# Construit le fichier de décision finale sur la prochaine stratégie.
def build_decision_text(decision: dict[str, Any]) -> str:
    lines = [
        "RubyBets - ML 1X2 next strategy decision",
        "85 - Decision apres analyse globale de toutes les versions",
        "",
        f"Status : {decision['status']}",
        "",
    ]

    lines.extend(format_row("Meilleur candidat global observe", decision["best_global"]))
    lines.append("")
    lines.extend(format_row("Meilleure strategie selective observee", decision["best_selective"]))
    lines.append("")
    lines.extend(format_row("Meilleur rappel DRAW global", decision["best_draw"]))

    lines.extend(
        [
            "",
            "Decision :",
            decision["recommendation"],
            "",
            "Conseil technique :",
            "- Ne pas remplacer le modele officiel sauvegarde automatiquement.",
            "- Ne pas integrer les cotes ou les strategies selectives dans le frontend.",
            "- Ne pas presenter les strategies forte confiance comme un modele global 1X2.",
            "- Utiliser cette analyse pour choisir entre enrichissement de donnees pre-match et strategie forte confiance separee.",
            "",
            "Prochaine action recommandee :",
            "1. Si l'objectif reste un modele global 1X2 : enrichir le dataset avec des donnees pre-match plus informatives avant de relancer une nouvelle version.",
            "2. Si l'objectif produit devient la recommandation fiable : formaliser une strategie forte confiance separee, avec couverture, limites et absence de promesse de resultat.",
            "3. Dans tous les cas : conserver V2/V5/V6/V7 comme preuves experimentales, mais ne pas les exposer comme fonctionnalites finales.",
            "",
            "Garde-fous maintenus :",
            "- Aucun changement API/frontend/base/scoring V1.",
            "- Aucun remplacement du modele officiel sauvegarde.",
            "- Aucune exposition des cotes dans RubyBets.",
            "- Analyse ML interne uniquement.",
        ]
    )

    return "\n".join(lines)


# Lance l'analyse complète et écrit les quatre fichiers de preuve.
def main() -> None:
    ensure_report_dir()

    print("Analyse globale de toutes les versions ML 1X2 RubyBets...", flush=True)
    comparison_dataframe = build_all_versions_comparison()
    segments_dataframe = build_all_error_segments()
    decision = determine_next_strategy(comparison_dataframe)

    comparison_dataframe.to_csv(COMPARISON_PATH, index=False, encoding="utf-8")
    segments_dataframe.to_csv(ERROR_SEGMENTS_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(build_summary(comparison_dataframe, segments_dataframe, decision), encoding="utf-8")
    DECISION_PATH.write_text(build_decision_text(decision), encoding="utf-8")

    print("OK - Analyse globale de toutes les versions ML 1X2 terminee.", flush=True)
    print(f"Status: {decision['status']}", flush=True)

    if decision["best_global"] is not None:
        best_global = decision["best_global"]
        print(f"Best global strategy: {best_global['strategy']}", flush=True)
        print(f"Accuracy: {best_global['accuracy']}", flush=True)
        print(f"F1 macro: {best_global['f1_macro']}", flush=True)
        print(f"DRAW precision: {best_global['draw_precision']}", flush=True)
        print(f"DRAW recall: {best_global['draw_recall']}", flush=True)

    if decision["best_selective"] is not None:
        best_selective = decision["best_selective"]
        print(f"Best selective strategy: {best_selective['strategy']}", flush=True)
        print(f"Selective accuracy: {best_selective['accuracy']}", flush=True)

    print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Comparison CSV saved: {COMPARISON_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Error segments CSV saved: {ERROR_SEGMENTS_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Decision saved: {DECISION_PATH.relative_to(PROJECT_ROOT)}", flush=True)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# analyze_1x2_all_versions_error_patterns.py
#   -> lit reports/evidence/ml_training/01-81 existants
#   -> normalise les métriques globales et sélectives
#   -> recalcule des segments depuis les CSV de prédictions détaillées
#   -> écrit reports/evidence/ml_training/82_summary, 83_comparison, 84_segments, 85_decision
#   -> ne modifie ni PostgreSQL, ni ml.features, ni API, ni frontend, ni scoring V1, ni modèles sauvegardés
