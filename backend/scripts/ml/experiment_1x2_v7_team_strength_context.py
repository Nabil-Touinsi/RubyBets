# Rôle du fichier : lancer l'expérimentation ML 1X2 V7 avec des blocs de force d'équipe, Elo, contexte domicile/extérieur, momentum, goal difference et calendrier, sans modifier la base, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from collections import defaultdict
from itertools import groupby
from pathlib import Path
import math
import sys
import warnings

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "79_1x2_v7_team_strength_context_summary.txt"
CSV_PATH = REPORT_DIR / "80_1x2_v7_team_strength_context_results.csv"
DECISION_PATH = REPORT_DIR / "81_1x2_v7_team_strength_context_decision.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    TARGET_COLUMN,
    TEST_SEASONS,
    calculate_overall_stats,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)
from experiment_1x2_v5_balance_features import (  # noqa: E402
    CLASS_LABELS,
    V2_REFERENCE_ACCURACY,
    V2_REFERENCE_DRAW_PRECISION,
    V2_REFERENCE_DRAW_RECALL,
    V2_REFERENCE_F1_MACRO,
    V2_REFERENCE_MODEL_NAME,
    add_v5_balance_features,
    build_reference_model,
    build_v5_feature_sets,
    build_v2_fast_feature_dataframe,
    prepare_train_test,
)

try:
    from experiment_1x2_v6_market_prior import (  # noqa: E402
        MARKET_GAP_COLUMNS,
        MARKET_PROBABILITY_COLUMNS,
        build_market_prior_dataframe,
        fetch_market_raw_data,
        filter_market_ready_scope,
        merge_market_prior_features,
    )

    MARKET_PRIOR_AVAILABLE = True
    MARKET_IMPORT_ERROR = ""
except Exception as import_error:  # pragma: no cover - garde-fou local si le script V6 n'est pas encore présent.
    MARKET_PRIOR_AVAILABLE = False
    MARKET_IMPORT_ERROR = str(import_error)
    MARKET_PROBABILITY_COLUMNS = []
    MARKET_GAP_COLUMNS = []

warnings.filterwarnings("ignore", category=UserWarning)

INITIAL_ELO = 1500.0
ELO_K_FACTOR = 22.0
ELO_SCALE = 400.0
ELO_HOME_ADVANTAGE = 55.0
ELO_RECENT_DELTA_WINDOW = 5
DEFAULT_REST_DAYS = 14
MAX_REST_DAYS = 21
EXPECTED_SEASON_MATCHES = 38

V2_REFERENCE_FEATURE_SET_NAME = "v2_reference"
V5_REFERENCE_FEATURE_SET_NAME = "v5_draw_context_scores"
V7_MARKET_BENCHMARK_NAME = "v7_all_plus_market_benchmark"

INTERESTING_ACCURACY = 0.5250
INTERESTING_F1_MACRO = 0.4900
INTERESTING_DRAW_RECALL = 0.3000
INTERESTING_DRAW_PRECISION = 0.3200
SERIOUS_ACCURACY = 0.5350
SERIOUS_F1_MACRO = 0.5000
SERIOUS_DRAW_RECALL = 0.3200
SERIOUS_DRAW_PRECISION = 0.3300

V7_ELO_COLUMNS = [
    "home_elo_pre_match",
    "away_elo_pre_match",
    "elo_diff",
    "elo_abs_diff",
    "elo_home_advantage_adjusted_diff",
    "elo_expected_home",
    "elo_expected_away",
    "elo_expected_gap",
    "elo_balance_score",
    "home_elo_recent_delta",
    "away_elo_recent_delta",
    "elo_recent_delta_diff",
    "elo_recent_delta_abs_diff",
]

V7_HOME_AWAY_FORM_COLUMNS = [
    "home_home_points_avg_last_10",
    "away_away_points_avg_last_10",
    "home_home_goals_scored_avg_last_10",
    "away_away_goals_scored_avg_last_10",
    "home_home_goals_conceded_avg_last_10",
    "away_away_goals_conceded_avg_last_10",
    "home_away_points_avg_diff",
    "home_away_scored_avg_diff",
    "home_away_conceded_avg_diff",
    "home_venue_goal_diff_avg_last_10",
    "away_venue_goal_diff_avg_last_10",
    "venue_goal_diff_gap",
    "abs_venue_goal_diff_gap",
]

V7_MOMENTUM_COLUMNS = [
    "home_points_per_match_last_5_overall",
    "away_points_per_match_last_5_overall",
    "home_points_per_match_last_15_overall",
    "away_points_per_match_last_15_overall",
    "home_goals_scored_avg_last_15",
    "away_goals_scored_avg_last_15",
    "home_goals_conceded_avg_last_15",
    "away_goals_conceded_avg_last_15",
    "home_momentum_delta",
    "away_momentum_delta",
    "momentum_delta_diff",
    "abs_momentum_delta_diff",
]

V7_GOAL_DIFF_COLUMNS = [
    "home_goal_diff_avg_last_10",
    "away_goal_diff_avg_last_10",
    "home_goal_diff_avg_last_15",
    "away_goal_diff_avg_last_15",
    "goal_diff_gap_last_10",
    "abs_goal_diff_gap_last_10",
    "goal_diff_gap_last_15",
    "abs_goal_diff_gap_last_15",
    "goal_diff_trend_home",
    "goal_diff_trend_away",
    "goal_diff_trend_gap",
]

V7_CALENDAR_COLUMNS = [
    "home_rest_days_capped",
    "away_rest_days_capped",
    "rest_days_diff",
    "abs_rest_days_diff",
    "home_rest_days_missing",
    "away_rest_days_missing",
    "home_season_matches_played_before",
    "away_season_matches_played_before",
    "matchday_progress",
    "season_phase_early",
    "season_phase_late",
]

V7_ALL_CONTEXT_COLUMNS = (
    V7_ELO_COLUMNS
    + V7_HOME_AWAY_FORM_COLUMNS
    + V7_MOMENTUM_COLUMNS
    + V7_GOAL_DIFF_COLUMNS
    + V7_CALENDAR_COLUMNS
)


# Arrondit une valeur numérique pour stabiliser les exports texte et CSV.
def rounded(value: float | int | None, digits: int = 4) -> float:
    if value is None:
        return 0.0

    return round(float(value), digits)


# Supprime les doublons dans une liste de colonnes en gardant l'ordre initial.
def dedupe_columns(columns: list[str]) -> list[str]:
    seen = set()
    result = []

    for column in columns:
        if column not in seen:
            result.append(column)
            seen.add(column)

    return result


# Calcule une différence si les deux valeurs existent.
def safe_diff(left_value: float | None, right_value: float | None, digits: int = 4) -> float | None:
    if left_value is None or right_value is None:
        return None

    return round(float(left_value) - float(right_value), digits)


# Calcule une différence absolue si les deux valeurs existent.
def safe_abs_diff(left_value: float | None, right_value: float | None, digits: int = 4) -> float | None:
    difference = safe_diff(left_value, right_value, digits)

    if difference is None:
        return None

    return round(abs(difference), digits)


# Calcule l'espérance Elo de l'équipe à domicile avant le match.
def calculate_home_elo_expected(home_elo: float, away_elo: float) -> float:
    adjusted_home_elo = home_elo + ELO_HOME_ADVANTAGE

    return 1 / (1 + 10 ** ((away_elo - adjusted_home_elo) / ELO_SCALE))


# Convertit un résultat 1X2 en score Elo pour l'équipe domicile et extérieur.
def get_elo_actual_scores(result: str) -> tuple[float, float]:
    if result == "HOME_WIN":
        return 1.0, 0.0

    if result == "AWAY_WIN":
        return 0.0, 1.0

    return 0.5, 0.5


# Calcule un multiplicateur simple selon l'écart de buts pour éviter de traiter 1-0 et 5-0 pareil.
def calculate_goal_margin_multiplier(home_goals: int, away_goals: int) -> float:
    goal_margin = abs(int(home_goals) - int(away_goals))

    return 1.0 + min(goal_margin, 4) * 0.12


# Calcule la variation Elo récente d'une équipe avant le match.
def calculate_recent_elo_delta(elo_history: list[float], current_elo: float) -> float | None:
    if len(elo_history) < ELO_RECENT_DELTA_WINDOW:
        return None

    previous_elo = elo_history[-ELO_RECENT_DELTA_WINDOW]

    return round(current_elo - previous_elo, 2)


# Calcule les statistiques globales seulement si la fenêtre demandée est complète.
def calculate_window_stats(history: list[dict], team_name: str, window: int) -> tuple[float | None, float | None, float | None]:
    if len(history) < window:
        return None, None, None

    return calculate_overall_stats(history[-window:], team_name)


# Transforme un total de points en points moyens par match si la fenêtre est complète.
def points_per_match(total_points: float | None, window: int) -> float | None:
    if total_points is None:
        return None

    return round(float(total_points) / window, 4)


# Calcule un goal difference moyen à partir des buts marqués et encaissés.
def goal_diff_average(scored_avg: float | None, conceded_avg: float | None) -> float | None:
    if scored_avg is None or conceded_avg is None:
        return None

    return round(float(scored_avg) - float(conceded_avg), 4)


# Calcule les jours de repos avant un match avec un garde-fou pour les premiers matchs connus.
def calculate_rest_days(current_date, previous_date) -> tuple[int, int]:
    if previous_date is None:
        return DEFAULT_REST_DAYS, 1

    days = (current_date - previous_date).days
    capped_days = max(0, min(days, MAX_REST_DAYS))

    return capped_days, 0


# Construit les features V7 connues avant le match sans utiliser le résultat futur.
def build_v7_context_row(
    match: dict,
    overall_history: dict,
    season_history: dict,
    last_match_dates: dict,
    elo_ratings: dict,
    elo_history: dict,
) -> dict:
    league_code = match["league_code"]
    season = match["season"]
    home_team = match["home_team"]
    away_team = match["away_team"]
    match_date = match["match_date"]

    home_key = (league_code, home_team)
    away_key = (league_code, away_team)
    home_season_key = (league_code, season, home_team)
    away_season_key = (league_code, season, away_team)

    home_elo = elo_ratings[home_key]
    away_elo = elo_ratings[away_key]
    elo_diff = round(home_elo - away_elo, 4)
    home_expected = round(calculate_home_elo_expected(home_elo, away_elo), 6)
    away_expected = round(1 - home_expected, 6)
    elo_expected_gap = round(abs(home_expected - away_expected), 6)

    home_elo_recent_delta = calculate_recent_elo_delta(elo_history[home_key], home_elo)
    away_elo_recent_delta = calculate_recent_elo_delta(elo_history[away_key], away_elo)

    home_history = overall_history[home_key]
    away_history = overall_history[away_key]

    home_points_5, home_scored_5, home_conceded_5 = calculate_window_stats(home_history, home_team, 5)
    away_points_5, away_scored_5, away_conceded_5 = calculate_window_stats(away_history, away_team, 5)
    home_points_15, home_scored_15, home_conceded_15 = calculate_window_stats(home_history, home_team, 15)
    away_points_15, away_scored_15, away_conceded_15 = calculate_window_stats(away_history, away_team, 15)

    home_ppm_5 = points_per_match(home_points_5, 5)
    away_ppm_5 = points_per_match(away_points_5, 5)
    home_ppm_15 = points_per_match(home_points_15, 15)
    away_ppm_15 = points_per_match(away_points_15, 15)

    home_momentum_delta = safe_diff(home_ppm_5, home_ppm_15)
    away_momentum_delta = safe_diff(away_ppm_5, away_ppm_15)

    home_goal_diff_15 = goal_diff_average(home_scored_15, home_conceded_15)
    away_goal_diff_15 = goal_diff_average(away_scored_15, away_conceded_15)

    home_rest_days, home_rest_missing = calculate_rest_days(match_date, last_match_dates.get(home_key))
    away_rest_days, away_rest_missing = calculate_rest_days(match_date, last_match_dates.get(away_key))

    home_season_matches_played = len(season_history[home_season_key])
    away_season_matches_played = len(season_history[away_season_key])
    matchday_progress = round(
        min(
            1.0,
            (home_season_matches_played + away_season_matches_played) / (2 * EXPECTED_SEASON_MATCHES),
        ),
        4,
    )

    return {
        "clean_match_id": match["id"],
        "home_elo_pre_match": round(home_elo, 4),
        "away_elo_pre_match": round(away_elo, 4),
        "elo_diff": elo_diff,
        "elo_abs_diff": abs(elo_diff),
        "elo_home_advantage_adjusted_diff": round((home_elo + ELO_HOME_ADVANTAGE) - away_elo, 4),
        "elo_expected_home": home_expected,
        "elo_expected_away": away_expected,
        "elo_expected_gap": elo_expected_gap,
        "elo_balance_score": round(1 / (1 + abs(elo_diff) / 75.0), 6),
        "home_elo_recent_delta": home_elo_recent_delta,
        "away_elo_recent_delta": away_elo_recent_delta,
        "elo_recent_delta_diff": safe_diff(home_elo_recent_delta, away_elo_recent_delta),
        "elo_recent_delta_abs_diff": safe_abs_diff(home_elo_recent_delta, away_elo_recent_delta),
        "home_points_per_match_last_5_overall": home_ppm_5,
        "away_points_per_match_last_5_overall": away_ppm_5,
        "home_points_per_match_last_15_overall": home_ppm_15,
        "away_points_per_match_last_15_overall": away_ppm_15,
        "home_goals_scored_avg_last_15": home_scored_15,
        "away_goals_scored_avg_last_15": away_scored_15,
        "home_goals_conceded_avg_last_15": home_conceded_15,
        "away_goals_conceded_avg_last_15": away_conceded_15,
        "home_momentum_delta": home_momentum_delta,
        "away_momentum_delta": away_momentum_delta,
        "momentum_delta_diff": safe_diff(home_momentum_delta, away_momentum_delta),
        "abs_momentum_delta_diff": safe_abs_diff(home_momentum_delta, away_momentum_delta),
        "home_goal_diff_avg_last_15": home_goal_diff_15,
        "away_goal_diff_avg_last_15": away_goal_diff_15,
        "goal_diff_gap_last_15": safe_diff(home_goal_diff_15, away_goal_diff_15),
        "abs_goal_diff_gap_last_15": safe_abs_diff(home_goal_diff_15, away_goal_diff_15),
        "home_rest_days_capped": home_rest_days,
        "away_rest_days_capped": away_rest_days,
        "rest_days_diff": round(home_rest_days - away_rest_days, 4),
        "abs_rest_days_diff": abs(home_rest_days - away_rest_days),
        "home_rest_days_missing": home_rest_missing,
        "away_rest_days_missing": away_rest_missing,
        "home_season_matches_played_before": home_season_matches_played,
        "away_season_matches_played_before": away_season_matches_played,
        "matchday_progress": matchday_progress,
        "season_phase_early": int(matchday_progress <= 0.25),
        "season_phase_late": int(matchday_progress >= 0.75),
    }


# Met à jour les ratings Elo après les matchs d'une même date pour éviter toute fuite de données.
def update_elo_after_matches(matches_for_date: list[dict], elo_ratings: dict, elo_history: dict) -> None:
    updates = []

    for match in matches_for_date:
        league_code = match["league_code"]
        home_key = (league_code, match["home_team"])
        away_key = (league_code, match["away_team"])

        home_elo = elo_ratings[home_key]
        away_elo = elo_ratings[away_key]
        expected_home = calculate_home_elo_expected(home_elo, away_elo)
        expected_away = 1 - expected_home
        actual_home, actual_away = get_elo_actual_scores(match["result"])
        margin_multiplier = calculate_goal_margin_multiplier(match["home_goals"], match["away_goals"])

        new_home_elo = home_elo + ELO_K_FACTOR * margin_multiplier * (actual_home - expected_home)
        new_away_elo = away_elo + ELO_K_FACTOR * margin_multiplier * (actual_away - expected_away)

        updates.append((home_key, new_home_elo))
        updates.append((away_key, new_away_elo))

    for team_key, new_elo in updates:
        elo_ratings[team_key] = new_elo
        elo_history[team_key].append(new_elo)


# Met à jour les historiques de matchs après calcul des features du jour.
def update_context_histories(
    matches_for_date: list[dict],
    overall_history: dict,
    season_history: dict,
    last_match_dates: dict,
) -> None:
    for match in matches_for_date:
        league_code = match["league_code"]
        season = match["season"]
        home_team = match["home_team"]
        away_team = match["away_team"]
        match_date = match["match_date"]

        home_key = (league_code, home_team)
        away_key = (league_code, away_team)

        overall_history[home_key].append(match)
        overall_history[away_key].append(match)
        season_history[(league_code, season, home_team)].append(match)
        season_history[(league_code, season, away_team)].append(match)
        last_match_dates[home_key] = match_date
        last_match_dates[away_key] = match_date


# Construit le DataFrame V7 complet en respectant l'ordre chronologique.
def build_v7_context_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    rows = []
    overall_history = defaultdict(list)
    season_history = defaultdict(list)
    last_match_dates = {}
    elo_ratings = defaultdict(lambda: INITIAL_ELO)
    elo_history = defaultdict(list)

    for _, matches_group in groupby(clean_matches, key=lambda row: row["match_date"]):
        matches_for_date = list(matches_group)

        for match in matches_for_date:
            rows.append(
                build_v7_context_row(
                    match=match,
                    overall_history=overall_history,
                    season_history=season_history,
                    last_match_dates=last_match_dates,
                    elo_ratings=elo_ratings,
                    elo_history=elo_history,
                )
            )

        update_elo_after_matches(
            matches_for_date=matches_for_date,
            elo_ratings=elo_ratings,
            elo_history=elo_history,
        )
        update_context_histories(
            matches_for_date=matches_for_date,
            overall_history=overall_history,
            season_history=season_history,
            last_match_dates=last_match_dates,
        )

    return pd.DataFrame(rows)


# Ajoute les features V7 dérivées qui reposent sur les colonnes V2/V5 déjà présentes.
def add_v7_derived_features(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = feature_dataframe.copy()
    required_columns = [
        "home_home_points_avg_last_10",
        "away_away_points_avg_last_10",
        "home_home_goals_scored_avg_last_10",
        "away_away_goals_scored_avg_last_10",
        "home_home_goals_conceded_avg_last_10",
        "away_away_goals_conceded_avg_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
    ]

    for column in required_columns:
        if column not in dataframe.columns:
            raise RuntimeError(f"Colonne requise absente pour la V7 : {column}")
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    dataframe["home_away_points_avg_diff"] = (
        dataframe["home_home_points_avg_last_10"] - dataframe["away_away_points_avg_last_10"]
    ).round(4)
    dataframe["home_away_scored_avg_diff"] = (
        dataframe["home_home_goals_scored_avg_last_10"] - dataframe["away_away_goals_scored_avg_last_10"]
    ).round(4)
    dataframe["home_away_conceded_avg_diff"] = (
        dataframe["home_home_goals_conceded_avg_last_10"] - dataframe["away_away_goals_conceded_avg_last_10"]
    ).round(4)

    dataframe["home_venue_goal_diff_avg_last_10"] = (
        dataframe["home_home_goals_scored_avg_last_10"] - dataframe["home_home_goals_conceded_avg_last_10"]
    ).round(4)
    dataframe["away_venue_goal_diff_avg_last_10"] = (
        dataframe["away_away_goals_scored_avg_last_10"] - dataframe["away_away_goals_conceded_avg_last_10"]
    ).round(4)
    dataframe["venue_goal_diff_gap"] = (
        dataframe["home_venue_goal_diff_avg_last_10"] - dataframe["away_venue_goal_diff_avg_last_10"]
    ).round(4)
    dataframe["abs_venue_goal_diff_gap"] = dataframe["venue_goal_diff_gap"].abs().round(4)

    dataframe["home_goal_diff_avg_last_10"] = (
        dataframe["home_goals_scored_avg_last_10"] - dataframe["home_goals_conceded_avg_last_10"]
    ).round(4)
    dataframe["away_goal_diff_avg_last_10"] = (
        dataframe["away_goals_scored_avg_last_10"] - dataframe["away_goals_conceded_avg_last_10"]
    ).round(4)
    dataframe["goal_diff_gap_last_10"] = (
        dataframe["home_goal_diff_avg_last_10"] - dataframe["away_goal_diff_avg_last_10"]
    ).round(4)
    dataframe["abs_goal_diff_gap_last_10"] = dataframe["goal_diff_gap_last_10"].abs().round(4)

    dataframe["goal_diff_trend_home"] = (
        dataframe["home_goal_diff_avg_last_10"] - dataframe["home_goal_diff_avg_last_15"]
    ).round(4)
    dataframe["goal_diff_trend_away"] = (
        dataframe["away_goal_diff_avg_last_10"] - dataframe["away_goal_diff_avg_last_15"]
    ).round(4)
    dataframe["goal_diff_trend_gap"] = (
        dataframe["goal_diff_trend_home"] - dataframe["goal_diff_trend_away"]
    ).round(4)

    return dataframe


# Fusionne les features V7 avec les features V5 déjà construites en mémoire.
def merge_v7_context_features(feature_dataframe: pd.DataFrame, v7_context_dataframe: pd.DataFrame) -> pd.DataFrame:
    merged_dataframe = feature_dataframe.merge(
        v7_context_dataframe,
        on="clean_match_id",
        how="left",
    )
    merged_dataframe = add_v7_derived_features(merged_dataframe)

    for column in V7_ALL_CONTEXT_COLUMNS:
        merged_dataframe[column] = pd.to_numeric(merged_dataframe[column], errors="coerce")

    return merged_dataframe


# Ajoute les features Market prior V6 si le script V6 est disponible.
def add_market_prior_if_available(database_url: str, feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    if not MARKET_PRIOR_AVAILABLE:
        return feature_dataframe.copy()

    market_raw_rows = fetch_market_raw_data(database_url)
    market_dataframe = build_market_prior_dataframe(market_raw_rows)

    return merge_market_prior_features(feature_dataframe, market_dataframe)


# Construit les familles de features à comparer dans l'expérience V7 groupée.
def build_v7_feature_sets(include_market: bool) -> dict[str, list[str]]:
    v5_feature_sets = build_v5_feature_sets()
    v2_reference_columns = v5_feature_sets[V2_REFERENCE_FEATURE_SET_NAME]
    v5_reference_columns = v5_feature_sets[V5_REFERENCE_FEATURE_SET_NAME]

    feature_sets = {
        V2_REFERENCE_FEATURE_SET_NAME: dedupe_columns(v2_reference_columns),
        V5_REFERENCE_FEATURE_SET_NAME: dedupe_columns(v5_reference_columns),
        "v7_elo_only": dedupe_columns(V7_ELO_COLUMNS),
        "v7_elo_plus_v5": dedupe_columns(v5_reference_columns + V7_ELO_COLUMNS),
        "v7_home_away_form": dedupe_columns(v2_reference_columns + V7_HOME_AWAY_FORM_COLUMNS),
        "v7_momentum_goal_diff": dedupe_columns(v2_reference_columns + V7_MOMENTUM_COLUMNS + V7_GOAL_DIFF_COLUMNS),
        "v7_calendar_context": dedupe_columns(v2_reference_columns + V7_CALENDAR_COLUMNS),
        "v7_all_without_market": dedupe_columns(v5_reference_columns + V7_ALL_CONTEXT_COLUMNS),
    }

    if include_market:
        feature_sets[V7_MARKET_BENCHMARK_NAME] = dedupe_columns(
            v5_reference_columns
            + V7_ALL_CONTEXT_COLUMNS
            + MARKET_PROBABILITY_COLUMNS
            + MARKET_GAP_COLUMNS
        )

    return feature_sets


# Calcule les métriques principales pour une stratégie 1X2.
def compute_metrics(
    strategy_name: str,
    model_name: str,
    feature_columns: list[str],
    y_true: pd.Series,
    predictions: list[str] | pd.Series,
    train_rows: int,
    test_rows: int,
    rows_after_cleaning: int,
    base_test_rows: int,
) -> dict:
    prediction_series = pd.Series(predictions).reset_index(drop=True)
    truth_series = y_true.reset_index(drop=True)
    report = classification_report(
        truth_series,
        prediction_series,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )
    prediction_distribution = prediction_series.value_counts().to_dict()
    actual_distribution = truth_series.value_counts().to_dict()

    return {
        "strategy": strategy_name,
        "model": model_name,
        "feature_count": len(feature_columns),
        "rows_after_cleaning": rows_after_cleaning,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "coverage": rounded(test_rows / base_test_rows if base_test_rows else 0.0),
        "accuracy": rounded(accuracy_score(truth_series, prediction_series)),
        "f1_macro": rounded(f1_score(truth_series, prediction_series, average="macro")),
        "f1_weighted": rounded(f1_score(truth_series, prediction_series, average="weighted")),
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
        "features": ", ".join(feature_columns),
    }


# Entraîne LogisticRegression_balanced sur une famille de features et retourne ses métriques.
def evaluate_feature_strategy(
    feature_dataframe: pd.DataFrame,
    strategy_name: str,
    feature_columns: list[str],
    base_test_rows: int,
) -> dict:
    x_train, y_train, x_test, y_test, working_dataframe, train_dataframe, test_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    model = build_reference_model()
    model.fit(x_train, y_train)
    predictions = list(model.predict(x_test))

    return compute_metrics(
        strategy_name=strategy_name,
        model_name=V2_REFERENCE_MODEL_NAME,
        feature_columns=feature_columns,
        y_true=y_test,
        predictions=predictions,
        train_rows=len(train_dataframe),
        test_rows=len(test_dataframe),
        rows_after_cleaning=len(working_dataframe),
        base_test_rows=base_test_rows,
    )


# Compare toutes les stratégies V2, V5 et V7 groupées.
def run_v7_team_strength_context_comparison(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    results = []
    include_market = MARKET_PRIOR_AVAILABLE and all(
        column in feature_dataframe.columns for column in MARKET_PROBABILITY_COLUMNS
    )
    feature_sets = build_v7_feature_sets(include_market=include_market)
    base_test_rows = int(feature_dataframe[feature_dataframe["season"].isin(TEST_SEASONS)].shape[0])

    for strategy_name, feature_columns in feature_sets.items():
        print(f"Evaluation V7 : {strategy_name}", flush=True)
        results.append(
            evaluate_feature_strategy(
                feature_dataframe=feature_dataframe,
                strategy_name=strategy_name,
                feature_columns=feature_columns,
                base_test_rows=base_test_rows,
            )
        )

    results_dataframe = pd.DataFrame(results)

    return results_dataframe.sort_values(
        by=["f1_macro", "draw_recall", "accuracy"],
        ascending=False,
    )


# Sélectionne le meilleur candidat V7 global sans Market prior.
def select_best_non_market_v7_candidate(results_dataframe: pd.DataFrame) -> pd.Series:
    eligible_dataframe = results_dataframe[
        results_dataframe["strategy"].str.startswith("v7_")
        & (results_dataframe["strategy"] != V7_MARKET_BENCHMARK_NAME)
    ].copy()

    if eligible_dataframe.empty:
        raise RuntimeError("Aucun candidat V7 sans marché trouvé dans les résultats.")

    return eligible_dataframe.sort_values(
        by=["f1_macro", "draw_recall", "accuracy"],
        ascending=False,
    ).iloc[0]


# Récupère une ligne de résultats par nom de stratégie.
def get_strategy_row(results_dataframe: pd.DataFrame, strategy_name: str) -> pd.Series | None:
    strategy_rows = results_dataframe[results_dataframe["strategy"] == strategy_name]

    if strategy_rows.empty:
        return None

    return strategy_rows.iloc[0]


# Détermine le statut final V7 selon les critères définis avant l'expérience.
def determine_v7_status(best_v7_row: pd.Series) -> str:
    if (
        best_v7_row["accuracy"] >= SERIOUS_ACCURACY
        and best_v7_row["f1_macro"] >= SERIOUS_F1_MACRO
        and best_v7_row["draw_recall"] >= SERIOUS_DRAW_RECALL
        and best_v7_row["draw_precision"] >= SERIOUS_DRAW_PRECISION
    ):
        return "V7_SERIOUS_EXPERIMENTAL_SIGNAL"

    if (
        best_v7_row["accuracy"] > INTERESTING_ACCURACY
        and best_v7_row["f1_macro"] > INTERESTING_F1_MACRO
        and best_v7_row["draw_recall"] >= INTERESTING_DRAW_RECALL
        and best_v7_row["draw_precision"] >= INTERESTING_DRAW_PRECISION
    ):
        return "V7_INTERESTING_EXPERIMENTAL_SIGNAL"

    return "V7_NOT_RETAINED_AS_GLOBAL_CANDIDATE"


# Construit la synthèse texte de l'expérience V7 groupée.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, results_dataframe: pd.DataFrame) -> str:
    best_v7_row = select_best_non_market_v7_candidate(results_dataframe)
    v2_row = get_strategy_row(results_dataframe, V2_REFERENCE_FEATURE_SET_NAME)
    v5_row = get_strategy_row(results_dataframe, V5_REFERENCE_FEATURE_SET_NAME)
    market_row = get_strategy_row(results_dataframe, V7_MARKET_BENCHMARK_NAME)
    v7_status = determine_v7_status(best_v7_row)

    lines = [
        "RubyBets - ML 1X2 V7 Team strength & context blocks",
        "79 - Synthese de l'experimentation V7 groupee",
        "",
        "Objectif :",
        "Tester en une seule experimentation plusieurs familles de signaux plus fortes que les petites features derivees : Elo pre-match, domicile/exterieur, momentum, goal difference et contexte calendrier.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Le bloc Market prior reste uniquement un benchmark interne si le script V6 est disponible.",
        "",
        "Point de depart avant V7 :",
        f"- V2 reference accuracy : {V2_REFERENCE_ACCURACY:.4f}",
        f"- V2 reference F1 macro : {V2_REFERENCE_F1_MACRO:.4f}",
        f"- V2 reference DRAW precision : {V2_REFERENCE_DRAW_PRECISION:.4f}",
        f"- V2 reference DRAW recall : {V2_REFERENCE_DRAW_RECALL:.4f}",
        "- V6 a apporte un benchmark utile mais n'a pas ete retenue comme candidat global.",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features V7 construites : {len(feature_dataframe)}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Meilleur candidat V7 global sans Market prior :",
        f"- Strategy : {best_v7_row['strategy']}",
        f"- Model : {best_v7_row['model']}",
        f"- Accuracy : {best_v7_row['accuracy']}",
        f"- F1 macro : {best_v7_row['f1_macro']}",
        f"- F1 weighted : {best_v7_row['f1_weighted']}",
        f"- DRAW precision : {best_v7_row['draw_precision']}",
        f"- DRAW recall : {best_v7_row['draw_recall']}",
        f"- Predicted DRAW rows : {best_v7_row['predicted_draw_rows']}",
        "",
        "Comparaison rapide :",
    ]

    for label, row in [
        ("V2 reference recalculee", v2_row),
        ("V5 reference recalculee", v5_row),
        ("V7 best non-market", best_v7_row),
        ("V7 all + market benchmark", market_row),
    ]:
        if row is None:
            continue

        lines.append(
            f"- {label} : strategy={row['strategy']}, coverage={row['coverage']}, accuracy={row['accuracy']}, f1_macro={row['f1_macro']}, draw_precision={row['draw_precision']}, draw_recall={row['draw_recall']}"
        )

    if not MARKET_PRIOR_AVAILABLE:
        lines.extend(
            [
                "",
                "Info Market prior :",
                "- Le benchmark market n'a pas ete lance car le script V6 n'a pas ete importe.",
                f"- Detail import : {MARKET_IMPORT_ERROR}",
            ]
        )

    lines.extend(
        [
            "",
            "Decision experimentale :",
            f"- Status : {v7_status}",
            "- La V7 ne remplace pas le scoring explicable V1.",
            "- La V7 ne modifie pas le modele officiel sauvegarde.",
            "- Toute integration future necessiterait une analyse de stabilite dediee.",
            "",
            "Criteres V7 :",
            f"- V7 interessante : accuracy > {INTERESTING_ACCURACY:.4f}, f1_macro > {INTERESTING_F1_MACRO:.4f}, draw_recall >= {INTERESTING_DRAW_RECALL:.4f}, draw_precision >= {INTERESTING_DRAW_PRECISION:.4f}",
            f"- V7 serieuse : accuracy >= {SERIOUS_ACCURACY:.4f}, f1_macro >= {SERIOUS_F1_MACRO:.4f}, draw_recall >= {SERIOUS_DRAW_RECALL:.4f}, draw_precision >= {SERIOUS_DRAW_PRECISION:.4f}",
            "",
            "Tableau des strategies testees :",
            results_dataframe[
                [
                    "strategy",
                    "model",
                    "coverage",
                    "train_rows",
                    "test_rows",
                    "accuracy",
                    "f1_macro",
                    "f1_weighted",
                    "draw_precision",
                    "draw_recall",
                    "predicted_draw_rows",
                ]
            ].to_string(index=False),
            "",
            "Fichiers generes :",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(CSV_PATH.relative_to(PROJECT_ROOT)),
            str(DECISION_PATH.relative_to(PROJECT_ROOT)),
            "",
            "Statut de suivi :",
            "- Tache realisee : experimentation V7 Team strength & context si les fichiers 79, 80 et 81 sont generes.",
            "- Statut source a mettre a jour : a produire -> realise pour les fichiers reports/evidence/ml_training/79, 80 et 81.",
            "",
        ]
    )

    return "\n".join(lines)


# Construit le fichier de décision final V7.
def build_decision(results_dataframe: pd.DataFrame) -> str:
    best_v7_row = select_best_non_market_v7_candidate(results_dataframe)
    v2_row = get_strategy_row(results_dataframe, V2_REFERENCE_FEATURE_SET_NAME)
    v5_row = get_strategy_row(results_dataframe, V5_REFERENCE_FEATURE_SET_NAME)
    market_row = get_strategy_row(results_dataframe, V7_MARKET_BENCHMARK_NAME)
    v7_status = determine_v7_status(best_v7_row)

    v2_accuracy_delta = None if v2_row is None else rounded(best_v7_row["accuracy"] - v2_row["accuracy"])
    v5_accuracy_delta = None if v5_row is None else rounded(best_v7_row["accuracy"] - v5_row["accuracy"])
    v2_f1_delta = None if v2_row is None else rounded(best_v7_row["f1_macro"] - v2_row["f1_macro"])
    v5_f1_delta = None if v5_row is None else rounded(best_v7_row["f1_macro"] - v5_row["f1_macro"])

    lines = [
        "RubyBets - ML 1X2 V7 Team strength & context decision",
        "81 - Decision finale de l'experimentation V7",
        "",
        f"Status : {v7_status}",
        "",
        "Meilleur candidat V7 global sans Market prior :",
        f"- Strategy : {best_v7_row['strategy']}",
        f"- Model : {best_v7_row['model']}",
        f"- Accuracy : {best_v7_row['accuracy']}",
        f"- F1 macro : {best_v7_row['f1_macro']}",
        f"- DRAW precision : {best_v7_row['draw_precision']}",
        f"- DRAW recall : {best_v7_row['draw_recall']}",
        "",
        "Delta avec les references recalculees sur le meme perimetre V7 :",
        f"- Accuracy delta vs V2 : {v2_accuracy_delta}",
        f"- F1 macro delta vs V2 : {v2_f1_delta}",
        f"- Accuracy delta vs V5 : {v5_accuracy_delta}",
        f"- F1 macro delta vs V5 : {v5_f1_delta}",
        "",
    ]

    if market_row is not None:
        lines.extend(
            [
                "Benchmark V7 + Market prior interne :",
                f"- Strategy : {market_row['strategy']}",
                f"- Accuracy : {market_row['accuracy']}",
                f"- F1 macro : {market_row['f1_macro']}",
                f"- DRAW precision : {market_row['draw_precision']}",
                f"- DRAW recall : {market_row['draw_recall']}",
                "- Ce benchmark ne doit pas etre expose dans le produit RubyBets.",
                "",
            ]
        )

    if v7_status == "V7_SERIOUS_EXPERIMENTAL_SIGNAL":
        lines.extend(
            [
                "Decision :",
                "La V7 montre un signal experimental fort. Elle merite une analyse de stabilite par ligue, saison, classe et segments d'erreurs avant toute sauvegarde candidate.",
            ]
        )
    elif v7_status == "V7_INTERESTING_EXPERIMENTAL_SIGNAL":
        lines.extend(
            [
                "Decision :",
                "La V7 montre un signal experimental interessant mais pas encore suffisant pour integration directe.",
                "Prochaine etape recommandee : analyser les segments ou les blocs V7 corrigent vraiment V2/V5.",
            ]
        )
    else:
        lines.extend(
            [
                "Decision :",
                "La V7 ne doit pas etre retenue comme candidat global a ce stade.",
                "Prochaine etape recommandee : identifier les familles de features les plus prometteuses ou enrichir le dataset pre-match avec des donnees plus informatives.",
            ]
        )

    lines.extend(
        [
            "",
            "Garde-fous maintenus :",
            "- Aucun changement API/frontend/base/scoring V1.",
            "- Aucun remplacement du modele officiel sauvegarde.",
            "- Aucun affichage des cotes dans RubyBets.",
            "- La V7 reste une experimentation ML interne jusqu'a validation de stabilite.",
            "",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les preuves texte et CSV de l'expérience V7.
def save_reports(results_dataframe: pd.DataFrame, summary: str, decision: str) -> None:
    ensure_report_dir()
    results_dataframe.to_csv(CSV_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    DECISION_PATH.write_text(decision, encoding="utf-8")


# Lance toute l'expérimentation V7 Team strength & context.
def main() -> None:
    try:
        database_url = get_database_url()

        print("Chargement des matchs nettoyes depuis ml.clean_matches...", flush=True)
        clean_matches = fetch_clean_matches(database_url)

        print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
        print("Construction des features V2 de reference en memoire...", flush=True)
        v2_feature_dataframe = build_v2_fast_feature_dataframe(clean_matches)

        print("Ajout des features V5 d'equilibre de match...", flush=True)
        v5_feature_dataframe = add_v5_balance_features(v2_feature_dataframe)

        print("Construction des features V7 Elo, momentum et contexte calendrier...", flush=True)
        v7_context_dataframe = build_v7_context_dataframe(clean_matches)
        v7_feature_dataframe = merge_v7_context_features(v5_feature_dataframe, v7_context_dataframe)

        if MARKET_PRIOR_AVAILABLE:
            print("Ajout du benchmark Market prior V6 pour comparaison interne...", flush=True)
            v7_feature_dataframe = add_market_prior_if_available(database_url, v7_feature_dataframe)
        else:
            print("Info - Benchmark Market prior ignore car le script V6 n'est pas disponible.", flush=True)

        print("Evaluation des strategies V7 Team strength & context...", flush=True)
        results_dataframe = run_v7_team_strength_context_comparison(v7_feature_dataframe)
        summary = build_summary(
            clean_matches=clean_matches,
            feature_dataframe=v7_feature_dataframe,
            results_dataframe=results_dataframe,
        )
        decision = build_decision(results_dataframe=results_dataframe)
        save_reports(results_dataframe, summary, decision)

        best_v7_row = select_best_non_market_v7_candidate(results_dataframe)
        v7_status = determine_v7_status(best_v7_row)

        print("OK - Experimentation V7 Team strength & context terminee.", flush=True)
        print(f"Status: {v7_status}", flush=True)
        print(f"Best V7 strategy: {best_v7_row['strategy']}", flush=True)
        print(f"Accuracy: {best_v7_row['accuracy']}", flush=True)
        print(f"F1 macro: {best_v7_row['f1_macro']}", flush=True)
        print(f"DRAW precision: {best_v7_row['draw_precision']}", flush=True)
        print(f"DRAW recall: {best_v7_row['draw_recall']}", flush=True)
        print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}", flush=True)
        print(f"CSV saved: {CSV_PATH.relative_to(PROJECT_ROOT)}", flush=True)
        print(f"Decision saved: {DECISION_PATH.relative_to(PROJECT_ROOT)}", flush=True)

    except Exception as error:
        print("Erreur pendant l'experimentation V7 Team strength & context.", flush=True)
        print(error, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schema de communication :
# experiment_1x2_v7_team_strength_context.py
#   -> lit backend/.env pour recuperer DATABASE_URL
#   -> lit PostgreSQL : ml.clean_matches
#   -> construit V2 + V5 en memoire sans modifier ml.features
#   -> construit les features V7 : Elo pre-match, domicile/exterieur, momentum, goal difference, calendrier
#   -> lit optionnellement les features Market prior V6 si experiment_1x2_v6_market_prior.py est disponible
#   -> compare V2, V5, blocs V7 et benchmark V7 + market
#   -> genere reports/evidence/ml_training/79_1x2_v7_team_strength_context_summary.txt
#   -> genere reports/evidence/ml_training/80_1x2_v7_team_strength_context_results.csv
#   -> genere reports/evidence/ml_training/81_1x2_v7_team_strength_context_decision.txt
#   -> ne modifie pas PostgreSQL, l'API, le frontend, le scoring V1 ou les modeles sauvegardes
