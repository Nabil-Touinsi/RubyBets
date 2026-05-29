# Rôle du fichier : tester V17.6 BTTS ultra-sélectif, en mémoire uniquement, pour chercher un signal BTTS assez fiable avant toute intégration au sélecteur.

from __future__ import annotations

import math
import time
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

OUTPUT_SUMMARY = "262_goals_v17_6_btts_ultra_selective_summary.txt"
OUTPUT_RESULTS = "263_goals_v17_6_btts_ultra_selective_results.csv"
OUTPUT_BY_LEAGUE_SEASON = "264_goals_v17_6_btts_ultra_selective_by_league_season.csv"
OUTPUT_BY_SIGNAL = "265_goals_v17_6_btts_ultra_selective_by_signal.csv"
OUTPUT_ERROR_PATTERNS = "266_goals_v17_6_btts_ultra_selective_error_patterns.csv"
OUTPUT_DECISION = "267_goals_v17_6_btts_ultra_selective_decision.txt"

VALIDATION_SEASON = "2021_2022"
TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]
TRAIN_MAX_SEASON_START = 2020

V16_REFERENCE_ACCURACY = 0.5790
V17_4_REFERENCE_ACCURACY = 0.5728
V17_4_REFERENCE_COVERAGE = 0.4782
V17_4_REFERENCE_SELECTED_ROWS = 2549

MIN_VALIDATION_SELECTED_ROWS = 80
MIN_VALIDATION_COVERAGE = 0.02
MIN_ACCEPTABLE_ACCURACY = 0.65
TARGET_ACCURACY = 0.70
MIN_TEST_ROWS_FOR_REVIEW = 80
MIN_TEST_ROWS_FOR_STRONG = 100
MIN_MAJOR_SEGMENT_ROWS = 25
MIN_MAJOR_SEGMENT_ACCURACY = 0.60

SCORE_COLUMNS = [
    "score_logistic_standard_btts_yes",
    "score_logistic_balanced_btts_yes",
    "score_random_forest_btts_yes",
    "score_proxy_btts_yes",
    "score_consensus_btts_yes",
]

YES_THRESHOLDS = [0.58, 0.60, 0.62, 0.64, 0.66, 0.68, 0.70, 0.72]
NO_THRESHOLDS = [None, 0.44, 0.42, 0.40, 0.38, 0.36]
MIN_HISTORY_COUNTS = [8, 10, 12, 14, 16]
MIN_EXPECTED_TEAM_GOALS = [0.90, 1.00, 1.10, 1.20]
MIN_EXPECTED_TOTAL_GOALS = [2.00, 2.20, 2.40, 2.60]
MIN_COMBINED_BTTS_RATES = [0.50, 0.55, 0.60, 0.65]
MAX_FAILED_TO_SCORE_RATES = [0.45, 0.40, 0.35, 0.30]
MIN_OVER_15_RATES = [0.55, 0.60, 0.65]
NO_MIN_FAILED_OR_CLEAN_RATES = [0.45, 0.50, 0.55]

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
    min_expected_team_goals: float
    min_expected_total_goals: float
    min_combined_btts_rate: float
    max_failed_to_score_rate: float
    min_over_15_rate: float
    no_min_failed_or_clean_rate: float
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


# Convertit un seuil numérique en suffixe lisible pour nommer les stratégies.
def threshold_suffix(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.3f}".replace(".", "")


# Construit le dataset enrichi V17.6 depuis les CSV bruts, via la logique V17.1.
def build_v17_6_dataset(project_root: Path) -> tuple[pd.DataFrame, int]:
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
        raise RuntimeError("Split V17.6 impossible : train, validation ou test vide.")
    return train, validation, test


# Prépare les colonnes features numériques et catégorielles utilisées par les modèles V17.6.
def get_model_columns() -> tuple[list[str], list[str]]:
    numeric_columns = list(FEATURE_COLUMNS)
    categorical_columns = ["league_code"]
    return numeric_columns, categorical_columns


# Transforme les labels BTTS YES/NO en cible binaire pour entraîner les modèles.
def build_binary_target(dataframe: pd.DataFrame) -> pd.Series:
    return (dataframe[TARGET_COLUMN].astype(str) == YES_LABEL).astype(int)


# Entraîne un modèle logistique V17.6 pour produire une probabilité BTTS_YES.
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
    classifier = LogisticRegression(max_iter=1200, C=0.35, solver="liblinear", class_weight=class_weight)
    model = Pipeline(steps=[("preprocessor", preprocessor), ("classifier", classifier)])
    model.fit(train[numeric_columns + categorical_columns], build_binary_target(train))
    return model


# Entraîne un Random Forest prudent pour capter des interactions goals/BTTS sans sauvegarder de modèle.
def train_random_forest_model(train: pd.DataFrame) -> Pipeline:
    numeric_columns, categorical_columns = get_model_columns()
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), numeric_columns),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_columns),
        ]
    )
    classifier = RandomForestClassifier(
        n_estimators=140,
        max_depth=5,
        min_samples_leaf=40,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model = Pipeline(steps=[("preprocessor", preprocessor), ("classifier", classifier)])
    model.fit(train[numeric_columns + categorical_columns], build_binary_target(train))
    return model


# Ajoute les scores probabilistes et les scores de consensus nécessaires aux stratégies V17.6.
def attach_scores(train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    numeric_columns, categorical_columns = get_model_columns()
    standard_model = train_logistic_model(train, balanced=False)
    balanced_model = train_logistic_model(train, balanced=True)
    random_forest_model = train_random_forest_model(train)

    outputs: list[pd.DataFrame] = []
    for frame in (train, validation, test):
        output = frame.copy()
        feature_frame = output[numeric_columns + categorical_columns]
        output["score_logistic_standard_btts_yes"] = standard_model.predict_proba(feature_frame)[:, 1]
        output["score_logistic_balanced_btts_yes"] = balanced_model.predict_proba(feature_frame)[:, 1]
        output["score_random_forest_btts_yes"] = random_forest_model.predict_proba(feature_frame)[:, 1]
        output["score_proxy_btts_yes"] = pd.to_numeric(output["prob_btts_proxy"], errors="coerce")
        output["score_combined_btts_rate"] = pd.to_numeric(output["combined_btts_rate_last_10"], errors="coerce")
        output["score_consensus_btts_yes"] = output[
            [
                "score_logistic_standard_btts_yes",
                "score_logistic_balanced_btts_yes",
                "score_random_forest_btts_yes",
                "score_proxy_btts_yes",
                "score_combined_btts_rate",
            ]
        ].mean(axis=1)
        outputs.append(output)

    return outputs[0], outputs[1], outputs[2]


# Crée les stratégies ultra-sélectives à comparer sur validation avant test final.
def build_strategies() -> list[StrategySpec]:
    strategies: list[StrategySpec] = []
    for score_column in SCORE_COLUMNS:
        for yes_threshold in YES_THRESHOLDS:
            for no_threshold in NO_THRESHOLDS:
                if no_threshold is not None and no_threshold >= yes_threshold:
                    continue
                for min_history_count in MIN_HISTORY_COUNTS:
                    for min_expected_team_goals in MIN_EXPECTED_TEAM_GOALS:
                        for min_expected_total_goals in MIN_EXPECTED_TOTAL_GOALS:
                            for min_combined_btts_rate in MIN_COMBINED_BTTS_RATES:
                                for max_failed_to_score_rate in MAX_FAILED_TO_SCORE_RATES:
                                    for min_over_15_rate in MIN_OVER_15_RATES:
                                        # Limitation volontaire : les filtres très proches sont suffisants pour une recherche ciblée sans exploser le temps d'exécution.
                                        if min_expected_total_goals < (min_expected_team_goals * 2.0 - 0.2):
                                            continue
                                        family = "btts_yes_only_ultra" if no_threshold is None else "btts_mixed_ultra"
                                        strategies.append(
                                            StrategySpec(
                                                name=(
                                                    "v17_6_"
                                                    f"{score_column.replace('score_', '').replace('_btts_yes', '').replace('_', '')}"
                                                    f"_yes_t{threshold_suffix(yes_threshold)}"
                                                    f"_no_t{threshold_suffix(no_threshold)}"
                                                    f"_mh{min_history_count}"
                                                    f"_eg{threshold_suffix(min_expected_team_goals)}"
                                                    f"_bt{threshold_suffix(min_combined_btts_rate)}"
                                                ),
                                                family=family,
                                                score_column=score_column,
                                                yes_threshold=yes_threshold,
                                                no_threshold=no_threshold,
                                                min_history_count=min_history_count,
                                                min_expected_team_goals=min_expected_team_goals,
                                                min_expected_total_goals=min_expected_total_goals,
                                                min_combined_btts_rate=min_combined_btts_rate,
                                                max_failed_to_score_rate=max_failed_to_score_rate,
                                                min_over_15_rate=min_over_15_rate,
                                                no_min_failed_or_clean_rate=0.50,
                                                notes="BTTS ultra-sélectif avec seuils forts et filtres de cohérence goals.",
                                            )
                                        )
    return strategies


# Applique les filtres de cohérence qui autorisent un BTTS_YES prudent.
def build_yes_mask(dataframe: pd.DataFrame, strategy: StrategySpec) -> pd.Series:
    score = pd.to_numeric(dataframe[strategy.score_column], errors="coerce")
    min_history = pd.to_numeric(dataframe["min_history_count_last_10"], errors="coerce").fillna(0)
    expected_home = pd.to_numeric(dataframe["expected_home_goals_proxy"], errors="coerce")
    expected_away = pd.to_numeric(dataframe["expected_away_goals_proxy"], errors="coerce")
    expected_total = pd.to_numeric(dataframe["expected_total_goals_proxy"], errors="coerce")
    combined_btts = pd.to_numeric(dataframe["combined_btts_rate_last_10"], errors="coerce")
    combined_over15 = pd.to_numeric(dataframe["combined_over_1_5_rate_last_10"], errors="coerce")
    home_scored = pd.to_numeric(dataframe["home_scored_at_least_1_rate_last_10"], errors="coerce")
    away_scored = pd.to_numeric(dataframe["away_scored_at_least_1_rate_last_10"], errors="coerce")
    home_failed = pd.to_numeric(dataframe["home_failed_to_score_rate_last_10"], errors="coerce")
    away_failed = pd.to_numeric(dataframe["away_failed_to_score_rate_last_10"], errors="coerce")

    return (
        (min_history >= strategy.min_history_count)
        & score.notna()
        & (score >= strategy.yes_threshold)
        & (expected_home >= strategy.min_expected_team_goals)
        & (expected_away >= strategy.min_expected_team_goals)
        & (expected_total >= strategy.min_expected_total_goals)
        & (combined_btts >= strategy.min_combined_btts_rate)
        & (combined_over15 >= strategy.min_over_15_rate)
        & (home_scored >= 0.60)
        & (away_scored >= 0.60)
        & (home_failed <= strategy.max_failed_to_score_rate)
        & (away_failed <= strategy.max_failed_to_score_rate)
    )


# Applique les filtres de cohérence qui autorisent un BTTS_NO très prudent.
def build_no_mask(dataframe: pd.DataFrame, strategy: StrategySpec) -> pd.Series:
    if strategy.no_threshold is None:
        return pd.Series(False, index=dataframe.index)

    score = pd.to_numeric(dataframe[strategy.score_column], errors="coerce")
    min_history = pd.to_numeric(dataframe["min_history_count_last_10"], errors="coerce").fillna(0)
    combined_btts = pd.to_numeric(dataframe["combined_btts_rate_last_10"], errors="coerce")
    home_failed = pd.to_numeric(dataframe["home_failed_to_score_rate_last_10"], errors="coerce")
    away_failed = pd.to_numeric(dataframe["away_failed_to_score_rate_last_10"], errors="coerce")
    home_clean_sheet = pd.to_numeric(dataframe["home_clean_sheet_rate_last_10"], errors="coerce")
    away_clean_sheet = pd.to_numeric(dataframe["away_clean_sheet_rate_last_10"], errors="coerce")
    expected_home = pd.to_numeric(dataframe["expected_home_goals_proxy"], errors="coerce")
    expected_away = pd.to_numeric(dataframe["expected_away_goals_proxy"], errors="coerce")

    one_side_low_goal_proxy = (expected_home <= 0.95) | (expected_away <= 0.95)
    one_side_risk = (
        (home_failed >= strategy.no_min_failed_or_clean_rate)
        | (away_failed >= strategy.no_min_failed_or_clean_rate)
        | (home_clean_sheet >= strategy.no_min_failed_or_clean_rate)
        | (away_clean_sheet >= strategy.no_min_failed_or_clean_rate)
        | one_side_low_goal_proxy
    )

    return (
        (min_history >= strategy.min_history_count)
        & score.notna()
        & (score <= strategy.no_threshold)
        & (combined_btts <= 0.45)
        & one_side_risk
    )


# Applique une stratégie V17.6 sur un DataFrame donné.
def apply_strategy(dataframe: pd.DataFrame, strategy: StrategySpec) -> pd.DataFrame:
    output = dataframe.copy()
    score = pd.to_numeric(output[strategy.score_column], errors="coerce")
    yes_mask = build_yes_mask(output, strategy)
    no_mask = build_no_mask(output, strategy)
    selected_mask = yes_mask | no_mask

    recommendation = np.where(yes_mask, YES_LABEL, np.where(no_mask, NO_LABEL, ABSTAIN_STATUS))
    output["v17_6_strategy"] = strategy.name
    output["v17_6_family"] = strategy.family
    output["v17_6_score_column"] = strategy.score_column
    output["v17_6_score"] = score
    output["v17_6_recommendation_status"] = np.where(selected_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v17_6_recommendation"] = recommendation
    output["v17_6_is_correct"] = (
        (output[TARGET_COLUMN].astype(str) == output["v17_6_recommendation"].astype(str)) & selected_mask
    )
    output["v17_6_signal_strength"] = pd.cut(
        output["v17_6_score"],
        bins=[-math.inf, 0.38, 0.44, 0.56, 0.64, math.inf],
        labels=["ULTRA_NO_ZONE", "NO_ZONE", "CENTRAL_ABSTAIN", "YES_ZONE", "ULTRA_YES_ZONE"],
        include_lowest=True,
    ).astype(str)
    return output



# Formate une durée en secondes pour rendre les logs de progression lisibles.
def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {remaining_seconds:02d}s"
    if minutes:
        return f"{minutes}m {remaining_seconds:02d}s"
    return f"{remaining_seconds}s"


# Évalue une grille de stratégies avec logs de progression pour suivre l'avancement dans le terminal.
def evaluate_strategies_with_progress(
    dataframe: pd.DataFrame,
    strategies: list[StrategySpec],
    split_name: str,
    log_every: int = 500,
) -> list[dict[str, object]]:
    total = len(strategies)
    start_time = time.perf_counter()
    current_score_column = ""
    rows: list[dict[str, object]] = []

    print(
        f"Début évaluation {split_name} : {total} stratégies à tester sur {len(dataframe)} lignes...",
        flush=True,
    )

    for index, strategy in enumerate(strategies, start=1):
        if strategy.score_column != current_score_column:
            current_score_column = strategy.score_column
            print(
                f"[{split_name}] Nouveau bloc score : {current_score_column} "
                f"({index}/{total})",
                flush=True,
            )

        rows.append(evaluate_strategy(dataframe, strategy, split_name))

        if index == 1 or index % log_every == 0 or index == total:
            elapsed = time.perf_counter() - start_time
            progress = index / total if total else 1.0
            estimated_total = elapsed / progress if progress else 0.0
            remaining = max(0.0, estimated_total - elapsed)
            last_result = rows[-1]
            print(
                f"[{split_name}] {index}/{total} stratégies testées "
                f"({progress * 100:.1f}%) | "
                f"elapsed={format_duration(elapsed)} | "
                f"ETA={format_duration(remaining)} | "
                f"last_acc={last_result.get('accuracy')} | "
                f"last_rows={last_result.get('selected_rows')} | "
                f"last_strategy={strategy.name}",
                flush=True,
            )

    print(
        f"Fin évaluation {split_name} : {total} stratégies testées en {format_duration(time.perf_counter() - start_time)}.",
        flush=True,
    )
    return rows


# Calcule les métriques principales d'une stratégie V17.6.
def evaluate_strategy(dataframe: pd.DataFrame, strategy: StrategySpec, split_name: str) -> dict[str, object]:
    predictions = apply_strategy(dataframe, strategy)
    selected = predictions[predictions["v17_6_recommendation_status"] == RECOMMEND_STATUS]
    yes_selected = selected[selected["v17_6_recommendation"] == YES_LABEL]
    no_selected = selected[selected["v17_6_recommendation"] == NO_LABEL]
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
        "min_expected_team_goals": strategy.min_expected_team_goals,
        "min_expected_total_goals": strategy.min_expected_total_goals,
        "min_combined_btts_rate": strategy.min_combined_btts_rate,
        "max_failed_to_score_rate": strategy.max_failed_to_score_rate,
        "min_over_15_rate": strategy.min_over_15_rate,
        "accuracy": rounded(safe_rate(int(selected["v17_6_is_correct"].sum()), selected_rows)),
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "selected_rows": selected_rows,
        "total_rows": total_rows,
        "yes_rows": yes_rows,
        "no_rows": no_rows,
        "yes_share": rounded(safe_rate(yes_rows, selected_rows)),
        "no_share": rounded(safe_rate(no_rows, selected_rows)),
        "yes_accuracy": rounded(safe_rate(int(yes_selected["v17_6_is_correct"].sum()), yes_rows)),
        "no_accuracy": rounded(safe_rate(int(no_selected["v17_6_is_correct"].sum()), no_rows)),
        "avg_selected_score": rounded(selected["v17_6_score"].mean()) if selected_rows else 0.0,
        "notes": strategy.notes,
    }


# Sélectionne la meilleure stratégie sur validation sans regarder le résultat de test.
def select_best_strategy(validation_results: pd.DataFrame, strategies: list[StrategySpec]) -> StrategySpec:
    candidates = validation_results[
        (validation_results["split"] == "validation")
        & (validation_results["coverage"] >= MIN_VALIDATION_COVERAGE)
        & (validation_results["selected_rows"] >= MIN_VALIDATION_SELECTED_ROWS)
    ].copy()

    if candidates.empty:
        candidates = validation_results[
            (validation_results["split"] == "validation")
            & (validation_results["selected_rows"] >= 40)
        ].copy()
    if candidates.empty:
        candidates = validation_results[validation_results["split"] == "validation"].copy()

    candidates["target_gate_validation"] = candidates["accuracy"] >= TARGET_ACCURACY
    candidates["acceptable_gate_validation"] = candidates["accuracy"] >= MIN_ACCEPTABLE_ACCURACY
    candidates = candidates.sort_values(
        by=["target_gate_validation", "acceptable_gate_validation", "accuracy", "selected_rows", "coverage"],
        ascending=[False, False, False, False, False],
    )
    selected_name = str(candidates.iloc[0]["strategy"])

    for strategy in strategies:
        if strategy.name == selected_name:
            return strategy
    raise RuntimeError("Impossible de retrouver la stratégie V17.6 sélectionnée.")


# Construit le tableau de stabilité par ligue/saison pour la stratégie retenue.
def build_by_league_season(final_predictions: pd.DataFrame) -> pd.DataFrame:
    total_groups = final_predictions.groupby(["league_code", "season"], dropna=False).size().reset_index(name="total_rows")
    selected = final_predictions[final_predictions["v17_6_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["league_code", "season"], dropna=False)
    for (league_code, season), group in grouped:
        total_rows = int(
            total_groups[(total_groups["league_code"] == league_code) & (total_groups["season"] == season)]["total_rows"].iloc[0]
        )
        yes_group = group[group["v17_6_recommendation"] == YES_LABEL]
        no_group = group[group["v17_6_recommendation"] == NO_LABEL]
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "total_rows": total_rows,
                "selected_rows": len(group),
                "coverage": rounded(safe_rate(len(group), total_rows)),
                "accuracy": rounded(safe_rate(int(group["v17_6_is_correct"].sum()), len(group))),
                "yes_rows": len(yes_group),
                "no_rows": len(no_group),
                "yes_accuracy": rounded(safe_rate(int(yes_group["v17_6_is_correct"].sum()), len(yes_group))),
                "no_accuracy": rounded(safe_rate(int(no_group["v17_6_is_correct"].sum()), len(no_group))),
                "avg_score": rounded(group["v17_6_score"].mean()),
                "avg_prob_btts_proxy": rounded(group["prob_btts_proxy"].mean()),
                "avg_combined_btts_rate": rounded(group["combined_btts_rate_last_10"].mean()),
                "is_major_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS,
                "is_major_fragile_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS
                and safe_rate(int(group["v17_6_is_correct"].sum()), len(group)) < MIN_MAJOR_SEGMENT_ACCURACY,
            }
        )

    return pd.DataFrame(rows).sort_values(["accuracy", "selected_rows"], ascending=[True, False])


# Construit le tableau de performance par signal recommandé et force de score.
def build_by_signal(final_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = final_predictions[final_predictions["v17_6_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = selected.groupby(["v17_6_recommendation", "v17_6_signal_strength"], dropna=False)
    for (recommendation, signal_strength), group in grouped:
        rows.append(
            {
                "recommendation": recommendation,
                "signal_strength": signal_strength,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v17_6_is_correct"].sum()), len(group))),
                "avg_score": rounded(group["v17_6_score"].mean()),
                "avg_prob_btts_proxy": rounded(group["prob_btts_proxy"].mean()),
                "avg_combined_btts_rate": rounded(group["combined_btts_rate_last_10"].mean()),
                "avg_expected_home_goals_proxy": rounded(group["expected_home_goals_proxy"].mean()),
                "avg_expected_away_goals_proxy": rounded(group["expected_away_goals_proxy"].mean()),
                "avg_home_failed_to_score_rate": rounded(group["home_failed_to_score_rate_last_10"].mean()),
                "avg_away_failed_to_score_rate": rounded(group["away_failed_to_score_rate_last_10"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values(["recommendation", "signal_strength"])


# Construit un extrait des erreurs restantes pour analyser les limites du BTTS ultra-sélectif.
def build_error_patterns(final_predictions: pd.DataFrame) -> pd.DataFrame:
    errors = final_predictions[
        (final_predictions["v17_6_recommendation_status"] == RECOMMEND_STATUS)
        & (~final_predictions["v17_6_is_correct"])
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
        "v17_6_recommendation",
        "v17_6_score_column",
        "v17_6_score",
        "prob_btts_proxy",
        "combined_btts_rate_last_10",
        "expected_home_goals_proxy",
        "expected_away_goals_proxy",
        "expected_total_goals_proxy",
        "home_failed_to_score_rate_last_10",
        "away_failed_to_score_rate_last_10",
        "home_clean_sheet_rate_last_10",
        "away_clean_sheet_rate_last_10",
        "min_history_count_last_10",
    ]
    return errors[keep_columns].sort_values(["season", "league_code", "match_date"]).head(500)


# Détermine le statut V17.6 selon les métriques et les gates ultra-sélectifs.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    selected_rows = int(metrics.get("selected_rows", 0))
    coverage = float(metrics.get("coverage", 0.0))

    major_fragile_segments = 0
    if not by_league_season.empty and "is_major_fragile_segment" in by_league_season.columns:
        major_fragile_segments = int(by_league_season["is_major_fragile_segment"].sum())

    blocking_reasons: list[str] = []
    warnings_list: list[str] = []

    if major_fragile_segments > 0:
        warnings_list.append(f"{major_fragile_segments} segment(s) BTTS majeur(s) sous {MIN_MAJOR_SEGMENT_ACCURACY}.")
    if selected_rows < MIN_TEST_ROWS_FOR_REVIEW:
        warnings_list.append(f"Volume BTTS très faible : {selected_rows} lignes sélectionnées sur test.")
    if accuracy < TARGET_ACCURACY:
        warnings_list.append(f"Accuracy sous l'objectif V17.6 de {TARGET_ACCURACY}.")
    if coverage < 0.01:
        warnings_list.append("Coverage très faible : BTTS devient un signal très rare.")

    if accuracy >= TARGET_ACCURACY and selected_rows >= MIN_TEST_ROWS_FOR_STRONG and major_fragile_segments == 0:
        return "V17_6_BTTS_ULTRA_SELECTIVE_STRONG_REVIEW", blocking_reasons, warnings_list

    if accuracy >= MIN_ACCEPTABLE_ACCURACY and selected_rows >= MIN_TEST_ROWS_FOR_REVIEW:
        return "V17_6_BTTS_ULTRA_SELECTIVE_REVIEW", blocking_reasons, warnings_list

    if accuracy >= V17_4_REFERENCE_ACCURACY and selected_rows >= 40:
        return "V17_6_BTTS_ULTRA_SELECTIVE_LIMITED_REVIEW", blocking_reasons, warnings_list

    blocking_reasons.append("BTTS ultra-sélectif ne produit pas encore un signal assez fiable pour intégrer le sélecteur.")
    return "V17_6_BTTS_ULTRA_SELECTIVE_REJECTED", blocking_reasons, warnings_list


# Écrit la synthèse détaillée V17.6.
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
    accuracy_delta_v17_4 = float(test_metrics.get("accuracy", 0.0)) - V17_4_REFERENCE_ACCURACY
    selected_delta_v17_4 = int(test_metrics.get("selected_rows", 0)) - V17_4_REFERENCE_SELECTED_ROWS

    lowest_segment = "Aucun"
    if not by_league_season.empty:
        first = by_league_season.iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"

    lines = [
        "RubyBets - ML Goals V17.6 BTTS ultra-selective",
        "262 - Synthèse expérience V17.6",
        "",
        "Objectif :",
        "Tester une manière propre et très sélective d'intégrer BTTS comme signal rare, sans forcer le marché dans le sélecteur multi-marchés.",
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
        "Meilleure stratégie V17.6 sélectionnée sur validation :",
        f"- Strategy : {best_strategy.name}",
        f"- Family : {best_strategy.family}",
        f"- Score column : {best_strategy.score_column}",
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
        "Comparaison avec V17.4 :",
        f"- V17.4 accuracy : {V17_4_REFERENCE_ACCURACY}",
        f"- V17.6 accuracy delta : {rounded(accuracy_delta_v17_4)}",
        f"- V17.4 selected rows : {V17_4_REFERENCE_SELECTED_ROWS}",
        f"- V17.6 selected rows delta : {selected_delta_v17_4}",
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
        "Ne pas intégrer V17.6 au produit à ce stade. Si le signal atteint les gates, il devra être comparé dans un sélecteur V17.7 avant toute décision.",
        "Le scoring explicable V1 reste le socle officiel de RubyBets.",
    ]
    (evidence_dir / OUTPUT_SUMMARY).write_text("\n".join(lines), encoding="utf-8")


# Écrit la décision opérationnelle V17.6.
def write_decision(
    evidence_dir: Path,
    best_strategy: StrategySpec,
    test_metrics: dict[str, object],
    status: str,
    blocking_reasons: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V17.6 BTTS ultra-sélectif",
        "267 - Décision expérience V17.6",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {best_strategy.name}",
        f"- Family : {best_strategy.family}",
        f"- Score column : {best_strategy.score_column}",
        f"- Accuracy : {test_metrics.get('accuracy')}",
        f"- Coverage : {test_metrics.get('coverage')}",
        f"- Abstention rate : {test_metrics.get('abstention_rate')}",
        f"- Selected rows : {test_metrics.get('selected_rows')}",
        f"- BTTS_YES rows : {test_metrics.get('yes_rows')}",
        f"- BTTS_NO rows : {test_metrics.get('no_rows')}",
        f"- BTTS_YES accuracy : {test_metrics.get('yes_accuracy')}",
        f"- BTTS_NO accuracy : {test_metrics.get('no_accuracy')}",
        "",
        "Gates V17.6 :",
        f"- Accuracy cible forte >= {TARGET_ACCURACY}",
        f"- Accuracy minimale acceptable >= {MIN_ACCEPTABLE_ACCURACY}",
        f"- Selected rows forts >= {MIN_TEST_ROWS_FOR_STRONG}",
        f"- Selected rows review >= {MIN_TEST_ROWS_FOR_REVIEW}",
        "- Aucun marché BTTS ne doit entrer automatiquement dans le sélecteur final sans comparaison V17.7.",
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

    if "STRONG_REVIEW" in status:
        lines.extend(
            [
                "- V17.6 produit un signal BTTS assez fort pour être testé dans un sélecteur V17.7.",
                "- BTTS doit rester rare et priorisé après 1X2 strict, double chance et OVER_1_5.",
            ]
        )
    elif status.endswith("_REVIEW"):
        lines.extend(
            [
                "- V17.6 produit un signal BTTS utilisable en comparaison expérimentale.",
                "- Une intégration V17.7 reste obligatoire avant toute décision finale.",
            ]
        )
    elif "LIMITED_REVIEW" in status:
        lines.extend(
            [
                "- V17.6 améliore la sélectivité BTTS mais reste insuffisant pour une intégration directe.",
                "- Le signal peut être conservé comme piste expérimentale uniquement.",
            ]
        )
    else:
        lines.extend(
            [
                "- V17.6 ne valide pas BTTS comme signal intégrable.",
                "- BTTS reste exclu du sélecteur final.",
            ]
        )

    lines.extend(
        [
            "- V17.6 ne remplace pas le scoring explicable V1.",
            "- V17.6 ne modifie ni PostgreSQL, ni ml.features, ni l'API, ni le frontend.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V17.6 BTTS ultra-sélectif : réalisée si les fichiers 262 à 267 sont générés.",
            "- Fichiers concernés : backend/scripts/ml/train_goals_v17_6_btts_ultra_selective.py et reports/evidence/ml_training/262-267.",
        ]
    )
    (evidence_dir / OUTPUT_DECISION).write_text("\n".join(lines), encoding="utf-8")


# Orchestre V17.6 : dataset enrichi, entraînement, sélection ultra-sélective, exports et décision.
def main() -> None:
    print("Chargement des features enrichies V17.1 pour V17.6 BTTS ultra-sélectif...", flush=True)
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)
    dataset, csv_count = build_v17_6_dataset(project_root)
    train, validation, test = split_dataset(dataset)
    print(
        f"Dataset prêt : {len(dataset)} lignes | train={len(train)} | validation={len(validation)} | test={len(test)} | CSV={csv_count}",
        flush=True,
    )

    print("Entraînement des scores V17.6 BTTS en mémoire...", flush=True)
    train_scored, validation_scored, test_scored = attach_scores(train, validation, test)
    print("Scores ajoutés : logistic standard, logistic balanced, random forest, proxy et consensus.", flush=True)
    strategies = build_strategies()
    print(f"Grille V17.6 construite : {len(strategies)} stratégies à tester.", flush=True)
    print(
        "Filtres conservés : seuil BTTS, expected goals home/away/total, combined_btts_rate, "
        "combined_over_1_5_rate, failed_to_score risk, minimum history.",
        flush=True,
    )

    print("Évaluation des stratégies V17.6 sur validation...", flush=True)
    validation_rows = evaluate_strategies_with_progress(validation_scored, strategies, "validation", log_every=500)
    validation_results = pd.DataFrame(validation_rows)
    best_strategy = select_best_strategy(validation_results, strategies)
    validation_metrics = evaluate_strategy(validation_scored, best_strategy, "validation")
    print(
        f"Meilleure stratégie validation : {best_strategy.name} | "
        f"acc={validation_metrics.get('accuracy')} | rows={validation_metrics.get('selected_rows')} | "
        f"coverage={validation_metrics.get('coverage')}",
        flush=True,
    )

    print("Évaluation des stratégies V17.6 sur test final avec logs de progression...", flush=True)
    test_rows = evaluate_strategies_with_progress(test_scored, strategies, "test", log_every=500)
    all_results = pd.concat([validation_results, pd.DataFrame(test_rows)], ignore_index=True)
    test_metrics = evaluate_strategy(test_scored, best_strategy, "test")
    final_predictions = apply_strategy(test_scored, best_strategy)

    by_league_season = build_by_league_season(final_predictions)
    by_signal = build_by_signal(final_predictions)
    error_patterns = build_error_patterns(final_predictions)
    status, blocking_reasons, warnings_list = determine_status(test_metrics, by_league_season)

    print("Export des preuves V17.6 dans reports/evidence/ml_training/...", flush=True)
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

    print("OK - Expérience V17.6 BTTS ultra-sélectif terminée.")
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
# data/ml/raw/*.csv -> build_multimarket_v17_1_enriched_features.py -> train_goals_v17_6_btts_ultra_selective.py -> reports/evidence/ml_training/262-267
# Ce script lit les CSV bruts, réutilise les features enrichies V17.1 en mémoire, teste BTTS ultra-sélectif et écrit uniquement des preuves expérimentales ML.
