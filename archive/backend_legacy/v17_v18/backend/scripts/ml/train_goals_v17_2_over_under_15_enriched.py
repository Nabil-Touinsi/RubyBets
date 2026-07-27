# Rôle du fichier : tester V17.2 Over/Under 1.5 avec les features enrichies V17.1, en mémoire uniquement, sans intégration produit.

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from build_multimarket_v17_1_enriched_features import (
    FEATURE_COLUMNS,
    build_enriched_dataset,
    build_raw_matches,
    find_project_root,
    get_evidence_dir,
    list_raw_csv_files,
)


TARGET_COLUMN = "target_over_under_15"
OVER_LABEL = "OVER_1_5"
UNDER_LABEL = "UNDER_1_5"
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

OUTPUT_SUMMARY = "238_goals_v17_2_over_under_15_enriched_summary.txt"
OUTPUT_RESULTS = "239_goals_v17_2_over_under_15_enriched_results.csv"
OUTPUT_BY_LEAGUE_SEASON = "240_goals_v17_2_over_under_15_by_league_season.csv"
OUTPUT_BY_SIGNAL = "241_goals_v17_2_over_under_15_by_signal.csv"
OUTPUT_ERROR_PATTERNS = "242_goals_v17_2_over_under_15_error_patterns.csv"
OUTPUT_DECISION = "243_goals_v17_2_over_under_15_decision.txt"

VALIDATION_SEASON = "2021_2022"
TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]
TRAIN_MAX_SEASON_START = 2020

V15_REFERENCE_OVER_ACCURACY = 0.8049
V15_REFERENCE_OVER_ROWS = 2753
V15_REFERENCE_UNDER_ACCURACY = 0.3077
V15_REFERENCE_UNDER_ROWS = 65

MIN_VALIDATION_COVERAGE_FOR_SELECTION = 0.58
MIN_VALIDATION_SELECTED_ROWS = 1000
MIN_REVIEW_ACCURACY = 0.80
MIN_REVIEW_COVERAGE = 0.53
STRONG_OVER_ACCURACY_GATE = 0.83
STRONG_OVER_COVERAGE_GATE = 0.55
UNDER_MIN_ROWS_GATE = 100
UNDER_MIN_ACCURACY_GATE = 0.58
MIN_MAJOR_SEGMENT_ROWS = 80
MIN_MAJOR_SEGMENT_ACCURACY = 0.75

LOGISTIC_STANDARD_THRESHOLDS = [0.735, 0.740, 0.745, 0.750, 0.755, 0.760, 0.775, 0.800]
LOGISTIC_BALANCED_THRESHOLDS = [0.550, 0.575, 0.600, 0.625]
PROXY_OVER_THRESHOLDS = [0.735, 0.750, 0.760, 0.775, 0.800]
COMBINED_RATE_THRESHOLDS = [0.700, 0.750, 0.800, 0.850]
EXPECTED_TOTAL_GOALS_THRESHOLDS = [2.60, 2.70, 2.80, 2.90]
UNDER_PROBE_THRESHOLDS = [0.350, 0.400, 0.425, 0.450]

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class StrategySpec:
    name: str
    family: str
    score_column: str
    over_threshold: float
    under_threshold: float | None
    min_history_count: int
    notes: str


# Arrondit une valeur numérique pour stabiliser les exports.
def rounded(value: object, digits: int = 4) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return round(result, digits)
    except (TypeError, ValueError):
        return 0.0


# Calcule un ratio sans risque de division par zéro.
def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# Convertit une valeur de seuil en suffixe court pour nommer les stratégies.
def threshold_suffix(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.3f}".replace(".", "")


# Construit le dataset enrichi V17.2 depuis les CSV bruts, via la logique V17.1.
def build_v17_2_dataset(project_root: Path) -> tuple[pd.DataFrame, int]:
    files = list_raw_csv_files(project_root)
    raw_matches = build_raw_matches(files)
    dataset = build_enriched_dataset(raw_matches)
    return dataset, len(files)


# Sépare le dataset selon un split chronologique stable : train, validation puis test récent.
def split_dataset(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = dataset[pd.to_numeric(dataset["season_start_year"], errors="coerce") <= TRAIN_MAX_SEASON_START].copy()
    validation = dataset[dataset["season"].astype(str) == VALIDATION_SEASON].copy()
    test = dataset[dataset["season"].astype(str).isin(TEST_SEASONS)].copy()

    if train.empty or validation.empty or test.empty:
        raise RuntimeError("Split V17.2 impossible : train, validation ou test vide.")
    return train, validation, test


# Prépare les colonnes features numériques et catégorielles utilisées par les modèles V17.2.
def get_model_columns() -> tuple[list[str], list[str]]:
    numeric_columns = list(FEATURE_COLUMNS)
    categorical_columns = ["league_code"]
    return numeric_columns, categorical_columns


# Transforme les labels OVER/UNDER 1.5 en cible binaire pour entraîner les modèles.
def build_binary_target(dataframe: pd.DataFrame) -> pd.Series:
    return (dataframe[TARGET_COLUMN].astype(str) == OVER_LABEL).astype(int)


# Entraîne le modèle logistique standard utilisé comme score principal V17.2.
def train_logistic_model(train: pd.DataFrame, balanced: bool = False) -> Pipeline:
    numeric_columns, categorical_columns = get_model_columns()
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_columns,
            ),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_columns),
        ]
    )

    class_weight = "balanced" if balanced else None
    classifier = LogisticRegression(
        max_iter=1000,
        C=0.5,
        solver="liblinear",
        class_weight=class_weight,
    )
    model = Pipeline(steps=[("preprocessor", preprocessor), ("classifier", classifier)])
    model.fit(train[numeric_columns + categorical_columns], build_binary_target(train))
    return model


# Ajoute les scores probabilistes ou heuristiques nécessaires aux stratégies V17.2.
def attach_scores(train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    numeric_columns, categorical_columns = get_model_columns()
    standard_model = train_logistic_model(train, balanced=False)
    balanced_model = train_logistic_model(train, balanced=True)

    outputs: list[pd.DataFrame] = []
    for frame in (train, validation, test):
        output = frame.copy()
        output["score_logistic_standard_over_1_5"] = standard_model.predict_proba(
            output[numeric_columns + categorical_columns]
        )[:, 1]
        output["score_logistic_balanced_over_1_5"] = balanced_model.predict_proba(
            output[numeric_columns + categorical_columns]
        )[:, 1]
        output["score_proxy_over_1_5"] = pd.to_numeric(output["prob_over_1_5_proxy"], errors="coerce")
        output["score_combined_rate_over_1_5"] = pd.to_numeric(
            output["combined_over_1_5_rate_last_10"], errors="coerce"
        )
        output["score_expected_total_goals"] = pd.to_numeric(output["expected_total_goals_proxy"], errors="coerce")
        outputs.append(output)

    return outputs[0], outputs[1], outputs[2]


# Crée la liste des stratégies V17.2 à comparer sur validation et test.
def build_strategies() -> list[StrategySpec]:
    strategies: list[StrategySpec] = []

    for threshold in LOGISTIC_STANDARD_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_2_logistic_enriched_over_t{threshold_suffix(threshold)}_under_none",
                family="logistic_standard_over_only",
                score_column="score_logistic_standard_over_1_5",
                over_threshold=threshold,
                under_threshold=None,
                min_history_count=8,
                notes="Signal OVER_1_5 enrichi, sans recommandation UNDER.",
            )
        )

    for threshold in LOGISTIC_BALANCED_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_2_logistic_balanced_over_t{threshold_suffix(threshold)}_under_none",
                family="logistic_balanced_over_only",
                score_column="score_logistic_balanced_over_1_5",
                over_threshold=threshold,
                under_threshold=None,
                min_history_count=8,
                notes="Variante équilibrée pour surveiller le risque UNDER, non prioritaire.",
            )
        )

    for over_threshold in [0.575, 0.600, 0.625]:
        for under_threshold in UNDER_PROBE_THRESHOLDS:
            strategies.append(
                StrategySpec(
                    name=(
                        "v17_2_logistic_balanced_mixed"
                        f"_over_t{threshold_suffix(over_threshold)}"
                        f"_under_t{threshold_suffix(under_threshold)}"
                    ),
                    family="logistic_balanced_mixed_under_probe",
                    score_column="score_logistic_balanced_over_1_5",
                    over_threshold=over_threshold,
                    under_threshold=under_threshold,
                    min_history_count=8,
                    notes="Variante exploratoire : teste UNDER_1_5 mais ne doit passer que si le gate UNDER est validé.",
                )
            )

    for threshold in PROXY_OVER_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_2_proxy_poisson_over_t{threshold_suffix(threshold)}_under_none",
                family="proxy_poisson_over_only",
                score_column="score_proxy_over_1_5",
                over_threshold=threshold,
                under_threshold=None,
                min_history_count=8,
                notes="Proxy Poisson sur expected_total_goals, OVER seulement.",
            )
        )

    for threshold in COMBINED_RATE_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_2_combined_rate_over_t{threshold_suffix(threshold)}_under_none",
                family="combined_rate_over_only",
                score_column="score_combined_rate_over_1_5",
                over_threshold=threshold,
                under_threshold=None,
                min_history_count=8,
                notes="Règle enrichie sur le taux rolling combiné OVER_1_5.",
            )
        )

    for threshold in EXPECTED_TOTAL_GOALS_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_2_expected_total_goals_over_t{threshold_suffix(threshold)}_under_none",
                family="expected_goals_over_only",
                score_column="score_expected_total_goals",
                over_threshold=threshold,
                under_threshold=None,
                min_history_count=8,
                notes="Règle enrichie sur le proxy expected_total_goals.",
            )
        )

    return strategies


# Applique une stratégie V17.2 sur un DataFrame donné.
def apply_strategy(dataframe: pd.DataFrame, strategy: StrategySpec) -> pd.DataFrame:
    output = dataframe.copy()
    score = pd.to_numeric(output[strategy.score_column], errors="coerce")
    min_history = pd.to_numeric(output["min_history_count_last_10"], errors="coerce").fillna(0)
    history_mask = min_history >= strategy.min_history_count

    over_mask = history_mask & score.notna() & (score >= strategy.over_threshold)
    if strategy.under_threshold is None:
        under_mask = pd.Series(False, index=output.index)
    else:
        under_mask = history_mask & score.notna() & (score <= strategy.under_threshold)

    recommendation = np.where(over_mask, OVER_LABEL, np.where(under_mask, UNDER_LABEL, ABSTAIN_STATUS))
    selected_mask = over_mask | under_mask

    output["v17_2_strategy"] = strategy.name
    output["v17_2_family"] = strategy.family
    output["v17_2_score"] = score
    output["v17_2_recommendation_status"] = np.where(selected_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v17_2_recommendation"] = recommendation
    output["v17_2_is_correct"] = (
        (output[TARGET_COLUMN].astype(str) == output["v17_2_recommendation"].astype(str)) & selected_mask
    )
    output["v17_2_signal_strength"] = pd.cut(
        output["v17_2_score"],
        bins=[-math.inf, 0.700, 0.745, 0.775, 0.800, math.inf],
        labels=["LOW_OR_UNDER_PROBE", "MEDIUM_OVER_SIGNAL", "STRONG_OVER_SIGNAL", "VERY_STRONG_OVER_SIGNAL", "ELITE_OVER_SIGNAL"],
        include_lowest=True,
    ).astype(str)
    return output


# Calcule les métriques principales d'une stratégie V17.2.
def evaluate_strategy(dataframe: pd.DataFrame, strategy: StrategySpec, split_name: str) -> dict[str, object]:
    predictions = apply_strategy(dataframe, strategy)
    selected = predictions[predictions["v17_2_recommendation_status"] == RECOMMEND_STATUS]
    over_selected = selected[selected["v17_2_recommendation"] == OVER_LABEL]
    under_selected = selected[selected["v17_2_recommendation"] == UNDER_LABEL]
    selected_rows = len(selected)
    total_rows = len(predictions)

    return {
        "strategy": strategy.name,
        "family": strategy.family,
        "split": split_name,
        "score_column": strategy.score_column,
        "over_threshold": strategy.over_threshold,
        "under_threshold": "none" if strategy.under_threshold is None else strategy.under_threshold,
        "min_history_count": strategy.min_history_count,
        "accuracy": rounded(safe_rate(int(selected["v17_2_is_correct"].sum()), selected_rows)),
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "selected_rows": selected_rows,
        "total_rows": total_rows,
        "over_rows": len(over_selected),
        "under_rows": len(under_selected),
        "over_accuracy": rounded(safe_rate(int(over_selected["v17_2_is_correct"].sum()), len(over_selected))),
        "under_accuracy": rounded(safe_rate(int(under_selected["v17_2_is_correct"].sum()), len(under_selected))),
        "avg_selected_score": rounded(selected["v17_2_score"].mean()) if selected_rows else 0.0,
        "notes": strategy.notes,
    }


# Sélectionne la meilleure stratégie sur validation sans utiliser les résultats de test.
def select_best_strategy(validation_results: pd.DataFrame, strategies: list[StrategySpec]) -> StrategySpec:
    candidates = validation_results[
        (validation_results["split"] == "validation")
        & (validation_results["coverage"] >= MIN_VALIDATION_COVERAGE_FOR_SELECTION)
        & (validation_results["selected_rows"] >= MIN_VALIDATION_SELECTED_ROWS)
        & (
            (validation_results["under_rows"] == 0)
            | (
                (validation_results["under_rows"] >= 30)
                & (validation_results["under_accuracy"] >= UNDER_MIN_ACCURACY_GATE)
            )
        )
    ].copy()

    if candidates.empty:
        candidates = validation_results[
            (validation_results["split"] == "validation")
            & (validation_results["coverage"] >= 0.45)
            & (validation_results["selected_rows"] >= 700)
        ].copy()
    if candidates.empty:
        candidates = validation_results[validation_results["split"] == "validation"].copy()

    candidates["strong_over_gate_on_validation"] = (
        (candidates["over_accuracy"] >= STRONG_OVER_ACCURACY_GATE)
        & (candidates["coverage"] >= STRONG_OVER_COVERAGE_GATE)
    )
    candidates = candidates.sort_values(
        by=["strong_over_gate_on_validation", "accuracy", "coverage", "selected_rows"],
        ascending=[False, False, False, False],
    )
    selected_name = str(candidates.iloc[0]["strategy"])

    for strategy in strategies:
        if strategy.name == selected_name:
            return strategy
    raise RuntimeError("Impossible de retrouver la stratégie V17.2 sélectionnée.")


# Construit le tableau de stabilité par ligue/saison pour la stratégie retenue.
def build_by_league_season(final_predictions: pd.DataFrame) -> pd.DataFrame:
    total_groups = final_predictions.groupby(["league_code", "season"], dropna=False).size().reset_index(name="total_rows")
    selected = final_predictions[final_predictions["v17_2_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["league_code", "season"], dropna=False)
    for (league_code, season), group in grouped:
        total_rows = int(
            total_groups[
                (total_groups["league_code"] == league_code) & (total_groups["season"] == season)
            ]["total_rows"].iloc[0]
        )
        over_group = group[group["v17_2_recommendation"] == OVER_LABEL]
        under_group = group[group["v17_2_recommendation"] == UNDER_LABEL]
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "total_rows": total_rows,
                "selected_rows": len(group),
                "coverage": rounded(safe_rate(len(group), total_rows)),
                "accuracy": rounded(safe_rate(int(group["v17_2_is_correct"].sum()), len(group))),
                "over_rows": len(over_group),
                "under_rows": len(under_group),
                "over_accuracy": rounded(safe_rate(int(over_group["v17_2_is_correct"].sum()), len(over_group))),
                "under_accuracy": rounded(safe_rate(int(under_group["v17_2_is_correct"].sum()), len(under_group))),
                "avg_score": rounded(group["v17_2_score"].mean()),
                "avg_expected_total_goals_proxy": rounded(group["expected_total_goals_proxy"].mean()),
                "avg_combined_over_1_5_rate": rounded(group["combined_over_1_5_rate_last_10"].mean()),
                "is_major_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS,
                "is_major_fragile_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS
                and safe_rate(int(group["v17_2_is_correct"].sum()), len(group)) < MIN_MAJOR_SEGMENT_ACCURACY,
            }
        )

    return pd.DataFrame(rows).sort_values(["accuracy", "selected_rows"], ascending=[True, False])


# Construit le tableau de performance par signal recommandé et force de score.
def build_by_signal(final_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = final_predictions[final_predictions["v17_2_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v17_2_recommendation", "v17_2_signal_strength"], dropna=False)
    for (recommendation, signal_strength), group in grouped:
        rows.append(
            {
                "recommendation": recommendation,
                "signal_strength": signal_strength,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v17_2_is_correct"].sum()), len(group))),
                "avg_score": rounded(group["v17_2_score"].mean()),
                "avg_expected_total_goals_proxy": rounded(group["expected_total_goals_proxy"].mean()),
                "avg_combined_over_1_5_rate": rounded(group["combined_over_1_5_rate_last_10"].mean()),
                "avg_prob_over_1_5_proxy": rounded(group["prob_over_1_5_proxy"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values(["recommendation", "signal_strength"])


# Construit un extrait des erreurs restantes pour analyse V17.2.
def build_error_patterns(final_predictions: pd.DataFrame) -> pd.DataFrame:
    errors = final_predictions[
        (final_predictions["v17_2_recommendation_status"] == RECOMMEND_STATUS)
        & (~final_predictions["v17_2_is_correct"])
    ].copy()
    if errors.empty:
        return pd.DataFrame()

    keep_columns = [
        "league_code",
        "season",
        "match_date",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "total_goals",
        TARGET_COLUMN,
        "v17_2_recommendation",
        "v17_2_score",
        "prob_over_1_5_proxy",
        "expected_total_goals_proxy",
        "combined_over_1_5_rate_last_10",
        "combined_over_2_5_rate_last_10",
        "combined_btts_rate_last_10",
        "min_history_count_last_10",
    ]
    return errors[keep_columns].sort_values(["season", "league_code", "match_date"]).head(500)


# Détermine le statut V17.2 selon les métriques et les gates prévus.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    coverage = float(metrics.get("coverage", 0.0))
    over_accuracy = float(metrics.get("over_accuracy", 0.0))
    over_rows = int(metrics.get("over_rows", 0))
    under_accuracy = float(metrics.get("under_accuracy", 0.0))
    under_rows = int(metrics.get("under_rows", 0))

    major_fragile_segments = 0
    if not by_league_season.empty and "is_major_fragile_segment" in by_league_season.columns:
        major_fragile_segments = int(by_league_season["is_major_fragile_segment"].sum())

    blocking_reasons: list[str] = []
    warnings_list: list[str] = []

    if major_fragile_segments > 0:
        warnings_list.append(f"{major_fragile_segments} segment(s) ligue/saison majeur(s) sous {MIN_MAJOR_SEGMENT_ACCURACY}.")
    if under_rows == 0:
        warnings_list.append("Aucun signal UNDER_1_5 retenu : V17.2 améliore surtout OVER_1_5.")
    elif under_rows < UNDER_MIN_ROWS_GATE or under_accuracy < UNDER_MIN_ACCURACY_GATE:
        warnings_list.append("UNDER_1_5 reste sous gate : ne pas l'intégrer au sélecteur final.")

    over_strong = over_accuracy >= STRONG_OVER_ACCURACY_GATE and coverage >= STRONG_OVER_COVERAGE_GATE
    under_accepted = under_rows == 0 or (under_rows >= UNDER_MIN_ROWS_GATE and under_accuracy >= UNDER_MIN_ACCURACY_GATE)

    if over_strong and under_accepted and major_fragile_segments == 0:
        if under_rows == 0:
            return "V17_2_OVER_15_ENRICHED_STRONG_REVIEW_UNDER_EXCLUDED", blocking_reasons, warnings_list
        return "V17_2_OVER_UNDER_15_ENRICHED_STRONG_REVIEW", blocking_reasons, warnings_list

    if accuracy >= MIN_REVIEW_ACCURACY and coverage >= MIN_REVIEW_COVERAGE and over_rows >= V15_REFERENCE_OVER_ROWS:
        return "V17_2_OVER_15_ENRICHED_REVIEW_UNDER_REJECTED", blocking_reasons, warnings_list

    if accuracy >= 0.78 and coverage >= 0.45:
        warnings_list.append("Le signal est utile mais ne passe pas les gates de review renforcée.")
        return "V17_2_OVER_15_ENRICHED_EXPERIMENTAL_ONLY", blocking_reasons, warnings_list

    blocking_reasons.append("Accuracy ou couverture insuffisante pour améliorer V17.0.")
    return "V17_2_OVER_UNDER_15_ENRICHED_REJECTED", blocking_reasons, warnings_list


# Écrit la synthèse détaillée V17.2.
def write_summary(
    evidence_dir: Path,
    dataset: pd.DataFrame,
    csv_count: int,
    best_strategy: StrategySpec,
    validation_metrics: dict[str, object],
    test_metrics: dict[str, object],
    by_league_season: pd.DataFrame,
    status: str,
    blocking_reasons: list[str],
    warnings_list: list[str],
) -> None:
    seasons = sorted(dataset["season"].astype(str).unique())
    leagues = sorted(dataset["league_code"].astype(str).unique())
    over_delta_accuracy = float(test_metrics.get("over_accuracy", 0.0)) - V15_REFERENCE_OVER_ACCURACY
    over_delta_rows = int(test_metrics.get("over_rows", 0)) - V15_REFERENCE_OVER_ROWS
    under_delta_accuracy = float(test_metrics.get("under_accuracy", 0.0)) - V15_REFERENCE_UNDER_ACCURACY
    under_delta_rows = int(test_metrics.get("under_rows", 0)) - V15_REFERENCE_UNDER_ROWS

    lowest_segment = "Aucun"
    if not by_league_season.empty:
        first = by_league_season.iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"

    lines = [
        "RubyBets - ML Goals V17.2 Over/Under 1.5 enriched selective",
        "238 - Synthèse expérience V17.2",
        "",
        "Objectif :",
        "Retester Over/Under 1.5 avec les features enrichies V17.1 goals/BTTS, afin de renforcer OVER_1_5 et de vérifier si UNDER_1_5 devient exploitable.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data dans data/ml/raw.",
        "- Construction des features enrichies en mémoire via la logique V17.1.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Périmètre data :",
        f"- CSV analysés : {csv_count}",
        f"- Lignes dataset enrichi : {len(dataset)}",
        f"- Ligues : {', '.join(leagues)}",
        f"- Saisons : {min(seasons)} -> {max(seasons)}",
        f"- Validation season : {VALIDATION_SEASON}",
        f"- Test seasons : {', '.join(TEST_SEASONS)}",
        "",
        "Distribution des labels :",
        f"- OVER_1_5 rows : {int((dataset[TARGET_COLUMN] == OVER_LABEL).sum())}",
        f"- UNDER_1_5 rows : {int((dataset[TARGET_COLUMN] == UNDER_LABEL).sum())}",
        "",
        "Meilleure stratégie V17.2 sélectionnée sur validation :",
        f"- Strategy : {best_strategy.name}",
        f"- Family : {best_strategy.family}",
        f"- Validation accuracy : {validation_metrics.get('accuracy')}",
        f"- Validation coverage : {validation_metrics.get('coverage')}",
        f"- Validation selected rows : {validation_metrics.get('selected_rows')}",
        f"- Validation OVER_1_5 accuracy : {validation_metrics.get('over_accuracy')}",
        f"- Validation UNDER_1_5 accuracy : {validation_metrics.get('under_accuracy')}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Accuracy : {test_metrics.get('accuracy')}",
        f"- Coverage : {test_metrics.get('coverage')}",
        f"- Abstention rate : {test_metrics.get('abstention_rate')}",
        f"- Selected rows : {test_metrics.get('selected_rows')}",
        f"- OVER_1_5 rows : {test_metrics.get('over_rows')}",
        f"- UNDER_1_5 rows : {test_metrics.get('under_rows')}",
        f"- OVER_1_5 accuracy : {test_metrics.get('over_accuracy')}",
        f"- UNDER_1_5 accuracy : {test_metrics.get('under_accuracy')}",
        "",
        "Comparaison avec V15 :",
        f"- V15 OVER_1_5 accuracy : {V15_REFERENCE_OVER_ACCURACY}",
        f"- V17.2 OVER_1_5 accuracy delta : {rounded(over_delta_accuracy)}",
        f"- V15 OVER_1_5 rows : {V15_REFERENCE_OVER_ROWS}",
        f"- V17.2 OVER_1_5 rows delta : {over_delta_rows}",
        f"- V15 UNDER_1_5 accuracy : {V15_REFERENCE_UNDER_ACCURACY}",
        f"- V17.2 UNDER_1_5 accuracy delta : {rounded(under_delta_accuracy)}",
        f"- V15 UNDER_1_5 rows : {V15_REFERENCE_UNDER_ROWS}",
        f"- V17.2 UNDER_1_5 rows delta : {under_delta_rows}",
        "",
        "Stabilité rapide :",
        f"- Segments ligue/saison analysés : {len(by_league_season)}",
        f"- Segment le plus bas : {lowest_segment}",
        "",
        "Raisons bloquantes :",
        f"- {'Aucune.' if not blocking_reasons else '; '.join(blocking_reasons)}",
        "",
        "Points de vigilance :",
        f"- {'Aucun.' if not warnings_list else '; '.join(warnings_list)}",
        "",
        "Décision produit :",
        "Ne pas intégrer V17.2 au produit. Si elle est conservée, elle sert uniquement à améliorer le signal expérimental OVER_1_5 dans le futur sélecteur V17.5.",
        "Le scoring explicable V1 reste le socle officiel de RubyBets.",
    ]
    (evidence_dir / OUTPUT_SUMMARY).write_text("\n".join(lines), encoding="utf-8")


# Écrit la décision opérationnelle V17.2.
def write_decision(
    evidence_dir: Path,
    best_strategy: StrategySpec,
    test_metrics: dict[str, object],
    status: str,
    blocking_reasons: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V17.2 Over/Under 1.5 enrichi",
        "243 - Décision expérience V17.2",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {best_strategy.name}",
        f"- Family : {best_strategy.family}",
        f"- Accuracy : {test_metrics.get('accuracy')}",
        f"- Coverage : {test_metrics.get('coverage')}",
        f"- Abstention rate : {test_metrics.get('abstention_rate')}",
        f"- Selected rows : {test_metrics.get('selected_rows')}",
        f"- OVER_1_5 rows : {test_metrics.get('over_rows')}",
        f"- UNDER_1_5 rows : {test_metrics.get('under_rows')}",
        f"- OVER_1_5 accuracy : {test_metrics.get('over_accuracy')}",
        f"- UNDER_1_5 accuracy : {test_metrics.get('under_accuracy')}",
        "",
        "Gates V17.2 :",
        f"- OVER_1_5 accuracy cible forte >= {STRONG_OVER_ACCURACY_GATE}",
        f"- Coverage cible forte >= {STRONG_OVER_COVERAGE_GATE}",
        f"- UNDER_1_5 accepté seulement si rows >= {UNDER_MIN_ROWS_GATE} et accuracy >= {UNDER_MIN_ACCURACY_GATE}",
        "- Aucun marché ne doit entrer dans V17.5 sans gate validé.",
        "- Aucun modèle officiel sauvegardé.",
        "- Aucune intégration API/frontend/scoring V1.",
        "",
        "Raisons bloquantes :",
        f"- {'Aucune.' if not blocking_reasons else '; '.join(blocking_reasons)}",
        "",
        "Points de vigilance :",
        f"- {'Aucun.' if not warnings_list else '; '.join(warnings_list)}",
        "",
        "Décision opérationnelle :",
    ]

    if "STRONG" in status:
        lines.extend(
            [
                "- V17.2 peut remplacer le signal OVER_1_5 de V17.0 dans un futur test V17.5.",
                "- UNDER_1_5 reste exclu si le statut indique UNDER_EXCLUDED.",
                "- Une comparaison V17.0 vs V17.5 sera nécessaire avant toute décision finale.",
            ]
        )
    elif "REVIEW" in status:
        lines.extend(
            [
                "- V17.2 améliore le signal OVER_1_5 par rapport à V15, mais ne passe pas encore le gate fort de 0.83.",
                "- Le signal peut être conservé pour comparaison dans V17.5, mais seulement comme candidat expérimental.",
                "- UNDER_1_5 reste rejeté et ne doit pas entrer dans le sélecteur final.",
            ]
        )
    elif "EXPERIMENTAL" in status:
        lines.extend(
            [
                "- V17.2 reste une expérimentation utile mais insuffisante pour renforcer V17.0.",
                "- Conserver les preuves, puis passer à V17.3 O/U 2.5 enrichi.",
            ]
        )
    else:
        lines.extend(
            [
                "- V17.2 est rejetée comme amélioration exploitable.",
                "- Ne pas remplacer le signal OVER_1_5 actuel de V17.0.",
            ]
        )

    lines.extend(
        [
            "- V17.2 ne remplace pas le scoring explicable V1.",
            "- V17.2 ne modifie ni PostgreSQL, ni ml.features, ni l'API, ni le frontend.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V17.2 Over/Under 1.5 enrichi : réalisée si les fichiers 238 à 243 sont générés.",
            "- Fichiers concernés : backend/scripts/ml/train_goals_v17_2_over_under_15_enriched.py et reports/evidence/ml_training/238-243.",
        ]
    )
    (evidence_dir / OUTPUT_DECISION).write_text("\n".join(lines), encoding="utf-8")


# Orchestre V17.2 : dataset enrichi, entraînement, sélection, exports et décision.
def main() -> None:
    print("Chargement des features enrichies V17.1 pour V17.2 Over/Under 1.5...")
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)
    dataset, csv_count = build_v17_2_dataset(project_root)
    train, validation, test = split_dataset(dataset)

    print("Entraînement des modèles logistiques V17.2 en mémoire...")
    train_scored, validation_scored, test_scored = attach_scores(train, validation, test)
    strategies = build_strategies()

    print("Évaluation des stratégies V17.2 sur validation et test...")
    validation_rows = [evaluate_strategy(validation_scored, strategy, "validation") for strategy in strategies]
    validation_results = pd.DataFrame(validation_rows)
    best_strategy = select_best_strategy(validation_results, strategies)
    validation_metrics = evaluate_strategy(validation_scored, best_strategy, "validation")

    test_rows = [evaluate_strategy(test_scored, strategy, "test") for strategy in strategies]
    all_results = pd.concat([validation_results, pd.DataFrame(test_rows)], ignore_index=True)
    test_metrics = evaluate_strategy(test_scored, best_strategy, "test")

    print("Application de la meilleure stratégie V17.2 sur test final...")
    final_predictions = apply_strategy(test_scored, best_strategy)
    by_league_season = build_by_league_season(final_predictions)
    by_signal = build_by_signal(final_predictions)
    error_patterns = build_error_patterns(final_predictions)
    status, blocking_reasons, warnings_list = determine_status(test_metrics, by_league_season)

    all_results.to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8-sig")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8-sig")
    by_signal.to_csv(evidence_dir / OUTPUT_BY_SIGNAL, index=False, encoding="utf-8-sig")
    error_patterns.to_csv(evidence_dir / OUTPUT_ERROR_PATTERNS, index=False, encoding="utf-8-sig")

    write_summary(
        evidence_dir=evidence_dir,
        dataset=dataset,
        csv_count=csv_count,
        best_strategy=best_strategy,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        by_league_season=by_league_season,
        status=status,
        blocking_reasons=blocking_reasons,
        warnings_list=warnings_list,
    )
    write_decision(
        evidence_dir=evidence_dir,
        best_strategy=best_strategy,
        test_metrics=test_metrics,
        status=status,
        blocking_reasons=blocking_reasons,
        warnings_list=warnings_list,
    )

    print("OK - Expérience V17.2 Over/Under 1.5 enrichie terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {best_strategy.name}")
    print(f"Test accuracy: {test_metrics.get('accuracy')}")
    print(f"Test coverage: {test_metrics.get('coverage')}")
    print(f"Test abstention rate: {test_metrics.get('abstention_rate')}")
    print(f"Selected rows: {test_metrics.get('selected_rows')}")
    print(f"OVER_1_5 rows: {test_metrics.get('over_rows')}")
    print(f"UNDER_1_5 rows: {test_metrics.get('under_rows')}")
    print(f"OVER_1_5 accuracy: {test_metrics.get('over_accuracy')}")
    print(f"UNDER_1_5 accuracy: {test_metrics.get('under_accuracy')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"By signal CSV saved: {evidence_dir / OUTPUT_BY_SIGNAL}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication :
# data/ml/raw/*.csv -> build_multimarket_v17_1_enriched_features.py -> train_goals_v17_2_over_under_15_enriched.py -> reports/evidence/ml_training/238-243
# Ce script lit les CSV bruts, réutilise les features enrichies V17.1 en mémoire et écrit uniquement des preuves expérimentales ML.
