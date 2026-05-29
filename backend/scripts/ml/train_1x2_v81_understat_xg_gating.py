# Rôle du fichier : tester une expérience ML 1X2 V8.1 de gating sélectif entre la référence V6 Market prior et le signal V8 Understat xG, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from __future__ import annotations

from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "140_1x2_v81_understat_xg_gating_summary.txt"
RESULTS_CSV_PATH = REPORT_DIR / "141_1x2_v81_understat_xg_gating_results.csv"
BEST_PREDICTIONS_CSV_PATH = REPORT_DIR / "142_1x2_v81_understat_xg_gating_best_predictions.csv"
SEGMENTS_CSV_PATH = REPORT_DIR / "143_1x2_v81_understat_xg_gating_segments.csv"
DECISION_PATH = REPORT_DIR / "144_1x2_v81_understat_xg_gating_decision.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import TARGET_COLUMN, ensure_report_dir, get_database_url  # noqa: E402
from experiment_1x2_v5_balance_features import CLASS_LABELS, V2_REFERENCE_MODEL_NAME, build_reference_model  # noqa: E402
from experiment_1x2_v6_market_prior import MARKET_PROBABILITY_COLUMNS  # noqa: E402
from train_1x2_v8_understat_xg_in_memory_v2 import (  # noqa: E402
    TEST_SEASONS,
    TRAIN_SEASONS,
    V6_GLOBAL_BEST_ACCURACY,
    V6_GLOBAL_BEST_DRAW_PRECISION,
    V6_GLOBAL_BEST_DRAW_RECALL,
    V6_GLOBAL_BEST_F1_MACRO,
    XG_ROLLING_FEATURE_COLUMNS,
    build_v8_feature_dataframe,
    dedupe_columns,
    rounded,
)

warnings.filterwarnings("ignore", category=UserWarning)

V6_STRATEGY_NAME = "v6_market_only_probs_same_xg_scope"
V8_STRATEGY_NAME = "v8_market_probs_plus_xg"

V6_FEATURE_COLUMNS = dedupe_columns(MARKET_PROBABILITY_COLUMNS)
V8_FEATURE_COLUMNS = dedupe_columns(MARKET_PROBABILITY_COLUMNS + XG_ROLLING_FEATURE_COLUMNS)
COMMON_REQUIRED_COLUMNS = dedupe_columns(V8_FEATURE_COLUMNS + [TARGET_COLUMN, "season", "clean_match_id"])

ACCURACY_TOLERANCE_FOR_SELECTIVE_GAIN = -0.0030
MIN_DRAW_RECALL_GAIN_FOR_SELECTIVE_GAIN = 0.0300


# Arrondit une valeur numérique et protège les divisions absentes.
def safe_round(value: float | int | None, digits: int = 4) -> float:
    if value is None:
        return 0.0
    return round(float(value), digits)


# Vérifie la présence des colonnes nécessaires à l'expérience V8.1.
def validate_columns(feature_dataframe: pd.DataFrame, columns: list[str]) -> None:
    missing_columns = [column for column in columns if column not in feature_dataframe.columns]
    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes pour V8.1 gating : {missing_columns}")


# Prépare un split chronologique commun à V6 et V8 pour comparer les deux signaux sur exactement les mêmes matchs.
def prepare_common_train_test(feature_dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    validate_columns(feature_dataframe, COMMON_REQUIRED_COLUMNS)

    working_dataframe = feature_dataframe.dropna(subset=COMMON_REQUIRED_COLUMNS).copy()
    for column in V8_FEATURE_COLUMNS:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=COMMON_REQUIRED_COLUMNS).copy()
    train_dataframe = working_dataframe[working_dataframe["season"].isin(TRAIN_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError(
            "Train ou test vide pour V8.1. "
            f"Train seasons={TRAIN_SEASONS}, test seasons={TEST_SEASONS}."
        )

    return working_dataframe, train_dataframe, test_dataframe


# Entraîne le modèle de référence LogisticRegression_balanced sur une famille de features donnée.
def train_predict_model(
    train_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[object, list[str], pd.DataFrame]:
    model = build_reference_model()
    model.fit(train_dataframe[feature_columns], train_dataframe[TARGET_COLUMN])
    predictions = list(model.predict(test_dataframe[feature_columns]))

    probabilities = pd.DataFrame(index=test_dataframe.index)
    if hasattr(model, "predict_proba"):
        proba_values = model.predict_proba(test_dataframe[feature_columns])
        model_classes = list(model.classes_)
        for class_name in CLASS_LABELS:
            if class_name in model_classes:
                probabilities[f"prob_{class_name}"] = proba_values[:, model_classes.index(class_name)]
            else:
                probabilities[f"prob_{class_name}"] = 0.0

    return model, predictions, probabilities


# Calcule les colonnes de confiance à partir des probabilités d'un modèle.
def add_probability_summary_columns(output: pd.DataFrame, prefix: str) -> pd.DataFrame:
    probability_columns = [f"{prefix}_prob_{class_name}" for class_name in CLASS_LABELS]
    for column in probability_columns:
        if column not in output.columns:
            raise RuntimeError(f"Colonne de probabilité absente : {column}")

    output[f"{prefix}_max_probability"] = output[probability_columns].max(axis=1)
    output[f"{prefix}_second_probability"] = output[probability_columns].apply(
        lambda row: sorted(row, reverse=True)[1], axis=1
    )
    output[f"{prefix}_prediction_margin"] = (
        output[f"{prefix}_max_probability"] - output[f"{prefix}_second_probability"]
    )
    return output


# Construit la table commune contenant les prédictions V6, V8, les probabilités et les features xG utiles au gating.
def build_comparison_dataframe(
    test_dataframe: pd.DataFrame,
    v6_predictions: list[str],
    v6_probabilities: pd.DataFrame,
    v8_predictions: list[str],
    v8_probabilities: pd.DataFrame,
) -> pd.DataFrame:
    preferred_metadata_columns = [
        "clean_match_id",
        "understat_match_id",
        "season",
        "league_code",
        "match_date",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "home_score",
        "away_score",
        "full_time_home_goals",
        "full_time_away_goals",
        TARGET_COLUMN,
    ]
    metadata_columns = [column for column in preferred_metadata_columns if column in test_dataframe.columns]
    feature_columns = [column for column in V8_FEATURE_COLUMNS if column in test_dataframe.columns]

    output = test_dataframe[dedupe_columns(metadata_columns + feature_columns)].copy()
    output["v6_prediction"] = v6_predictions
    output["v8_prediction"] = v8_predictions
    output["v6_is_correct"] = output[TARGET_COLUMN] == output["v6_prediction"]
    output["v8_is_correct"] = output[TARGET_COLUMN] == output["v8_prediction"]

    for class_name in CLASS_LABELS:
        output[f"v6_prob_{class_name}"] = v6_probabilities[f"prob_{class_name}"].values
        output[f"v8_prob_{class_name}"] = v8_probabilities[f"prob_{class_name}"].values

    output = add_probability_summary_columns(output, "v6")
    output = add_probability_summary_columns(output, "v8")

    output["abs_xg_balance_diff_last_5"] = output["xg_balance_diff_last_5"].abs()
    output["abs_xg_for_diff_last_5"] = output["xg_for_diff_last_5"].abs()
    output["abs_xg_against_diff_last_5"] = output["xg_against_diff_last_5"].abs()
    market_probability_columns = [column for column in MARKET_PROBABILITY_COLUMNS if column in output.columns]
    if len(market_probability_columns) != 3:
        raise RuntimeError(
            "Colonnes de probabilites marche incompletes pour V8.1 : "
            f"attendu={MARKET_PROBABILITY_COLUMNS}, trouve={market_probability_columns}"
        )

    output["v6_market_draw_prob"] = output["market_draw_prob"]
    output["v6_market_max_probability"] = output[market_probability_columns].max(axis=1)
    output["v6_market_second_probability"] = output[market_probability_columns].apply(
        lambda row: sorted(row, reverse=True)[1], axis=1
    )
    output["v6_market_confidence_gap"] = (
        output["v6_market_max_probability"] - output["v6_market_second_probability"]
    )

    return output.reset_index(drop=True)


# Calcule les métriques principales pour une série de prédictions 1X2.
def compute_strategy_metrics(
    strategy_name: str,
    y_true: pd.Series,
    predictions: pd.Series,
    base_metrics: dict | None = None,
    switched_rows: int = 0,
    switched_to_draw_rows: int = 0,
    correct_delta_on_switched_rows: int = 0,
) -> dict:
    report = classification_report(
        y_true,
        predictions,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )
    prediction_distribution = predictions.value_counts().to_dict()
    actual_distribution = y_true.value_counts().to_dict()

    correct_rows = int((y_true == predictions).sum())
    rows = int(len(y_true))
    accuracy = float(accuracy_score(y_true, predictions)) if rows else 0.0
    f1_macro = float(f1_score(y_true, predictions, average="macro")) if rows else 0.0
    f1_weighted = float(f1_score(y_true, predictions, average="weighted")) if rows else 0.0

    metrics = {
        "strategy": strategy_name,
        "model": V2_REFERENCE_MODEL_NAME,
        "rows": rows,
        "correct_rows": correct_rows,
        "accuracy": rounded(accuracy),
        "f1_macro": rounded(f1_macro),
        "f1_weighted": rounded(f1_weighted),
        "home_win_precision": rounded(report["HOME_WIN"]["precision"]),
        "home_win_recall": rounded(report["HOME_WIN"]["recall"]),
        "draw_precision": rounded(report["DRAW"]["precision"]),
        "draw_recall": rounded(report["DRAW"]["recall"]),
        "away_win_precision": rounded(report["AWAY_WIN"]["precision"]),
        "away_win_recall": rounded(report["AWAY_WIN"]["recall"]),
        "predicted_home_win_rows": int(prediction_distribution.get("HOME_WIN", 0)),
        "predicted_draw_rows": int(prediction_distribution.get("DRAW", 0)),
        "predicted_away_win_rows": int(prediction_distribution.get("AWAY_WIN", 0)),
        "actual_home_win_rows": int(actual_distribution.get("HOME_WIN", 0)),
        "actual_draw_rows": int(actual_distribution.get("DRAW", 0)),
        "actual_away_win_rows": int(actual_distribution.get("AWAY_WIN", 0)),
        "predicted_draw_rate": rounded(prediction_distribution.get("DRAW", 0) / rows if rows else 0.0),
        "actual_draw_rate": rounded(actual_distribution.get("DRAW", 0) / rows if rows else 0.0),
        "switched_rows": int(switched_rows),
        "switch_rate": rounded(switched_rows / rows if rows else 0.0),
        "switched_to_draw_rows": int(switched_to_draw_rows),
        "correct_delta_on_switched_rows": int(correct_delta_on_switched_rows),
    }

    if base_metrics is None:
        metrics.update(
            {
                "accuracy_delta_vs_v6_scope": 0.0,
                "f1_macro_delta_vs_v6_scope": 0.0,
                "draw_precision_delta_vs_v6_scope": 0.0,
                "draw_recall_delta_vs_v6_scope": 0.0,
                "net_correct_delta_vs_v6_scope": 0,
            }
        )
    else:
        metrics.update(
            {
                "accuracy_delta_vs_v6_scope": rounded(metrics["accuracy"] - base_metrics["accuracy"]),
                "f1_macro_delta_vs_v6_scope": rounded(metrics["f1_macro"] - base_metrics["f1_macro"]),
                "draw_precision_delta_vs_v6_scope": rounded(metrics["draw_precision"] - base_metrics["draw_precision"]),
                "draw_recall_delta_vs_v6_scope": rounded(metrics["draw_recall"] - base_metrics["draw_recall"]),
                "net_correct_delta_vs_v6_scope": int(metrics["correct_rows"] - base_metrics["correct_rows"]),
            }
        )

    return metrics


# Définit les règles de gating à tester entre la référence V6 et la prédiction V8 xG.
def build_gate_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    xg_predicts_draw = df["v8_prediction"] == "DRAW"
    market_draw_ge_030 = df["market_draw_prob"] >= 0.30
    market_draw_ge_033 = df["market_draw_prob"] >= 0.33
    v6_margin_le_005 = df["v6_prediction_margin"] <= 0.05
    v6_margin_le_010 = df["v6_prediction_margin"] <= 0.10
    v6_margin_le_015 = df["v6_prediction_margin"] <= 0.15
    low_or_medium_confidence = df["v6_max_probability"] <= 0.55
    xg_balance_le_010 = df["abs_xg_balance_diff_last_5"] <= 0.10
    xg_balance_le_020 = df["abs_xg_balance_diff_last_5"] <= 0.20
    xg_balance_le_030 = df["abs_xg_balance_diff_last_5"] <= 0.30

    return {
        "v81_gate_xg_draw_when_v6_margin_le_005": xg_predicts_draw & v6_margin_le_005,
        "v81_gate_xg_draw_when_v6_margin_le_010": xg_predicts_draw & v6_margin_le_010,
        "v81_gate_xg_draw_when_market_draw_ge_030": xg_predicts_draw & market_draw_ge_030,
        "v81_gate_xg_draw_when_market_draw_ge_033": xg_predicts_draw & market_draw_ge_033,
        "v81_gate_xg_draw_when_xg_balance_abs_le_010": xg_predicts_draw & xg_balance_le_010,
        "v81_gate_xg_draw_when_xg_balance_abs_le_020": xg_predicts_draw & xg_balance_le_020,
        "v81_gate_xg_draw_when_margin_010_and_draw_030": xg_predicts_draw & v6_margin_le_010 & market_draw_ge_030,
        "v81_gate_xg_draw_when_margin_015_and_balance_020": xg_predicts_draw & v6_margin_le_015 & xg_balance_le_020,
        "v81_gate_xg_draw_when_draw_030_and_balance_030": xg_predicts_draw & market_draw_ge_030 & xg_balance_le_030,
        "v81_gate_xg_any_when_v6_margin_le_005": v6_margin_le_005,
        "v81_gate_xg_any_when_v6_margin_le_010": v6_margin_le_010,
        "v81_gate_xg_any_when_low_or_medium_confidence": low_or_medium_confidence,
    }


# Applique une règle de gating : par défaut V6, et V8 uniquement sur les lignes activées par le masque.
def apply_gate_predictions(df: pd.DataFrame, gate_mask: pd.Series) -> pd.Series:
    predictions = df["v6_prediction"].copy()
    predictions.loc[gate_mask] = df.loc[gate_mask, "v8_prediction"]
    return predictions


# Evalue toutes les stratégies de gating V8.1 et retourne le tableau comparatif.
def evaluate_gating_strategies(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.Series, pd.Series]:
    y_true = df[TARGET_COLUMN]
    v6_predictions = df["v6_prediction"]
    v8_predictions = df["v8_prediction"]

    v6_metrics = compute_strategy_metrics(V6_STRATEGY_NAME, y_true, v6_predictions)
    v8_metrics = compute_strategy_metrics(V8_STRATEGY_NAME, y_true, v8_predictions, base_metrics=v6_metrics)

    rows = [v6_metrics, v8_metrics]
    best_metrics = v6_metrics
    best_predictions = v6_predictions.copy()
    best_gate_mask = pd.Series(False, index=df.index)

    for strategy_name, gate_mask in build_gate_masks(df).items():
        gate_mask = gate_mask.fillna(False)
        hybrid_predictions = apply_gate_predictions(df, gate_mask)
        switched_rows = int(gate_mask.sum())
        switched_to_draw_rows = int((gate_mask & (df["v8_prediction"] == "DRAW")).sum())
        correct_delta_on_switched_rows = int(
            ((hybrid_predictions == y_true) & gate_mask).sum()
            - ((v6_predictions == y_true) & gate_mask).sum()
        )

        metrics = compute_strategy_metrics(
            strategy_name=strategy_name,
            y_true=y_true,
            predictions=hybrid_predictions,
            base_metrics=v6_metrics,
            switched_rows=switched_rows,
            switched_to_draw_rows=switched_to_draw_rows,
            correct_delta_on_switched_rows=correct_delta_on_switched_rows,
        )
        rows.append(metrics)

        if is_better_gating_candidate(metrics, best_metrics, v6_metrics):
            best_metrics = metrics
            best_predictions = hybrid_predictions.copy()
            best_gate_mask = gate_mask.copy()

    results_dataframe = pd.DataFrame(rows)
    results_dataframe = results_dataframe.sort_values(
        by=[
            "net_correct_delta_vs_v6_scope",
            "accuracy_delta_vs_v6_scope",
            "f1_macro_delta_vs_v6_scope",
            "draw_recall_delta_vs_v6_scope",
            "draw_precision_delta_vs_v6_scope",
        ],
        ascending=False,
    )

    return results_dataframe, best_metrics, best_predictions, best_gate_mask


# Détermine si une stratégie de gating est meilleure selon l'objectif : préserver V6 et améliorer le signal DRAW.
def is_better_gating_candidate(candidate: dict, current_best: dict, v6_metrics: dict) -> bool:
    if current_best["strategy"] == V6_STRATEGY_NAME:
        current_score = (
            0,
            current_best["accuracy"],
            current_best["f1_macro"],
            current_best["draw_recall"],
            current_best["draw_precision"],
        )
    else:
        current_score = candidate_score_for_selection(current_best)

    candidate_score = candidate_score_for_selection(candidate)

    preserves_accuracy = candidate["accuracy_delta_vs_v6_scope"] >= ACCURACY_TOLERANCE_FOR_SELECTIVE_GAIN
    improves_draw_recall = candidate["draw_recall"] > v6_metrics["draw_recall"]
    has_switches = candidate["switched_rows"] > 0

    if preserves_accuracy and improves_draw_recall and has_switches:
        return candidate_score > current_score

    if current_best["strategy"] == V6_STRATEGY_NAME and candidate["net_correct_delta_vs_v6_scope"] > 0:
        return True

    return False


# Crée un score de tri pour choisir le meilleur gating sans sacrifier la stabilité globale.
def candidate_score_for_selection(metrics: dict) -> tuple:
    return (
        1 if metrics["accuracy_delta_vs_v6_scope"] >= ACCURACY_TOLERANCE_FOR_SELECTIVE_GAIN else 0,
        metrics["net_correct_delta_vs_v6_scope"],
        metrics["accuracy_delta_vs_v6_scope"],
        metrics["f1_macro_delta_vs_v6_scope"],
        metrics["draw_recall_delta_vs_v6_scope"],
        metrics["draw_precision_delta_vs_v6_scope"],
        -metrics["switch_rate"],
    )


# Calcule les métriques d'un segment pour le fichier 143.
def compute_segment_metrics(df: pd.DataFrame, predictions_column: str) -> dict:
    if df.empty:
        return {
            "rows": 0,
            "accuracy": 0.0,
            "f1_macro": 0.0,
            "draw_precision": 0.0,
            "draw_recall": 0.0,
            "predicted_draw_rate": 0.0,
            "actual_draw_rate": 0.0,
        }

    metrics = compute_strategy_metrics(
        strategy_name="segment",
        y_true=df[TARGET_COLUMN],
        predictions=df[predictions_column],
    )
    return {
        "rows": metrics["rows"],
        "accuracy": metrics["accuracy"],
        "f1_macro": metrics["f1_macro"],
        "draw_precision": metrics["draw_precision"],
        "draw_recall": metrics["draw_recall"],
        "predicted_draw_rate": metrics["predicted_draw_rate"],
        "actual_draw_rate": metrics["actual_draw_rate"],
    }


# Construit les segments de stabilité du meilleur gating : ligue, saison, activation du gate et changements V6/V8.
def build_segments_dataframe(df: pd.DataFrame, best_predictions: pd.Series, best_gate_mask: pd.Series) -> pd.DataFrame:
    segment_df = df.copy()
    segment_df["best_prediction"] = best_predictions.values
    segment_df["gate_applied"] = best_gate_mask.values
    segment_df["switch_type"] = "no_switch"
    segment_df.loc[segment_df["gate_applied"], "switch_type"] = (
        segment_df.loc[segment_df["gate_applied"], "v6_prediction"]
        + "_to_"
        + segment_df.loc[segment_df["gate_applied"], "v8_prediction"]
    )

    rows = []
    segment_definitions = [
        ("league", ["league_code"]),
        ("season", ["season"]),
        ("league_season", ["league_code", "season"]),
        ("gate_applied", ["gate_applied"]),
        ("switch_type", ["switch_type"]),
        ("v6_prediction", ["v6_prediction"]),
        ("v8_prediction", ["v8_prediction"]),
    ]

    for segment_type, group_columns in segment_definitions:
        for keys, group in segment_df.groupby(group_columns, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            prefix = {"segment_type": segment_type}
            for column_name, value in zip(group_columns, keys):
                prefix[column_name] = value
            prefix.update(compute_segment_metrics(group, "best_prediction"))
            rows.append(prefix)

    return pd.DataFrame(rows).sort_values(["segment_type", "rows"], ascending=[True, False])


# Détermine le statut expérimental final de V8.1.
def determine_status(best_metrics: dict, v6_metrics: dict) -> str:
    accuracy_delta = best_metrics["accuracy"] - v6_metrics["accuracy"]
    f1_delta = best_metrics["f1_macro"] - v6_metrics["f1_macro"]
    draw_recall_delta = best_metrics["draw_recall"] - v6_metrics["draw_recall"]

    if accuracy_delta >= 0 and f1_delta >= 0 and draw_recall_delta > 0:
        return "V81_UNDERSTAT_XG_GATING_GLOBAL_CANDIDATE"

    if (
        accuracy_delta >= ACCURACY_TOLERANCE_FOR_SELECTIVE_GAIN
        and draw_recall_delta >= MIN_DRAW_RECALL_GAIN_FOR_SELECTIVE_GAIN
    ):
        return "V81_UNDERSTAT_XG_GATING_SELECTIVE_DRAW_CANDIDATE"

    if best_metrics["strategy"] != V6_STRATEGY_NAME and draw_recall_delta > 0:
        return "V81_UNDERSTAT_XG_GATING_SELECTIVE_REVIEW"

    return "V81_UNDERSTAT_XG_GATING_NO_GAIN"


# Crée le CSV de prédictions détaillées pour le meilleur gating V8.1.
def build_best_predictions_dataframe(
    df: pd.DataFrame,
    best_metrics: dict,
    best_predictions: pd.Series,
    best_gate_mask: pd.Series,
) -> pd.DataFrame:
    output = df.copy()
    output.insert(0, "strategy", best_metrics["strategy"])
    output["gate_applied"] = best_gate_mask.values
    output["predicted_result"] = best_predictions.values
    output["is_correct"] = output[TARGET_COLUMN] == output["predicted_result"]
    output["v6_to_v8_switch"] = output["gate_applied"] & (output["v6_prediction"] != output["v8_prediction"])
    output["switch_gain_vs_v6"] = output["is_correct"].astype(int) - output["v6_is_correct"].astype(int)
    return output


# Rédige la synthèse V8.1 avec les résultats et les garde-fous.
def build_summary(
    metadata: dict,
    working_dataframe: pd.DataFrame,
    train_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
    results_dataframe: pd.DataFrame,
    best_metrics: dict,
    status: str,
) -> str:
    v6_row = results_dataframe[results_dataframe["strategy"] == V6_STRATEGY_NAME].iloc[0].to_dict()
    v8_row = results_dataframe[results_dataframe["strategy"] == V8_STRATEGY_NAME].iloc[0].to_dict()

    lines = [
        "RubyBets - ML 1X2 V8.1 Understat xG gating",
        "140 - Synthese experience V8.1 gating selectif",
        "",
        "Objectif :",
        "Tester si le signal rolling xG Understat peut etre active seulement sur certains profils de matchs, en conservant V6 Market prior comme reference globale.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Aucune integration produit d'Understat.",
        "- Experience ML interne uniquement, sans sauvegarde de modele.",
        "",
        "Split chronologique :",
        f"- Train : {', '.join(TRAIN_SEASONS)}",
        f"- Test : {', '.join(TEST_SEASONS)}",
        "",
        "Volumes :",
        f"- Clean matches loaded : {metadata['clean_matches_loaded']}",
        f"- Rolling xG rows loaded : {metadata['rolling_xg_rows']}",
        f"- V8 merged rows : {metadata['v8_merged_rows']}",
        f"- Rows after common V6/V8 cleaning : {len(working_dataframe)}",
        f"- Train rows : {len(train_dataframe)}",
        f"- Test rows : {len(test_dataframe)}",
        "",
        "Reference V6 sur le perimetre xG commun :",
        f"- Accuracy : {v6_row['accuracy']}",
        f"- F1 macro : {v6_row['f1_macro']}",
        f"- DRAW precision : {v6_row['draw_precision']}",
        f"- DRAW recall : {v6_row['draw_recall']}",
        "",
        "V8 xG complete sur le meme perimetre :",
        f"- Accuracy : {v8_row['accuracy']}",
        f"- F1 macro : {v8_row['f1_macro']}",
        f"- DRAW precision : {v8_row['draw_precision']}",
        f"- DRAW recall : {v8_row['draw_recall']}",
        "",
        "Meilleur gating V8.1 :",
        f"- Strategy : {best_metrics['strategy']}",
        f"- Status : {status}",
        f"- Accuracy : {best_metrics['accuracy']}",
        f"- F1 macro : {best_metrics['f1_macro']}",
        f"- DRAW precision : {best_metrics['draw_precision']}",
        f"- DRAW recall : {best_metrics['draw_recall']}",
        f"- Net correct delta vs V6 scope : {best_metrics['net_correct_delta_vs_v6_scope']}",
        f"- Accuracy delta vs V6 scope : {best_metrics['accuracy_delta_vs_v6_scope']}",
        f"- F1 macro delta vs V6 scope : {best_metrics['f1_macro_delta_vs_v6_scope']}",
        f"- DRAW recall delta vs V6 scope : {best_metrics['draw_recall_delta_vs_v6_scope']}",
        f"- Switched rows : {best_metrics['switched_rows']}",
        f"- Switch rate : {best_metrics['switch_rate']}",
        "",
        "Reference V6 globale observee avant V8 :",
        f"- Accuracy : {V6_GLOBAL_BEST_ACCURACY}",
        f"- F1 macro : {V6_GLOBAL_BEST_F1_MACRO}",
        f"- DRAW precision : {V6_GLOBAL_BEST_DRAW_PRECISION}",
        f"- DRAW recall : {V6_GLOBAL_BEST_DRAW_RECALL}",
        "",
        "Top strategies V8.1 :",
    ]

    for _, row in results_dataframe.head(8).iterrows():
        lines.append(
            f"- {row['strategy']} | acc={row['accuracy']} | f1_macro={row['f1_macro']} | "
            f"draw_precision={row['draw_precision']} | draw_recall={row['draw_recall']} | "
            f"net_delta={row['net_correct_delta_vs_v6_scope']} | switched={row['switched_rows']}"
        )

    lines.extend(
        [
            "",
            "Fichiers generes :",
            f"- {SUMMARY_PATH}",
            f"- {RESULTS_CSV_PATH}",
            f"- {BEST_PREDICTIONS_CSV_PATH}",
            f"- {SEGMENTS_CSV_PATH}",
            f"- {DECISION_PATH}",
        ]
    )

    return "\n".join(lines)


# Rédige la décision technique V8.1 après comparaison avec V6.
def build_decision(best_metrics: dict, status: str) -> str:
    lines = [
        "RubyBets - ML 1X2 V8.1 Understat xG gating",
        "144 - Decision experimentale V8.1 gating selectif",
        "",
        f"Status : {status}",
        "",
        "Decision :",
    ]

    if status == "V81_UNDERSTAT_XG_GATING_GLOBAL_CANDIDATE":
        lines.append(
            "Le gating V8.1 obtient un gain global sur le perimetre teste. Il peut etre conserve comme candidat experimental, mais il ne doit pas etre integre au produit sans validation supplementaire."
        )
    elif status == "V81_UNDERSTAT_XG_GATING_SELECTIVE_DRAW_CANDIDATE":
        lines.append(
            "Le gating V8.1 conserve presque la stabilite de V6 tout en recuperant un gain utile sur les matchs nuls. Il doit rester experimental et passer par une analyse de stabilite supplementaire."
        )
    elif status == "V81_UNDERSTAT_XG_GATING_SELECTIVE_REVIEW":
        lines.append(
            "Le gating V8.1 montre un signal selectif sur les matchs nuls, mais le compromis performance/stabilite reste a revoir avant toute decision."
        )
    else:
        lines.append(
            "Le gating V8.1 ne produit pas de gain suffisant par rapport a V6. Le signal xG reste utile pour l'analyse, mais pas pour une activation automatique."
        )

    lines.extend(
        [
            "",
            "Meilleure strategie :",
            f"- Strategy : {best_metrics['strategy']}",
            f"- Accuracy : {best_metrics['accuracy']}",
            f"- F1 macro : {best_metrics['f1_macro']}",
            f"- DRAW precision : {best_metrics['draw_precision']}",
            f"- DRAW recall : {best_metrics['draw_recall']}",
            f"- Net correct delta vs V6 scope : {best_metrics['net_correct_delta_vs_v6_scope']}",
            f"- Switched rows : {best_metrics['switched_rows']}",
            "",
            "Garde-fou :",
            "Ne pas modifier ml.features, ne pas sauvegarder de modele et ne pas brancher Understat a l'API ou au frontend avant validation forte.",
            "",
            "Prochaine action recommandee :",
            "Analyser les fichiers 141, 142 et 143. Si un gating ressort comme candidat, lancer ensuite une analyse de stabilite V8.1 par ligue, saison, classe et segments de switch.",
            "",
            "Statut de suivi :",
            "- Tache realisee si les fichiers 140, 141, 142, 143 et 144 sont generes.",
            "- Statut source a mettre a jour : a produire -> realise pour l'experience V8.1 Understat xG gating selectif.",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les preuves de l'expérience V8.1 dans reports/evidence/ml_training.
def save_reports(
    results_dataframe: pd.DataFrame,
    best_predictions_dataframe: pd.DataFrame,
    segments_dataframe: pd.DataFrame,
    summary: str,
    decision: str,
) -> None:
    ensure_report_dir()
    results_dataframe.to_csv(RESULTS_CSV_PATH, index=False, encoding="utf-8")
    best_predictions_dataframe.to_csv(BEST_PREDICTIONS_CSV_PATH, index=False, encoding="utf-8")
    segments_dataframe.to_csv(SEGMENTS_CSV_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    DECISION_PATH.write_text(decision, encoding="utf-8")


# Lance toute l'expérience V8.1 de gating sélectif.
def main() -> None:
    try:
        database_url = get_database_url()

        print("Chargement des features V6/V8 et rolling xG Understat...", flush=True)
        feature_dataframe, metadata = build_v8_feature_dataframe(database_url)
        working_dataframe, train_dataframe, test_dataframe = prepare_common_train_test(feature_dataframe)
        print(f"Rows common scope: {len(working_dataframe)}", flush=True)
        print(f"Train rows: {len(train_dataframe)}", flush=True)
        print(f"Test rows: {len(test_dataframe)}", flush=True)

        print("Entrainement reference V6 Market prior sur le perimetre commun...", flush=True)
        _, v6_predictions, v6_probabilities = train_predict_model(
            train_dataframe=train_dataframe,
            test_dataframe=test_dataframe,
            feature_columns=V6_FEATURE_COLUMNS,
        )

        print("Entrainement V8 Market prior + rolling xG sur le meme perimetre...", flush=True)
        _, v8_predictions, v8_probabilities = train_predict_model(
            train_dataframe=train_dataframe,
            test_dataframe=test_dataframe,
            feature_columns=V8_FEATURE_COLUMNS,
        )

        comparison_dataframe = build_comparison_dataframe(
            test_dataframe=test_dataframe,
            v6_predictions=v6_predictions,
            v6_probabilities=v6_probabilities,
            v8_predictions=v8_predictions,
            v8_probabilities=v8_probabilities,
        )

        print("Evaluation des strategies de gating V8.1...", flush=True)
        results_dataframe, best_metrics, best_predictions, best_gate_mask = evaluate_gating_strategies(
            comparison_dataframe
        )
        status = determine_status(
            best_metrics=best_metrics,
            v6_metrics=results_dataframe[results_dataframe["strategy"] == V6_STRATEGY_NAME].iloc[0].to_dict(),
        )

        best_predictions_dataframe = build_best_predictions_dataframe(
            df=comparison_dataframe,
            best_metrics=best_metrics,
            best_predictions=best_predictions,
            best_gate_mask=best_gate_mask,
        )
        segments_dataframe = build_segments_dataframe(
            df=comparison_dataframe,
            best_predictions=best_predictions,
            best_gate_mask=best_gate_mask,
        )
        summary = build_summary(
            metadata=metadata,
            working_dataframe=working_dataframe,
            train_dataframe=train_dataframe,
            test_dataframe=test_dataframe,
            results_dataframe=results_dataframe,
            best_metrics=best_metrics,
            status=status,
        )
        decision = build_decision(best_metrics=best_metrics, status=status)

        save_reports(
            results_dataframe=results_dataframe,
            best_predictions_dataframe=best_predictions_dataframe,
            segments_dataframe=segments_dataframe,
            summary=summary,
            decision=decision,
        )

        print("OK - Experience V8.1 Understat xG gating terminee.", flush=True)
        print(f"Status: {status}", flush=True)
        print(f"Best strategy: {best_metrics['strategy']}", flush=True)
        print(f"Accuracy: {best_metrics['accuracy']}", flush=True)
        print(f"F1 macro: {best_metrics['f1_macro']}", flush=True)
        print(f"DRAW precision: {best_metrics['draw_precision']}", flush=True)
        print(f"DRAW recall: {best_metrics['draw_recall']}", flush=True)
        print(f"Net correct delta vs V6 scope: {best_metrics['net_correct_delta_vs_v6_scope']}", flush=True)
        print(f"Switched rows: {best_metrics['switched_rows']}", flush=True)
        print(f"Summary saved: {SUMMARY_PATH}", flush=True)
        print(f"Results CSV saved: {RESULTS_CSV_PATH}", flush=True)
        print(f"Best predictions CSV saved: {BEST_PREDICTIONS_CSV_PATH}", flush=True)
        print(f"Segments CSV saved: {SEGMENTS_CSV_PATH}", flush=True)
        print(f"Decision saved: {DECISION_PATH}", flush=True)

    except Exception as error:
        print("Erreur pendant l'experience V8.1 Understat xG gating.", flush=True)
        print(error, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
#
# backend/scripts/ml/train_1x2_v81_understat_xg_gating.py
#   -> lit backend/.env via get_database_url()
#   -> lit PostgreSQL en lecture seule : ml.clean_matches + ml.raw_matches.raw_data
#   -> lit reports/evidence/ml_training/125_1x2_understat_rolling_xg_dry_run_features.csv
#   -> reutilise les builders V2/V5/V6/V8 en memoire
#   -> compare V6 Market prior, V8 rolling xG et plusieurs gates V8.1
#   -> ecrit uniquement des preuves dans reports/evidence/ml_training/140 a 144
#   -> ne modifie pas PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou models/
