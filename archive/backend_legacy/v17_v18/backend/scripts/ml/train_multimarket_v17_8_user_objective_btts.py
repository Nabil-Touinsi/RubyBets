# Rôle du fichier : tester V17.8, un sélecteur multi-marchés orienté objectif utilisateur qui intègre plus de BTTS_YES tout en gardant une accuracy globale minimale contrôlée, sans intégration produit.

from __future__ import annotations

import importlib.util
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd


RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"
STRICT_TYPE = "STRICT_1X2"
DOUBLE_CHANCE_TYPE = "DOUBLE_CHANCE"
GOALS_OVER_15_TYPE = "GOALS_OVER_1_5"
BTTS_TYPE = "BTTS"
BTTS_YES_VALUE = "BTTS_YES"

OUTPUT_SUMMARY = "274_multimarket_v17_8_user_objective_btts_summary.txt"
OUTPUT_RESULTS = "275_multimarket_v17_8_user_objective_btts_results.csv"
OUTPUT_BY_MARKET = "276_multimarket_v17_8_user_objective_btts_by_market.csv"
OUTPUT_BY_LEAGUE_SEASON = "277_multimarket_v17_8_user_objective_btts_by_league_season.csv"
OUTPUT_ERROR_PATTERNS = "278_multimarket_v17_8_user_objective_btts_error_patterns.csv"
OUTPUT_DECISION = "279_multimarket_v17_8_user_objective_btts_decision.txt"
OUTPUT_STRATEGY_AUDIT = "279b_multimarket_v17_8_user_objective_btts_strategy_audit.csv"

V17_REFERENCE_STRATEGY = "v17_controlled_v13_mixed_plus_over15_only"
V17_8_STRATEGY_PREFIX = "v17_8_user_objective_btts"
V17_7_REQUIRED_SCRIPT = "train_multimarket_v17_7_selector_with_btts.py"
V17_6_REQUIRED_SCRIPT = "train_goals_v17_6_btts_ultra_selective.py"

V17_REFERENCE_ACCURACY = 0.8382
V17_REFERENCE_COVERAGE = 0.7651
V17_REFERENCE_SELECTED_ROWS = 4078

MIN_USER_GLOBAL_ACCURACY = 0.70
MIN_PRO_GLOBAL_ACCURACY = 0.80
MIN_REVIEW_BTTS_ROWS = 100
MIN_REVIEW_BTTS_ACCURACY = 0.58
MIN_PRO_BTTS_ACCURACY = 0.60
MIN_MAJOR_SEGMENT_ROWS = 80
MIN_MAJOR_SEGMENT_ACCURACY = 0.70
STRONG_SEGMENT_ACCURACY = 0.75

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class StrategySpec:
    name: str
    mode: str
    min_btts_score: float
    min_history_count: int
    min_expected_team_goals: float
    min_expected_total_goals: float
    min_combined_btts_rate: float
    min_combined_over_15_rate: float
    max_failed_to_score_rate: float
    max_btts_rows: int | None


# Charge un script ML voisin comme module réutilisable, sans modifier son contenu.
def load_module(module_name: str, filename: str) -> ModuleType:
    script_path = Path(__file__).resolve().parent / filename
    if not script_path.exists():
        raise FileNotFoundError(f"Script requis introuvable : {script_path}")

    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de charger le module : {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Arrondit une valeur numérique pour stabiliser les exports et les logs.
def rounded(value: object, digits: int = 4) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return round(result, digits)
    except (TypeError, ValueError):
        return 0.0


# Calcule un ratio en évitant les divisions par zéro.
def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# Convertit proprement une valeur en booléen pour éviter les ambiguïtés CSV True/False.
def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


# Retourne les lignes où V17.0 avait déjà une recommandation.
def get_v17_base_selected_mask(dataframe: pd.DataFrame) -> pd.Series:
    if "v17_recommendation_status" in dataframe.columns:
        return dataframe["v17_recommendation_status"] == RECOMMEND_STATUS
    return dataframe["v17_recommendation_type"].isin([STRICT_TYPE, DOUBLE_CHANCE_TYPE, GOALS_OVER_15_TYPE])


# Construit le nom lisible d'une stratégie V17.8.
def build_strategy_name(spec: StrategySpec) -> str:
    limit = "all" if spec.max_btts_rows is None else str(spec.max_btts_rows)
    return (
        f"{V17_8_STRATEGY_PREFIX}_{spec.mode}"
        f"_s{int(spec.min_btts_score * 1000):03d}"
        f"_mh{spec.min_history_count}"
        f"_eg{int(spec.min_expected_team_goals * 1000):04d}"
        f"_tot{int(spec.min_expected_total_goals * 1000):04d}"
        f"_bt{int(spec.min_combined_btts_rate * 1000):03d}"
        f"_ov{int(spec.min_combined_over_15_rate * 1000):03d}"
        f"_fail{int(spec.max_failed_to_score_rate * 1000):03d}"
        f"_limit{limit}"
    )


# Génère une grille contrôlée : on garde les critères BTTS, mais on évite le brute force massif.
def generate_strategy_grid() -> list[StrategySpec]:
    strategies: list[StrategySpec] = []
    modes = ["replace_over15_or_fallback", "fallback_only"]
    score_thresholds = [0.52, 0.54, 0.56, 0.58, 0.60, 0.62]
    min_history_values = [6, 8]
    min_expected_team_values = [0.80, 0.85, 0.90]
    min_expected_total_values = [1.80, 2.00]
    min_btts_rate_values = [0.45, 0.50, 0.55]
    min_over_15_rate_values = [0.50, 0.55]
    max_failed_values = [0.45, 0.50]
    max_btts_rows_values: list[int | None] = [None, 1000, 500, 250]

    for mode in modes:
        for score_threshold in score_thresholds:
            for min_history in min_history_values:
                for min_expected_team in min_expected_team_values:
                    for min_expected_total in min_expected_total_values:
                        for min_btts_rate in min_btts_rate_values:
                            for min_over_15_rate in min_over_15_rate_values:
                                for max_failed in max_failed_values:
                                    for max_btts_rows in max_btts_rows_values:
                                        placeholder = StrategySpec(
                                            name="",
                                            mode=mode,
                                            min_btts_score=score_threshold,
                                            min_history_count=min_history,
                                            min_expected_team_goals=min_expected_team,
                                            min_expected_total_goals=min_expected_total,
                                            min_combined_btts_rate=min_btts_rate,
                                            min_combined_over_15_rate=min_over_15_rate,
                                            max_failed_to_score_rate=max_failed,
                                            max_btts_rows=max_btts_rows,
                                        )
                                        strategies.append(
                                            StrategySpec(
                                                name=build_strategy_name(placeholder),
                                                mode=mode,
                                                min_btts_score=score_threshold,
                                                min_history_count=min_history,
                                                min_expected_team_goals=min_expected_team,
                                                min_expected_total_goals=min_expected_total,
                                                min_combined_btts_rate=min_btts_rate,
                                                min_combined_over_15_rate=min_over_15_rate,
                                                max_failed_to_score_rate=max_failed,
                                                max_btts_rows=max_btts_rows,
                                            )
                                        )
    return strategies


# Sélectionne les candidats BTTS_YES selon une stratégie V17.8.
def build_btts_candidate_mask(dataframe: pd.DataFrame, spec: StrategySpec) -> pd.Series:
    required_columns = [
        "v17_6_score",
        "min_history_count_last_10",
        "expected_home_goals_proxy",
        "expected_away_goals_proxy",
        "expected_total_goals_proxy",
        "combined_btts_rate_last_10",
        "combined_over_1_5_rate_last_10",
        "home_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
    ]
    missing_columns = [column for column in required_columns if column not in dataframe.columns]
    if missing_columns:
        raise KeyError(f"Colonnes V17.8 manquantes : {missing_columns}")

    base_selected = get_v17_base_selected_mask(dataframe)
    is_over_15_base = dataframe["v17_recommendation_type"] == GOALS_OVER_15_TYPE

    if spec.mode == "fallback_only":
        eligible_mode = ~base_selected
    elif spec.mode == "replace_over15_or_fallback":
        eligible_mode = (~base_selected) | is_over_15_base
    else:
        raise ValueError(f"Mode V17.8 non reconnu : {spec.mode}")

    raw_mask = (
        eligible_mode
        & (dataframe["v17_6_score"] >= spec.min_btts_score)
        & (dataframe["min_history_count_last_10"] >= spec.min_history_count)
        & (dataframe["expected_home_goals_proxy"] >= spec.min_expected_team_goals)
        & (dataframe["expected_away_goals_proxy"] >= spec.min_expected_team_goals)
        & (dataframe["expected_total_goals_proxy"] >= spec.min_expected_total_goals)
        & (dataframe["combined_btts_rate_last_10"] >= spec.min_combined_btts_rate)
        & (dataframe["combined_over_1_5_rate_last_10"] >= spec.min_combined_over_15_rate)
        & (dataframe["home_failed_to_score_rate_last_10"] <= spec.max_failed_to_score_rate)
        & (dataframe["away_failed_to_score_rate_last_10"] <= spec.max_failed_to_score_rate)
    )

    if spec.max_btts_rows is None or int(raw_mask.sum()) <= spec.max_btts_rows:
        return raw_mask

    top_indices = dataframe[raw_mask].sort_values("v17_6_score", ascending=False).head(spec.max_btts_rows).index
    limited_mask = pd.Series(False, index=dataframe.index)
    limited_mask.loc[top_indices] = True
    return limited_mask


# Applique une stratégie V17.8 : V17.0 reste la base, BTTS peut remplacer Over 1.5 ou compléter les abstentions selon le mode.
def apply_v17_8_strategy(dataframe: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    output = dataframe.copy()
    base_selected = get_v17_base_selected_mask(output)
    btts_mask = build_btts_candidate_mask(output, spec)
    selected = base_selected | btts_mask

    output["v17_8_strategy"] = spec.name
    output["v17_8_recommendation_status"] = np.where(selected, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v17_8_recommendation_type"] = "ABSTAIN"
    output.loc[base_selected, "v17_8_recommendation_type"] = output.loc[base_selected, "v17_recommendation_type"]
    output.loc[btts_mask, "v17_8_recommendation_type"] = BTTS_TYPE

    output["v17_8_recommendation_value"] = "ABSTAIN"
    output.loc[base_selected, "v17_8_recommendation_value"] = output.loc[base_selected, "v17_recommendation_value"]
    output.loc[btts_mask, "v17_8_recommendation_value"] = BTTS_YES_VALUE

    output["v17_8_source"] = "ABSTAIN"
    output.loc[base_selected, "v17_8_source"] = output.loc[base_selected, "v17_source"].astype(str)
    output.loc[btts_mask, "v17_8_source"] = "V17_8_BTTS_YES_USER_OBJECTIVE"

    output["v17_8_is_correct"] = False
    output.loc[base_selected, "v17_8_is_correct"] = output.loc[base_selected, "v17_is_correct"].map(to_bool)
    output.loc[btts_mask, "v17_8_is_correct"] = output.loc[btts_mask, "target_btts"].astype(str) == BTTS_YES_VALUE

    output["v17_8_is_btts"] = btts_mask
    output["v17_8_is_added_btts"] = btts_mask & (~base_selected)
    output["v17_8_is_replaced_over15"] = btts_mask & (output["v17_recommendation_type"] == GOALS_OVER_15_TYPE)
    output["v17_8_excluded_reason"] = ""
    output.loc[(~selected) & (output["v17_8_excluded_reason"] == ""), "v17_8_excluded_reason"] = "NO_SELECTED_SIGNAL"
    return output


# Calcule les métriques principales d'une prédiction V17.8.
def compute_metrics(predictions: pd.DataFrame, spec: StrategySpec) -> dict[str, object]:
    selected = predictions[predictions["v17_8_recommendation_status"] == RECOMMEND_STATUS]
    base_selected = predictions[get_v17_base_selected_mask(predictions)]
    strict = selected[selected["v17_8_recommendation_type"] == STRICT_TYPE]
    double = selected[selected["v17_8_recommendation_type"] == DOUBLE_CHANCE_TYPE]
    over_15 = selected[selected["v17_8_recommendation_type"] == GOALS_OVER_15_TYPE]
    btts = selected[selected["v17_8_recommendation_type"] == BTTS_TYPE]

    total_rows = len(predictions)
    selected_rows = len(selected)
    correct_rows = int(selected["v17_8_is_correct"].map(to_bool).sum())
    base_correct_rows = int(base_selected["v17_is_correct"].map(to_bool).sum())

    return {
        "strategy": spec.name,
        "mode": spec.mode,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstained_rows": total_rows - selected_rows,
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "accuracy": rounded(safe_rate(correct_rows, selected_rows)),
        "correct_rows": correct_rows,
        "strict_1x2_rows": len(strict),
        "strict_1x2_accuracy": rounded(safe_rate(int(strict["v17_8_is_correct"].map(to_bool).sum()), len(strict))),
        "double_chance_rows": len(double),
        "double_chance_accuracy": rounded(safe_rate(int(double["v17_8_is_correct"].map(to_bool).sum()), len(double))),
        "over_15_rows": len(over_15),
        "over_15_accuracy": rounded(safe_rate(int(over_15["v17_8_is_correct"].map(to_bool).sum()), len(over_15))),
        "btts_rows": len(btts),
        "btts_accuracy": rounded(safe_rate(int(btts["v17_8_is_correct"].map(to_bool).sum()), len(btts))),
        "added_btts_rows": int(predictions["v17_8_is_added_btts"].sum()),
        "replaced_over15_rows": int(predictions["v17_8_is_replaced_over15"].sum()),
        "v17_reference_selected_rows": len(base_selected),
        "v17_reference_accuracy_recomputed": rounded(safe_rate(base_correct_rows, len(base_selected))),
        "selected_rows_delta_vs_v17_0": selected_rows - len(base_selected),
        "coverage_delta_vs_v17_0": rounded(safe_rate(selected_rows, total_rows) - safe_rate(len(base_selected), total_rows)),
        "accuracy_delta_vs_v17_0": rounded(safe_rate(correct_rows, selected_rows) - safe_rate(base_correct_rows, len(base_selected))),
        "min_btts_score": spec.min_btts_score,
        "min_history_count": spec.min_history_count,
        "min_expected_team_goals": spec.min_expected_team_goals,
        "min_expected_total_goals": spec.min_expected_total_goals,
        "min_combined_btts_rate": spec.min_combined_btts_rate,
        "min_combined_over_15_rate": spec.min_combined_over_15_rate,
        "max_failed_to_score_rate": spec.max_failed_to_score_rate,
        "max_btts_rows": "all" if spec.max_btts_rows is None else spec.max_btts_rows,
    }


# Évalue toutes les stratégies V17.8 de la grille contrôlée.
def evaluate_strategy_grid(dataframe: pd.DataFrame, strategies: list[StrategySpec]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total = len(strategies)
    print(f"Nombre total de stratégies V17.8 à tester : {total}")

    for index, spec in enumerate(strategies, start=1):
        predictions = apply_v17_8_strategy(dataframe, spec)
        metrics = compute_metrics(predictions, spec)
        metrics["passes_user_objective"] = (
            metrics["accuracy"] >= MIN_USER_GLOBAL_ACCURACY
            and metrics["selected_rows"] > V17_REFERENCE_SELECTED_ROWS
            and metrics["btts_rows"] >= MIN_REVIEW_BTTS_ROWS
        )
        metrics["passes_professional_objective"] = (
            metrics["accuracy"] >= MIN_PRO_GLOBAL_ACCURACY
            and metrics["selected_rows"] > V17_REFERENCE_SELECTED_ROWS
            and metrics["btts_rows"] >= MIN_REVIEW_BTTS_ROWS
            and metrics["btts_accuracy"] >= MIN_PRO_BTTS_ACCURACY
        )
        rows.append(metrics)

        if index % 500 == 0 or index == total:
            best_so_far = pd.DataFrame(rows).sort_values(
                ["passes_professional_objective", "passes_user_objective", "btts_rows", "accuracy"],
                ascending=[False, False, False, False],
            ).iloc[0]
            print(
                f"[V17.8] {index}/{total} stratégies testées | "
                f"best_acc={best_so_far['accuracy']} | best_btts_rows={best_so_far['btts_rows']} | "
                f"best_btts_acc={best_so_far['btts_accuracy']} | best={best_so_far['strategy']}"
            )

    return pd.DataFrame(rows)


# Choisit la meilleure stratégie selon l'objectif utilisateur, en privilégiant une intégration BTTS propre et mesurable.
def choose_best_strategy(strategy_audit: pd.DataFrame) -> StrategySpec:
    candidates = strategy_audit[strategy_audit["passes_professional_objective"]].copy()
    if candidates.empty:
        candidates = strategy_audit[strategy_audit["passes_user_objective"]].copy()
    if candidates.empty:
        candidates = strategy_audit.copy()

    candidates["mode_priority"] = candidates["mode"].map({"replace_over15_or_fallback": 2, "fallback_only": 1}).fillna(0)
    best = candidates.sort_values(
        ["passes_professional_objective", "passes_user_objective", "mode_priority", "btts_rows", "btts_accuracy", "accuracy"],
        ascending=[False, False, False, False, False, False],
    ).iloc[0]

    max_btts_rows = None if str(best["max_btts_rows"]) == "all" else int(best["max_btts_rows"])
    return StrategySpec(
        name=str(best["strategy"]),
        mode=str(best["mode"]),
        min_btts_score=float(best["min_btts_score"]),
        min_history_count=int(best["min_history_count"]),
        min_expected_team_goals=float(best["min_expected_team_goals"]),
        min_expected_total_goals=float(best["min_expected_total_goals"]),
        min_combined_btts_rate=float(best["min_combined_btts_rate"]),
        min_combined_over_15_rate=float(best["min_combined_over_15_rate"]),
        max_failed_to_score_rate=float(best["max_failed_to_score_rate"]),
        max_btts_rows=max_btts_rows,
    )


# Agrège les performances V17.8 par marché retenu.
def build_by_market(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions[predictions["v17_8_recommendation_status"] == RECOMMEND_STATUS]
    rows: list[dict[str, object]] = []

    for (recommendation_type, recommendation_value), group in selected.groupby(
        ["v17_8_recommendation_type", "v17_8_recommendation_value"], dropna=False
    ):
        rows.append(
            {
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v17_8_is_correct"].map(to_bool).sum()), len(group))),
                "added_btts_rows": int(group["v17_8_is_added_btts"].sum()) if "v17_8_is_added_btts" in group else 0,
                "replaced_over15_rows": int(group["v17_8_is_replaced_over15"].sum()) if "v17_8_is_replaced_over15" in group else 0,
                "avg_btts_score": rounded(group["v17_6_score"].mean()) if "v17_6_score" in group else 0.0,
                "avg_prob_btts_proxy": rounded(group["prob_btts_proxy"].mean()) if "prob_btts_proxy" in group else 0.0,
                "avg_combined_btts_rate": rounded(group["combined_btts_rate_last_10"].mean()) if "combined_btts_rate_last_10" in group else 0.0,
                "avg_expected_total_goals_proxy": rounded(group["expected_total_goals_proxy"].mean()) if "expected_total_goals_proxy" in group else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["recommendation_type", "selected_rows"], ascending=[True, False])


# Agrège les performances V17.8 par ligue et saison pour contrôler la stabilité.
def build_by_league_season(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions[predictions["v17_8_recommendation_status"] == RECOMMEND_STATUS]
    rows: list[dict[str, object]] = []

    for (league_code, season), group in selected.groupby(["__league_code", "__season"], dropna=False):
        selected_rows = len(group)
        accuracy = rounded(safe_rate(int(group["v17_8_is_correct"].map(to_bool).sum()), selected_rows))
        segment_status = "OK"
        if selected_rows < MIN_MAJOR_SEGMENT_ROWS:
            segment_status = "LOW_VOLUME"
        elif accuracy < MIN_MAJOR_SEGMENT_ACCURACY:
            segment_status = "BELOW_0_70"
        elif accuracy < STRONG_SEGMENT_ACCURACY:
            segment_status = "UNDER_STRONG_0_75"

        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "selected_rows": selected_rows,
                "accuracy": accuracy,
                "strict_1x2_rows": int((group["v17_8_recommendation_type"] == STRICT_TYPE).sum()),
                "double_chance_rows": int((group["v17_8_recommendation_type"] == DOUBLE_CHANCE_TYPE).sum()),
                "over_15_rows": int((group["v17_8_recommendation_type"] == GOALS_OVER_15_TYPE).sum()),
                "btts_rows": int((group["v17_8_recommendation_type"] == BTTS_TYPE).sum()),
                "segment_status": segment_status,
            }
        )
    return pd.DataFrame(rows).sort_values(["season", "league_code"])


# Exporte les erreurs V17.8 pour analyser les limites du compromis utilisateur.
def build_error_patterns(predictions: pd.DataFrame) -> pd.DataFrame:
    errors = predictions[
        (predictions["v17_8_recommendation_status"] == RECOMMEND_STATUS)
        & (~predictions["v17_8_is_correct"].map(to_bool))
    ].copy()
    if errors.empty:
        return pd.DataFrame()

    keep_columns = [
        "__league_code",
        "__season",
        "Date",
        "HomeTeam",
        "AwayTeam",
        "target_result",
        "target_over_under_15",
        "target_btts",
        "v17_8_recommendation_type",
        "v17_8_recommendation_value",
        "v17_8_source",
        "v17_8_is_correct",
        "v17_8_is_added_btts",
        "v17_8_is_replaced_over15",
        "v17_recommendation_type",
        "v17_recommendation_value",
        "v17_is_correct",
        "v17_6_score",
        "prob_btts_proxy",
        "combined_btts_rate_last_10",
        "combined_over_1_5_rate_last_10",
        "expected_home_goals_proxy",
        "expected_away_goals_proxy",
        "expected_total_goals_proxy",
        "home_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
        "min_history_count_last_10",
    ]
    available_columns = [column for column in keep_columns if column in errors.columns]
    return errors[available_columns].sort_values(["__season", "__league_code", "Date"]).head(1000)


# Prépare les colonnes de prédiction finale à exporter.
def build_predictions_export(predictions: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "__league_code",
        "__season",
        "Date",
        "HomeTeam",
        "AwayTeam",
        "target_result",
        "target_over_under_15",
        "target_btts",
        "v17_8_strategy",
        "v17_8_recommendation_status",
        "v17_8_recommendation_type",
        "v17_8_recommendation_value",
        "v17_8_source",
        "v17_8_is_correct",
        "v17_8_is_btts",
        "v17_8_is_added_btts",
        "v17_8_is_replaced_over15",
        "v17_recommendation_type",
        "v17_recommendation_value",
        "v17_source",
        "v17_is_correct",
        "v17_6_score",
        "prob_btts_proxy",
        "combined_btts_rate_last_10",
        "combined_over_1_5_rate_last_10",
        "expected_home_goals_proxy",
        "expected_away_goals_proxy",
        "expected_total_goals_proxy",
        "home_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
        "min_history_count_last_10",
    ]
    available_columns = [column for column in columns if column in predictions.columns]
    return predictions[available_columns].copy()


# Détermine le statut V17.8 selon l'objectif utilisateur et la stabilité minimale.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings_list: list[str] = []

    accuracy = float(metrics.get("accuracy", 0.0))
    btts_rows = int(metrics.get("btts_rows", 0))
    btts_accuracy = float(metrics.get("btts_accuracy", 0.0))
    selected_rows = int(metrics.get("selected_rows", 0))

    major_under_70 = 0
    major_under_75 = 0
    if not by_league_season.empty:
        major_segments = by_league_season[by_league_season["selected_rows"] >= MIN_MAJOR_SEGMENT_ROWS]
        major_under_70 = len(major_segments[major_segments["accuracy"] < MIN_MAJOR_SEGMENT_ACCURACY])
        major_under_75 = len(major_segments[major_segments["accuracy"] < STRONG_SEGMENT_ACCURACY])

    if accuracy < MIN_USER_GLOBAL_ACCURACY:
        blockers.append("Accuracy globale sous l'objectif utilisateur minimal de 0.70.")
    if btts_rows < MIN_REVIEW_BTTS_ROWS:
        blockers.append(f"Volume BTTS sous le minimum review de {MIN_REVIEW_BTTS_ROWS} lignes.")
    if selected_rows <= V17_REFERENCE_SELECTED_ROWS:
        warnings_list.append("Le sélecteur ne dépasse pas le volume de sélection V17.0.")
    if btts_accuracy < MIN_REVIEW_BTTS_ACCURACY:
        warnings_list.append(f"BTTS accuracy sous le seuil review de {MIN_REVIEW_BTTS_ACCURACY}.")
    if btts_accuracy < MIN_PRO_BTTS_ACCURACY:
        warnings_list.append(f"BTTS accuracy sous le seuil professionnel de {MIN_PRO_BTTS_ACCURACY}.")
    if major_under_70 > 0:
        warnings_list.append(f"{major_under_70} segment(s) majeur(s) sous {MIN_MAJOR_SEGMENT_ACCURACY}.")
    if major_under_75 > 0:
        warnings_list.append(f"{major_under_75} segment(s) majeur(s) sous {STRONG_SEGMENT_ACCURACY}.")
    if accuracy < V17_REFERENCE_ACCURACY:
        warnings_list.append("Accuracy globale inférieure à V17.0 : l'ajout de BTTS a un coût mesurable.")

    if blockers:
        return "V17_8_USER_OBJECTIVE_BTTS_REJECTED", blockers, warnings_list

    if accuracy >= MIN_PRO_GLOBAL_ACCURACY and btts_accuracy >= MIN_PRO_BTTS_ACCURACY and major_under_70 == 0:
        return "V17_8_USER_OBJECTIVE_BTTS_PRO_REVIEW", blockers, warnings_list

    return "V17_8_USER_OBJECTIVE_BTTS_LIMITED_REVIEW", blockers, warnings_list


# Écrit la synthèse V17.8 dans le dossier de preuves ML.
def write_summary(
    output_path: Path,
    metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
    by_league_season: pd.DataFrame,
    strategy_audit: pd.DataFrame,
) -> None:
    lowest_segment = "Aucun"
    major_under_70 = 0
    if not by_league_season.empty:
        first = by_league_season.sort_values(["accuracy", "selected_rows"], ascending=[True, False]).iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"
        major_segments = by_league_season[by_league_season["selected_rows"] >= MIN_MAJOR_SEGMENT_ROWS]
        major_under_70 = len(major_segments[major_segments["accuracy"] < MIN_MAJOR_SEGMENT_ACCURACY])

    top_candidates = strategy_audit.sort_values(
        ["passes_professional_objective", "passes_user_objective", "btts_rows", "btts_accuracy", "accuracy"],
        ascending=[False, False, False, False, False],
    ).head(5)

    lines = [
        "RubyBets - ML V17.8 sélecteur objectif utilisateur avec BTTS",
        "274 - Synthèse expérience V17.8",
        "",
        "Objectif :",
        "Tester une intégration plus visible de BTTS dans un sélecteur multi-marchés tout en conservant une accuracy globale au-dessus de l'objectif utilisateur minimal de 70%.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data via les scripts existants.",
        "- Construction des signaux en mémoire.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Logique V17.8 :",
        "1. Conserver V17.0 comme socle fort.",
        "2. Autoriser BTTS_YES à remplacer uniquement OVER_1_5 ou à compléter une abstention.",
        "3. Ne pas remplacer 1X2 strict ni double chance, pour protéger les signaux les plus solides.",
        "4. Sélectionner la meilleure stratégie selon accuracy globale, volume BTTS et stabilité minimale.",
        "5. Garder UNDER_1_5, O/U 2.5 et BTTS_NO exclus.",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Strategy : {metrics.get('strategy')}",
        f"- Mode : {metrics.get('mode')}",
        f"- Accuracy : {metrics.get('accuracy')}",
        f"- Coverage : {metrics.get('coverage')}",
        f"- Abstention rate : {metrics.get('abstention_rate')}",
        f"- Selected rows : {metrics.get('selected_rows')}",
        f"- Strict 1X2 rows : {metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 accuracy : {metrics.get('strict_1x2_accuracy')}",
        f"- Double chance rows : {metrics.get('double_chance_rows')}",
        f"- Double chance accuracy : {metrics.get('double_chance_accuracy')}",
        f"- OVER_1_5 rows : {metrics.get('over_15_rows')}",
        f"- OVER_1_5 accuracy : {metrics.get('over_15_accuracy')}",
        f"- BTTS rows : {metrics.get('btts_rows')}",
        f"- BTTS accuracy : {metrics.get('btts_accuracy')}",
        f"- Added BTTS rows vs V17.0 : {metrics.get('added_btts_rows')}",
        f"- Replaced OVER_1_5 rows by BTTS : {metrics.get('replaced_over15_rows')}",
        "",
        "Comparaison avec V17.0 :",
        f"- V17.0 selected rows recalculées : {metrics.get('v17_reference_selected_rows')}",
        f"- V17.0 accuracy recalculée : {metrics.get('v17_reference_accuracy_recomputed')}",
        f"- Selected rows delta vs V17.0 : {metrics.get('selected_rows_delta_vs_v17_0')}",
        f"- Coverage delta vs V17.0 : {metrics.get('coverage_delta_vs_v17_0')}",
        f"- Accuracy delta vs V17.0 : {metrics.get('accuracy_delta_vs_v17_0')}",
        "",
        "Paramètres BTTS retenus :",
        f"- min_btts_score : {metrics.get('min_btts_score')}",
        f"- min_history_count : {metrics.get('min_history_count')}",
        f"- min_expected_team_goals : {metrics.get('min_expected_team_goals')}",
        f"- min_expected_total_goals : {metrics.get('min_expected_total_goals')}",
        f"- min_combined_btts_rate : {metrics.get('min_combined_btts_rate')}",
        f"- min_combined_over_15_rate : {metrics.get('min_combined_over_15_rate')}",
        f"- max_failed_to_score_rate : {metrics.get('max_failed_to_score_rate')}",
        "",
        "Stabilité rapide :",
        f"- Segments ligue/saison analysés : {len(by_league_season)}",
        f"- Segment le plus bas : {lowest_segment}",
        f"- Segments majeurs sous {MIN_MAJOR_SEGMENT_ACCURACY} : {major_under_70}",
        "",
        "Top 5 stratégies testées :",
    ]

    for _, row in top_candidates.iterrows():
        lines.append(
            f"- {row['strategy']} | accuracy={row['accuracy']} | btts_rows={row['btts_rows']} | btts_accuracy={row['btts_accuracy']} | selected_rows={row['selected_rows']}"
        )

    lines.extend(
        [
            "",
            "Raisons bloquantes :",
            *(f"- {item}" for item in blockers),
            "- Aucune." if not blockers else "",
            "",
            "Points de vigilance :",
            *(f"- {item}" for item in warnings_list),
            "- Aucun." if not warnings_list else "",
            "",
            "Décision produit :",
            "Ne pas intégrer V17.8 au produit à ce stade. V17.8 sert à mesurer un compromis utilisateur où BTTS est plus visible, mais le scoring explicable V1 reste le socle officiel de RubyBets.",
        ]
    )
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Écrit la décision opérationnelle V17.8.
def write_decision(output_path: Path, metrics: dict[str, object], status: str, blockers: list[str], warnings_list: list[str]) -> None:
    lines = [
        "RubyBets - Décision V17.8 sélecteur objectif utilisateur avec BTTS",
        "279 - Décision expérience V17.8",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {metrics.get('strategy')}",
        f"- Accuracy : {metrics.get('accuracy')}",
        f"- Coverage : {metrics.get('coverage')}",
        f"- Abstention rate : {metrics.get('abstention_rate')}",
        f"- Selected rows : {metrics.get('selected_rows')}",
        f"- Strict 1X2 rows : {metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 accuracy : {metrics.get('strict_1x2_accuracy')}",
        f"- Double chance rows : {metrics.get('double_chance_rows')}",
        f"- Double chance accuracy : {metrics.get('double_chance_accuracy')}",
        f"- OVER_1_5 rows : {metrics.get('over_15_rows')}",
        f"- OVER_1_5 accuracy : {metrics.get('over_15_accuracy')}",
        f"- BTTS rows : {metrics.get('btts_rows')}",
        f"- BTTS accuracy : {metrics.get('btts_accuracy')}",
        f"- Added BTTS rows : {metrics.get('added_btts_rows')}",
        f"- Replaced OVER_1_5 rows : {metrics.get('replaced_over15_rows')}",
        f"- Selected rows delta vs V17.0 : {metrics.get('selected_rows_delta_vs_v17_0')}",
        f"- Coverage delta vs V17.0 : {metrics.get('coverage_delta_vs_v17_0')}",
        f"- Accuracy delta vs V17.0 : {metrics.get('accuracy_delta_vs_v17_0')}",
        "",
        "Gates V17.8 :",
        f"- Accuracy globale minimale utilisateur >= {MIN_USER_GLOBAL_ACCURACY}",
        f"- Accuracy globale professionnelle cible >= {MIN_PRO_GLOBAL_ACCURACY}",
        f"- BTTS rows review >= {MIN_REVIEW_BTTS_ROWS}",
        f"- BTTS accuracy review >= {MIN_REVIEW_BTTS_ACCURACY}",
        f"- BTTS accuracy professionnelle >= {MIN_PRO_BTTS_ACCURACY}",
        f"- Aucun segment majeur sous {MIN_MAJOR_SEGMENT_ACCURACY}",
        "- Aucun modèle officiel sauvegardé.",
        "- Aucune intégration API/frontend/scoring V1.",
        "",
        "Raisons bloquantes :",
        *(f"- {item}" for item in blockers),
        "- Aucune." if not blockers else "",
        "",
        "Points de vigilance :",
        *(f"- {item}" for item in warnings_list),
        "- Aucun." if not warnings_list else "",
        "",
        "Décision opérationnelle :",
    ]

    if status == "V17_8_USER_OBJECTIVE_BTTS_PRO_REVIEW":
        lines.extend(
            [
                "- V17.8 atteint l'objectif utilisateur et conserve un niveau global professionnel.",
                "- BTTS_YES peut être documenté comme signal expérimental plus visible, mais il reste séparé du produit.",
            ]
        )
    elif status == "V17_8_USER_OBJECTIVE_BTTS_LIMITED_REVIEW":
        lines.extend(
            [
                "- V17.8 atteint l'objectif utilisateur minimal, mais reste trop fragile pour remplacer V17.0.",
                "- BTTS_YES peut être présenté comme expérimentation contrôlée, pas comme signal produit validé.",
            ]
        )
    else:
        lines.extend(
            [
                "- V17.8 ne valide pas l'objectif utilisateur avec BTTS.",
                "- V17.0 reste la référence expérimentale multi-marchés contrôlée.",
            ]
        )

    lines.extend(
        [
            "- BTTS_NO reste exclu.",
            "- UNDER_1_5 reste exclu.",
            "- O/U 2.5 reste exclu.",
            "- V17.8 ne remplace pas le scoring explicable V1.",
            "- V17.8 ne modifie ni PostgreSQL, ni ml.features, ni l'API, ni le frontend.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V17.8 sélecteur objectif utilisateur avec BTTS : réalisée si les fichiers 274 à 279 sont générés.",
            "- Fichiers concernés : backend/scripts/ml/train_multimarket_v17_8_user_objective_btts.py et reports/evidence/ml_training/274-279.",
        ]
    )
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Orchestre V17.8 sans modifier RubyBets produit.
def main() -> None:
    print("Chargement de V17.0, V17.6 et V17.7 pour préparer V17.8 objectif utilisateur BTTS...")
    v17_7_module = load_module("rubybets_v17_7_for_v17_8", V17_7_REQUIRED_SCRIPT)
    v17_6_module = v17_7_module.load_module("rubybets_v17_6_for_v17_8", V17_6_REQUIRED_SCRIPT)
    project_root = v17_6_module.find_project_root()
    evidence_dir = v17_6_module.get_evidence_dir(project_root)

    v17_reference = v17_7_module.load_v17_reference_predictions(evidence_dir)
    if v17_reference is None:
        print("Fichier 228 introuvable ou incomplet : reconstruction de V17.0 depuis les scripts V13.1/V15...")
        v17_module = v17_7_module.load_module("rubybets_v17_controlled_for_v17_8", "train_multimarket_v17_selector_controlled.py")
        v17_reference = v17_7_module.rebuild_v17_reference_predictions(project_root, v17_module)
    else:
        print("Référence V17.0 chargée depuis 228_multimarket_v17_selector_results.csv.")

    print("Reconstruction rapide des scores BTTS V17.6, sans relancer les 864 000 combinaisons...")
    btts_predictions, _ = v17_7_module.build_v17_6_btts_predictions(project_root, v17_6_module)
    merged = v17_7_module.merge_v17_and_btts(v17_reference, btts_predictions)

    print("Évaluation V17.8 : objectif utilisateur global >= 70% avec BTTS plus visible...")
    strategies = generate_strategy_grid()
    strategy_audit = evaluate_strategy_grid(merged, strategies)
    best_spec = choose_best_strategy(strategy_audit)

    print(f"Application de la meilleure stratégie V17.8 : {best_spec.name}")
    final_predictions = apply_v17_8_strategy(merged, best_spec)
    metrics = compute_metrics(final_predictions, best_spec)
    by_market = build_by_market(final_predictions)
    by_league_season = build_by_league_season(final_predictions)
    error_patterns = build_error_patterns(final_predictions)
    status, blockers, warnings_list = determine_status(metrics, by_league_season)

    write_summary(evidence_dir / OUTPUT_SUMMARY, metrics, status, blockers, warnings_list, by_league_season, strategy_audit)
    build_predictions_export(final_predictions).to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8-sig")
    by_market.to_csv(evidence_dir / OUTPUT_BY_MARKET, index=False, encoding="utf-8-sig")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8-sig")
    error_patterns.to_csv(evidence_dir / OUTPUT_ERROR_PATTERNS, index=False, encoding="utf-8-sig")
    write_decision(evidence_dir / OUTPUT_DECISION, metrics, status, blockers, warnings_list)
    strategy_audit.sort_values(
        ["passes_professional_objective", "passes_user_objective", "btts_rows", "btts_accuracy", "accuracy"],
        ascending=[False, False, False, False, False],
    ).to_csv(evidence_dir / OUTPUT_STRATEGY_AUDIT, index=False, encoding="utf-8-sig")

    print("OK - Expérience V17.8 selector objectif utilisateur avec BTTS terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {metrics.get('strategy')}")
    print(f"Mode: {metrics.get('mode')}")
    print(f"Test accuracy: {metrics.get('accuracy')}")
    print(f"Test coverage: {metrics.get('coverage')}")
    print(f"Test abstention rate: {metrics.get('abstention_rate')}")
    print(f"Selected rows: {metrics.get('selected_rows')}")
    print(f"Strict 1X2 rows: {metrics.get('strict_1x2_rows')}")
    print(f"Strict 1X2 accuracy: {metrics.get('strict_1x2_accuracy')}")
    print(f"Double chance rows: {metrics.get('double_chance_rows')}")
    print(f"Double chance accuracy: {metrics.get('double_chance_accuracy')}")
    print(f"OVER_1_5 rows: {metrics.get('over_15_rows')}")
    print(f"OVER_1_5 accuracy: {metrics.get('over_15_accuracy')}")
    print(f"BTTS rows: {metrics.get('btts_rows')}")
    print(f"BTTS accuracy: {metrics.get('btts_accuracy')}")
    print(f"Added BTTS rows vs V17.0: {metrics.get('added_btts_rows')}")
    print(f"Replaced OVER_1_5 rows by BTTS: {metrics.get('replaced_over15_rows')}")
    print(f"Selected rows delta vs V17.0: {metrics.get('selected_rows_delta_vs_v17_0')}")
    print(f"Coverage delta vs V17.0: {metrics.get('coverage_delta_vs_v17_0')}")
    print(f"Accuracy delta vs V17.0: {metrics.get('accuracy_delta_vs_v17_0')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By market CSV saved: {evidence_dir / OUTPUT_BY_MARKET}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")
    print(f"Strategy audit saved: {evidence_dir / OUTPUT_STRATEGY_AUDIT}")


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# train_multimarket_v17_8_user_objective_btts.py
#   -> réutilise backend/scripts/ml/train_multimarket_v17_7_selector_with_btts.py
#   -> réutilise backend/scripts/ml/train_goals_v17_6_btts_ultra_selective.py
#   -> réutilise reports/evidence/ml_training/228_multimarket_v17_selector_results.csv si disponible
#   -> lit data/ml/raw/*.csv en lecture seule via les scripts réutilisés
#   -> écrit reports/evidence/ml_training/274 à 279 + 279b audit stratégie
#   -> ne communique pas avec PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou models/
