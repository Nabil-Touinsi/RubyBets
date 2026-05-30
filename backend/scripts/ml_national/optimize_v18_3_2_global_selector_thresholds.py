# Role du fichier :
# Ce script optimise les seuils du selecteur national global RubyBets V18.3.2.
# Il cherche a augmenter la couverture sans perdre trop de fiabilite et sans redevenir trop dependant de DOUBLE_CHANCE.
# Les resultats restent experimentaux et ne doivent pas etre presentes comme une garantie sportive.

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import floor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


PREDICTIONS_FILENAME = "348_v18_3_global_multimarket_test_predictions.csv"
SUMMARY_FILENAME = "360_v18_3_2_global_selector_threshold_search_summary.txt"
SEARCH_RESULTS_FILENAME = "361_v18_3_2_global_selector_threshold_search_results.csv"
BEST_RESULTS_FILENAME = "362_v18_3_2_global_selector_best_results.csv"
BEST_BREAKDOWN_FILENAME = "363_v18_3_2_global_selector_best_market_breakdown.csv"

TARGET_RELIABILITY_FLOOR = 0.895
TARGET_COVERAGE_FLOOR = 0.50
TARGET_MAX_DOUBLE_CHANCE_SHARE = 0.72

REFERENCE_V18_3 = {
    "reliability": 0.9071,
    "coverage": 0.5747,
    "double_chance_share_selected": 0.7676,
    "selected_rows": 1119,
}

REFERENCE_V18_3_1 = {
    "reliability": 0.9013,
    "coverage": 0.4735,
    "double_chance_share_selected": 0.6703,
    "selected_rows": 922,
}


@dataclass(frozen=True)
class ThresholdConfig:
    name: str
    strict_1x2_min_confidence: float
    over_1_5_yes_min_confidence: float
    over_2_5_min_confidence: float
    btts_no_min_confidence: float
    double_chance_max_excluded_probability: Optional[float]
    double_chance_share_cap: Optional[float]
    allow_btts: bool
    priority_name: str
    priority: Tuple[str, ...]
    config_family: str = "threshold_search"


# Retrouve la racine du projet RubyBets a partir de l'emplacement du script.
def find_project_root() -> Path:
    current_path = Path(__file__).resolve()

    for candidate in [current_path.parent, *current_path.parents]:
        if (candidate / "backend").exists() and (candidate / "reports").exists():
            return candidate

    return Path.cwd().resolve()


# Construit les chemins d'entree et de sortie de l'experience V18.3.2.
def build_paths(project_root: Path) -> Dict[str, Path]:
    evidence_dir = project_root / "reports" / "evidence" / "ml_training"
    return {
        "evidence_dir": evidence_dir,
        "predictions_csv": evidence_dir / PREDICTIONS_FILENAME,
        "summary_txt": evidence_dir / SUMMARY_FILENAME,
        "search_results_csv": evidence_dir / SEARCH_RESULTS_FILENAME,
        "best_results_csv": evidence_dir / BEST_RESULTS_FILENAME,
        "best_breakdown_csv": evidence_dir / BEST_BREAKDOWN_FILENAME,
    }


# Verifie que le fichier 348 existe avant de lancer l'optimisation.
def validate_input_file(predictions_csv: Path) -> None:
    if not predictions_csv.exists():
        raise FileNotFoundError(
            "Fichier de predictions introuvable : "
            f"{predictions_csv}\n"
            "Relancer d'abord train_v18_3_global_multimarket_models.py."
        )


# Charge les predictions test produites par l'etape 348.
def load_predictions(predictions_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(predictions_csv)

    required_columns = [
        "clean_match_id",
        "match_date_utc",
        "season",
        "competition_code",
        "competition_name",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "target_1x2",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
        "1x2_prediction",
        "1x2_prob_TEAM_A_WIN",
        "1x2_prob_DRAW",
        "1x2_prob_TEAM_B_WIN",
        "1x2_max_probability",
        "over_1_5_prediction",
        "over_1_5_prob_YES",
        "over_2_5_prediction",
        "over_2_5_max_probability",
        "btts_prediction",
        "btts_prob_NO",
        "btts_max_probability",
    ]

    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Colonnes manquantes dans le fichier 348 : " + ", ".join(missing_columns)
        )

    return df


# Formate un nombre en code court utilisable dans les noms de variantes.
def format_threshold_code(value: Optional[float]) -> str:
    if value is None:
        return "none"
    return str(int(round(float(value) * 1000))).zfill(3)


# Genere toutes les configurations de seuils a tester pour V18.3.2.
def generate_threshold_configs() -> List[ThresholdConfig]:
    strict_1x2_thresholds = [0.76, 0.78, 0.80]
    over_1_5_thresholds = [0.76, 0.78, 0.80]
    over_2_5_thresholds = [0.64, 0.66, 0.68, 0.70]
    btts_no_thresholds = [0.70, 0.72, 0.75]
    double_chance_thresholds = [0.12, 0.13, 0.14, 0.15]
    double_chance_share_caps: List[Optional[float]] = [None, 0.70, 0.72]
    allow_btts_options = [False, True]

    priority_modes = {
        "reference_order": (
            "STRICT_1X2",
            "OVER_1_5",
            "OVER_2_5",
            "BTTS",
            "DOUBLE_CHANCE",
        ),
        "balanced_order": (
            "STRICT_1X2",
            "OVER_2_5",
            "OVER_1_5",
            "BTTS",
            "DOUBLE_CHANCE",
        ),
    }

    configs: List[ThresholdConfig] = []

    for (
        strict_threshold,
        over_1_5_threshold,
        over_2_5_threshold,
        btts_no_threshold,
        dc_threshold,
        dc_share_cap,
        allow_btts,
        priority_item,
    ) in product(
        strict_1x2_thresholds,
        over_1_5_thresholds,
        over_2_5_thresholds,
        btts_no_thresholds,
        double_chance_thresholds,
        double_chance_share_caps,
        allow_btts_options,
        priority_modes.items(),
    ):
        priority_name, priority = priority_item
        name = (
            "v18_3_2_"
            f"s{format_threshold_code(strict_threshold)}_"
            f"o15{format_threshold_code(over_1_5_threshold)}_"
            f"o25{format_threshold_code(over_2_5_threshold)}_"
            f"b{format_threshold_code(btts_no_threshold)}_"
            f"dc{format_threshold_code(dc_threshold)}_"
            f"cap{format_threshold_code(dc_share_cap)}_"
            f"{priority_name}_"
            f"btts{int(allow_btts)}"
        )

        configs.append(
            ThresholdConfig(
                name=name,
                strict_1x2_min_confidence=strict_threshold,
                over_1_5_yes_min_confidence=over_1_5_threshold,
                over_2_5_min_confidence=over_2_5_threshold,
                btts_no_min_confidence=btts_no_threshold,
                double_chance_max_excluded_probability=dc_threshold,
                double_chance_share_cap=dc_share_cap,
                allow_btts=allow_btts,
                priority_name=priority_name,
                priority=priority,
            )
        )

    return configs


# Prepare les tableaux numpy qui accelerent l'evaluation des nombreuses variantes.
def prepare_prediction_arrays(df: pd.DataFrame) -> Dict[str, np.ndarray]:
    probabilities = np.vstack(
        [
            df["1x2_prob_TEAM_A_WIN"].to_numpy(dtype=float),
            df["1x2_prob_DRAW"].to_numpy(dtype=float),
            df["1x2_prob_TEAM_B_WIN"].to_numpy(dtype=float),
        ]
    ).T
    labels = np.array(["TEAM_A_WIN", "DRAW", "TEAM_B_WIN"], dtype=object)
    excluded_index = np.argmin(probabilities, axis=1)
    excluded_outcome = labels[excluded_index]
    excluded_probability = probabilities[np.arange(len(df)), excluded_index]

    double_chance_prediction = np.where(
        excluded_outcome == "TEAM_A_WIN",
        "DRAW_OR_TEAM_B",
        np.where(
            excluded_outcome == "DRAW",
            "TEAM_A_OR_TEAM_B",
            "TEAM_A_OR_DRAW",
        ),
    )

    return {
        "target_1x2": df["target_1x2"].to_numpy(dtype=object),
        "target_over_1_5": df["target_over_1_5"].to_numpy(dtype=object),
        "target_over_2_5": df["target_over_2_5"].to_numpy(dtype=object),
        "target_btts": df["target_btts"].to_numpy(dtype=object),
        "1x2_prediction": df["1x2_prediction"].to_numpy(dtype=object),
        "1x2_max_probability": df["1x2_max_probability"].to_numpy(dtype=float),
        "over_1_5_prediction": df["over_1_5_prediction"].to_numpy(dtype=object),
        "over_1_5_prob_YES": df["over_1_5_prob_YES"].to_numpy(dtype=float),
        "over_2_5_prediction": df["over_2_5_prediction"].to_numpy(dtype=object),
        "over_2_5_max_probability": df["over_2_5_max_probability"].to_numpy(dtype=float),
        "btts_prediction": df["btts_prediction"].to_numpy(dtype=object),
        "btts_prob_NO": df["btts_prob_NO"].to_numpy(dtype=float),
        "btts_max_probability": df["btts_max_probability"].to_numpy(dtype=float),
        "double_chance_prediction": double_chance_prediction.astype(object),
        "double_chance_excluded_outcome": excluded_outcome.astype(object),
        "double_chance_excluded_probability": excluded_probability.astype(float),
        "double_chance_confidence": (1.0 - excluded_probability).astype(float),
    }


# Convertit une confiance numerique en niveau de risque simple pour les preuves CSV.
def compute_risk_level(confidence: Optional[float]) -> str:
    if confidence is None or pd.isna(confidence):
        return "none"
    if confidence >= 0.85:
        return "low"
    if confidence >= 0.75:
        return "medium"
    return "high"


# Applique une limite de part DOUBLE_CHANCE en supprimant les doubles chances les moins confiantes.
def apply_double_chance_share_cap(
    selected_market: np.ndarray,
    selected_confidence: np.ndarray,
    dc_share_cap: Optional[float],
) -> None:
    if dc_share_cap is None:
        return

    selected_mask = selected_market != "ABSTAIN"
    double_chance_mask = selected_market == "DOUBLE_CHANCE"
    double_chance_rows = int(double_chance_mask.sum())
    direct_rows = int(selected_mask.sum() - double_chance_rows)

    if double_chance_rows == 0:
        return

    if direct_rows == 0:
        max_double_chance_rows = 0
    else:
        max_double_chance_rows = floor((dc_share_cap * direct_rows) / (1.0 - dc_share_cap))

    if double_chance_rows <= max_double_chance_rows:
        return

    remove_count = double_chance_rows - max_double_chance_rows
    double_chance_indices = np.where(double_chance_mask)[0]
    sorted_indices = double_chance_indices[
        np.argsort(selected_confidence[double_chance_indices])
    ]
    indices_to_remove = sorted_indices[:remove_count]
    selected_market[indices_to_remove] = "ABSTAIN"
    selected_confidence[indices_to_remove] = np.nan


# Evalue une configuration de seuils et retourne les selections sous forme de tableaux.
def evaluate_config_arrays(
    arrays: Dict[str, np.ndarray],
    config: ThresholdConfig,
) -> Dict[str, np.ndarray]:
    row_count = len(arrays["target_1x2"])

    selected_market = np.full(row_count, "ABSTAIN", dtype=object)
    selected_confidence = np.full(row_count, np.nan, dtype=float)
    is_correct = np.full(row_count, False, dtype=bool)

    strict_valid = (
        (arrays["1x2_prediction"] != "DRAW")
        & (arrays["1x2_max_probability"] >= config.strict_1x2_min_confidence)
    )
    strict_correct = arrays["1x2_prediction"] == arrays["target_1x2"]

    over_1_5_valid = (
        (arrays["over_1_5_prediction"] == "YES")
        & (arrays["over_1_5_prob_YES"] >= config.over_1_5_yes_min_confidence)
    )
    over_1_5_correct = arrays["target_over_1_5"] == "YES"

    over_2_5_valid = arrays["over_2_5_max_probability"] >= config.over_2_5_min_confidence
    over_2_5_correct = arrays["over_2_5_prediction"] == arrays["target_over_2_5"]

    if config.allow_btts:
        btts_valid = (
            (arrays["btts_prediction"] == "NO")
            & (arrays["btts_prob_NO"] >= config.btts_no_min_confidence)
        )
    else:
        btts_valid = np.full(row_count, False, dtype=bool)
    btts_correct = arrays["target_btts"] == "NO"

    if config.double_chance_max_excluded_probability is None:
        double_chance_valid = np.full(row_count, False, dtype=bool)
    else:
        double_chance_valid = (
            arrays["double_chance_excluded_probability"]
            <= config.double_chance_max_excluded_probability
        )
    double_chance_correct = arrays["target_1x2"] != arrays["double_chance_excluded_outcome"]

    market_definitions = {
        "STRICT_1X2": (
            strict_valid,
            arrays["1x2_max_probability"],
            strict_correct,
        ),
        "OVER_1_5": (
            over_1_5_valid,
            arrays["over_1_5_prob_YES"],
            over_1_5_correct,
        ),
        "OVER_2_5": (
            over_2_5_valid,
            arrays["over_2_5_max_probability"],
            over_2_5_correct,
        ),
        "BTTS": (
            btts_valid,
            arrays["btts_prob_NO"],
            btts_correct,
        ),
        "DOUBLE_CHANCE": (
            double_chance_valid,
            arrays["double_chance_confidence"],
            double_chance_correct,
        ),
    }

    for market in config.priority:
        valid_mask, confidence_values, correct_values = market_definitions[market]
        select_mask = (selected_market == "ABSTAIN") & valid_mask
        selected_market[select_mask] = market
        selected_confidence[select_mask] = confidence_values[select_mask]
        is_correct[select_mask] = correct_values[select_mask]

    apply_double_chance_share_cap(
        selected_market,
        selected_confidence,
        config.double_chance_share_cap,
    )

    selected_mask = selected_market != "ABSTAIN"
    is_correct = is_correct & selected_mask

    return {
        "selected_market": selected_market,
        "selected_confidence": selected_confidence,
        "is_correct": is_correct,
    }


# Calcule les indicateurs d'une configuration V18.3.2.
def compute_config_metrics(
    arrays_result: Dict[str, np.ndarray],
    config: ThresholdConfig,
) -> Dict[str, Any]:
    selected_market = arrays_result["selected_market"]
    selected_confidence = arrays_result["selected_confidence"]
    is_correct = arrays_result["is_correct"]

    total_rows = len(selected_market)
    selected_mask = selected_market != "ABSTAIN"
    selected_rows = int(selected_mask.sum())
    abstain_rows = total_rows - selected_rows
    double_chance_rows = int((selected_market == "DOUBLE_CHANCE").sum())
    strict_1x2_rows = int((selected_market == "STRICT_1X2").sum())
    over_1_5_rows = int((selected_market == "OVER_1_5").sum())
    over_2_5_rows = int((selected_market == "OVER_2_5").sum())
    btts_rows = int((selected_market == "BTTS").sum())

    if selected_rows:
        reliability = float(is_correct[selected_mask].mean())
        avg_confidence = float(np.nanmean(selected_confidence[selected_mask]))
        selected_markets_count = int(len(set(selected_market[selected_mask].tolist())))
    else:
        reliability = 0.0
        avg_confidence = 0.0
        selected_markets_count = 0

    coverage = selected_rows / total_rows if total_rows else 0.0
    abstention_rate = abstain_rows / total_rows if total_rows else 0.0
    double_chance_share_selected = double_chance_rows / selected_rows if selected_rows else 0.0
    direct_market_rows = selected_rows - double_chance_rows
    direct_market_share_selected = direct_market_rows / selected_rows if selected_rows else 0.0
    market_diversity_score = selected_markets_count / 5 if selected_markets_count else 0.0
    double_chance_balance_score = 1.0 - double_chance_share_selected

    quality_score = (
        reliability * 0.45
        + coverage * 0.40
        + double_chance_balance_score * 0.10
        + market_diversity_score * 0.05
    )

    meets_targets = bool(
        reliability >= TARGET_RELIABILITY_FLOOR
        and coverage >= TARGET_COVERAGE_FLOOR
        and double_chance_share_selected <= TARGET_MAX_DOUBLE_CHANCE_SHARE
    )

    return {
        "selector_variant": config.name,
        "config_family": config.config_family,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstain_rows": abstain_rows,
        "coverage": coverage,
        "abstention_rate": abstention_rate,
        "reliability": reliability,
        "avg_confidence": avg_confidence,
        "double_chance_rows": double_chance_rows,
        "double_chance_share_selected": double_chance_share_selected,
        "direct_market_rows": direct_market_rows,
        "direct_market_share_selected": direct_market_share_selected,
        "strict_1x2_rows": strict_1x2_rows,
        "over_1_5_rows": over_1_5_rows,
        "over_2_5_rows": over_2_5_rows,
        "btts_rows": btts_rows,
        "selected_markets_count": selected_markets_count,
        "quality_score": quality_score,
        "meets_v18_3_2_targets": meets_targets,
        "strict_1x2_min_confidence": config.strict_1x2_min_confidence,
        "over_1_5_yes_min_confidence": config.over_1_5_yes_min_confidence,
        "over_2_5_min_confidence": config.over_2_5_min_confidence,
        "btts_no_min_confidence": config.btts_no_min_confidence,
        "double_chance_max_excluded_probability": config.double_chance_max_excluded_probability,
        "double_chance_share_cap": config.double_chance_share_cap,
        "allow_btts": config.allow_btts,
        "priority_name": config.priority_name,
        "priority": " > ".join(config.priority),
    }


# Selectionne la meilleure configuration en priorisant la couverture sous contraintes.
def select_best_config(search_results_df: pd.DataFrame) -> str:
    target_df = search_results_df[search_results_df["meets_v18_3_2_targets"] == True].copy()

    if not target_df.empty:
        target_df = target_df.sort_values(
            by=["quality_score", "coverage", "reliability"],
            ascending=False,
        )
        return str(target_df.iloc[0]["selector_variant"])

    fallback_df = search_results_df.sort_values(
        by=["quality_score", "coverage", "reliability"],
        ascending=False,
    )
    return str(fallback_df.iloc[0]["selector_variant"])


# Rejoue la meilleure configuration pour produire un CSV detaille lisible.
def build_detailed_results(
    predictions_df: pd.DataFrame,
    arrays: Dict[str, np.ndarray],
    config: ThresholdConfig,
) -> pd.DataFrame:
    arrays_result = evaluate_config_arrays(arrays, config)
    selected_market = arrays_result["selected_market"]
    selected_confidence = arrays_result["selected_confidence"]
    is_correct = arrays_result["is_correct"]

    selected_prediction = np.full(len(predictions_df), "ABSTAIN", dtype=object)
    actual_value = np.full(len(predictions_df), "", dtype=object)
    selector_rule = np.full(
        len(predictions_df),
        "Aucun signal ne respecte les seuils V18.3.2.",
        dtype=object,
    )
    excluded_outcome = np.full(len(predictions_df), "", dtype=object)
    excluded_probability = np.full(len(predictions_df), np.nan, dtype=float)

    mask = selected_market == "STRICT_1X2"
    selected_prediction[mask] = arrays["1x2_prediction"][mask]
    actual_value[mask] = arrays["target_1x2"][mask]
    selector_rule[mask] = (
        "1X2 non-DRAW avec confiance >= "
        f"{config.strict_1x2_min_confidence}"
    )

    mask = selected_market == "OVER_1_5"
    selected_prediction[mask] = "YES"
    actual_value[mask] = arrays["target_over_1_5"][mask]
    selector_rule[mask] = (
        "OVER_1_5 YES avec confiance >= "
        f"{config.over_1_5_yes_min_confidence}"
    )

    mask = selected_market == "OVER_2_5"
    selected_prediction[mask] = arrays["over_2_5_prediction"][mask]
    actual_value[mask] = arrays["target_over_2_5"][mask]
    selector_rule[mask] = (
        "OVER_2_5 avec confiance >= "
        f"{config.over_2_5_min_confidence}"
    )

    mask = selected_market == "BTTS"
    selected_prediction[mask] = "NO"
    actual_value[mask] = arrays["target_btts"][mask]
    selector_rule[mask] = "BTTS NO avec confiance >= " f"{config.btts_no_min_confidence}"

    mask = selected_market == "DOUBLE_CHANCE"
    selected_prediction[mask] = arrays["double_chance_prediction"][mask]
    actual_value[mask] = arrays["target_1x2"][mask]
    excluded_outcome[mask] = arrays["double_chance_excluded_outcome"][mask]
    excluded_probability[mask] = arrays["double_chance_excluded_probability"][mask]
    selector_rule[mask] = (
        "DOUBLE_CHANCE si probabilite de l'issue exclue <= "
        f"{config.double_chance_max_excluded_probability}"
    )

    risk_levels = [compute_risk_level(value) for value in selected_confidence]

    base_columns = [
        "clean_match_id",
        "match_date_utc",
        "season",
        "competition_code",
        "competition_name",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "target_1x2",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
        "1x2_prediction",
        "1x2_max_probability",
        "over_1_5_prediction",
        "over_1_5_max_probability",
        "over_2_5_prediction",
        "over_2_5_max_probability",
        "btts_prediction",
        "btts_max_probability",
    ]
    available_columns = [column for column in base_columns if column in predictions_df.columns]

    result_df = predictions_df[available_columns].copy().reset_index(drop=True)
    result_df.insert(0, "selector_variant", config.name)
    result_df["selected_market"] = selected_market
    result_df["selected_prediction"] = selected_prediction
    result_df["selected_confidence"] = selected_confidence
    result_df["risk_level"] = risk_levels
    result_df["actual_value"] = actual_value
    result_df["is_correct"] = np.where(selected_market == "ABSTAIN", None, is_correct)
    result_df["selector_rule"] = selector_rule
    result_df["excluded_outcome"] = excluded_outcome
    result_df["excluded_probability"] = excluded_probability
    return result_df


# Produit la repartition par marche pour le meilleur selecteur V18.3.2.
def compute_market_breakdown(results_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    total_rows = len(results_df)
    selected_total = int((results_df["selected_market"] != "ABSTAIN").sum())

    market_order = {
        "STRICT_1X2": 1,
        "DOUBLE_CHANCE": 2,
        "OVER_1_5": 3,
        "OVER_2_5": 4,
        "BTTS": 5,
        "ABSTAIN": 6,
    }

    for market, market_df in results_df.groupby("selected_market", dropna=False):
        selected_market = market != "ABSTAIN"
        market_rows = len(market_df)

        if selected_market and market_rows > 0:
            correct_rows = int(market_df["is_correct"].astype(bool).sum())
            accuracy = correct_rows / market_rows
            avg_confidence = float(market_df["selected_confidence"].mean())
        else:
            correct_rows = 0
            accuracy = None
            avg_confidence = None

        rows.append(
            {
                "selected_market": market,
                "rows": market_rows,
                "share_total": market_rows / total_rows if total_rows else 0.0,
                "share_selected": market_rows / selected_total if selected_market and selected_total else 0.0,
                "correct_rows": correct_rows,
                "error_rows": market_rows - correct_rows if selected_market else 0,
                "accuracy": accuracy,
                "avg_confidence": avg_confidence,
            }
        )

    breakdown_df = pd.DataFrame(rows)
    breakdown_df["market_order"] = breakdown_df["selected_market"].map(market_order).fillna(99)
    breakdown_df = breakdown_df.sort_values("market_order").drop(columns=["market_order"])
    return breakdown_df


# Formate un ratio pour les fichiers texte de preuve.
def format_ratio(value: Any) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value):.4f}"


# Construit la synthese texte de l'optimisation V18.3.2.
def build_summary(
    paths: Dict[str, Path],
    predictions_df: pd.DataFrame,
    configs: List[ThresholdConfig],
    search_results_df: pd.DataFrame,
    best_config: ThresholdConfig,
    best_results_df: pd.DataFrame,
    best_breakdown_df: pd.DataFrame,
) -> str:
    best_row = search_results_df.loc[
        search_results_df["selector_variant"] == best_config.name
    ].iloc[0]
    target_count = int(search_results_df["meets_v18_3_2_targets"].sum())

    lines: List[str] = []
    lines.extend(
        [
            "OK - Optimisation V18.3.2 global selector thresholds terminee.",
            "",
            "Contexte :",
            "- Phase : V18.3.2 national global multi-market.",
            "- Objectif : augmenter la couverture sans perdre trop de fiabilite.",
            "- StatsBomb : non utilise dans V18.3.2 global.",
            "- DOUBLE_CHANCE : derivee des probabilites 1X2, jamais entrainee comme target separee.",
            "- ABSTAIN : conserve comme mecanisme de prudence.",
            "",
            "Fichier utilise :",
            f"- Predictions test : {paths['predictions_csv']}",
            "",
            "References :",
            f"- V18.3 : reliability={REFERENCE_V18_3['reliability']}, coverage={REFERENCE_V18_3['coverage']}, dc_share={REFERENCE_V18_3['double_chance_share_selected']}, selected={REFERENCE_V18_3['selected_rows']}",
            f"- V18.3.1 : reliability={REFERENCE_V18_3_1['reliability']}, coverage={REFERENCE_V18_3_1['coverage']}, dc_share={REFERENCE_V18_3_1['double_chance_share_selected']}, selected={REFERENCE_V18_3_1['selected_rows']}",
            "",
            "Objectifs V18.3.2 :",
            f"- Reliability minimale : {TARGET_RELIABILITY_FLOOR}",
            f"- Coverage minimale : {TARGET_COVERAGE_FLOOR}",
            f"- DOUBLE_CHANCE share maximale : {TARGET_MAX_DOUBLE_CHANCE_SHARE}",
            "",
            "Recherche effectuee :",
            f"- Configurations testees : {len(configs)}",
            f"- Configurations atteignant les objectifs : {target_count}",
            f"- Lignes test analysees : {len(predictions_df)}",
            "",
            "Meilleure configuration V18.3.2 :",
            f"- Variante retenue : {best_config.name}",
            f"- Reliability : {format_ratio(best_row['reliability'])}",
            f"- Coverage : {format_ratio(best_row['coverage'])}",
            f"- Selected rows : {int(best_row['selected_rows'])}",
            f"- Abstention rate : {format_ratio(best_row['abstention_rate'])}",
            f"- DOUBLE_CHANCE rows : {int(best_row['double_chance_rows'])}",
            f"- DOUBLE_CHANCE share selected : {format_ratio(best_row['double_chance_share_selected'])}",
            f"- Direct market share selected : {format_ratio(best_row['direct_market_share_selected'])}",
            f"- Quality score : {format_ratio(best_row['quality_score'])}",
            f"- Objectifs V18.3.2 atteints : {bool(best_row['meets_v18_3_2_targets'])}",
            "",
            "Seuils retenus :",
            f"- STRICT_1X2 min confidence : {best_config.strict_1x2_min_confidence}",
            f"- OVER_1_5 YES min confidence : {best_config.over_1_5_yes_min_confidence}",
            f"- OVER_2_5 min confidence : {best_config.over_2_5_min_confidence}",
            f"- BTTS NO min confidence : {best_config.btts_no_min_confidence}",
            f"- DOUBLE_CHANCE excluded probability max : {best_config.double_chance_max_excluded_probability}",
            f"- DOUBLE_CHANCE share cap : {best_config.double_chance_share_cap}",
            f"- BTTS autorise : {best_config.allow_btts}",
            f"- Priorite : {' > '.join(best_config.priority)}",
            "",
            "Repartition du meilleur selecteur :",
        ]
    )

    for _, row in best_breakdown_df.iterrows():
        lines.append(
            "- {market} : rows={rows}, accuracy={accuracy}, avg_conf={avg_conf}, share_selected={share_selected}".format(
                market=row["selected_market"],
                rows=int(row["rows"]),
                accuracy=format_ratio(row["accuracy"]),
                avg_conf=format_ratio(row["avg_confidence"]),
                share_selected=format_ratio(row["share_selected"]),
            )
        )

    lines.extend(["", "Top 10 configurations par quality_score :"])
    top_df = search_results_df.sort_values("quality_score", ascending=False).head(10)
    for _, row in top_df.iterrows():
        lines.append(
            "- {variant} | reliability={reliability} | coverage={coverage} | dc_share={dc_share} | selected={selected} | score={score} | targets={targets}".format(
                variant=row["selector_variant"],
                reliability=format_ratio(row["reliability"]),
                coverage=format_ratio(row["coverage"]),
                dc_share=format_ratio(row["double_chance_share_selected"]),
                selected=int(row["selected_rows"]),
                score=format_ratio(row["quality_score"]),
                targets=bool(row["meets_v18_3_2_targets"]),
            )
        )

    competitions = predictions_df["competition_code"].value_counts(dropna=False).to_dict()
    lines.extend(["", "Repartition competitions test :"])
    for competition_code, count in competitions.items():
        lines.append(f"- {competition_code} : {count}")

    lines.extend(
        [
            "",
            "Fichiers generes :",
            f"- Synthese : {paths['summary_txt']}",
            f"- Resultats recherche seuils : {paths['search_results_csv']}",
            f"- Resultats meilleur selecteur : {paths['best_results_csv']}",
            f"- Repartition meilleur selecteur : {paths['best_breakdown_csv']}",
            "",
            "Decision technique provisoire :",
            "- V18.3.2 sert a optimiser les seuils, pas encore a integrer le frontend.",
            "- La configuration retenue doit etre analysee avant commit definitif comme nouvelle variante.",
            "- Si la reliability descend trop bas, conserver V18.3.1 comme variante equilibree et V18.3 comme reference globale.",
            "- Les resultats restent experimentaux et ne promettent aucun resultat sportif.",
        ]
    )

    return "\n".join(lines)


# Orchestre l'optimisation V18.3.2 et l'ecriture des preuves 360 a 363.
def main() -> None:
    project_root = find_project_root()
    paths = build_paths(project_root)
    paths["evidence_dir"].mkdir(parents=True, exist_ok=True)

    validate_input_file(paths["predictions_csv"])
    predictions_df = load_predictions(paths["predictions_csv"])
    arrays = prepare_prediction_arrays(predictions_df)
    configs = generate_threshold_configs()

    metrics_rows: List[Dict[str, Any]] = []
    for config in configs:
        arrays_result = evaluate_config_arrays(arrays, config)
        metrics_rows.append(compute_config_metrics(arrays_result, config))

    search_results_df = pd.DataFrame(metrics_rows)
    best_config_name = select_best_config(search_results_df)
    config_by_name = {config.name: config for config in configs}
    best_config = config_by_name[best_config_name]
    best_results_df = build_detailed_results(predictions_df, arrays, best_config)
    best_breakdown_df = compute_market_breakdown(best_results_df)
    summary_text = build_summary(
        paths,
        predictions_df,
        configs,
        search_results_df,
        best_config,
        best_results_df,
        best_breakdown_df,
    )

    search_results_df = search_results_df.sort_values(
        by=["quality_score", "coverage", "reliability"], ascending=False
    )
    search_results_df.to_csv(paths["search_results_csv"], index=False, encoding="utf-8")
    best_results_df.to_csv(paths["best_results_csv"], index=False, encoding="utf-8")
    best_breakdown_df.to_csv(paths["best_breakdown_csv"], index=False, encoding="utf-8")
    paths["summary_txt"].write_text(summary_text, encoding="utf-8")

    best_row = search_results_df.loc[
        search_results_df["selector_variant"] == best_config_name
    ].iloc[0]
    target_count = int(search_results_df["meets_v18_3_2_targets"].sum())

    print("OK - Optimisation V18.3.2 global selector thresholds terminee.")
    print(f"Lignes test analysees : {len(predictions_df)}")
    print(f"Configurations testees : {len(configs)}")
    print(f"Configurations objectifs atteints : {target_count}")
    print(f"Best variant : {best_config_name}")
    print(f"Selected rows : {int(best_row['selected_rows'])}")
    print(f"Coverage : {best_row['coverage']:.4f}")
    print(f"Reliability : {best_row['reliability']:.4f}")
    print(
        "DOUBLE_CHANCE share selected : "
        f"{best_row['double_chance_share_selected']:.4f}"
    )
    print(f"Summary saved: {paths['summary_txt']}")
    print(f"Search results CSV saved: {paths['search_results_csv']}")
    print(f"Best results CSV saved: {paths['best_results_csv']}")
    print(f"Best breakdown CSV saved: {paths['best_breakdown_csv']}")


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
# 348_v18_3_global_multimarket_test_predictions.csv
#        -> optimize_v18_3_2_global_selector_thresholds.py
#        -> 360_v18_3_2_global_selector_threshold_search_summary.txt
#        -> 361_v18_3_2_global_selector_threshold_search_results.csv
#        -> 362_v18_3_2_global_selector_best_results.csv
#        -> 363_v18_3_2_global_selector_best_market_breakdown.csv
