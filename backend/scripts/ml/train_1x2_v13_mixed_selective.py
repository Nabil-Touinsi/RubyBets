# Rôle du fichier : tester une V13.1 expérimentale mixte, avec 1X2 strict quand le signal est très fort, double chance quand le signal est moyen, et abstention quand le signal est trop faible.

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


TARGET_COLUMN = "target_result"
TARGET_CLASSES = ["HOME_WIN", "DRAW", "AWAY_WIN"]
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"
STRICT_TYPE = "STRICT_1X2"
DOUBLE_CHANCE_TYPE = "DOUBLE_CHANCE"

OUTPUT_SUMMARY = "193_1x2_v13_mixed_selective_summary.txt"
OUTPUT_RESULTS = "194_1x2_v13_mixed_selective_results.csv"
OUTPUT_BY_TYPE_MARKET = "195_1x2_v13_mixed_selective_by_type_market.csv"
OUTPUT_BY_LEAGUE_SEASON = "196_1x2_v13_mixed_selective_by_league_season.csv"
OUTPUT_ERROR_PATTERNS = "197_1x2_v13_mixed_selective_error_patterns.csv"
OUTPUT_DECISION = "198_1x2_v13_mixed_selective_decision.txt"

STATIC_V9_SELECTED_ROWS = 795
STATIC_V9_COVERAGE = 0.1492
STATIC_V11_SELECTED_ROWS = 1240
STATIC_V11_COVERAGE = 0.2326
STATIC_V13_DOUBLE_CHANCE_ROWS = 3563
STATIC_V13_DOUBLE_CHANCE_COVERAGE = 0.6685
STATIC_V13_DOUBLE_CHANCE_ACCURACY = 0.8375

ACCEPT_MIN_MIXED_ACCURACY = 0.82
ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY = 0.82
ACCEPT_MIN_STRICT_ACCURACY = 0.78
ACCEPT_MIN_COVERAGE = 0.50
ACCEPT_MIN_SELECTED_ROWS = 2500
ACCEPT_MIN_STRICT_ROWS = 100
ACCEPT_MIN_DOUBLE_ROWS = 1800
ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY = 0.75

REVIEW_MIN_MIXED_ACCURACY = 0.78
REVIEW_MIN_COVERAGE = 0.40
REVIEW_MIN_STRICT_ROWS = 50
REVIEW_MIN_DOUBLE_ROWS = 1200

STRICT_PROBABILITY_THRESHOLDS = [0.72, 0.74, 0.76, 0.78, 0.80, 0.82]
STRICT_MARGIN_THRESHOLDS = [0.10, 0.12, 0.15, 0.18, 0.20]
DOUBLE_CHANCE_TOP2_THRESHOLDS = [0.68, 0.70, 0.72, 0.74, 0.76, 0.78, 0.80]
MAX_ENTROPY_THRESHOLDS = [1.05, 1.07, 1.09]
MIN_AVAILABLE_TRIPLETS = [1, 3]
MIN_AGREEMENT_THRESHOLDS = [0.00, 0.50]

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class MixedPolicy:
    strict_probability_threshold: float
    strict_margin_threshold: float
    double_chance_top2_threshold: float
    max_entropy_threshold: float
    min_available_triplets: int
    min_agreement_threshold: float

    @property
    def name(self) -> str:
        return (
            "v13_mixed"
            f"_sp{self.strict_probability_threshold:.2f}"
            f"_sm{self.strict_margin_threshold:.2f}"
            f"_top2{self.double_chance_top2_threshold:.2f}"
            f"_ent{self.max_entropy_threshold:.2f}"
            f"_trip{self.min_available_triplets}"
            f"_agr{self.min_agreement_threshold:.2f}"
        ).replace(".", "")


# Charge le script V13 double chance comme module technique réutilisable.
def load_v13_base_module() -> ModuleType:
    base_script = Path(__file__).resolve().parent / "train_1x2_v13_double_chance_selective.py"
    if not base_script.exists():
        raise FileNotFoundError(
            "Le script V13 double chance est requis pour réutiliser la préparation des données : "
            f"{base_script}"
        )

    spec = importlib.util.spec_from_file_location("rubybets_v13_double_chance_base", base_script)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de charger le module de base V13 : {base_script}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["rubybets_v13_double_chance_base"] = module
    spec.loader.exec_module(module)
    return module


# Arrondit une valeur numérique pour stabiliser les sorties CSV et TXT.
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


# Crée toutes les politiques mixtes à tester sur validation.
def build_policies() -> list[MixedPolicy]:
    policies: list[MixedPolicy] = []
    for strict_probability in STRICT_PROBABILITY_THRESHOLDS:
        for strict_margin in STRICT_MARGIN_THRESHOLDS:
            for top2_threshold in DOUBLE_CHANCE_TOP2_THRESHOLDS:
                for entropy_threshold in MAX_ENTROPY_THRESHOLDS:
                    for min_triplets in MIN_AVAILABLE_TRIPLETS:
                        for agreement_threshold in MIN_AGREEMENT_THRESHOLDS:
                            policies.append(
                                MixedPolicy(
                                    strict_probability_threshold=strict_probability,
                                    strict_margin_threshold=strict_margin,
                                    double_chance_top2_threshold=top2_threshold,
                                    max_entropy_threshold=entropy_threshold,
                                    min_available_triplets=min_triplets,
                                    min_agreement_threshold=agreement_threshold,
                                )
                            )
    return policies


# Calcule le masque des recommandations 1X2 strictes pour les favoris très forts.
def build_strict_mask(dataframe: pd.DataFrame, policy: MixedPolicy) -> pd.Series:
    return (
        (dataframe["market_favorite_prob"] >= policy.strict_probability_threshold)
        & (dataframe["market_margin_top1_top2"] >= policy.strict_margin_threshold)
        & (dataframe["v13_strict_prediction"] != "DRAW")
    )


# Calcule le masque double chance sur les matchs non retenus en 1X2 strict.
def build_double_chance_mask(dataframe: pd.DataFrame, policy: MixedPolicy, strict_mask: pd.Series) -> pd.Series:
    return (
        (dataframe["market_top2_sum"] >= policy.double_chance_top2_threshold)
        & (dataframe["market_entropy"] <= policy.max_entropy_threshold)
        & (dataframe["market_available_triplets"] >= policy.min_available_triplets)
        & (dataframe["market_bookmaker_agreement_score"] >= policy.min_agreement_threshold)
        & (~strict_mask)
    )


# Vérifie si une double chance couvre correctement le résultat réel.
def is_double_chance_correct(target: str, double_chance: str) -> bool:
    covered = {
        "1X": {"HOME_WIN", "DRAW"},
        "X2": {"DRAW", "AWAY_WIN"},
        "12": {"HOME_WIN", "AWAY_WIN"},
    }
    return str(target) in covered.get(str(double_chance), set())


# Applique une politique mixte et ajoute les colonnes de recommandation.
def apply_policy(dataframe: pd.DataFrame, policy: MixedPolicy) -> pd.DataFrame:
    output = dataframe.copy()

    numeric_columns = [
        "market_favorite_prob",
        "market_margin_top1_top2",
        "market_top2_sum",
        "market_entropy",
        "market_available_triplets",
        "market_bookmaker_agreement_score",
    ]
    for column in numeric_columns:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0.0)

    strict_mask = build_strict_mask(output, policy)
    double_chance_mask = build_double_chance_mask(output, policy, strict_mask)
    selected_mask = strict_mask | double_chance_mask

    output["v13_mixed_strategy"] = policy.name
    output["v13_mixed_recommendation_status"] = np.where(selected_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v13_mixed_recommendation_type"] = np.where(
        strict_mask,
        STRICT_TYPE,
        np.where(double_chance_mask, DOUBLE_CHANCE_TYPE, "ABSTAIN"),
    )
    output["v13_mixed_recommendation_value"] = np.where(
        strict_mask,
        output["v13_strict_prediction"],
        np.where(double_chance_mask, output["v13_double_chance"], "ABSTAIN"),
    )
    output["v13_mixed_strict_is_correct"] = (
        output[TARGET_COLUMN].astype(str) == output["v13_strict_prediction"].astype(str)
    )
    output["v13_mixed_double_chance_is_correct"] = [
        is_double_chance_correct(target, double_chance)
        for target, double_chance in zip(output[TARGET_COLUMN], output["v13_double_chance"], strict=False)
    ]
    output["v13_mixed_is_correct"] = np.where(
        output["v13_mixed_recommendation_type"] == STRICT_TYPE,
        output["v13_mixed_strict_is_correct"],
        np.where(
            output["v13_mixed_recommendation_type"] == DOUBLE_CHANCE_TYPE,
            output["v13_mixed_double_chance_is_correct"],
            False,
        ),
    )
    return output


# Prépare les tableaux NumPy pour évaluer rapidement les politiques sans recopier les DataFrames.
def prepare_metric_arrays(dataframe: pd.DataFrame) -> dict[str, np.ndarray]:
    target = dataframe[TARGET_COLUMN].astype(str).to_numpy()
    strict_prediction = dataframe["v13_strict_prediction"].astype(str).to_numpy()
    double_chance = dataframe["v13_double_chance"].astype(str).to_numpy()
    strict_correct = target == strict_prediction
    double_correct = (
        ((double_chance == "1X") & ((target == "HOME_WIN") | (target == "DRAW")))
        | ((double_chance == "X2") & ((target == "DRAW") | (target == "AWAY_WIN")))
        | ((double_chance == "12") & ((target == "HOME_WIN") | (target == "AWAY_WIN")))
    )

    return {
        "favorite_prob": dataframe["market_favorite_prob"].astype(float).to_numpy(),
        "margin": dataframe["market_margin_top1_top2"].astype(float).to_numpy(),
        "top2_sum": dataframe["market_top2_sum"].astype(float).to_numpy(),
        "entropy": dataframe["market_entropy"].astype(float).to_numpy(),
        "available_triplets": dataframe["market_available_triplets"].astype(float).to_numpy(),
        "agreement": dataframe["market_bookmaker_agreement_score"].astype(float).to_numpy(),
        "target": target,
        "strict_prediction": strict_prediction,
        "double_chance": double_chance,
        "strict_correct": strict_correct,
        "double_correct": double_correct,
    }


# Calcule les métriques d'une politique mixte avec des tableaux en mémoire.
def compute_policy_metrics_fast(metric_arrays: dict[str, np.ndarray], policy: MixedPolicy, scope: str) -> dict[str, object]:
    strict_mask = (
        (metric_arrays["favorite_prob"] >= policy.strict_probability_threshold)
        & (metric_arrays["margin"] >= policy.strict_margin_threshold)
        & (metric_arrays["strict_prediction"] != "DRAW")
    )
    double_mask = (
        (metric_arrays["top2_sum"] >= policy.double_chance_top2_threshold)
        & (metric_arrays["entropy"] <= policy.max_entropy_threshold)
        & (metric_arrays["available_triplets"] >= policy.min_available_triplets)
        & (metric_arrays["agreement"] >= policy.min_agreement_threshold)
        & (~strict_mask)
    )
    selected_mask = strict_mask | double_mask

    total_rows = len(selected_mask)
    selected_rows = int(selected_mask.sum())
    strict_rows = int(strict_mask.sum())
    double_rows = int(double_mask.sum())
    strict_correct_rows = int(metric_arrays["strict_correct"][strict_mask].sum()) if strict_rows else 0
    double_correct_rows = int(metric_arrays["double_correct"][double_mask].sum()) if double_rows else 0
    mixed_correct_rows = strict_correct_rows + double_correct_rows
    strict_reference_correct_rows = int(metric_arrays["strict_correct"].sum())
    double_reference_correct_rows = int(metric_arrays["double_correct"].sum())
    double_chance = metric_arrays["double_chance"]
    strict_prediction = metric_arrays["strict_prediction"]

    return {
        "scope": scope,
        "strategy": policy.name,
        "strict_probability_threshold": policy.strict_probability_threshold,
        "strict_margin_threshold": policy.strict_margin_threshold,
        "double_chance_top2_threshold": policy.double_chance_top2_threshold,
        "max_entropy_threshold": policy.max_entropy_threshold,
        "min_available_triplets": policy.min_available_triplets,
        "min_agreement_threshold": policy.min_agreement_threshold,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstained_rows": total_rows - selected_rows,
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "mixed_accuracy": rounded(safe_rate(mixed_correct_rows, selected_rows)),
        "mixed_correct_rows": mixed_correct_rows,
        "strict_1x2_rows": strict_rows,
        "strict_1x2_share": rounded(safe_rate(strict_rows, selected_rows)),
        "strict_1x2_accuracy": rounded(safe_rate(strict_correct_rows, strict_rows)),
        "strict_1x2_correct_rows": strict_correct_rows,
        "double_chance_rows": double_rows,
        "double_chance_share": rounded(safe_rate(double_rows, selected_rows)),
        "double_chance_accuracy": rounded(safe_rate(double_correct_rows, double_rows)),
        "double_chance_correct_rows": double_correct_rows,
        "strict_reference_accuracy_all_rows": rounded(safe_rate(strict_reference_correct_rows, total_rows)),
        "double_chance_reference_accuracy_all_rows": rounded(safe_rate(double_reference_correct_rows, total_rows)),
        "selected_rows_delta_vs_v9": selected_rows - STATIC_V9_SELECTED_ROWS if scope == "test" else 0,
        "selected_rows_delta_vs_v11": selected_rows - STATIC_V11_SELECTED_ROWS if scope == "test" else 0,
        "selected_rows_delta_vs_v13_double_chance": selected_rows - STATIC_V13_DOUBLE_CHANCE_ROWS if scope == "test" else 0,
        "coverage_delta_vs_v9": rounded(safe_rate(selected_rows, total_rows) - STATIC_V9_COVERAGE) if scope == "test" else 0.0,
        "coverage_delta_vs_v11": rounded(safe_rate(selected_rows, total_rows) - STATIC_V11_COVERAGE) if scope == "test" else 0.0,
        "coverage_delta_vs_v13_double_chance": rounded(safe_rate(selected_rows, total_rows) - STATIC_V13_DOUBLE_CHANCE_COVERAGE) if scope == "test" else 0.0,
        "strict_home_win_rows": int(((strict_prediction == "HOME_WIN") & strict_mask).sum()),
        "strict_away_win_rows": int(((strict_prediction == "AWAY_WIN") & strict_mask).sum()),
        "double_1x_rows": int(((double_chance == "1X") & double_mask).sum()),
        "double_x2_rows": int(((double_chance == "X2") & double_mask).sum()),
        "double_12_rows": int(((double_chance == "12") & double_mask).sum()),
        "actual_draw_rows_selected": int(((metric_arrays["target"] == "DRAW") & selected_mask).sum()),
    }


# Évalue toutes les politiques sur validation puis sur test final sans modifier les données.
def evaluate_policies(validation: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, MixedPolicy]]:
    validation_arrays = prepare_metric_arrays(validation)
    test_arrays = prepare_metric_arrays(test)
    rows: list[dict[str, object]] = []
    policies_by_name: dict[str, MixedPolicy] = {}

    for policy in build_policies():
        policies_by_name[policy.name] = policy
        rows.append(compute_policy_metrics_fast(validation_arrays, policy, "validation"))
        rows.append(compute_policy_metrics_fast(test_arrays, policy, "test"))

    results = pd.DataFrame(rows)
    return results, policies_by_name


# Sélectionne la meilleure stratégie qui respecte bien le format mixte attendu.
def select_best_policy(results: pd.DataFrame) -> str:
    validation = results[results["scope"] == "validation"].copy()
    validation["strict_ratio_ok"] = validation["strict_1x2_rows"] >= REVIEW_MIN_STRICT_ROWS
    validation["double_volume_ok"] = validation["double_chance_rows"] >= 500
    validation["coverage_ok"] = validation["coverage"] >= ACCEPT_MIN_COVERAGE
    validation["accuracy_ok"] = validation["mixed_accuracy"] >= ACCEPT_MIN_MIXED_ACCURACY

    eligible = validation[
        validation["strict_ratio_ok"]
        & validation["double_volume_ok"]
        & validation["coverage_ok"]
        & validation["accuracy_ok"]
    ].copy()

    if eligible.empty:
        eligible = validation[
            validation["strict_ratio_ok"]
            & validation["double_volume_ok"]
            & (validation["coverage"] >= REVIEW_MIN_COVERAGE)
        ].copy()

    if eligible.empty:
        eligible = validation.copy()

    eligible = eligible.sort_values(
        by=["mixed_accuracy", "coverage", "strict_1x2_rows", "double_chance_rows"],
        ascending=[False, False, False, False],
    )
    return str(eligible.iloc[0]["strategy"])


# Prépare les colonnes utiles pour exporter les prédictions sélectionnées.
def build_best_predictions(dataframe: pd.DataFrame, policy: MixedPolicy) -> pd.DataFrame:
    predictions = apply_policy(dataframe, policy)
    columns = [
        "__league_code",
        "__season",
        "Date",
        "HomeTeam",
        "AwayTeam",
        TARGET_COLUMN,
        "market_home_prob_avg",
        "market_draw_prob_avg",
        "market_away_prob_avg",
        "market_favorite_prob",
        "market_margin_top1_top2",
        "market_top2_sum",
        "market_entropy",
        "v13_strict_prediction",
        "v13_double_chance",
        "v13_signal_profile",
        "v13_mixed_strategy",
        "v13_mixed_recommendation_status",
        "v13_mixed_recommendation_type",
        "v13_mixed_recommendation_value",
        "v13_mixed_is_correct",
        "v13_mixed_strict_is_correct",
        "v13_mixed_double_chance_is_correct",
    ]
    available_columns = [column for column in columns if column in predictions.columns]
    return predictions[available_columns].copy()


# Agrège les résultats par type de recommandation et marché affiché.
def build_by_type_market(best_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = best_predictions[best_predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS]
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v13_mixed_recommendation_type", "v13_mixed_recommendation_value"], dropna=False)
    for (recommendation_type, recommendation_value), group in grouped:
        rows.append(
            {
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "selected_rows": len(group),
                "accuracy": rounded(group["v13_mixed_is_correct"].mean()),
                "actual_home_win_rows": int((group[TARGET_COLUMN] == "HOME_WIN").sum()),
                "actual_draw_rows": int((group[TARGET_COLUMN] == "DRAW").sum()),
                "actual_away_win_rows": int((group[TARGET_COLUMN] == "AWAY_WIN").sum()),
                "average_market_favorite_prob": rounded(group["market_favorite_prob"].mean()),
                "average_market_top2_sum": rounded(group["market_top2_sum"].mean()),
                "average_market_entropy": rounded(group["market_entropy"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["recommendation_type", "selected_rows"], ascending=[True, False])


# Agrège les performances par ligue et saison afin de détecter les segments fragiles.
def build_by_league_season(best_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = best_predictions[best_predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS]
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["__league_code", "__season"], dropna=False)
    for (league_code, season), group in grouped:
        strict_group = group[group["v13_mixed_recommendation_type"] == STRICT_TYPE]
        double_group = group[group["v13_mixed_recommendation_type"] == DOUBLE_CHANCE_TYPE]
        selected_rows = len(group)
        accuracy = rounded(group["v13_mixed_is_correct"].mean())
        segment_status = "OK"
        if selected_rows < 50:
            segment_status = "LOW_VOLUME"
        elif accuracy < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY:
            segment_status = "BELOW_GATE"

        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "selected_rows": selected_rows,
                "mixed_accuracy": accuracy,
                "strict_1x2_rows": len(strict_group),
                "strict_1x2_accuracy": rounded(strict_group["v13_mixed_is_correct"].mean()) if len(strict_group) else 0.0,
                "double_chance_rows": len(double_group),
                "double_chance_accuracy": rounded(double_group["v13_mixed_is_correct"].mean()) if len(double_group) else 0.0,
                "double_1x_rows": int((double_group["v13_mixed_recommendation_value"] == "1X").sum()),
                "double_x2_rows": int((double_group["v13_mixed_recommendation_value"] == "X2").sum()),
                "double_12_rows": int((double_group["v13_mixed_recommendation_value"] == "12").sum()),
                "segment_status": segment_status,
            }
        )
    return pd.DataFrame(rows).sort_values(["season", "league_code"])


# Agrège les erreurs restantes pour comprendre quand la stratégie mixte échoue.
def build_error_patterns(best_predictions: pd.DataFrame) -> pd.DataFrame:
    selected_errors = best_predictions[
        (best_predictions["v13_mixed_recommendation_status"] == RECOMMEND_STATUS)
        & (~best_predictions["v13_mixed_is_correct"])
    ].copy()

    if selected_errors.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected_errors.groupby(
        [
            "__league_code",
            "__season",
            "v13_mixed_recommendation_type",
            "v13_mixed_recommendation_value",
            TARGET_COLUMN,
            "v13_signal_profile",
        ],
        dropna=False,
    )
    for keys, group in grouped:
        league_code, season, recommendation_type, recommendation_value, actual_result, signal_profile = keys
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "actual_result": actual_result,
                "signal_profile": signal_profile,
                "rows": len(group),
                "average_market_favorite_prob": rounded(group["market_favorite_prob"].mean()),
                "average_market_top2_sum": rounded(group["market_top2_sum"].mean()),
                "average_market_entropy": rounded(group["market_entropy"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("rows", ascending=False)


# Décide si la stratégie mixte mérite une revue forte, une revue simple ou un rejet.
def decide_v13_mixed(test_metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings_list: list[str] = []

    mixed_accuracy = float(test_metrics.get("mixed_accuracy", 0.0))
    double_accuracy = float(test_metrics.get("double_chance_accuracy", 0.0))
    strict_accuracy = float(test_metrics.get("strict_1x2_accuracy", 0.0))
    coverage = float(test_metrics.get("coverage", 0.0))
    selected_rows = int(test_metrics.get("selected_rows", 0))
    strict_rows = int(test_metrics.get("strict_1x2_rows", 0))
    double_rows = int(test_metrics.get("double_chance_rows", 0))

    major_segments_below_gate = by_league_season[
        (by_league_season["selected_rows"] >= 100)
        & (by_league_season["mixed_accuracy"] < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY)
    ]

    if mixed_accuracy < ACCEPT_MIN_MIXED_ACCURACY:
        blockers.append(f"Mixed accuracy inférieure au gate fort : {mixed_accuracy} < {ACCEPT_MIN_MIXED_ACCURACY}.")
    if double_accuracy < ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY:
        blockers.append(
            "Accuracy double chance inférieure au gate fort : "
            f"{double_accuracy} < {ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY}."
        )
    if strict_accuracy < ACCEPT_MIN_STRICT_ACCURACY:
        warnings_list.append(
            "Accuracy 1X2 stricte sous le gate fort, à surveiller : "
            f"{strict_accuracy} < {ACCEPT_MIN_STRICT_ACCURACY}."
        )
    if coverage < ACCEPT_MIN_COVERAGE:
        blockers.append(f"Coverage inférieur au gate fort : {coverage} < {ACCEPT_MIN_COVERAGE}.")
    if selected_rows < ACCEPT_MIN_SELECTED_ROWS:
        blockers.append(f"Nombre de matchs sélectionnés insuffisant : {selected_rows} < {ACCEPT_MIN_SELECTED_ROWS}.")
    if strict_rows < ACCEPT_MIN_STRICT_ROWS:
        blockers.append(f"Nombre de 1X2 stricts insuffisant pour un vrai mix : {strict_rows} < {ACCEPT_MIN_STRICT_ROWS}.")
    if double_rows < ACCEPT_MIN_DOUBLE_ROWS:
        blockers.append(f"Nombre de doubles chances insuffisant : {double_rows} < {ACCEPT_MIN_DOUBLE_ROWS}.")
    if not major_segments_below_gate.empty:
        warnings_list.append(
            "Au moins un segment ligue/saison majeur passe sous le gate 0.75 : "
            f"{len(major_segments_below_gate)} segment(s)."
        )

    if not blockers and major_segments_below_gate.empty:
        return "V13_MIXED_SELECTIVE_STRONG_REVIEW", blockers, warnings_list

    review_ok = (
        mixed_accuracy >= REVIEW_MIN_MIXED_ACCURACY
        and coverage >= REVIEW_MIN_COVERAGE
        and strict_rows >= REVIEW_MIN_STRICT_ROWS
        and double_rows >= REVIEW_MIN_DOUBLE_ROWS
    )
    if review_ok:
        return "V13_MIXED_SELECTIVE_REVIEW", blockers, warnings_list

    return "V13_MIXED_SELECTIVE_REJECTED", blockers, warnings_list


# Écrit la synthèse de la V13.1 mixte dans un fichier texte.
def write_summary(
    output_path: Path,
    metadata: dict[str, object],
    split_metadata: dict[str, object],
    best_test_metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - ML 1X2 V13.1 mixed selective",
        "193 - Synthèse expérience V13.1",
        "",
        "Objectif :",
        "Tester une stratégie mixte : 1X2 strict quand le signal est très fort, double chance 1X / X2 / 12 quand le signal est moyen, et abstention quand le signal est trop faible.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data dans data/ml/raw.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "- Aucune donnée Understat/xG ajoutée au produit.",
        "",
        "Périmètre data :",
        f"- CSV analysés : {metadata.get('csv_files')}",
        f"- Lignes brutes : {metadata.get('raw_rows')}",
        f"- Lignes dataset V13.1 : {metadata.get('dataset_rows')}",
        f"- Ligues : {metadata.get('leagues')}",
        f"- Saisons : {metadata.get('first_season')} -> {metadata.get('last_season')}",
        f"- Triplets détectés : {metadata.get('detected_triplets')}",
        f"- Triplets utilisés : {metadata.get('usable_triplets')}",
        f"- Exemples triplets utilisés : {metadata.get('usable_triplet_keys')}",
        "",
        "Splits temporels :",
        f"- Mode : {split_metadata.get('split_mode')}",
        f"- Train rows référence uniquement : {split_metadata.get('train_rows_reference_only')}",
        f"- Validation rows : {split_metadata.get('validation_rows')}",
        f"- Test rows : {split_metadata.get('test_rows')}",
        f"- Validation seasons : {split_metadata.get('validation_seasons')}",
        f"- Test seasons : {split_metadata.get('test_seasons')}",
        "",
        "Meilleure stratégie V13.1 sélectionnée sur validation :",
        f"- Strategy : {best_test_metrics.get('strategy')}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Mixed accuracy : {best_test_metrics.get('mixed_accuracy')}",
        f"- Coverage : {best_test_metrics.get('coverage')}",
        f"- Abstention rate : {best_test_metrics.get('abstention_rate')}",
        f"- Selected rows : {best_test_metrics.get('selected_rows')}",
        f"- Strict 1X2 rows : {best_test_metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 share : {best_test_metrics.get('strict_1x2_share')}",
        f"- Strict 1X2 accuracy : {best_test_metrics.get('strict_1x2_accuracy')}",
        f"- Double chance rows : {best_test_metrics.get('double_chance_rows')}",
        f"- Double chance share : {best_test_metrics.get('double_chance_share')}",
        f"- Double chance accuracy : {best_test_metrics.get('double_chance_accuracy')}",
        f"- Strict reference accuracy all rows : {best_test_metrics.get('strict_reference_accuracy_all_rows')}",
        f"- Double chance reference accuracy all rows : {best_test_metrics.get('double_chance_reference_accuracy_all_rows')}",
        f"- Selected rows delta vs V9 : {best_test_metrics.get('selected_rows_delta_vs_v9')}",
        f"- Selected rows delta vs V11 : {best_test_metrics.get('selected_rows_delta_vs_v11')}",
        f"- Selected rows delta vs V13 double chance pure : {best_test_metrics.get('selected_rows_delta_vs_v13_double_chance')}",
        f"- Coverage delta vs V9 : {best_test_metrics.get('coverage_delta_vs_v9')}",
        f"- Coverage delta vs V11 : {best_test_metrics.get('coverage_delta_vs_v11')}",
        f"- Coverage delta vs V13 double chance pure : {best_test_metrics.get('coverage_delta_vs_v13_double_chance')}",
        f"- Répartition stricte HOME/AWAY : {best_test_metrics.get('strict_home_win_rows')} / {best_test_metrics.get('strict_away_win_rows')}",
        f"- Répartition double chance 1X / X2 / 12 : {best_test_metrics.get('double_1x_rows')} / {best_test_metrics.get('double_x2_rows')} / {best_test_metrics.get('double_12_rows')}",
        "",
        "Références connues :",
        f"- V9 coverage : {STATIC_V9_COVERAGE}",
        f"- V9 selected rows : {STATIC_V9_SELECTED_ROWS}",
        f"- V11 coverage : {STATIC_V11_COVERAGE}",
        f"- V11 selected rows : {STATIC_V11_SELECTED_ROWS}",
        f"- V13 double chance pure accuracy : {STATIC_V13_DOUBLE_CHANCE_ACCURACY}",
        f"- V13 double chance pure coverage : {STATIC_V13_DOUBLE_CHANCE_COVERAGE}",
        f"- V13 double chance pure selected rows : {STATIC_V13_DOUBLE_CHANCE_ROWS}",
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
        "Ne pas intégrer V13.1 au produit à ce stade. V13.1 reste une expérimentation mixte prudente ; le scoring explicable V1 reste le socle officiel.",
        "",
        "Statut de suivi :",
        "- V13 double chance pure : réalisée, mais elle ne correspondait pas au format produit attendu.",
        "- V13.1 mixed selective : réalisée si les fichiers 193 à 198 sont générés.",
        "- Prochaine étape seulement après validation utilisateur : analyse de stabilité dédiée de la stratégie mixte.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Écrit la décision opérationnelle V13.1 dans un fichier court.
def write_decision(
    output_path: Path,
    best_test_metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V13.1 mixed selective",
        "198 - Décision expérience V13.1",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {best_test_metrics.get('strategy')}",
        f"- Mixed accuracy : {best_test_metrics.get('mixed_accuracy')}",
        f"- Coverage : {best_test_metrics.get('coverage')}",
        f"- Abstention rate : {best_test_metrics.get('abstention_rate')}",
        f"- Selected rows : {best_test_metrics.get('selected_rows')}",
        f"- Strict 1X2 rows : {best_test_metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 accuracy : {best_test_metrics.get('strict_1x2_accuracy')}",
        f"- Double chance rows : {best_test_metrics.get('double_chance_rows')}",
        f"- Double chance accuracy : {best_test_metrics.get('double_chance_accuracy')}",
        f"- Selected rows delta vs V11 : {best_test_metrics.get('selected_rows_delta_vs_v11')}",
        f"- Coverage delta vs V11 : {best_test_metrics.get('coverage_delta_vs_v11')}",
        "",
        "Gates appliqués :",
        f"- Mixed accuracy >= {ACCEPT_MIN_MIXED_ACCURACY}",
        f"- Double chance accuracy >= {ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY}",
        f"- Coverage >= {ACCEPT_MIN_COVERAGE}",
        f"- Selected rows >= {ACCEPT_MIN_SELECTED_ROWS}",
        f"- Strict 1X2 rows >= {ACCEPT_MIN_STRICT_ROWS}",
        f"- Double chance rows >= {ACCEPT_MIN_DOUBLE_ROWS}",
        f"- Segment majeur >= {ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY}",
        "- Pas de sauvegarde de modèle officiel.",
        "- Pas d'intégration API/frontend/scoring V1.",
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
        "- V13.1 peut être conservée comme expérimentation mixed selective si le statut est REVIEW ou STRONG_REVIEW.",
        "- V13.1 ne doit pas être intégrée au produit sans analyse de stabilité dédiée et arbitrage explicite.",
        "- V13.1 ne remplace pas le scoring explicable V1.",
        "",
        "Statut de suivi à mettre à jour :",
        "- V13 double chance pure : réalisée.",
        "- V13.1 mixed selective : réalisée.",
        "- Fichiers concernés : 193, 194, 195, 196, 197, 198.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Orchestre l'expérience V13.1 sans modifier le produit RubyBets.
def main() -> None:
    base = load_v13_base_module()
    project_root = base.find_project_root()
    evidence_dir = base.get_evidence_dir(project_root)

    print("Chargement et enrichissement des CSV bruts pour V13.1 mixed selective...")
    dataset, _, metadata = base.build_v13_dataset(project_root)

    print("Préparation des splits temporels V13.1...")
    _, validation, test, split_metadata = base.prepare_temporal_splits(dataset)

    print("Évaluation des stratégies V13.1 1X2 strict + double chance + abstention...")
    results, policies_by_name = evaluate_policies(validation, test)
    best_strategy = select_best_policy(results)
    best_policy = policies_by_name[best_strategy]
    best_predictions = build_best_predictions(test, best_policy)

    best_test_metrics = results[(results["scope"] == "test") & (results["strategy"] == best_strategy)].iloc[0].to_dict()
    by_type_market = build_by_type_market(best_predictions)
    by_league_season = build_by_league_season(best_predictions)
    error_patterns = build_error_patterns(best_predictions)
    status, blockers, warnings_list = decide_v13_mixed(best_test_metrics, by_league_season)

    results.to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8")
    by_type_market.to_csv(evidence_dir / OUTPUT_BY_TYPE_MARKET, index=False, encoding="utf-8")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8")
    error_patterns.to_csv(evidence_dir / OUTPUT_ERROR_PATTERNS, index=False, encoding="utf-8")
    write_summary(evidence_dir / OUTPUT_SUMMARY, metadata, split_metadata, best_test_metrics, status, blockers, warnings_list)
    write_decision(evidence_dir / OUTPUT_DECISION, best_test_metrics, status, blockers, warnings_list)

    print("OK - Expérience V13.1 mixed selective terminée.")
    print(f"Status: {status}")
    print(f"Selected validation strategy: {best_strategy}")
    print(f"Test mixed accuracy: {best_test_metrics.get('mixed_accuracy')}")
    print(f"Test coverage: {best_test_metrics.get('coverage')}")
    print(f"Test abstention rate: {best_test_metrics.get('abstention_rate')}")
    print(f"Selected rows: {best_test_metrics.get('selected_rows')}")
    print(f"Strict 1X2 rows: {best_test_metrics.get('strict_1x2_rows')}")
    print(f"Strict 1X2 accuracy: {best_test_metrics.get('strict_1x2_accuracy')}")
    print(f"Double chance rows: {best_test_metrics.get('double_chance_rows')}")
    print(f"Double chance accuracy: {best_test_metrics.get('double_chance_accuracy')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By type/market CSV saved: {evidence_dir / OUTPUT_BY_TYPE_MARKET}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# train_1x2_v13_mixed_selective.py
#   -> réutilise backend/scripts/ml/train_1x2_v13_double_chance_selective.py pour charger les CSV et reconstruire les signaux market
#   -> lit data/ml/raw/*.csv en lecture seule
#   -> écrit reports/evidence/ml_training/193 à 198
#   -> ne communique pas avec PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou models/
