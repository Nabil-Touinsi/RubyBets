# Rôle du fichier : tester la V9 ML 1X2 avec calibration des probabilités et abstention intelligente, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, brier_score_loss, classification_report, f1_score, log_loss


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "145_1x2_v9_selective_calibration_abstention_summary.txt"
RESULTS_CSV_PATH = REPORT_DIR / "146_1x2_v9_selective_calibration_abstention_results.csv"
BEST_PREDICTIONS_CSV_PATH = REPORT_DIR / "147_1x2_v9_selective_calibration_abstention_best_predictions.csv"
CONFIDENCE_BINS_CSV_PATH = REPORT_DIR / "148_1x2_v9_selective_calibration_abstention_confidence_bins.csv"
ERROR_PATTERNS_CSV_PATH = REPORT_DIR / "149_1x2_v9_selective_calibration_abstention_error_patterns.csv"
DECISION_PATH = REPORT_DIR / "150_1x2_v9_selective_calibration_abstention_decision.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    TARGET_COLUMN,
    TEST_SEASONS,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)
from experiment_1x2_v2_feature_candidates import build_v2_fast_feature_dataframe # noqa: E402
from experiment_1x2_v5_balance_features import (  # noqa: E402
    CLASS_LABELS,
    V2_REFERENCE_MODEL_NAME,
    add_v5_balance_features,
    build_reference_model,
)
from experiment_1x2_v6_market_prior import (  # noqa: E402
    MARKET_GAP_COLUMNS,
    MARKET_PROBABILITY_COLUMNS,
    build_market_prior_dataframe,
    fetch_market_raw_data,
    merge_market_prior_features,
)

warnings.filterwarnings("ignore", category=UserWarning)

VALIDATION_SEASONS = ["2021_2022"]
V9_FEATURE_COLUMNS = MARKET_PROBABILITY_COLUMNS
V9_REQUIRED_COLUMNS = [TARGET_COLUMN, "season", "clean_match_id"] + V9_FEATURE_COLUMNS

CALIBRATION_METHODS = ["raw", "sigmoid", "isotonic"]
MAX_PROBABILITY_THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
MARGIN_THRESHOLDS = [0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20]
DRAW_PROBABILITY_THRESHOLDS = [0.33, 0.35, 0.38, 0.40]
DRAW_MARGIN_THRESHOLDS = [0.03, 0.05, 0.08]
CONFIDENCE_BINS = [0.0, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80, 1.0]

MIN_ACCEPTED_COVERAGE = 0.10
TARGET_SELECTIVE_ACCURACY = 0.60
REVIEW_SELECTIVE_ACCURACY = 0.56
MIN_SELECTED_ROWS_PER_SEASON_FOR_STABILITY = 30
MIN_SEASON_ACCURACY_FOR_ACCEPTANCE = 0.55

V6_GLOBAL_REFERENCE_ACCURACY = 0.5205
V6_GLOBAL_REFERENCE_F1_MACRO = 0.4878
V6_GLOBAL_REFERENCE_DRAW_PRECISION = 0.3166
V6_GLOBAL_REFERENCE_DRAW_RECALL = 0.2628
V8_REFERENCE_ACCURACY = 0.5097
V8_REFERENCE_F1_MACRO = 0.4926
V8_REFERENCE_DRAW_PRECISION = 0.3073
V8_REFERENCE_DRAW_RECALL = 0.3584
V81_REFERENCE_ACCURACY = 0.5103
V81_REFERENCE_F1_MACRO = 0.4921
V81_REFERENCE_DRAW_PRECISION = 0.3061
V81_REFERENCE_DRAW_RECALL = 0.3517


@dataclass(frozen=True)
class SelectivePolicy:
    model_variant: str
    max_probability_threshold: float
    margin_threshold: float
    draw_probability_threshold: float
    draw_margin_threshold: float

    @property
    def name(self) -> str:
        return (
            f"v9_{self.model_variant}"
            f"_p{self.max_probability_threshold:.2f}"
            f"_m{self.margin_threshold:.2f}"
            f"_drawp{self.draw_probability_threshold:.2f}"
            f"_drawm{self.draw_margin_threshold:.2f}"
        ).replace(".", "")


# Arrondit une valeur numérique pour stabiliser les exports.
def rounded(value: float | int | None, digits: int = 4) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return round(float(value), digits)


# Evite les doublons de colonnes dans les exports de prédictions.
def dedupe_columns(columns: list[str]) -> list[str]:
    seen = set()
    result = []
    for column in columns:
        if column not in seen:
            result.append(column)
            seen.add(column)
    return result


# Vérifie la présence des colonnes nécessaires à l'expérience V9.
def validate_columns(dataframe: pd.DataFrame, columns: list[str]) -> None:
    missing_columns = [column for column in columns if column not in dataframe.columns]
    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes pour V9 selective calibration : {missing_columns}")


# Construit le DataFrame V6 market-ready utilisé comme base de la V9.
def build_v9_feature_dataframe(database_url: str) -> tuple[pd.DataFrame, dict]:
    clean_matches = fetch_clean_matches(database_url)
    v2_feature_dataframe = build_v2_fast_feature_dataframe(clean_matches)
    v5_feature_dataframe = add_v5_balance_features(v2_feature_dataframe)

    market_raw_rows = fetch_market_raw_data(database_url)
    market_dataframe = build_market_prior_dataframe(market_raw_rows)
    v6_feature_dataframe = merge_market_prior_features(v5_feature_dataframe, market_dataframe)

    validate_columns(v6_feature_dataframe, V9_REQUIRED_COLUMNS)
    working_dataframe = v6_feature_dataframe.dropna(subset=V9_REQUIRED_COLUMNS).copy()

    for column in MARKET_PROBABILITY_COLUMNS + MARKET_GAP_COLUMNS:
        if column in working_dataframe.columns:
            working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=V9_REQUIRED_COLUMNS).copy()

    metadata = {
        "clean_matches_loaded": len(clean_matches),
        "v2_rows": len(v2_feature_dataframe),
        "v5_rows": len(v5_feature_dataframe),
        "v6_rows": len(v6_feature_dataframe),
        "market_ready_rows": len(working_dataframe),
        "market_ready_rate": len(working_dataframe) / len(v6_feature_dataframe) if len(v6_feature_dataframe) else 0.0,
    }

    return working_dataframe, metadata


# Prépare un split chronologique train / validation / test pour éviter de choisir les seuils directement sur le test.
def prepare_temporal_splits(feature_dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    validation_dataframe = feature_dataframe[feature_dataframe["season"].isin(VALIDATION_SEASONS)].copy()
    test_dataframe = feature_dataframe[feature_dataframe["season"].isin(TEST_SEASONS)].copy()
    train_core_dataframe = feature_dataframe[
        (~feature_dataframe["season"].isin(VALIDATION_SEASONS))
        & (~feature_dataframe["season"].isin(TEST_SEASONS))
    ].copy()

    if train_core_dataframe.empty or validation_dataframe.empty or test_dataframe.empty:
        raise RuntimeError(
            "Split V9 vide ou incomplet. "
            f"Train core={len(train_core_dataframe)}, validation={len(validation_dataframe)}, test={len(test_dataframe)}."
        )

    return train_core_dataframe, validation_dataframe, test_dataframe


# Crée le modèle V6 brut ou calibré selon la variante demandée.
def build_model_variant(model_variant: str):
    if model_variant == "raw":
        return build_reference_model()

    if model_variant not in {"sigmoid", "isotonic"}:
        raise RuntimeError(f"Variante de calibration inconnue : {model_variant}")

    try:
        return CalibratedClassifierCV(
            estimator=build_reference_model(),
            method=model_variant,
            cv=3,
        )
    except TypeError:
        return CalibratedClassifierCV(
            base_estimator=build_reference_model(),
            method=model_variant,
            cv=3,
        )


# Entraîne une variante V6 et retourne les probabilités alignées avec les classes RubyBets.
def train_and_predict_probabilities(
    model_variant: str,
    train_dataframe: pd.DataFrame,
    predict_dataframe: pd.DataFrame,
) -> tuple[object, pd.DataFrame]:
    model = build_model_variant(model_variant)
    model.fit(train_dataframe[V9_FEATURE_COLUMNS], train_dataframe[TARGET_COLUMN])

    proba_values = model.predict_proba(predict_dataframe[V9_FEATURE_COLUMNS])
    model_classes = list(model.classes_)
    probabilities = pd.DataFrame(index=predict_dataframe.index)

    for class_name in CLASS_LABELS:
        if class_name in model_classes:
            probabilities[f"prob_{class_name}"] = proba_values[:, model_classes.index(class_name)]
        else:
            probabilities[f"prob_{class_name}"] = 0.0

    return model, probabilities


# Transforme les probabilités en prédiction, confiance maximale et marge entre les deux premières classes.
def add_probability_decision_columns(probabilities: pd.DataFrame, prefix: str) -> pd.DataFrame:
    output = probabilities.copy()
    probability_columns = [f"prob_{class_name}" for class_name in CLASS_LABELS]

    output[f"{prefix}_predicted_class"] = output[probability_columns].idxmax(axis=1).str.replace("prob_", "", regex=False)
    output[f"{prefix}_max_probability"] = output[probability_columns].max(axis=1)
    output[f"{prefix}_second_probability"] = output[probability_columns].apply(
        lambda row: sorted(row, reverse=True)[1], axis=1
    )
    output[f"{prefix}_margin"] = output[f"{prefix}_max_probability"] - output[f"{prefix}_second_probability"]

    for class_name in CLASS_LABELS:
        output[f"{prefix}_prob_{class_name}"] = output[f"prob_{class_name}"]
        output = output.drop(columns=[f"prob_{class_name}"])

    return output


# Construit la table de prédictions pour une variante de modèle sur un split donné.
def build_prediction_dataframe(
    source_dataframe: pd.DataFrame,
    probabilities: pd.DataFrame,
    model_variant: str,
    raw_v6_probabilities: pd.DataFrame | None = None,
) -> pd.DataFrame:
    preferred_columns = [
        "clean_match_id",
        "match_date",
        "league_code",
        "season",
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
    metadata_columns = [column for column in preferred_columns if column in source_dataframe.columns]
    market_columns = [column for column in MARKET_PROBABILITY_COLUMNS + MARKET_GAP_COLUMNS if column in source_dataframe.columns]
    output = source_dataframe[dedupe_columns(metadata_columns + market_columns)].copy()

    model_probabilities = add_probability_decision_columns(probabilities, model_variant)
    output = output.join(model_probabilities)
    output[f"{model_variant}_is_correct"] = output[TARGET_COLUMN] == output[f"{model_variant}_predicted_class"]

    if raw_v6_probabilities is not None:
        raw_probabilities = add_probability_decision_columns(raw_v6_probabilities, "raw_v6_reference")
        reference_columns = [
            "raw_v6_reference_predicted_class",
            "raw_v6_reference_max_probability",
            "raw_v6_reference_margin",
            "raw_v6_reference_prob_HOME_WIN",
            "raw_v6_reference_prob_DRAW",
            "raw_v6_reference_prob_AWAY_WIN",
        ]
        output = output.join(raw_probabilities[reference_columns])
        output["raw_v6_reference_is_correct"] = output[TARGET_COLUMN] == output["raw_v6_reference_predicted_class"]

    return output.reset_index(drop=True)


# Génère toutes les politiques d'abstention à tester sur la validation et sur le test.
def build_selective_policies(model_variant: str) -> list[SelectivePolicy]:
    policies = []
    for max_threshold in MAX_PROBABILITY_THRESHOLDS:
        for margin_threshold in MARGIN_THRESHOLDS:
            for draw_threshold in DRAW_PROBABILITY_THRESHOLDS:
                for draw_margin_threshold in DRAW_MARGIN_THRESHOLDS:
                    policies.append(
                        SelectivePolicy(
                            model_variant=model_variant,
                            max_probability_threshold=max_threshold,
                            margin_threshold=margin_threshold,
                            draw_probability_threshold=draw_threshold,
                            draw_margin_threshold=draw_margin_threshold,
                        )
                    )
    return policies


# Applique une politique V9 et ajoute les colonnes recommandation / abstention.
def apply_selective_policy(prediction_dataframe: pd.DataFrame, policy: SelectivePolicy) -> pd.DataFrame:
    output = prediction_dataframe.copy()
    prefix = policy.model_variant
    predicted_class_column = f"{prefix}_predicted_class"
    max_probability_column = f"{prefix}_max_probability"
    margin_column = f"{prefix}_margin"
    draw_probability_column = f"{prefix}_prob_DRAW"

    base_accept_mask = (
        (output[max_probability_column] >= policy.max_probability_threshold)
        & (output[margin_column] >= policy.margin_threshold)
    )
    non_draw_mask = output[predicted_class_column] != "DRAW"
    draw_accept_mask = (
        (output[predicted_class_column] == "DRAW")
        & (output[draw_probability_column] >= policy.draw_probability_threshold)
        & (output[margin_column] >= policy.draw_margin_threshold)
    )

    output["v9_policy"] = policy.name
    output["v9_model_variant"] = policy.model_variant
    output["v9_recommendation_status"] = np.where(base_accept_mask & (non_draw_mask | draw_accept_mask), "RECOMMEND", "ABSTAIN")
    output["v9_prediction"] = np.where(output["v9_recommendation_status"] == "RECOMMEND", output[predicted_class_column], "ABSTAIN")
    output["v9_confidence_probability"] = output[max_probability_column]
    output["v9_margin"] = output[margin_column]
    output["v9_is_correct"] = output[TARGET_COLUMN] == output["v9_prediction"]

    output["v9_abstention_reason"] = "accepted"
    output.loc[~base_accept_mask, "v9_abstention_reason"] = "low_probability_or_margin"
    output.loc[
        base_accept_mask & (output[predicted_class_column] == "DRAW") & ~draw_accept_mask,
        "v9_abstention_reason",
    ] = "draw_not_strong_enough"

    return output


# Calcule le score Brier multiclasses pour mesurer la qualité probabiliste.
def compute_multiclass_brier_score(y_true: pd.Series, probabilities: pd.DataFrame, prefix: str) -> float:
    y_true_array = pd.get_dummies(y_true).reindex(columns=CLASS_LABELS, fill_value=0).to_numpy()
    probability_array = probabilities[[f"{prefix}_prob_{class_name}" for class_name in CLASS_LABELS]].to_numpy()
    return float(np.mean(np.sum((probability_array - y_true_array) ** 2, axis=1)))


# Calcule l'erreur de calibration attendue à partir des probabilités de confiance maximale.
def compute_expected_calibration_error(prediction_dataframe: pd.DataFrame, prefix: str) -> float:
    confidence_column = f"{prefix}_max_probability"
    correct_column = f"{prefix}_is_correct"
    total_rows = len(prediction_dataframe)
    if total_rows == 0:
        return 0.0

    ece = 0.0
    for bin_start, bin_end in zip(CONFIDENCE_BINS[:-1], CONFIDENCE_BINS[1:]):
        if bin_end == CONFIDENCE_BINS[-1]:
            bin_mask = (prediction_dataframe[confidence_column] >= bin_start) & (prediction_dataframe[confidence_column] <= bin_end)
        else:
            bin_mask = (prediction_dataframe[confidence_column] >= bin_start) & (prediction_dataframe[confidence_column] < bin_end)

        bin_dataframe = prediction_dataframe[bin_mask]
        if bin_dataframe.empty:
            continue

        bin_accuracy = float(bin_dataframe[correct_column].mean())
        bin_confidence = float(bin_dataframe[confidence_column].mean())
        ece += (len(bin_dataframe) / total_rows) * abs(bin_accuracy - bin_confidence)

    return float(ece)


# Calcule les métriques globales d'une variante de modèle sans abstention.
def compute_model_probability_metrics(
    model_variant: str,
    evaluation_scope: str,
    prediction_dataframe: pd.DataFrame,
) -> dict:
    y_true = prediction_dataframe[TARGET_COLUMN].reset_index(drop=True)
    y_pred = prediction_dataframe[f"{model_variant}_predicted_class"].reset_index(drop=True)
    probability_columns = [f"{model_variant}_prob_{class_name}" for class_name in CLASS_LABELS]
    report = classification_report(y_true, y_pred, labels=CLASS_LABELS, output_dict=True, zero_division=0)

    try:
        model_log_loss = log_loss(y_true, prediction_dataframe[probability_columns], labels=CLASS_LABELS)
    except ValueError:
        model_log_loss = 0.0

    return {
        "evaluation_scope": evaluation_scope,
        "strategy": f"v9_{model_variant}_all_predictions_no_abstention",
        "model_variant": model_variant,
        "policy_type": "all_predictions_no_abstention",
        "rows": int(len(prediction_dataframe)),
        "selected_rows": int(len(prediction_dataframe)),
        "abstained_rows": 0,
        "coverage": 1.0,
        "abstention_rate": 0.0,
        "accuracy": rounded(accuracy_score(y_true, y_pred)),
        "selective_accuracy": rounded(accuracy_score(y_true, y_pred)),
        "f1_macro": rounded(f1_score(y_true, y_pred, average="macro")),
        "selective_f1_macro": rounded(f1_score(y_true, y_pred, average="macro")),
        "home_win_precision": rounded(report["HOME_WIN"]["precision"]),
        "home_win_recall": rounded(report["HOME_WIN"]["recall"]),
        "draw_precision": rounded(report["DRAW"]["precision"]),
        "draw_recall": rounded(report["DRAW"]["recall"]),
        "away_win_precision": rounded(report["AWAY_WIN"]["precision"]),
        "away_win_recall": rounded(report["AWAY_WIN"]["recall"]),
        "brier_score": rounded(compute_multiclass_brier_score(y_true, prediction_dataframe, model_variant)),
        "log_loss": rounded(model_log_loss),
        "expected_calibration_error": rounded(compute_expected_calibration_error(prediction_dataframe, model_variant)),
        "selected_accuracy_delta_vs_raw_v6_full": 0.0,
        "net_correct_delta_vs_raw_v6_same_selected": 0,
        "max_probability_threshold": 0.0,
        "margin_threshold": 0.0,
        "draw_probability_threshold": 0.0,
        "draw_margin_threshold": 0.0,
        "predicted_home_win_rows": int((y_pred == "HOME_WIN").sum()),
        "predicted_draw_rows": int((y_pred == "DRAW").sum()),
        "predicted_away_win_rows": int((y_pred == "AWAY_WIN").sum()),
    }


# Calcule les métriques d'une politique avec abstention.
def compute_selective_policy_metrics(
    policy: SelectivePolicy,
    evaluation_scope: str,
    policy_dataframe: pd.DataFrame,
    raw_v6_full_accuracy: float,
) -> dict:
    selected_dataframe = policy_dataframe[policy_dataframe["v9_recommendation_status"] == "RECOMMEND"].copy()
    rows = int(len(policy_dataframe))
    selected_rows = int(len(selected_dataframe))
    abstained_rows = rows - selected_rows
    coverage = selected_rows / rows if rows else 0.0

    if selected_rows == 0:
        return {
            "evaluation_scope": evaluation_scope,
            "strategy": policy.name,
            "model_variant": policy.model_variant,
            "policy_type": "selective_abstention",
            "rows": rows,
            "selected_rows": 0,
            "abstained_rows": abstained_rows,
            "coverage": 0.0,
            "abstention_rate": 1.0,
            "accuracy": 0.0,
            "selective_accuracy": 0.0,
            "f1_macro": 0.0,
            "selective_f1_macro": 0.0,
            "home_win_precision": 0.0,
            "home_win_recall": 0.0,
            "draw_precision": 0.0,
            "draw_recall": 0.0,
            "away_win_precision": 0.0,
            "away_win_recall": 0.0,
            "brier_score": 0.0,
            "log_loss": 0.0,
            "expected_calibration_error": 0.0,
            "selected_accuracy_delta_vs_raw_v6_full": rounded(0.0 - raw_v6_full_accuracy),
            "net_correct_delta_vs_raw_v6_same_selected": 0,
            "max_probability_threshold": policy.max_probability_threshold,
            "margin_threshold": policy.margin_threshold,
            "draw_probability_threshold": policy.draw_probability_threshold,
            "draw_margin_threshold": policy.draw_margin_threshold,
            "predicted_home_win_rows": 0,
            "predicted_draw_rows": 0,
            "predicted_away_win_rows": 0,
        }

    y_true = selected_dataframe[TARGET_COLUMN].reset_index(drop=True)
    y_pred = selected_dataframe["v9_prediction"].reset_index(drop=True)
    report = classification_report(y_true, y_pred, labels=CLASS_LABELS, output_dict=True, zero_division=0)
    raw_v6_correct_same_rows = int(selected_dataframe["raw_v6_reference_is_correct"].sum()) if "raw_v6_reference_is_correct" in selected_dataframe.columns else 0
    v9_correct_rows = int((y_true == y_pred).sum())
    prediction_distribution = y_pred.value_counts().to_dict()

    return {
        "evaluation_scope": evaluation_scope,
        "strategy": policy.name,
        "model_variant": policy.model_variant,
        "policy_type": "selective_abstention",
        "rows": rows,
        "selected_rows": selected_rows,
        "abstained_rows": abstained_rows,
        "coverage": rounded(coverage),
        "abstention_rate": rounded(1 - coverage),
        "accuracy": rounded(v9_correct_rows / rows if rows else 0.0),
        "selective_accuracy": rounded(accuracy_score(y_true, y_pred)),
        "f1_macro": rounded(f1_score(y_true, y_pred, average="macro")),
        "selective_f1_macro": rounded(f1_score(y_true, y_pred, average="macro")),
        "home_win_precision": rounded(report["HOME_WIN"]["precision"]),
        "home_win_recall": rounded(report["HOME_WIN"]["recall"]),
        "draw_precision": rounded(report["DRAW"]["precision"]),
        "draw_recall": rounded(report["DRAW"]["recall"]),
        "away_win_precision": rounded(report["AWAY_WIN"]["precision"]),
        "away_win_recall": rounded(report["AWAY_WIN"]["recall"]),
        "brier_score": 0.0,
        "log_loss": 0.0,
        "expected_calibration_error": 0.0,
        "selected_accuracy_delta_vs_raw_v6_full": rounded(accuracy_score(y_true, y_pred) - raw_v6_full_accuracy),
        "net_correct_delta_vs_raw_v6_same_selected": int(v9_correct_rows - raw_v6_correct_same_rows),
        "max_probability_threshold": policy.max_probability_threshold,
        "margin_threshold": policy.margin_threshold,
        "draw_probability_threshold": policy.draw_probability_threshold,
        "draw_margin_threshold": policy.draw_margin_threshold,
        "predicted_home_win_rows": int(prediction_distribution.get("HOME_WIN", 0)),
        "predicted_draw_rows": int(prediction_distribution.get("DRAW", 0)),
        "predicted_away_win_rows": int(prediction_distribution.get("AWAY_WIN", 0)),
    }


# Evalue toutes les politiques V9 pour une variante de modèle sur un split donné.
def evaluate_model_variant_policies(
    model_variant: str,
    evaluation_scope: str,
    prediction_dataframe: pd.DataFrame,
    raw_v6_full_accuracy: float,
) -> tuple[list[dict], dict[str, pd.DataFrame]]:
    metrics = [compute_model_probability_metrics(model_variant, evaluation_scope, prediction_dataframe)]
    policy_outputs = {}

    for policy in build_selective_policies(model_variant):
        policy_dataframe = apply_selective_policy(prediction_dataframe, policy)
        metrics.append(
            compute_selective_policy_metrics(
                policy=policy,
                evaluation_scope=evaluation_scope,
                policy_dataframe=policy_dataframe,
                raw_v6_full_accuracy=raw_v6_full_accuracy,
            )
        )
        policy_outputs[policy.name] = policy_dataframe

    return metrics, policy_outputs


# Sélectionne la meilleure politique à partir de la validation uniquement.
def select_best_validation_policy(results_dataframe: pd.DataFrame) -> pd.Series:
    validation_results = results_dataframe[
        (results_dataframe["evaluation_scope"] == "validation")
        & (results_dataframe["policy_type"] == "selective_abstention")
        & (results_dataframe["coverage"] >= MIN_ACCEPTED_COVERAGE)
    ].copy()

    if validation_results.empty:
        raise RuntimeError("Aucune politique V9 ne respecte la couverture minimale en validation.")

    return validation_results.sort_values(
        by=["selective_accuracy", "net_correct_delta_vs_raw_v6_same_selected", "coverage", "selective_f1_macro"],
        ascending=[False, False, False, False],
    ).iloc[0]


# Retrouve une politique à partir de sa ligne de métriques.
def policy_from_result_row(result_row: pd.Series) -> SelectivePolicy:
    return SelectivePolicy(
        model_variant=str(result_row["model_variant"]),
        max_probability_threshold=float(result_row["max_probability_threshold"]),
        margin_threshold=float(result_row["margin_threshold"]),
        draw_probability_threshold=float(result_row["draw_probability_threshold"]),
        draw_margin_threshold=float(result_row["draw_margin_threshold"]),
    )


# Calcule les métriques par saison pour savoir si la sélection V9 est stable.
def compute_selected_season_stability(best_predictions_dataframe: pd.DataFrame) -> pd.DataFrame:
    selected_dataframe = best_predictions_dataframe[best_predictions_dataframe["v9_recommendation_status"] == "RECOMMEND"].copy()
    if selected_dataframe.empty:
        return pd.DataFrame()

    rows = []
    for season, season_dataframe in selected_dataframe.groupby("season"):
        rows.append(
            {
                "season": season,
                "selected_rows": int(len(season_dataframe)),
                "selective_accuracy": rounded(float(season_dataframe["v9_is_correct"].mean())),
                "predicted_home_win_rows": int((season_dataframe["v9_prediction"] == "HOME_WIN").sum()),
                "predicted_draw_rows": int((season_dataframe["v9_prediction"] == "DRAW").sum()),
                "predicted_away_win_rows": int((season_dataframe["v9_prediction"] == "AWAY_WIN").sum()),
            }
        )

    return pd.DataFrame(rows)


# Détermine le statut de décision de la V9 selon le test final et la stabilité par saison.
def determine_v9_status(test_row: pd.Series, season_stability_dataframe: pd.DataFrame) -> str:
    has_minimum_stability = False
    if not season_stability_dataframe.empty:
        has_minimum_stability = bool(
            (season_stability_dataframe["selected_rows"] >= MIN_SELECTED_ROWS_PER_SEASON_FOR_STABILITY).all()
            and (season_stability_dataframe["selective_accuracy"] >= MIN_SEASON_ACCURACY_FOR_ACCEPTANCE).all()
        )

    if (
        test_row["selective_accuracy"] >= TARGET_SELECTIVE_ACCURACY
        and test_row["coverage"] >= MIN_ACCEPTED_COVERAGE
        and test_row["selected_accuracy_delta_vs_raw_v6_full"] > 0
        and has_minimum_stability
    ):
        return "V9_ACCEPTED_SELECTIVE_CANDIDATE"

    if test_row["selective_accuracy"] >= TARGET_SELECTIVE_ACCURACY and test_row["coverage"] >= MIN_ACCEPTED_COVERAGE:
        return "V9_SELECTIVE_CANDIDATE_REQUIRES_STABILITY"

    if test_row["selective_accuracy"] >= REVIEW_SELECTIVE_ACCURACY and test_row["coverage"] >= MIN_ACCEPTED_COVERAGE:
        return "V9_SELECTIVE_REVIEW"

    return "V9_REJECTED_NO_STABLE_GAIN"


# Construit les bins de confiance pour la meilleure politique V9 sur le test.
def build_confidence_bins(best_predictions_dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for status in ["ALL", "RECOMMEND", "ABSTAIN"]:
        if status == "ALL":
            scope_dataframe = best_predictions_dataframe.copy()
        else:
            scope_dataframe = best_predictions_dataframe[best_predictions_dataframe["v9_recommendation_status"] == status].copy()

        for bin_start, bin_end in zip(CONFIDENCE_BINS[:-1], CONFIDENCE_BINS[1:]):
            if bin_end == CONFIDENCE_BINS[-1]:
                bin_mask = (scope_dataframe["v9_confidence_probability"] >= bin_start) & (scope_dataframe["v9_confidence_probability"] <= bin_end)
            else:
                bin_mask = (scope_dataframe["v9_confidence_probability"] >= bin_start) & (scope_dataframe["v9_confidence_probability"] < bin_end)

            bin_dataframe = scope_dataframe[bin_mask]
            if bin_dataframe.empty:
                continue

            if status == "ABSTAIN":
                accuracy = 0.0
            else:
                accuracy = float(bin_dataframe["v9_is_correct"].mean())

            rows.append(
                {
                    "scope": status,
                    "bin_start": bin_start,
                    "bin_end": bin_end,
                    "rows": int(len(bin_dataframe)),
                    "avg_confidence": rounded(bin_dataframe["v9_confidence_probability"].mean()),
                    "accuracy": rounded(accuracy),
                    "predicted_home_win_rows": int((bin_dataframe["v9_prediction"] == "HOME_WIN").sum()),
                    "predicted_draw_rows": int((bin_dataframe["v9_prediction"] == "DRAW").sum()),
                    "predicted_away_win_rows": int((bin_dataframe["v9_prediction"] == "AWAY_WIN").sum()),
                }
            )

    return pd.DataFrame(rows)


# Construit une synthèse des erreurs et des abstentions pour la meilleure politique V9.
def build_error_patterns(best_predictions_dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    selected_dataframe = best_predictions_dataframe[best_predictions_dataframe["v9_recommendation_status"] == "RECOMMEND"].copy()
    error_dataframe = selected_dataframe[~selected_dataframe["v9_is_correct"]].copy()
    abstained_dataframe = best_predictions_dataframe[best_predictions_dataframe["v9_recommendation_status"] == "ABSTAIN"].copy()

    if not error_dataframe.empty:
        group_columns = [column for column in ["league_code", "season", "v9_prediction", TARGET_COLUMN] if column in error_dataframe.columns]
        grouped_errors = error_dataframe.groupby(group_columns).size().reset_index(name="rows")
        grouped_errors["pattern_type"] = "selected_error"
        rows.append(grouped_errors)

    if not abstained_dataframe.empty:
        group_columns = [column for column in ["league_code", "season", "v9_abstention_reason", TARGET_COLUMN] if column in abstained_dataframe.columns]
        grouped_abstentions = abstained_dataframe.groupby(group_columns).size().reset_index(name="rows")
        grouped_abstentions["pattern_type"] = "abstention"
        rows.append(grouped_abstentions)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True, sort=False).sort_values(by="rows", ascending=False)


# Construit le texte de synthèse de l'expérience V9.
def build_summary(
    metadata: dict,
    feature_dataframe: pd.DataFrame,
    train_core_dataframe: pd.DataFrame,
    validation_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
    results_dataframe: pd.DataFrame,
    best_validation_row: pd.Series,
    best_test_row: pd.Series,
    v9_status: str,
    season_stability_dataframe: pd.DataFrame,
) -> str:
    validation_baseline = results_dataframe[
        (results_dataframe["evaluation_scope"] == "validation")
        & (results_dataframe["strategy"] == "v9_raw_all_predictions_no_abstention")
    ].iloc[0]
    test_baseline = results_dataframe[
        (results_dataframe["evaluation_scope"] == "test")
        & (results_dataframe["strategy"] == "v9_raw_all_predictions_no_abstention")
    ].iloc[0]

    top_validation = results_dataframe[
        (results_dataframe["evaluation_scope"] == "validation")
        & (results_dataframe["policy_type"] == "selective_abstention")
        & (results_dataframe["coverage"] >= MIN_ACCEPTED_COVERAGE)
    ].sort_values(by=["selective_accuracy", "coverage"], ascending=[False, False]).head(10)

    lines = [
        "RubyBets - ML 1X2 V9 selective calibration + abstention",
        "145 - Synthese experience V9 selective",
        "",
        "Objectif :",
        "Tester une couche de decision selective au-dessus de la V6 Market prior : calibration des probabilites, seuils de confiance, marge entre classes et abstention intelligente.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Aucune integration Understat/xG dans le produit.",
        "- Experience ML interne uniquement, sans sauvegarde de modele.",
        "",
        "Split chronologique :",
        f"- Train core : toutes les saisons hors validation et test ({len(train_core_dataframe)} lignes).",
        f"- Validation seuils : {', '.join(VALIDATION_SEASONS)} ({len(validation_dataframe)} lignes).",
        f"- Test final : {', '.join(TEST_SEASONS)} ({len(test_dataframe)} lignes).",
        "",
        "Volumes :",
        f"- Clean matches loaded : {metadata['clean_matches_loaded']}",
        f"- V6 feature rows : {metadata['v6_rows']}",
        f"- Market-ready rows : {metadata['market_ready_rows']}",
        f"- Market-ready rate : {rounded(metadata['market_ready_rate'])}",
        f"- Rows used by V9 : {len(feature_dataframe)}",
        "",
        "Reference V6 brute sans abstention :",
        f"- Validation accuracy : {validation_baseline['accuracy']}",
        f"- Validation F1 macro : {validation_baseline['f1_macro']}",
        f"- Test accuracy : {test_baseline['accuracy']}",
        f"- Test F1 macro : {test_baseline['f1_macro']}",
        f"- Test ECE : {test_baseline['expected_calibration_error']}",
        "",
        "Reference globale observee avant V9 :",
        f"- V6 global accuracy : {V6_GLOBAL_REFERENCE_ACCURACY}",
        f"- V6 global F1 macro : {V6_GLOBAL_REFERENCE_F1_MACRO}",
        f"- V6 global DRAW precision : {V6_GLOBAL_REFERENCE_DRAW_PRECISION}",
        f"- V6 global DRAW recall : {V6_GLOBAL_REFERENCE_DRAW_RECALL}",
        f"- V8 xG accuracy : {V8_REFERENCE_ACCURACY}",
        f"- V8.1 gating accuracy : {V81_REFERENCE_ACCURACY}",
        "",
        "Meilleure politique choisie sur validation :",
        f"- Strategy : {best_validation_row['strategy']}",
        f"- Model variant : {best_validation_row['model_variant']}",
        f"- Validation selected accuracy : {best_validation_row['selective_accuracy']}",
        f"- Validation coverage : {best_validation_row['coverage']}",
        f"- Validation selected rows : {best_validation_row['selected_rows']}",
        "",
        "Evaluation finale de cette politique sur test :",
        f"- Status : {v9_status}",
        f"- Strategy : {best_test_row['strategy']}",
        f"- Selected accuracy : {best_test_row['selective_accuracy']}",
        f"- Coverage : {best_test_row['coverage']}",
        f"- Abstention rate : {best_test_row['abstention_rate']}",
        f"- Selected rows : {best_test_row['selected_rows']}",
        f"- Abstained rows : {best_test_row['abstained_rows']}",
        f"- Selected accuracy delta vs raw V6 full : {best_test_row['selected_accuracy_delta_vs_raw_v6_full']}",
        f"- Net correct delta vs raw V6 same selected : {best_test_row['net_correct_delta_vs_raw_v6_same_selected']}",
        f"- DRAW precision selected : {best_test_row['draw_precision']}",
        f"- DRAW recall selected : {best_test_row['draw_recall']}",
        "",
        "Stabilite par saison sur les matchs selectionnes :",
        season_stability_dataframe.to_string(index=False) if not season_stability_dataframe.empty else "Aucune ligne selectionnee.",
        "",
        "Top strategies validation avec couverture minimale :",
        top_validation[[
            "strategy",
            "model_variant",
            "selected_rows",
            "coverage",
            "selective_accuracy",
            "selective_f1_macro",
            "draw_precision",
            "draw_recall",
            "selected_accuracy_delta_vs_raw_v6_full",
        ]].to_string(index=False),
        "",
        "Fichiers generes :",
        str(SUMMARY_PATH),
        str(RESULTS_CSV_PATH),
        str(BEST_PREDICTIONS_CSV_PATH),
        str(CONFIDENCE_BINS_CSV_PATH),
        str(ERROR_PATTERNS_CSV_PATH),
        str(DECISION_PATH),
    ]

    return "\n".join(lines)


# Construit le fichier de décision final de l'expérience V9.
def build_decision(best_validation_row: pd.Series, best_test_row: pd.Series, v9_status: str) -> str:
    lines = [
        "RubyBets - ML 1X2 V9 selective calibration + abstention",
        "150 - Decision experimentale V9 selective",
        "",
        f"Status : {v9_status}",
        "",
        "Decision :",
    ]

    if v9_status == "V9_ACCEPTED_SELECTIVE_CANDIDATE":
        lines.append("La V9 selective est un candidat experimental solide : elle ameliore la fiabilite sur les matchs selectionnes avec une couverture minimale et une stabilite saisonniere acceptable.")
    elif v9_status == "V9_SELECTIVE_CANDIDATE_REQUIRES_STABILITY":
        lines.append("La V9 selective produit un signal interessant sur le test, mais elle doit passer une analyse de stabilite detaillee avant toute adoption comme candidat officiel.")
    elif v9_status == "V9_SELECTIVE_REVIEW":
        lines.append("La V9 selective montre un gain potentiel, mais le compromis fiabilite/couverture reste insuffisant pour une decision officielle.")
    else:
        lines.append("La V9 selective ne produit pas encore un gain assez stable pour remplacer ou completer officiellement la reference V6.")

    lines.extend(
        [
            "",
            "Politique choisie sur validation :",
            f"- Strategy : {best_validation_row['strategy']}",
            f"- Model variant : {best_validation_row['model_variant']}",
            f"- Validation selective accuracy : {best_validation_row['selective_accuracy']}",
            f"- Validation coverage : {best_validation_row['coverage']}",
            "",
            "Resultat final sur test :",
            f"- Strategy : {best_test_row['strategy']}",
            f"- Selected accuracy : {best_test_row['selective_accuracy']}",
            f"- Coverage : {best_test_row['coverage']}",
            f"- Abstention rate : {best_test_row['abstention_rate']}",
            f"- Selected rows : {best_test_row['selected_rows']}",
            f"- Net correct delta vs raw V6 same selected : {best_test_row['net_correct_delta_vs_raw_v6_same_selected']}",
            f"- Selected accuracy delta vs raw V6 full : {best_test_row['selected_accuracy_delta_vs_raw_v6_full']}",
            "",
            "Garde-fou :",
            "Ne pas modifier ml.features, ne pas sauvegarder de modele et ne pas brancher V9 a l'API ou au frontend avant validation forte.",
            "",
            "Prochaine action recommandee :",
            "Si le statut est candidat ou review, analyser les fichiers 146, 147, 148 et 149. Si le gain semble stable, creer ensuite analyze_1x2_v9_selective_stability.py pour auditer par ligue, saison, classe predite et type d'erreur.",
            "",
            "Statut de suivi :",
            "- Tache realisee si les fichiers 145, 146, 147, 148, 149 et 150 sont generes.",
            "- Statut source a mettre a jour : a produire -> realise pour l'experience V9 selective calibration + abstention.",
        ]
    )

    return "\n".join(lines)


# Sauvegarde tous les rapports V9 dans reports/evidence/ml_training.
def save_reports(
    results_dataframe: pd.DataFrame,
    best_predictions_dataframe: pd.DataFrame,
    confidence_bins_dataframe: pd.DataFrame,
    error_patterns_dataframe: pd.DataFrame,
    summary: str,
    decision: str,
) -> None:
    ensure_report_dir()
    results_dataframe.to_csv(RESULTS_CSV_PATH, index=False, encoding="utf-8")
    best_predictions_dataframe.to_csv(BEST_PREDICTIONS_CSV_PATH, index=False, encoding="utf-8")
    confidence_bins_dataframe.to_csv(CONFIDENCE_BINS_CSV_PATH, index=False, encoding="utf-8")
    error_patterns_dataframe.to_csv(ERROR_PATTERNS_CSV_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    DECISION_PATH.write_text(decision, encoding="utf-8")


# Lance toute l'expérience V9 selective calibration + abstention.
def main() -> None:
    try:
        database_url = get_database_url()

        print("Chargement des features V6 market-ready pour V9...", flush=True)
        feature_dataframe, metadata = build_v9_feature_dataframe(database_url)
        train_core_dataframe, validation_dataframe, test_dataframe = prepare_temporal_splits(feature_dataframe)

        print(f"Rows market-ready: {len(feature_dataframe)}", flush=True)
        print(f"Train core rows: {len(train_core_dataframe)}", flush=True)
        print(f"Validation rows: {len(validation_dataframe)}", flush=True)
        print(f"Test rows: {len(test_dataframe)}", flush=True)

        validation_outputs_by_variant = {}
        test_outputs_by_variant = {}
        all_metrics = []

        print("Entrainement reference raw V6 pour comparaison...", flush=True)
        _, raw_validation_probabilities = train_and_predict_probabilities("raw", train_core_dataframe, validation_dataframe)
        _, raw_test_probabilities = train_and_predict_probabilities("raw", pd.concat([train_core_dataframe, validation_dataframe]), test_dataframe)
        raw_validation_predictions = build_prediction_dataframe(validation_dataframe, raw_validation_probabilities, "raw")
        raw_test_predictions = build_prediction_dataframe(test_dataframe, raw_test_probabilities, "raw")
        raw_validation_accuracy = float(raw_validation_predictions["raw_is_correct"].mean())
        raw_test_accuracy = float(raw_test_predictions["raw_is_correct"].mean())

        for model_variant in CALIBRATION_METHODS:
            print(f"Evaluation V9 calibration : {model_variant}", flush=True)
            _, validation_probabilities = train_and_predict_probabilities(model_variant, train_core_dataframe, validation_dataframe)
            _, test_probabilities = train_and_predict_probabilities(
                model_variant,
                pd.concat([train_core_dataframe, validation_dataframe]),
                test_dataframe,
            )

            validation_prediction_dataframe = build_prediction_dataframe(
                validation_dataframe,
                validation_probabilities,
                model_variant,
                raw_v6_probabilities=raw_validation_probabilities,
            )
            test_prediction_dataframe = build_prediction_dataframe(
                test_dataframe,
                test_probabilities,
                model_variant,
                raw_v6_probabilities=raw_test_probabilities,
            )

            validation_metrics, validation_policy_outputs = evaluate_model_variant_policies(
                model_variant=model_variant,
                evaluation_scope="validation",
                prediction_dataframe=validation_prediction_dataframe,
                raw_v6_full_accuracy=raw_validation_accuracy,
            )
            test_metrics, test_policy_outputs = evaluate_model_variant_policies(
                model_variant=model_variant,
                evaluation_scope="test",
                prediction_dataframe=test_prediction_dataframe,
                raw_v6_full_accuracy=raw_test_accuracy,
            )

            all_metrics.extend(validation_metrics)
            all_metrics.extend(test_metrics)
            validation_outputs_by_variant[model_variant] = validation_policy_outputs
            test_outputs_by_variant[model_variant] = test_policy_outputs

        results_dataframe = pd.DataFrame(all_metrics)
        best_validation_row = select_best_validation_policy(results_dataframe)
        selected_policy = policy_from_result_row(best_validation_row)
        best_predictions_dataframe = test_outputs_by_variant[selected_policy.model_variant][selected_policy.name]
        best_test_rows = results_dataframe[
            (results_dataframe["evaluation_scope"] == "test")
            & (results_dataframe["strategy"] == selected_policy.name)
        ]

        if best_test_rows.empty:
            raise RuntimeError(f"Politique selectionnee introuvable sur test : {selected_policy.name}")

        best_test_row = best_test_rows.iloc[0]
        season_stability_dataframe = compute_selected_season_stability(best_predictions_dataframe)
        v9_status = determine_v9_status(best_test_row, season_stability_dataframe)
        confidence_bins_dataframe = build_confidence_bins(best_predictions_dataframe)
        error_patterns_dataframe = build_error_patterns(best_predictions_dataframe)

        summary = build_summary(
            metadata=metadata,
            feature_dataframe=feature_dataframe,
            train_core_dataframe=train_core_dataframe,
            validation_dataframe=validation_dataframe,
            test_dataframe=test_dataframe,
            results_dataframe=results_dataframe,
            best_validation_row=best_validation_row,
            best_test_row=best_test_row,
            v9_status=v9_status,
            season_stability_dataframe=season_stability_dataframe,
        )
        decision = build_decision(best_validation_row, best_test_row, v9_status)

        save_reports(
            results_dataframe=results_dataframe,
            best_predictions_dataframe=best_predictions_dataframe,
            confidence_bins_dataframe=confidence_bins_dataframe,
            error_patterns_dataframe=error_patterns_dataframe,
            summary=summary,
            decision=decision,
        )

        print("OK - Experience V9 selective calibration + abstention terminee.", flush=True)
        print(f"Status: {v9_status}", flush=True)
        print(f"Selected validation strategy: {best_validation_row['strategy']}", flush=True)
        print(f"Test selected accuracy: {best_test_row['selective_accuracy']}", flush=True)
        print(f"Test coverage: {best_test_row['coverage']}", flush=True)
        print(f"Test abstention rate: {best_test_row['abstention_rate']}", flush=True)
        print(f"Selected rows: {best_test_row['selected_rows']}", flush=True)
        print(f"Summary saved: {SUMMARY_PATH}", flush=True)
        print(f"Results CSV saved: {RESULTS_CSV_PATH}", flush=True)
        print(f"Best predictions CSV saved: {BEST_PREDICTIONS_CSV_PATH}", flush=True)
        print(f"Confidence bins CSV saved: {CONFIDENCE_BINS_CSV_PATH}", flush=True)
        print(f"Error patterns CSV saved: {ERROR_PATTERNS_CSV_PATH}", flush=True)
        print(f"Decision saved: {DECISION_PATH}", flush=True)

    except Exception as error:
        print("Erreur pendant l'experience V9 selective calibration + abstention.", flush=True)
        print(str(error), flush=True)
        raise


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
#
# backend/.env -> DATABASE_URL
#        ↓
# PostgreSQL ml.clean_matches + ml.raw_matches.raw_data
#        ↓
# fonctions V2/V5/V6 existantes -> features V6 market-ready en mémoire
#        ↓
# V9 calibration + abstention -> rapports 145 à 150
#        ↓
# reports/evidence/ml_training/
