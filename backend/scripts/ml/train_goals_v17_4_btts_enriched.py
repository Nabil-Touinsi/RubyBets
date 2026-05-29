# Rôle du fichier : tester V17.4 BTTS avec les features enrichies V17.1, en mémoire uniquement, sans intégration produit.

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
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


TARGET_COLUMN = "target_btts"
YES_LABEL = "BTTS_YES"
NO_LABEL = "BTTS_NO"
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

OUTPUT_SUMMARY = "250_goals_v17_4_btts_enriched_summary.txt"
OUTPUT_RESULTS = "251_goals_v17_4_btts_enriched_results.csv"
OUTPUT_BY_LEAGUE_SEASON = "252_goals_v17_4_btts_by_league_season.csv"
OUTPUT_BY_SIGNAL = "253_goals_v17_4_btts_by_signal.csv"
OUTPUT_ERROR_PATTERNS = "254_goals_v17_4_btts_error_patterns.csv"
OUTPUT_DECISION = "255_goals_v17_4_btts_decision.txt"

VALIDATION_SEASON = "2021_2022"
TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]
TRAIN_MAX_SEASON_START = 2020

V16_REFERENCE_ACCURACY = 0.5790
V16_REFERENCE_COVERAGE = 0.3931
V16_REFERENCE_SELECTED_ROWS = 2095
V16_REFERENCE_YES_ROWS = 1891
V16_REFERENCE_NO_ROWS = 204
V16_REFERENCE_YES_ACCURACY = 0.5849
V16_REFERENCE_NO_ACCURACY = 0.5245

MIN_VALIDATION_COVERAGE_FOR_SELECTION = 0.35
MIN_VALIDATION_SELECTED_ROWS = 600
MIN_REVIEW_ACCURACY = 0.62
MIN_REVIEW_COVERAGE = 0.35
MIN_STRONG_ACCURACY = 0.65
MIN_SIGNAL_ROWS_FOR_BALANCE = 100
MIN_SIGNAL_SHARE_FOR_BALANCE = 0.10
MIN_MAJOR_SEGMENT_ROWS = 80
MIN_MAJOR_SEGMENT_ACCURACY = 0.57

LOGISTIC_STANDARD_YES_THRESHOLDS = [0.53, 0.54, 0.55, 0.56, 0.57, 0.58]
LOGISTIC_STANDARD_NO_THRESHOLDS = [0.49, 0.48, 0.47, 0.46]
LOGISTIC_BALANCED_YES_THRESHOLDS = [0.52, 0.53, 0.54, 0.55, 0.56]
LOGISTIC_BALANCED_NO_THRESHOLDS = [0.49, 0.48, 0.47, 0.46]
RANDOM_FOREST_YES_THRESHOLDS = [0.51, 0.52, 0.53, 0.54]
RANDOM_FOREST_NO_THRESHOLDS = [0.48, 0.47, 0.46, 0.45, 0.44]
PROXY_YES_THRESHOLDS = [0.58, 0.59, 0.60, 0.61]
PROXY_NO_THRESHOLDS = [0.50, 0.49, 0.48]
RATE_YES_THRESHOLDS = [0.55, 0.58, 0.60, 0.62]
RATE_NO_THRESHOLDS = [0.48, 0.45, 0.42]

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class StrategySpec:
    name: str
    family: str
    score_column: str
    yes_threshold: float
    no_threshold: float | None
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


# Construit le dataset enrichi V17.4 depuis les CSV bruts, via la logique V17.1.
def build_v17_4_dataset(project_root: Path) -> tuple[pd.DataFrame, int]:
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
        raise RuntimeError("Split V17.4 impossible : train, validation ou test vide.")
    return train, validation, test


# Prépare les colonnes features numériques et catégorielles utilisées par les modèles V17.4.
def get_model_columns() -> tuple[list[str], list[str]]:
    numeric_columns = list(FEATURE_COLUMNS)
    categorical_columns = ["league_code"]
    return numeric_columns, categorical_columns


# Transforme les labels BTTS YES/NO en cible binaire pour entraîner les modèles.
def build_binary_target(dataframe: pd.DataFrame) -> pd.Series:
    return (dataframe[TARGET_COLUMN].astype(str) == YES_LABEL).astype(int)


# Entraîne un modèle logistique V17.4 pour produire une probabilité BTTS_YES.
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


# Entraîne un Random Forest prudent pour tester un signal BTTS non linéaire sans sauvegarder de modèle.
def train_random_forest_model(train: pd.DataFrame) -> Pipeline:
    numeric_columns, categorical_columns = get_model_columns()
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), numeric_columns),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_columns),
        ]
    )
    classifier = RandomForestClassifier(
        n_estimators=120,
        max_depth=6,
        min_samples_leaf=30,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model = Pipeline(steps=[("preprocessor", preprocessor), ("classifier", classifier)])
    model.fit(train[numeric_columns + categorical_columns], build_binary_target(train))
    return model


# Ajoute les scores probabilistes ou heuristiques nécessaires aux stratégies V17.4.
def attach_scores(train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    numeric_columns, categorical_columns = get_model_columns()
    standard_model = train_logistic_model(train, balanced=False)
    balanced_model = train_logistic_model(train, balanced=True)
    random_forest_model = train_random_forest_model(train)

    outputs: list[pd.DataFrame] = []
    for frame in (train, validation, test):
        output = frame.copy()
        output["score_logistic_standard_btts_yes"] = standard_model.predict_proba(
            output[numeric_columns + categorical_columns]
        )[:, 1]
        output["score_logistic_balanced_btts_yes"] = balanced_model.predict_proba(
            output[numeric_columns + categorical_columns]
        )[:, 1]
        output["score_random_forest_btts_yes"] = random_forest_model.predict_proba(
            output[numeric_columns + categorical_columns]
        )[:, 1]
        output["score_proxy_btts_yes"] = pd.to_numeric(output["prob_btts_proxy"], errors="coerce")
        output["score_combined_btts_rate"] = pd.to_numeric(output["combined_btts_rate_last_10"], errors="coerce")
        output["score_btts_yes_context"] = (
            pd.to_numeric(output["home_btts_rate_last_10"], errors="coerce")
            + pd.to_numeric(output["away_btts_rate_last_10"], errors="coerce")
            + pd.to_numeric(output["home_team_home_btts_rate_last_10"], errors="coerce")
            + pd.to_numeric(output["away_team_away_btts_rate_last_10"], errors="coerce")
        ) / 4.0
        outputs.append(output)

    return outputs[0], outputs[1], outputs[2]


# Crée la liste des stratégies V17.4 à comparer sur validation et test.
def build_strategies() -> list[StrategySpec]:
    strategies: list[StrategySpec] = []

    for yes_threshold in LOGISTIC_STANDARD_YES_THRESHOLDS:
        for no_threshold in LOGISTIC_STANDARD_NO_THRESHOLDS:
            if no_threshold >= yes_threshold:
                continue
            strategies.append(
                StrategySpec(
                    name=(
                        "v17_4_logistic_standard_btts"
                        f"_yes_t{threshold_suffix(yes_threshold)}"
                        f"_no_t{threshold_suffix(no_threshold)}"
                    ),
                    family="logistic_standard_btts_mixed",
                    score_column="score_logistic_standard_btts_yes",
                    yes_threshold=yes_threshold,
                    no_threshold=no_threshold,
                    min_history_count=8,
                    notes="Logistic standard enrichie, BTTS_YES et BTTS_NO.",
                )
            )

    for yes_threshold in LOGISTIC_BALANCED_YES_THRESHOLDS:
        for no_threshold in LOGISTIC_BALANCED_NO_THRESHOLDS:
            if no_threshold >= yes_threshold:
                continue
            strategies.append(
                StrategySpec(
                    name=(
                        "v17_4_logistic_balanced_btts"
                        f"_yes_t{threshold_suffix(yes_threshold)}"
                        f"_no_t{threshold_suffix(no_threshold)}"
                    ),
                    family="logistic_balanced_btts_mixed",
                    score_column="score_logistic_balanced_btts_yes",
                    yes_threshold=yes_threshold,
                    no_threshold=no_threshold,
                    min_history_count=8,
                    notes="Logistic équilibrée pour surveiller BTTS_NO.",
                )
            )

    for yes_threshold in RANDOM_FOREST_YES_THRESHOLDS:
        for no_threshold in RANDOM_FOREST_NO_THRESHOLDS:
            if no_threshold >= yes_threshold:
                continue
            strategies.append(
                StrategySpec(
                    name=(
                        "v17_4_random_forest_btts"
                        f"_yes_t{threshold_suffix(yes_threshold)}"
                        f"_no_t{threshold_suffix(no_threshold)}"
                    ),
                    family="random_forest_btts_mixed",
                    score_column="score_random_forest_btts_yes",
                    yes_threshold=yes_threshold,
                    no_threshold=no_threshold,
                    min_history_count=8,
                    notes="Random Forest prudent pour capter les interactions goals/BTTS.",
                )
            )

    for yes_threshold in PROXY_YES_THRESHOLDS:
        for no_threshold in PROXY_NO_THRESHOLDS:
            if no_threshold >= yes_threshold:
                continue
            strategies.append(
                StrategySpec(
                    name=(
                        "v17_4_proxy_btts"
                        f"_yes_t{threshold_suffix(yes_threshold)}"
                        f"_no_t{threshold_suffix(no_threshold)}"
                    ),
                    family="proxy_btts_mixed",
                    score_column="score_proxy_btts_yes",
                    yes_threshold=yes_threshold,
                    no_threshold=no_threshold,
                    min_history_count=8,
                    notes="Proxy BTTS construit depuis les buts attendus proxy.",
                )
            )

    for yes_threshold in RATE_YES_THRESHOLDS:
        for no_threshold in RATE_NO_THRESHOLDS:
            if no_threshold >= yes_threshold:
                continue
            strategies.append(
                StrategySpec(
                    name=(
                        "v17_4_combined_rate_btts"
                        f"_yes_t{threshold_suffix(yes_threshold)}"
                        f"_no_t{threshold_suffix(no_threshold)}"
                    ),
                    family="combined_rate_btts_mixed",
                    score_column="score_combined_btts_rate",
                    yes_threshold=yes_threshold,
                    no_threshold=no_threshold,
                    min_history_count=8,
                    notes="Règle enrichie sur le taux rolling combiné BTTS.",
                )
            )

    return strategies


# Applique une stratégie V17.4 sur un DataFrame donné.
def apply_strategy(dataframe: pd.DataFrame, strategy: StrategySpec) -> pd.DataFrame:
    output = dataframe.copy()
    score = pd.to_numeric(output[strategy.score_column], errors="coerce")
    min_history = pd.to_numeric(output["min_history_count_last_10"], errors="coerce").fillna(0)
    history_mask = min_history >= strategy.min_history_count

    yes_mask = history_mask & score.notna() & (score >= strategy.yes_threshold)
    if strategy.no_threshold is None:
        no_mask = pd.Series(False, index=output.index)
    else:
        no_mask = history_mask & score.notna() & (score <= strategy.no_threshold)

    recommendation = np.where(yes_mask, YES_LABEL, np.where(no_mask, NO_LABEL, ABSTAIN_STATUS))
    selected_mask = yes_mask | no_mask

    output["v17_4_strategy"] = strategy.name
    output["v17_4_family"] = strategy.family
    output["v17_4_score"] = score
    output["v17_4_recommendation_status"] = np.where(selected_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v17_4_recommendation"] = recommendation
    output["v17_4_is_correct"] = (
        (output[TARGET_COLUMN].astype(str) == output["v17_4_recommendation"].astype(str)) & selected_mask
    )
    output["v17_4_signal_strength"] = pd.cut(
        output["v17_4_score"],
        bins=[-math.inf, 0.45, 0.49, 0.53, 0.57, math.inf],
        labels=["STRONG_NO_SIGNAL", "LIGHT_NO_SIGNAL", "CENTRAL_UNCERTAIN", "LIGHT_YES_SIGNAL", "STRONG_YES_SIGNAL"],
        include_lowest=True,
    ).astype(str)
    return output


# Calcule les métriques principales d'une stratégie V17.4.
def evaluate_strategy(dataframe: pd.DataFrame, strategy: StrategySpec, split_name: str) -> dict[str, object]:
    predictions = apply_strategy(dataframe, strategy)
    selected = predictions[predictions["v17_4_recommendation_status"] == RECOMMEND_STATUS]
    yes_selected = selected[selected["v17_4_recommendation"] == YES_LABEL]
    no_selected = selected[selected["v17_4_recommendation"] == NO_LABEL]
    selected_rows = len(selected)
    total_rows = len(predictions)
    yes_rows = len(yes_selected)
    no_rows = len(no_selected)

    return {
        "strategy": strategy.name,
        "family": strategy.family,
        "split": split_name,
        "score_column": strategy.score_column,
        "yes_threshold": strategy.yes_threshold,
        "no_threshold": "none" if strategy.no_threshold is None else strategy.no_threshold,
        "min_history_count": strategy.min_history_count,
        "accuracy": rounded(safe_rate(int(selected["v17_4_is_correct"].sum()), selected_rows)),
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "selected_rows": selected_rows,
        "total_rows": total_rows,
        "yes_rows": yes_rows,
        "no_rows": no_rows,
        "yes_share": rounded(safe_rate(yes_rows, selected_rows)),
        "no_share": rounded(safe_rate(no_rows, selected_rows)),
        "yes_accuracy": rounded(safe_rate(int(yes_selected["v17_4_is_correct"].sum()), yes_rows)),
        "no_accuracy": rounded(safe_rate(int(no_selected["v17_4_is_correct"].sum()), no_rows)),
        "avg_selected_score": rounded(selected["v17_4_score"].mean()) if selected_rows else 0.0,
        "notes": strategy.notes,
    }


# Sélectionne la meilleure stratégie sur validation sans utiliser les résultats de test.
def select_best_strategy(validation_results: pd.DataFrame, strategies: list[StrategySpec]) -> StrategySpec:
    candidates = validation_results[
        (validation_results["split"] == "validation")
        & (validation_results["coverage"] >= MIN_VALIDATION_COVERAGE_FOR_SELECTION)
        & (validation_results["selected_rows"] >= MIN_VALIDATION_SELECTED_ROWS)
    ].copy()

    if candidates.empty:
        candidates = validation_results[
            (validation_results["split"] == "validation")
            & (validation_results["coverage"] >= 0.25)
            & (validation_results["selected_rows"] >= 400)
        ].copy()
    if candidates.empty:
        candidates = validation_results[validation_results["split"] == "validation"].copy()

    candidates["signal_balance_ok"] = (
        (candidates["yes_rows"] >= MIN_SIGNAL_ROWS_FOR_BALANCE)
        & (candidates["no_rows"] >= MIN_SIGNAL_ROWS_FOR_BALANCE)
        & (candidates["yes_share"] >= MIN_SIGNAL_SHARE_FOR_BALANCE)
        & (candidates["no_share"] >= MIN_SIGNAL_SHARE_FOR_BALANCE)
    )
    candidates["review_gate_on_validation"] = (
        (candidates["accuracy"] >= MIN_REVIEW_ACCURACY)
        & (candidates["coverage"] >= MIN_REVIEW_COVERAGE)
        & candidates["signal_balance_ok"]
    )
    candidates = candidates.sort_values(
        by=["review_gate_on_validation", "signal_balance_ok", "accuracy", "coverage", "selected_rows"],
        ascending=[False, False, False, False, False],
    )
    selected_name = str(candidates.iloc[0]["strategy"])

    for strategy in strategies:
        if strategy.name == selected_name:
            return strategy
    raise RuntimeError("Impossible de retrouver la stratégie V17.4 sélectionnée.")


# Construit le tableau de stabilité par ligue/saison pour la stratégie retenue.
def build_by_league_season(final_predictions: pd.DataFrame) -> pd.DataFrame:
    total_groups = final_predictions.groupby(["league_code", "season"], dropna=False).size().reset_index(name="total_rows")
    selected = final_predictions[final_predictions["v17_4_recommendation_status"] == RECOMMEND_STATUS].copy()
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
        yes_group = group[group["v17_4_recommendation"] == YES_LABEL]
        no_group = group[group["v17_4_recommendation"] == NO_LABEL]
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "total_rows": total_rows,
                "selected_rows": len(group),
                "coverage": rounded(safe_rate(len(group), total_rows)),
                "accuracy": rounded(safe_rate(int(group["v17_4_is_correct"].sum()), len(group))),
                "yes_rows": len(yes_group),
                "no_rows": len(no_group),
                "yes_accuracy": rounded(safe_rate(int(yes_group["v17_4_is_correct"].sum()), len(yes_group))),
                "no_accuracy": rounded(safe_rate(int(no_group["v17_4_is_correct"].sum()), len(no_group))),
                "avg_score": rounded(group["v17_4_score"].mean()),
                "avg_combined_btts_rate": rounded(group["combined_btts_rate_last_10"].mean()),
                "avg_prob_btts_proxy": rounded(group["prob_btts_proxy"].mean()),
                "is_major_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS,
                "is_major_fragile_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS
                and safe_rate(int(group["v17_4_is_correct"].sum()), len(group)) < MIN_MAJOR_SEGMENT_ACCURACY,
            }
        )

    return pd.DataFrame(rows).sort_values(["accuracy", "selected_rows"], ascending=[True, False])


# Construit le tableau de performance par signal recommandé et force de score.
def build_by_signal(final_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = final_predictions[final_predictions["v17_4_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v17_4_recommendation", "v17_4_signal_strength"], dropna=False)
    for (recommendation, signal_strength), group in grouped:
        rows.append(
            {
                "recommendation": recommendation,
                "signal_strength": signal_strength,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v17_4_is_correct"].sum()), len(group))),
                "avg_score": rounded(group["v17_4_score"].mean()),
                "avg_combined_btts_rate": rounded(group["combined_btts_rate_last_10"].mean()),
                "avg_prob_btts_proxy": rounded(group["prob_btts_proxy"].mean()),
                "avg_home_failed_to_score_rate": rounded(group["home_failed_to_score_rate_last_10"].mean()),
                "avg_away_failed_to_score_rate": rounded(group["away_failed_to_score_rate_last_10"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values(["recommendation", "signal_strength"])


# Construit un extrait des erreurs restantes pour analyse V17.4.
def build_error_patterns(final_predictions: pd.DataFrame) -> pd.DataFrame:
    errors = final_predictions[
        (final_predictions["v17_4_recommendation_status"] == RECOMMEND_STATUS)
        & (~final_predictions["v17_4_is_correct"])
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
        "v17_4_recommendation",
        "v17_4_score",
        "prob_btts_proxy",
        "combined_btts_rate_last_10",
        "home_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
        "home_clean_sheet_rate_last_10",
        "away_clean_sheet_rate_last_10",
        "expected_home_goals_proxy",
        "expected_away_goals_proxy",
        "min_history_count_last_10",
    ]
    return errors[keep_columns].sort_values(["season", "league_code", "match_date"]).head(500)


# Détermine le statut V17.4 selon les métriques et les gates prévus.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    coverage = float(metrics.get("coverage", 0.0))
    yes_rows = int(metrics.get("yes_rows", 0))
    no_rows = int(metrics.get("no_rows", 0))
    yes_share = float(metrics.get("yes_share", 0.0))
    no_share = float(metrics.get("no_share", 0.0))

    major_fragile_segments = 0
    if not by_league_season.empty and "is_major_fragile_segment" in by_league_season.columns:
        major_fragile_segments = int(by_league_season["is_major_fragile_segment"].sum())

    blocking_reasons: list[str] = []
    warnings_list: list[str] = []

    signal_balance_ok = (
        yes_rows >= MIN_SIGNAL_ROWS_FOR_BALANCE
        and no_rows >= MIN_SIGNAL_ROWS_FOR_BALANCE
        and yes_share >= MIN_SIGNAL_SHARE_FOR_BALANCE
        and no_share >= MIN_SIGNAL_SHARE_FOR_BALANCE
    )

    if major_fragile_segments > 0:
        warnings_list.append(f"{major_fragile_segments} segment(s) ligue/saison majeur(s) sous {MIN_MAJOR_SEGMENT_ACCURACY}.")
    if not signal_balance_ok:
        warnings_list.append("Répartition BTTS_YES / BTTS_NO encore déséquilibrée ou volume NO insuffisant.")
    if accuracy < MIN_REVIEW_ACCURACY:
        warnings_list.append(f"Accuracy sous le gate REVIEW V17.4 de {MIN_REVIEW_ACCURACY}.")
    if coverage < MIN_REVIEW_COVERAGE:
        warnings_list.append(f"Coverage sous le gate V17.4 de {MIN_REVIEW_COVERAGE}.")

    if accuracy >= MIN_STRONG_ACCURACY and coverage >= MIN_REVIEW_COVERAGE and signal_balance_ok and major_fragile_segments == 0:
        return "V17_4_BTTS_ENRICHED_STRONG_REVIEW", blocking_reasons, warnings_list

    if accuracy >= MIN_REVIEW_ACCURACY and coverage >= MIN_REVIEW_COVERAGE and signal_balance_ok:
        return "V17_4_BTTS_ENRICHED_REVIEW", blocking_reasons, warnings_list

    if accuracy >= V16_REFERENCE_ACCURACY and coverage >= 0.35:
        return "V17_4_BTTS_ENRICHED_LIMITED_REVIEW", blocking_reasons, warnings_list

    blocking_reasons.append("BTTS enrichi ne passe pas les gates et n'améliore pas assez V16.")
    return "V17_4_BTTS_ENRICHED_REJECTED", blocking_reasons, warnings_list


# Écrit la synthèse détaillée V17.4.
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
    accuracy_delta = float(test_metrics.get("accuracy", 0.0)) - V16_REFERENCE_ACCURACY
    coverage_delta = float(test_metrics.get("coverage", 0.0)) - V16_REFERENCE_COVERAGE
    selected_delta = int(test_metrics.get("selected_rows", 0)) - V16_REFERENCE_SELECTED_ROWS
    yes_delta_rows = int(test_metrics.get("yes_rows", 0)) - V16_REFERENCE_YES_ROWS
    no_delta_rows = int(test_metrics.get("no_rows", 0)) - V16_REFERENCE_NO_ROWS

    lowest_segment = "Aucun"
    if not by_league_season.empty:
        first = by_league_season.iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"

    lines = [
        "RubyBets - ML Goals V17.4 BTTS enriched selective",
        "250 - Synthèse expérience V17.4",
        "",
        "Objectif :",
        "Retester BTTS avec les features enrichies V17.1 goals/BTTS, afin de vérifier si BTTS_YES et BTTS_NO deviennent exploitables sans cotes BTTS.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data dans data/ml/raw.",
        "- Construction des features enrichies en mémoire via la logique V17.1.",
        "- Aucune cote BTTS ajoutée : test labels-only enrichi.",
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
        f"- BTTS_YES rows : {int((dataset[TARGET_COLUMN] == YES_LABEL).sum())}",
        f"- BTTS_NO rows : {int((dataset[TARGET_COLUMN] == NO_LABEL).sum())}",
        "",
        "Meilleure stratégie V17.4 sélectionnée sur validation :",
        f"- Strategy : {best_strategy.name}",
        f"- Family : {best_strategy.family}",
        f"- Validation accuracy : {validation_metrics.get('accuracy')}",
        f"- Validation coverage : {validation_metrics.get('coverage')}",
        f"- Validation selected rows : {validation_metrics.get('selected_rows')}",
        f"- Validation BTTS_YES accuracy : {validation_metrics.get('yes_accuracy')}",
        f"- Validation BTTS_NO accuracy : {validation_metrics.get('no_accuracy')}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Accuracy : {test_metrics.get('accuracy')}",
        f"- Coverage : {test_metrics.get('coverage')}",
        f"- Abstention rate : {test_metrics.get('abstention_rate')}",
        f"- Selected rows : {test_metrics.get('selected_rows')}",
        f"- BTTS_YES rows : {test_metrics.get('yes_rows')}",
        f"- BTTS_NO rows : {test_metrics.get('no_rows')}",
        f"- BTTS_YES accuracy : {test_metrics.get('yes_accuracy')}",
        f"- BTTS_NO accuracy : {test_metrics.get('no_accuracy')}",
        "",
        "Comparaison avec V16 :",
        f"- V16 accuracy : {V16_REFERENCE_ACCURACY}",
        f"- V17.4 accuracy delta : {rounded(accuracy_delta)}",
        f"- V16 coverage : {V16_REFERENCE_COVERAGE}",
        f"- V17.4 coverage delta : {rounded(coverage_delta)}",
        f"- V16 selected rows : {V16_REFERENCE_SELECTED_ROWS}",
        f"- V17.4 selected rows delta : {selected_delta}",
        f"- V16 BTTS_YES rows : {V16_REFERENCE_YES_ROWS}",
        f"- V17.4 BTTS_YES rows delta : {yes_delta_rows}",
        f"- V16 BTTS_NO rows : {V16_REFERENCE_NO_ROWS}",
        f"- V17.4 BTTS_NO rows delta : {no_delta_rows}",
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
        "Ne pas intégrer V17.4 au produit. BTTS reste un signal expérimental fragile tant que les gates V17.4 ne sont pas atteints.",
        "Le scoring explicable V1 reste le socle officiel de RubyBets.",
    ]
    (evidence_dir / OUTPUT_SUMMARY).write_text("\n".join(lines), encoding="utf-8")


# Écrit la décision opérationnelle V17.4.
def write_decision(
    evidence_dir: Path,
    best_strategy: StrategySpec,
    test_metrics: dict[str, object],
    status: str,
    blocking_reasons: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V17.4 BTTS enrichi",
        "255 - Décision expérience V17.4",
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
        f"- BTTS_YES rows : {test_metrics.get('yes_rows')}",
        f"- BTTS_NO rows : {test_metrics.get('no_rows')}",
        f"- BTTS_YES accuracy : {test_metrics.get('yes_accuracy')}",
        f"- BTTS_NO accuracy : {test_metrics.get('no_accuracy')}",
        "",
        "Gates V17.4 :",
        f"- Accuracy REVIEW cible >= {MIN_REVIEW_ACCURACY}",
        f"- Accuracy candidat exploitable >= {MIN_STRONG_ACCURACY}",
        f"- Coverage cible >= {MIN_REVIEW_COVERAGE}",
        f"- BTTS_YES et BTTS_NO doivent avoir au moins {MIN_SIGNAL_ROWS_FOR_BALANCE} lignes chacun et au moins {MIN_SIGNAL_SHARE_FOR_BALANCE} de part sélectionnée.",
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
                "- V17.4 peut être conservée comme candidat fort pour un test V17.5.",
                "- Une comparaison V17.0 vs V17.5 reste obligatoire avant toute décision finale.",
            ]
        )
    elif status.endswith("_REVIEW"):
        lines.extend(
            [
                "- V17.4 passe un niveau REVIEW mais reste à comparer prudemment dans V17.5.",
                "- BTTS ne doit entrer dans le sélecteur final que si la stabilité globale reste suffisante.",
            ]
        )
    elif "LIMITED_REVIEW" in status:
        lines.extend(
            [
                "- V17.4 améliore légèrement certains signaux mais reste sous les gates forts BTTS.",
                "- BTTS ne doit pas entrer automatiquement dans V17.5.",
                "- Le signal peut être conservé uniquement comme comparaison expérimentale.",
            ]
        )
    else:
        lines.extend(
            [
                "- V17.4 est rejetée comme amélioration exploitable.",
                "- BTTS doit rester exclu du sélecteur final.",
            ]
        )

    lines.extend(
        [
            "- V17.4 ne remplace pas le scoring explicable V1.",
            "- V17.4 ne modifie ni PostgreSQL, ni ml.features, ni l'API, ni le frontend.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V17.4 BTTS enrichi : réalisée si les fichiers 250 à 255 sont générés.",
            "- Fichiers concernés : backend/scripts/ml/train_goals_v17_4_btts_enriched.py et reports/evidence/ml_training/250-255.",
        ]
    )
    (evidence_dir / OUTPUT_DECISION).write_text("\n".join(lines), encoding="utf-8")


# Orchestre V17.4 : dataset enrichi, entraînement, sélection, exports et décision.
def main() -> None:
    print("Chargement des features enrichies V17.1 pour V17.4 BTTS...")
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)
    dataset, csv_count = build_v17_4_dataset(project_root)
    train, validation, test = split_dataset(dataset)

    print("Entraînement des modèles V17.4 BTTS enrichis en mémoire...")
    train_scored, validation_scored, test_scored = attach_scores(train, validation, test)
    strategies = build_strategies()

    print("Évaluation des stratégies V17.4 sur validation et test...")
    validation_rows = [evaluate_strategy(validation_scored, strategy, "validation") for strategy in strategies]
    validation_results = pd.DataFrame(validation_rows)
    best_strategy = select_best_strategy(validation_results, strategies)
    validation_metrics = evaluate_strategy(validation_scored, best_strategy, "validation")

    test_rows = [evaluate_strategy(test_scored, strategy, "test") for strategy in strategies]
    all_results = pd.concat([validation_results, pd.DataFrame(test_rows)], ignore_index=True)
    test_metrics = evaluate_strategy(test_scored, best_strategy, "test")

    print("Application de la meilleure stratégie V17.4 sur test final...")
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

    print("OK - Expérience V17.4 BTTS enrichie terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {best_strategy.name}")
    print(f"Test accuracy: {test_metrics.get('accuracy')}")
    print(f"Test coverage: {test_metrics.get('coverage')}")
    print(f"Test abstention rate: {test_metrics.get('abstention_rate')}")
    print(f"Selected rows: {test_metrics.get('selected_rows')}")
    print(f"BTTS_YES rows: {test_metrics.get('yes_rows')}")
    print(f"BTTS_NO rows: {test_metrics.get('no_rows')}")
    print(f"BTTS_YES accuracy: {test_metrics.get('yes_accuracy')}")
    print(f"BTTS_NO accuracy: {test_metrics.get('no_accuracy')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"By signal CSV saved: {evidence_dir / OUTPUT_BY_SIGNAL}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication :
# data/ml/raw/*.csv -> build_multimarket_v17_1_enriched_features.py -> train_goals_v17_4_btts_enriched.py -> reports/evidence/ml_training/250-255
# Ce script lit les CSV bruts, réutilise les features enrichies V17.1 en mémoire et écrit uniquement des preuves expérimentales ML.
