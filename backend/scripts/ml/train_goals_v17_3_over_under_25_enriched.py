# Rôle du fichier : tester V17.3 Over/Under 2.5 avec les features enrichies V17.1 et les cotes O/U 2.5 disponibles, en mémoire uniquement, sans intégration produit.

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
    clean_columns,
    find_project_root,
    get_evidence_dir,
    list_raw_csv_files,
    numeric_series,
    read_csv_safely,
)


TARGET_COLUMN = "target_over_under_25"
OVER_LABEL = "OVER_2_5"
UNDER_LABEL = "UNDER_2_5"
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

OUTPUT_SUMMARY = "244_goals_v17_3_over_under_25_enriched_summary.txt"
OUTPUT_RESULTS = "245_goals_v17_3_over_under_25_enriched_results.csv"
OUTPUT_BY_LEAGUE_SEASON = "246_goals_v17_3_over_under_25_by_league_season.csv"
OUTPUT_BY_MARKET_SIGNAL = "247_goals_v17_3_over_under_25_by_market_signal.csv"
OUTPUT_ERROR_PATTERNS = "248_goals_v17_3_over_under_25_error_patterns.csv"
OUTPUT_DECISION = "249_goals_v17_3_over_under_25_decision.txt"

VALIDATION_SEASON = "2021_2022"
TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]
TRAIN_MAX_SEASON_START = 2020

V14_REFERENCE_ACCURACY = 0.6444
V14_REFERENCE_COVERAGE = 0.5355
V14_REFERENCE_SELECTED_ROWS = 2854
V14_REFERENCE_OVER_ROWS = 1911
V14_REFERENCE_UNDER_ROWS = 943

STRONG_ACCURACY_GATE = 0.70
REVIEW_ACCURACY_GATE = 0.68
MIN_TEST_COVERAGE_GATE = 0.45
MIN_VALIDATION_SELECTED_ROWS = 650
MIN_VALIDATION_COVERAGE_FOR_SELECTION = 0.38
MIN_MAJOR_SEGMENT_ROWS = 80
MIN_MAJOR_SEGMENT_ACCURACY = 0.60

MARKET_COLUMNS = [
    "ou25_market_over_probability",
    "ou25_market_under_probability",
    "ou25_market_favorite_probability",
    "ou25_market_margin",
    "ou25_market_entropy",
    "ou25_available_pairs",
    "ou25_bookmaker_agreement_score",
]

LOGISTIC_STANDARD_THRESHOLDS = [0.52, 0.54, 0.56, 0.58, 0.60, 0.62]
LOGISTIC_BALANCED_THRESHOLDS = [0.52, 0.54, 0.56, 0.58, 0.60, 0.62]
RANDOM_FOREST_THRESHOLDS = [0.52, 0.54, 0.56, 0.58, 0.60]
MARKET_THRESHOLDS = [0.52, 0.54, 0.56, 0.58, 0.60, 0.62]
PROXY_THRESHOLDS = [0.52, 0.54, 0.56, 0.58, 0.60]
BLEND_THRESHOLDS = [0.52, 0.54, 0.56, 0.58, 0.60]
BLEND_WEIGHTS = [0.25, 0.50, 0.75]

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class OddsPair:
    bookmaker_prefix: str
    over_col: str
    under_col: str

    @property
    def key(self) -> str:
        return f"OVER_UNDER_2_5_{self.bookmaker_prefix}"


@dataclass(frozen=True)
class StrategySpec:
    name: str
    family: str
    score_column: str
    threshold: float
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


# Détecte les paires de colonnes Over/Under 2.5 disponibles dans un CSV Football-Data.
def detect_over_under_25_pairs(columns: Iterable[str]) -> list[OddsPair]:
    column_set = {str(column).strip().replace("\ufeff", "") for column in columns}
    pairs: dict[str, OddsPair] = {}

    for column in column_set:
        if ">2.5" not in column:
            continue
        prefix = column.split(">2.5", 1)[0]
        under_col = f"{prefix}<2.5"
        if under_col in column_set:
            pairs[prefix] = OddsPair(bookmaker_prefix=prefix, over_col=column, under_col=under_col)

    return sorted(pairs.values(), key=lambda pair: pair.key)


# Calcule la probabilité implicite normalisée OVER_2_5 pour une paire de cotes.
def calculate_pair_probability(frame: pd.DataFrame, pair: OddsPair) -> pd.Series:
    over_odds = numeric_series(frame, pair.over_col)
    under_odds = numeric_series(frame, pair.under_col)
    valid = (over_odds > 1.0) & (under_odds > 1.0)

    implied_over = 1.0 / over_odds
    implied_under = 1.0 / under_odds
    denominator = implied_over + implied_under
    probability = implied_over / denominator
    return probability.where(valid)


# Construit les signaux de marché O/U 2.5 pour un seul CSV brut.
def build_single_file_market_dataset(file_info: object) -> pd.DataFrame:
    frame = read_csv_safely(file_info.path)
    frame.columns = clean_columns(frame.columns)
    pairs = detect_over_under_25_pairs(frame.columns)
    if not pairs:
        return pd.DataFrame()

    required_columns = {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not required_columns.issubset(set(frame.columns)):
        return pd.DataFrame()

    home_goals = numeric_series(frame, "FTHG")
    away_goals = numeric_series(frame, "FTAG")
    valid_score = home_goals.notna() & away_goals.notna() & (home_goals >= 0) & (away_goals >= 0)

    probability_columns: list[pd.Series] = []
    for pair in pairs:
        probability_columns.append(calculate_pair_probability(frame, pair).rename(pair.key))

    probabilities = pd.concat(probability_columns, axis=1)
    available_pairs = probabilities.notna().sum(axis=1)
    over_probability = probabilities.mean(axis=1, skipna=True)
    under_probability = 1.0 - over_probability
    favorite_probability = pd.concat([over_probability, under_probability], axis=1).max(axis=1)
    market_margin = (over_probability - under_probability).abs()
    entropy = -(
        over_probability.clip(0.000001, 0.999999) * np.log(over_probability.clip(0.000001, 0.999999))
        + under_probability.clip(0.000001, 0.999999) * np.log(under_probability.clip(0.000001, 0.999999))
    )

    favorite = np.where(over_probability >= 0.5, OVER_LABEL, UNDER_LABEL)
    agreement_values: list[float] = []
    for index, row in probabilities.iterrows():
        values = row.dropna().to_numpy(dtype="float64")
        if len(values) == 0:
            agreement_values.append(0.0)
            continue
        pair_choices = np.where(values >= 0.5, OVER_LABEL, UNDER_LABEL)
        agreement_values.append(float(np.mean(pair_choices == favorite[index])))

    output = pd.DataFrame(
        {
            "source_file": file_info.path.name,
            "source_order": np.arange(len(frame)),
            "ou25_market_over_probability": over_probability,
            "ou25_market_under_probability": under_probability,
            "ou25_market_recommendation": favorite,
            "ou25_market_favorite_probability": favorite_probability,
            "ou25_market_margin": market_margin,
            "ou25_market_entropy": entropy,
            "ou25_available_pairs": available_pairs,
            "ou25_bookmaker_agreement_score": agreement_values,
        }
    )

    return output[valid_score & (available_pairs > 0)].copy()


# Construit le dataset de signaux de marché O/U 2.5 pour tous les CSV bruts.
def build_ou25_market_dataset(files: list[object]) -> tuple[pd.DataFrame, int]:
    datasets: list[pd.DataFrame] = []
    csv_with_pairs = 0

    for file_info in files:
        dataset = build_single_file_market_dataset(file_info)
        if dataset.empty:
            continue
        csv_with_pairs += 1
        datasets.append(dataset)

    if not datasets:
        raise RuntimeError("Aucune cote O/U 2.5 exploitable n'a été trouvée.")

    market_dataset = pd.concat(datasets, ignore_index=True)
    return market_dataset, csv_with_pairs


# Construit le dataset V17.3 en combinant features enrichies V17.1 et signaux de marché O/U 2.5.
def build_v17_3_dataset(project_root: Path) -> tuple[pd.DataFrame, int, int]:
    files = list_raw_csv_files(project_root)
    raw_matches = build_raw_matches(files)
    enriched_dataset = build_enriched_dataset(raw_matches)
    market_dataset, csv_with_pairs = build_ou25_market_dataset(files)

    dataset = enriched_dataset.merge(market_dataset, on=["source_file", "source_order"], how="inner")
    dataset = dataset.sort_values(["season_start_year", "league_code", "source_order", "home_team", "away_team"]).reset_index(drop=True)
    return dataset, len(files), csv_with_pairs


# Sépare le dataset selon un split chronologique stable : train, validation puis test récent.
def split_dataset(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = dataset[pd.to_numeric(dataset["season_start_year"], errors="coerce") <= TRAIN_MAX_SEASON_START].copy()
    validation = dataset[dataset["season"].astype(str) == VALIDATION_SEASON].copy()
    test = dataset[dataset["season"].astype(str).isin(TEST_SEASONS)].copy()

    if train.empty or validation.empty or test.empty:
        raise RuntimeError("Split V17.3 impossible : train, validation ou test vide.")
    return train, validation, test


# Prépare les colonnes numériques et catégorielles utilisées par les modèles V17.3.
def get_model_columns() -> tuple[list[str], list[str]]:
    numeric_columns = list(FEATURE_COLUMNS) + MARKET_COLUMNS
    categorical_columns = ["league_code"]
    return numeric_columns, categorical_columns


# Transforme les labels OVER/UNDER 2.5 en cible binaire pour entraîner les modèles.
def build_binary_target(dataframe: pd.DataFrame) -> pd.Series:
    return (dataframe[TARGET_COLUMN].astype(str) == OVER_LABEL).astype(int)


# Entraîne le modèle logistique V17.3.
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
    classifier = LogisticRegression(max_iter=1000, C=0.5, solver="liblinear", class_weight=class_weight)
    model = Pipeline(steps=[("preprocessor", preprocessor), ("classifier", classifier)])
    model.fit(train[numeric_columns + categorical_columns], build_binary_target(train))
    return model


# Entraîne un modèle Random Forest prudent pour comparaison non linéaire.
def train_random_forest_model(train: pd.DataFrame) -> Pipeline:
    numeric_columns, categorical_columns = get_model_columns()
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(steps=[("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                numeric_columns,
            ),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_columns),
        ]
    )
    classifier = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=40,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    model = Pipeline(steps=[("preprocessor", preprocessor), ("classifier", classifier)])
    model.fit(train[numeric_columns + categorical_columns], build_binary_target(train))
    return model


# Ajoute les scores probabilistes ou heuristiques nécessaires aux stratégies V17.3.
def attach_scores(train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    numeric_columns, categorical_columns = get_model_columns()
    standard_model = train_logistic_model(train, balanced=False)
    balanced_model = train_logistic_model(train, balanced=True)
    random_forest_model = train_random_forest_model(train)

    outputs: list[pd.DataFrame] = []
    for frame in (train, validation, test):
        output = frame.copy()
        features = output[numeric_columns + categorical_columns]
        output["score_logistic_standard_over_2_5"] = standard_model.predict_proba(features)[:, 1]
        output["score_logistic_balanced_over_2_5"] = balanced_model.predict_proba(features)[:, 1]
        output["score_random_forest_over_2_5"] = random_forest_model.predict_proba(features)[:, 1]
        output["score_market_over_2_5"] = pd.to_numeric(output["ou25_market_over_probability"], errors="coerce")
        output["score_proxy_over_2_5"] = pd.to_numeric(output["prob_over_2_5_proxy"], errors="coerce")
        output["score_blend_025_logistic_market_over_2_5"] = (
            0.25 * output["score_logistic_standard_over_2_5"] + 0.75 * output["score_market_over_2_5"]
        )
        output["score_blend_050_logistic_market_over_2_5"] = (
            0.50 * output["score_logistic_standard_over_2_5"] + 0.50 * output["score_market_over_2_5"]
        )
        output["score_blend_075_logistic_market_over_2_5"] = (
            0.75 * output["score_logistic_standard_over_2_5"] + 0.25 * output["score_market_over_2_5"]
        )
        outputs.append(output)

    return outputs[0], outputs[1], outputs[2]


# Crée la liste des stratégies V17.3 à comparer sur validation et test.
def build_strategies() -> list[StrategySpec]:
    strategies: list[StrategySpec] = []

    for threshold in LOGISTIC_STANDARD_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_3_logistic_enriched_ou25_t{threshold_suffix(threshold)}",
                family="logistic_standard_enriched_market",
                score_column="score_logistic_standard_over_2_5",
                threshold=threshold,
                min_history_count=8,
                notes="Logistic Regression avec features V17.1 + cotes O/U 2.5.",
            )
        )

    for threshold in LOGISTIC_BALANCED_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_3_logistic_balanced_ou25_t{threshold_suffix(threshold)}",
                family="logistic_balanced_enriched_market",
                score_column="score_logistic_balanced_over_2_5",
                threshold=threshold,
                min_history_count=8,
                notes="Logistic Regression équilibrée avec features V17.1 + cotes O/U 2.5.",
            )
        )

    for threshold in RANDOM_FOREST_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_3_random_forest_ou25_t{threshold_suffix(threshold)}",
                family="random_forest_enriched_market",
                score_column="score_random_forest_over_2_5",
                threshold=threshold,
                min_history_count=8,
                notes="Random Forest prudent avec features V17.1 + cotes O/U 2.5.",
            )
        )

    for threshold in MARKET_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_3_market_only_ou25_t{threshold_suffix(threshold)}",
                family="market_only_reference",
                score_column="score_market_over_2_5",
                threshold=threshold,
                min_history_count=0,
                notes="Référence marché O/U 2.5 seule, équivalente à la logique V14 enrichie en audit.",
            )
        )

    for threshold in PROXY_THRESHOLDS:
        strategies.append(
            StrategySpec(
                name=f"v17_3_proxy_poisson_ou25_t{threshold_suffix(threshold)}",
                family="proxy_poisson_enriched",
                score_column="score_proxy_over_2_5",
                threshold=threshold,
                min_history_count=8,
                notes="Proxy Poisson V17.1 sur expected_total_goals, sans cotes directes.",
            )
        )

    for weight in BLEND_WEIGHTS:
        score_column = f"score_blend_{int(weight * 100):03d}_logistic_market_over_2_5"
        for threshold in BLEND_THRESHOLDS:
            strategies.append(
                StrategySpec(
                    name=f"v17_3_blend{int(weight * 100):02d}_logistic_market_ou25_t{threshold_suffix(threshold)}",
                    family="blend_logistic_market",
                    score_column=score_column,
                    threshold=threshold,
                    min_history_count=8,
                    notes=f"Blend contrôlé : {weight:.2f} logistic + {1 - weight:.2f} marché.",
                )
            )

    return strategies


# Applique une stratégie V17.3 sur un DataFrame donné.
def apply_strategy(dataframe: pd.DataFrame, strategy: StrategySpec) -> pd.DataFrame:
    output = dataframe.copy()
    score = pd.to_numeric(output[strategy.score_column], errors="coerce")
    min_history = pd.to_numeric(output["min_history_count_last_10"], errors="coerce").fillna(0)
    history_mask = min_history >= strategy.min_history_count

    over_mask = history_mask & score.notna() & (score >= strategy.threshold)
    under_mask = history_mask & score.notna() & (score <= (1.0 - strategy.threshold))
    selected_mask = over_mask | under_mask
    recommendation = np.where(over_mask, OVER_LABEL, np.where(under_mask, UNDER_LABEL, ABSTAIN_STATUS))

    output["v17_3_strategy"] = strategy.name
    output["v17_3_family"] = strategy.family
    output["v17_3_score"] = score
    output["v17_3_recommendation_status"] = np.where(selected_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v17_3_recommendation"] = recommendation
    output["v17_3_is_correct"] = (
        (output[TARGET_COLUMN].astype(str) == output["v17_3_recommendation"].astype(str)) & selected_mask
    )
    output["v17_3_signal_strength"] = pd.cut(
        output["v17_3_score"],
        bins=[-math.inf, 0.40, 0.44, 0.56, 0.60, math.inf],
        labels=["STRONG_UNDER_SIGNAL", "MEDIUM_UNDER_SIGNAL", "NEUTRAL_ZONE", "MEDIUM_OVER_SIGNAL", "STRONG_OVER_SIGNAL"],
        include_lowest=True,
    ).astype(str)
    return output


# Calcule les métriques principales d'une stratégie V17.3.
def evaluate_strategy(dataframe: pd.DataFrame, strategy: StrategySpec, split_name: str) -> dict[str, object]:
    predictions = apply_strategy(dataframe, strategy)
    selected = predictions[predictions["v17_3_recommendation_status"] == RECOMMEND_STATUS]
    over_selected = selected[selected["v17_3_recommendation"] == OVER_LABEL]
    under_selected = selected[selected["v17_3_recommendation"] == UNDER_LABEL]
    selected_rows = len(selected)
    total_rows = len(predictions)

    return {
        "strategy": strategy.name,
        "family": strategy.family,
        "split": split_name,
        "score_column": strategy.score_column,
        "threshold": strategy.threshold,
        "min_history_count": strategy.min_history_count,
        "accuracy": rounded(safe_rate(int(selected["v17_3_is_correct"].sum()), selected_rows)),
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "selected_rows": selected_rows,
        "total_rows": total_rows,
        "over_rows": len(over_selected),
        "under_rows": len(under_selected),
        "over_accuracy": rounded(safe_rate(int(over_selected["v17_3_is_correct"].sum()), len(over_selected))),
        "under_accuracy": rounded(safe_rate(int(under_selected["v17_3_is_correct"].sum()), len(under_selected))),
        "avg_selected_score": rounded(selected["v17_3_score"].mean()) if selected_rows else 0.0,
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
            & (validation_results["coverage"] >= 0.30)
            & (validation_results["selected_rows"] >= 500)
        ].copy()
    if candidates.empty:
        candidates = validation_results[validation_results["split"] == "validation"].copy()

    candidates["passes_review_validation_hint"] = (
        (candidates["accuracy"] >= 0.63) & (candidates["coverage"] >= MIN_VALIDATION_COVERAGE_FOR_SELECTION)
    )
    candidates = candidates.sort_values(
        by=["passes_review_validation_hint", "accuracy", "coverage", "selected_rows"],
        ascending=[False, False, False, False],
    )
    selected_name = str(candidates.iloc[0]["strategy"])

    for strategy in strategies:
        if strategy.name == selected_name:
            return strategy
    raise RuntimeError("Impossible de retrouver la stratégie V17.3 sélectionnée.")


# Construit le tableau de stabilité par ligue/saison pour la stratégie retenue.
def build_by_league_season(final_predictions: pd.DataFrame) -> pd.DataFrame:
    total_groups = final_predictions.groupby(["league_code", "season"], dropna=False).size().reset_index(name="total_rows")
    selected = final_predictions[final_predictions["v17_3_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["league_code", "season"], dropna=False)
    for (league_code, season), group in grouped:
        total_rows = int(
            total_groups[(total_groups["league_code"] == league_code) & (total_groups["season"] == season)]["total_rows"].iloc[0]
        )
        over_group = group[group["v17_3_recommendation"] == OVER_LABEL]
        under_group = group[group["v17_3_recommendation"] == UNDER_LABEL]
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "total_rows": total_rows,
                "selected_rows": len(group),
                "coverage": rounded(safe_rate(len(group), total_rows)),
                "accuracy": rounded(safe_rate(int(group["v17_3_is_correct"].sum()), len(group))),
                "over_rows": len(over_group),
                "under_rows": len(under_group),
                "over_accuracy": rounded(safe_rate(int(over_group["v17_3_is_correct"].sum()), len(over_group))),
                "under_accuracy": rounded(safe_rate(int(under_group["v17_3_is_correct"].sum()), len(under_group))),
                "avg_score": rounded(group["v17_3_score"].mean()),
                "avg_market_over_probability": rounded(group["ou25_market_over_probability"].mean()),
                "avg_expected_total_goals_proxy": rounded(group["expected_total_goals_proxy"].mean()),
                "is_major_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS,
                "is_major_fragile_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS
                and safe_rate(int(group["v17_3_is_correct"].sum()), len(group)) < MIN_MAJOR_SEGMENT_ACCURACY,
            }
        )

    return pd.DataFrame(rows).sort_values(["accuracy", "selected_rows"], ascending=[True, False])


# Construit le tableau de performance par marché recommandé et force de signal.
def build_by_market_signal(final_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = final_predictions[final_predictions["v17_3_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v17_3_recommendation", "v17_3_signal_strength"], dropna=False)
    for (recommendation, signal_strength), group in grouped:
        rows.append(
            {
                "recommendation": recommendation,
                "signal_strength": signal_strength,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v17_3_is_correct"].sum()), len(group))),
                "avg_score": rounded(group["v17_3_score"].mean()),
                "avg_market_over_probability": rounded(group["ou25_market_over_probability"].mean()),
                "avg_expected_total_goals_proxy": rounded(group["expected_total_goals_proxy"].mean()),
                "avg_combined_over_2_5_rate": rounded(group["combined_over_2_5_rate_last_10"].mean()),
                "avg_prob_over_2_5_proxy": rounded(group["prob_over_2_5_proxy"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values(["recommendation", "signal_strength"])


# Construit un extrait des erreurs restantes pour analyse V17.3.
def build_error_patterns(final_predictions: pd.DataFrame) -> pd.DataFrame:
    errors = final_predictions[
        (final_predictions["v17_3_recommendation_status"] == RECOMMEND_STATUS)
        & (~final_predictions["v17_3_is_correct"])
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
        "v17_3_recommendation",
        "v17_3_score",
        "ou25_market_over_probability",
        "ou25_market_under_probability",
        "ou25_available_pairs",
        "expected_total_goals_proxy",
        "prob_over_2_5_proxy",
        "combined_over_2_5_rate_last_10",
        "combined_btts_rate_last_10",
        "min_history_count_last_10",
    ]
    return errors[keep_columns].sort_values(["season", "league_code", "match_date"]).head(500)


# Détermine le statut V17.3 selon les métriques et gates prévus.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    coverage = float(metrics.get("coverage", 0.0))
    selected_rows = int(metrics.get("selected_rows", 0))

    major_fragile_segments = 0
    if not by_league_season.empty and "is_major_fragile_segment" in by_league_season.columns:
        major_fragile_segments = int(by_league_season["is_major_fragile_segment"].sum())

    blocking_reasons: list[str] = []
    warnings_list: list[str] = []

    if major_fragile_segments > 0:
        warnings_list.append(f"{major_fragile_segments} segment(s) ligue/saison majeur(s) sous {MIN_MAJOR_SEGMENT_ACCURACY}.")

    if accuracy >= STRONG_ACCURACY_GATE and coverage >= MIN_TEST_COVERAGE_GATE and major_fragile_segments == 0:
        return "V17_3_OVER_UNDER_25_ENRICHED_STRONG_REVIEW", blocking_reasons, warnings_list

    if accuracy >= REVIEW_ACCURACY_GATE and coverage >= MIN_TEST_COVERAGE_GATE and major_fragile_segments == 0:
        return "V17_3_OVER_UNDER_25_ENRICHED_REVIEW", blocking_reasons, warnings_list

    if accuracy >= V14_REFERENCE_ACCURACY and coverage >= MIN_TEST_COVERAGE_GATE and selected_rows >= 2400:
        warnings_list.append("V17.3 améliore légèrement V14, mais reste sous le gate V17.3 de 0.68 d'accuracy.")
        return "V17_3_OVER_UNDER_25_ENRICHED_LIMITED_REVIEW", blocking_reasons, warnings_list

    if accuracy >= 0.62 and coverage >= 0.35:
        warnings_list.append("Le signal O/U 2.5 reste exploitable uniquement comme comparaison expérimentale.")
        return "V17_3_OVER_UNDER_25_ENRICHED_EXPERIMENTAL_ONLY", blocking_reasons, warnings_list

    blocking_reasons.append("Accuracy ou couverture insuffisante pour renforcer le sélecteur V17.x.")
    return "V17_3_OVER_UNDER_25_ENRICHED_REJECTED", blocking_reasons, warnings_list


# Écrit la synthèse détaillée V17.3.
def write_summary(
    evidence_dir: Path,
    dataset: pd.DataFrame,
    csv_count: int,
    csv_with_pairs: int,
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
    selected_rows = int(test_metrics.get("selected_rows", 0))
    over_rows = int(test_metrics.get("over_rows", 0))
    under_rows = int(test_metrics.get("under_rows", 0))
    accuracy_delta = float(test_metrics.get("accuracy", 0.0)) - V14_REFERENCE_ACCURACY
    coverage_delta = float(test_metrics.get("coverage", 0.0)) - V14_REFERENCE_COVERAGE
    selected_rows_delta = selected_rows - V14_REFERENCE_SELECTED_ROWS

    lowest_segment = "Aucun"
    if not by_league_season.empty:
        first = by_league_season.iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"

    lines = [
        "RubyBets - ML Goals V17.3 Over/Under 2.5 enriched selective",
        "244 - Synthèse expérience V17.3",
        "",
        "Objectif :",
        "Retester Over/Under 2.5 avec les features enrichies V17.1 et les cotes O/U 2.5 disponibles, afin de vérifier si V14 peut être améliorée.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data dans data/ml/raw.",
        "- Construction des features enrichies en mémoire via la logique V17.1.",
        "- Ajout des cotes O/U 2.5 uniquement en mémoire.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Périmètre data :",
        f"- CSV analysés : {csv_count}",
        f"- CSV avec paires O/U 2.5 exploitables : {csv_with_pairs}",
        f"- Lignes dataset V17.3 O/U 2.5 enrichi : {len(dataset)}",
        f"- Ligues : {', '.join(leagues)}",
        f"- Saisons : {min(seasons)} -> {max(seasons)}",
        f"- Validation season : {VALIDATION_SEASON}",
        f"- Test seasons : {', '.join(TEST_SEASONS)}",
        "",
        "Distribution des labels :",
        f"- OVER_2_5 rows : {int((dataset[TARGET_COLUMN] == OVER_LABEL).sum())}",
        f"- UNDER_2_5 rows : {int((dataset[TARGET_COLUMN] == UNDER_LABEL).sum())}",
        "",
        "Meilleure stratégie V17.3 sélectionnée sur validation :",
        f"- Strategy : {best_strategy.name}",
        f"- Family : {best_strategy.family}",
        f"- Validation accuracy : {validation_metrics.get('accuracy')}",
        f"- Validation coverage : {validation_metrics.get('coverage')}",
        f"- Validation selected rows : {validation_metrics.get('selected_rows')}",
        f"- Validation OVER_2_5 accuracy : {validation_metrics.get('over_accuracy')}",
        f"- Validation UNDER_2_5 accuracy : {validation_metrics.get('under_accuracy')}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Accuracy : {test_metrics.get('accuracy')}",
        f"- Coverage : {test_metrics.get('coverage')}",
        f"- Abstention rate : {test_metrics.get('abstention_rate')}",
        f"- Selected rows : {selected_rows}",
        f"- OVER_2_5 rows : {over_rows}",
        f"- UNDER_2_5 rows : {under_rows}",
        f"- OVER_2_5 accuracy : {test_metrics.get('over_accuracy')}",
        f"- UNDER_2_5 accuracy : {test_metrics.get('under_accuracy')}",
        "",
        "Comparaison avec V14 :",
        f"- V14 accuracy : {V14_REFERENCE_ACCURACY}",
        f"- V17.3 accuracy delta : {rounded(accuracy_delta)}",
        f"- V14 coverage : {V14_REFERENCE_COVERAGE}",
        f"- V17.3 coverage delta : {rounded(coverage_delta)}",
        f"- V14 selected rows : {V14_REFERENCE_SELECTED_ROWS}",
        f"- V17.3 selected rows delta : {selected_rows_delta}",
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
        "Ne pas intégrer V17.3 au produit. O/U 2.5 reste un candidat expérimental qui doit passer les gates avant toute entrée dans V17.5.",
        "Le scoring explicable V1 reste le socle officiel de RubyBets.",
    ]
    (evidence_dir / OUTPUT_SUMMARY).write_text("\n".join(lines), encoding="utf-8")


# Écrit la décision opérationnelle V17.3.
def write_decision(
    evidence_dir: Path,
    best_strategy: StrategySpec,
    test_metrics: dict[str, object],
    status: str,
    blocking_reasons: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V17.3 Over/Under 2.5 enrichi",
        "249 - Décision expérience V17.3",
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
        f"- OVER_2_5 rows : {test_metrics.get('over_rows')}",
        f"- UNDER_2_5 rows : {test_metrics.get('under_rows')}",
        f"- OVER_2_5 accuracy : {test_metrics.get('over_accuracy')}",
        f"- UNDER_2_5 accuracy : {test_metrics.get('under_accuracy')}",
        "",
        "Gates V17.3 :",
        f"- Accuracy REVIEW cible >= {REVIEW_ACCURACY_GATE}",
        f"- Accuracy candidat fort >= {STRONG_ACCURACY_GATE}",
        f"- Coverage cible >= {MIN_TEST_COVERAGE_GATE}",
        f"- Aucun segment majeur sous {MIN_MAJOR_SEGMENT_ACCURACY}.",
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
                "- V17.3 passe le gate fort et peut être testée comme marché candidat dans V17.5.",
                "- Une comparaison V17.0/V17.5 sera obligatoire avant toute décision finale.",
            ]
        )
    elif "LIMITED_REVIEW" in status:
        lines.extend(
            [
                "- V17.3 améliore légèrement V14 mais reste sous le gate REVIEW de 0.68.",
                "- O/U 2.5 ne doit pas entrer automatiquement dans V17.5.",
                "- Le signal peut être conservé uniquement comme comparaison expérimentale.",
            ]
        )
    elif status.endswith("_REVIEW"):
        lines.extend(
            [
                "- V17.3 passe le gate REVIEW et peut être conservée comme candidat contrôlé pour V17.5.",
                "- L'intégration reste interdite sans comparaison finale du sélecteur enrichi.",
            ]
        )
    elif "EXPERIMENTAL" in status:
        lines.extend(
            [
                "- V17.3 reste une expérimentation utile mais insuffisante pour rejoindre le sélecteur final.",
                "- Conserver les preuves, puis passer à V17.4 BTTS enrichi.",
            ]
        )
    else:
        lines.extend(
            [
                "- V17.3 est rejetée comme amélioration exploitable.",
                "- Ne pas intégrer O/U 2.5 dans V17.5.",
            ]
        )

    lines.extend(
        [
            "- V17.3 ne remplace pas le scoring explicable V1.",
            "- V17.3 ne modifie ni PostgreSQL, ni ml.features, ni l'API, ni le frontend.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V17.3 Over/Under 2.5 enrichi : réalisée si les fichiers 244 à 249 sont générés.",
            "- Fichiers concernés : backend/scripts/ml/train_goals_v17_3_over_under_25_enriched.py et reports/evidence/ml_training/244-249.",
        ]
    )
    (evidence_dir / OUTPUT_DECISION).write_text("\n".join(lines), encoding="utf-8")


# Orchestre V17.3 : dataset enrichi, cotes O/U 2.5, entraînement, sélection, exports et décision.
def main() -> None:
    print("Chargement des features enrichies V17.1 et des cotes O/U 2.5 pour V17.3...")
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)
    dataset, csv_count, csv_with_pairs = build_v17_3_dataset(project_root)
    train, validation, test = split_dataset(dataset)

    print("Entraînement des modèles V17.3 O/U 2.5 enrichis en mémoire...")
    train_scored, validation_scored, test_scored = attach_scores(train, validation, test)
    strategies = build_strategies()

    print("Évaluation des stratégies V17.3 sur validation et test...")
    validation_rows = [evaluate_strategy(validation_scored, strategy, "validation") for strategy in strategies]
    validation_results = pd.DataFrame(validation_rows)
    best_strategy = select_best_strategy(validation_results, strategies)
    validation_metrics = evaluate_strategy(validation_scored, best_strategy, "validation")

    test_rows = [evaluate_strategy(test_scored, strategy, "test") for strategy in strategies]
    all_results = pd.concat([validation_results, pd.DataFrame(test_rows)], ignore_index=True)
    test_metrics = evaluate_strategy(test_scored, best_strategy, "test")

    print("Application de la meilleure stratégie V17.3 sur test final...")
    final_predictions = apply_strategy(test_scored, best_strategy)
    by_league_season = build_by_league_season(final_predictions)
    by_market_signal = build_by_market_signal(final_predictions)
    error_patterns = build_error_patterns(final_predictions)
    status, blocking_reasons, warnings_list = determine_status(test_metrics, by_league_season)

    all_results.to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8-sig")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8-sig")
    by_market_signal.to_csv(evidence_dir / OUTPUT_BY_MARKET_SIGNAL, index=False, encoding="utf-8-sig")
    error_patterns.to_csv(evidence_dir / OUTPUT_ERROR_PATTERNS, index=False, encoding="utf-8-sig")

    write_summary(
        evidence_dir=evidence_dir,
        dataset=dataset,
        csv_count=csv_count,
        csv_with_pairs=csv_with_pairs,
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

    print("OK - Expérience V17.3 Over/Under 2.5 enrichie terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {best_strategy.name}")
    print(f"Test accuracy: {test_metrics.get('accuracy')}")
    print(f"Test coverage: {test_metrics.get('coverage')}")
    print(f"Test abstention rate: {test_metrics.get('abstention_rate')}")
    print(f"Selected rows: {test_metrics.get('selected_rows')}")
    print(f"OVER_2_5 rows: {test_metrics.get('over_rows')}")
    print(f"UNDER_2_5 rows: {test_metrics.get('under_rows')}")
    print(f"OVER_2_5 accuracy: {test_metrics.get('over_accuracy')}")
    print(f"UNDER_2_5 accuracy: {test_metrics.get('under_accuracy')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"By market signal CSV saved: {evidence_dir / OUTPUT_BY_MARKET_SIGNAL}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication :
# data/ml/raw/*.csv -> build_multimarket_v17_1_enriched_features.py -> train_goals_v17_3_over_under_25_enriched.py -> reports/evidence/ml_training/244-249
# Ce script lit les CSV bruts, reconstruit les features V17.1 en mémoire, ajoute les cotes O/U 2.5 en mémoire et écrit uniquement des preuves expérimentales ML.
