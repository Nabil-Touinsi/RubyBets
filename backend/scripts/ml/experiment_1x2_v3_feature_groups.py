# Rôle du fichier : tester les familles de features ML 1X2 V3 en mémoire, sans modifier PostgreSQL, l'API, le frontend ou le modèle officiel RubyBets.

from collections import defaultdict
from itertools import groupby
from pathlib import Path
from statistics import pstdev
import sys
import warnings

import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "50_1x2_v3_feature_groups_summary.txt"
CSV_PATH = REPORT_DIR / "51_1x2_v3_feature_groups_results.csv"
DECISION_PATH = REPORT_DIR / "52_1x2_v3_feature_groups_decision.txt"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    FEATURE_SETS,
    OFFICIAL_BASELINE_ACCURACY,
    OFFICIAL_BASELINE_F1_MACRO,
    TARGET_COLUMN,
    TEST_SEASONS,
    build_feature_dataframe,
    calculate_points_for_team,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
    get_goals_for_team,
)

warnings.filterwarnings("ignore", category=UserWarning)

CLASS_LABELS = ["HOME_WIN", "DRAW", "AWAY_WIN"]

V2_CANDIDATE_ACCURACY = 0.5111
V2_CANDIDATE_F1_MACRO = 0.4824
V2_CANDIDATE_DRAW_RECALL = 0.2803
V2_CANDIDATE_FEATURE_SET = "last10_plus_team_strength_plus_match_balance"

REFERENCE_HIGH_CONFIDENCE_ACCURACY = 0.7000
REFERENCE_HIGH_CONFIDENCE_COVERAGE = 0.1721
HIGH_CONFIDENCE_THRESHOLDS = [round(value / 100, 2) for value in range(50, 81)]

INITIAL_TEAM_STRENGTH = 1500.0
TEAM_STRENGTH_K_FACTOR = 20.0
TEAM_STRENGTH_SCALE = 400.0
RECENT_DELTA_MATCH_WINDOW = 5

TEAM_STRENGTH_COLUMNS = [
    "home_team_strength_before",
    "away_team_strength_before",
    "team_strength_diff",
    "abs_team_strength_diff",
    "home_team_strength_recent_delta",
    "away_team_strength_recent_delta",
]

MATCH_BALANCE_WITH_STRENGTH_COLUMNS = [
    "home_expected_goal_pressure",
    "away_expected_goal_pressure",
    "expected_goal_pressure_diff",
    "abs_expected_goal_pressure_diff",
    "is_close_form_match",
    "is_close_scoring_match",
    "is_close_defense_match",
    "is_close_goal_pressure_match",
    "balance_signal_count",
    "match_balance_score",
    "draw_profile_score",
    "is_close_strength_match",
    "balance_signal_count_with_strength",
    "match_balance_score_with_strength",
    "draw_profile_score_with_strength",
]

HOME_AWAY_CONTEXT_COLUMNS = [
    "home_points_home_last_10",
    "away_points_away_last_10",
    "home_goals_scored_home_avg_last_10",
    "home_goals_conceded_home_avg_last_10",
    "away_goals_scored_away_avg_last_10",
    "away_goals_conceded_away_avg_last_10",
    "home_home_context_strength",
    "away_away_context_strength",
    "home_away_context_diff",
]

DRAW_RATE_COLUMNS = [
    "home_draw_rate_last_10",
    "away_draw_rate_last_10",
    "combined_draw_rate_last_10",
    "league_draw_rate_before_match",
    "season_draw_rate_before_match",
    "v3_draw_profile_score",
]

STREAK_COLUMNS = [
    "home_win_streak",
    "home_unbeaten_streak",
    "home_winless_streak",
    "home_draw_streak",
    "away_win_streak",
    "away_unbeaten_streak",
    "away_winless_streak",
    "away_draw_streak",
]

STABILITY_COLUMNS = [
    "home_points_std_last_10",
    "away_points_std_last_10",
    "home_goals_scored_std_last_10",
    "away_goals_scored_std_last_10",
    "home_goals_conceded_std_last_10",
    "away_goals_conceded_std_last_10",
    "stability_diff",
    "combined_match_volatility",
]

FATIGUE_COLUMNS = [
    "home_days_since_last_match",
    "away_days_since_last_match",
    "days_rest_diff",
    "home_matches_last_14_days",
    "away_matches_last_14_days",
    "fixture_congestion_diff",
]

V2_REFERENCE_COLUMNS = []


# Supprime les doublons dans une liste de colonnes tout en conservant l'ordre.
def dedupe_columns(columns: list[str]) -> list[str]:
    seen = set()
    result = []

    for column in columns:
        if column not in seen:
            result.append(column)
            seen.add(column)

    return result


V2_REFERENCE_COLUMNS = dedupe_columns(
    FEATURE_SETS["v2_last10_overall_with_diff_and_abs"]
    + TEAM_STRENGTH_COLUMNS
    + MATCH_BALANCE_WITH_STRENGTH_COLUMNS
)

FEATURE_GROUPS = {
    "v2_reference": V2_REFERENCE_COLUMNS,
    "v2_reference_plus_home_away_context": dedupe_columns(V2_REFERENCE_COLUMNS + HOME_AWAY_CONTEXT_COLUMNS),
    "v2_reference_plus_draw_rates": dedupe_columns(V2_REFERENCE_COLUMNS + DRAW_RATE_COLUMNS),
    "v2_reference_plus_streaks": dedupe_columns(V2_REFERENCE_COLUMNS + STREAK_COLUMNS),
    "v2_reference_plus_stability": dedupe_columns(V2_REFERENCE_COLUMNS + STABILITY_COLUMNS),
    "v2_reference_plus_fatigue": dedupe_columns(V2_REFERENCE_COLUMNS + FATIGUE_COLUMNS),
    "v3_all_feature_groups": dedupe_columns(
        V2_REFERENCE_COLUMNS
        + HOME_AWAY_CONTEXT_COLUMNS
        + DRAW_RATE_COLUMNS
        + STREAK_COLUMNS
        + STABILITY_COLUMNS
        + FATIGUE_COLUMNS
    ),
}


# Crée les modèles utiles pour comparer les familles V3 sans multiplier les tests inutiles.
def build_candidate_models() -> dict:
    models = {
        "LogisticRegression_balanced": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=2000,
                        random_state=42,
                    ),
                ),
            ]
        ),
        "RandomForest_balanced": RandomForestClassifier(
            n_estimators=180,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
            min_samples_leaf=5,
        ),
        "GradientBoosting": GradientBoostingClassifier(random_state=42),
    }

    try:
        from xgboost import XGBClassifier

        models["XGBoost"] = XGBClassifier(
            objective="multi:softprob",
            eval_metric="mlogloss",
            random_state=42,
            n_estimators=220,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            n_jobs=-1,
        )
    except Exception:
        print("Info - XGBoost non disponible, comparaison continue sans XGBoost.", flush=True)

    return models


# Calcule le score attendu d'une équipe selon l'écart de force avant-match.
def calculate_expected_score(team_strength: float, opponent_strength: float) -> float:
    return 1 / (1 + 10 ** ((opponent_strength - team_strength) / TEAM_STRENGTH_SCALE))


# Convertit le résultat 1X2 en score numérique pour chaque équipe.
def get_actual_scores(result: str) -> tuple[float, float]:
    if result == "HOME_WIN":
        return 1.0, 0.0

    if result == "AWAY_WIN":
        return 0.0, 1.0

    return 0.5, 0.5


# Calcule la variation récente de force d'une équipe.
def calculate_recent_strength_delta(team_history: list[float], current_strength: float) -> float | None:
    if len(team_history) < RECENT_DELTA_MATCH_WINDOW:
        return None

    previous_strength = team_history[-RECENT_DELTA_MATCH_WINDOW]

    return round(current_strength - previous_strength, 2)


# Construit les features de force d'équipe avant-match pour une ligne.
def build_team_strength_row(match: dict, team_strengths: dict, strength_history: dict) -> dict:
    league_code = match["league_code"]
    home_team = match["home_team"]
    away_team = match["away_team"]

    home_key = (league_code, home_team)
    away_key = (league_code, away_team)

    home_strength_before = team_strengths[home_key]
    away_strength_before = team_strengths[away_key]
    strength_diff = round(home_strength_before - away_strength_before, 2)

    return {
        "clean_match_id": match["id"],
        "home_team_strength_before": round(home_strength_before, 2),
        "away_team_strength_before": round(away_strength_before, 2),
        "team_strength_diff": strength_diff,
        "abs_team_strength_diff": abs(strength_diff),
        "home_team_strength_recent_delta": calculate_recent_strength_delta(
            team_history=strength_history[home_key],
            current_strength=home_strength_before,
        ),
        "away_team_strength_recent_delta": calculate_recent_strength_delta(
            team_history=strength_history[away_key],
            current_strength=away_strength_before,
        ),
    }


# Met à jour les forces d'équipe après tous les matchs d'une même date pour éviter toute fuite de données.
def update_team_strengths_after_matches(matches_for_date: list[dict], team_strengths: dict, strength_history: dict) -> None:
    updates = []

    for match in matches_for_date:
        league_code = match["league_code"]
        home_team = match["home_team"]
        away_team = match["away_team"]

        home_key = (league_code, home_team)
        away_key = (league_code, away_team)

        home_strength_before = team_strengths[home_key]
        away_strength_before = team_strengths[away_key]

        expected_home = calculate_expected_score(home_strength_before, away_strength_before)
        expected_away = calculate_expected_score(away_strength_before, home_strength_before)
        actual_home, actual_away = get_actual_scores(match["result"])

        new_home_strength = home_strength_before + TEAM_STRENGTH_K_FACTOR * (actual_home - expected_home)
        new_away_strength = away_strength_before + TEAM_STRENGTH_K_FACTOR * (actual_away - expected_away)

        updates.append((home_key, new_home_strength))
        updates.append((away_key, new_away_strength))

    for team_key, new_strength in updates:
        team_strengths[team_key] = new_strength
        strength_history[team_key].append(new_strength)


# Construit les features team_strength_rating en respectant l'ordre chronologique.
def build_team_strength_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    rows = []
    team_strengths = defaultdict(lambda: INITIAL_TEAM_STRENGTH)
    strength_history = defaultdict(list)

    for _, matches_group in groupby(clean_matches, key=lambda row: row["match_date"]):
        matches_for_date = list(matches_group)

        for match in matches_for_date:
            rows.append(
                build_team_strength_row(
                    match=match,
                    team_strengths=team_strengths,
                    strength_history=strength_history,
                )
            )

        update_team_strengths_after_matches(
            matches_for_date=matches_for_date,
            team_strengths=team_strengths,
            strength_history=strength_history,
        )

    return pd.DataFrame(rows)


# Transforme une colonne en numérique sans bloquer l'expérimentation.
def to_numeric_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(dataframe[column], errors="coerce")


# Calcule une différence simple quand les deux valeurs existent.
def safe_diff(left_value: float | None, right_value: float | None) -> float | None:
    if left_value is None or right_value is None:
        return None

    return round(float(left_value) - float(right_value), 4)


# Calcule une division sûre pour éviter les erreurs sur valeurs absentes ou nulles.
def safe_divide(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None

    return round(float(numerator) / float(denominator), 4)


# Ajoute les features V2 liées aux matchs équilibrés et au profil de nul.
def add_match_balance_features(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = feature_dataframe.copy()

    numeric_columns = [
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "abs_form_points_diff",
        "abs_goals_scored_diff",
        "abs_goals_conceded_diff",
        "abs_team_strength_diff",
    ]

    for column in numeric_columns:
        if column in dataframe.columns:
            dataframe[column] = to_numeric_series(dataframe, column)

    dataframe["home_expected_goal_pressure"] = (
        dataframe["home_goals_scored_avg_last_10"] + dataframe["away_goals_conceded_avg_last_10"]
    ) / 2
    dataframe["away_expected_goal_pressure"] = (
        dataframe["away_goals_scored_avg_last_10"] + dataframe["home_goals_conceded_avg_last_10"]
    ) / 2
    dataframe["expected_goal_pressure_diff"] = (
        dataframe["home_expected_goal_pressure"] - dataframe["away_expected_goal_pressure"]
    ).round(4)
    dataframe["abs_expected_goal_pressure_diff"] = dataframe["expected_goal_pressure_diff"].abs().round(4)

    dataframe["is_close_form_match"] = (dataframe["abs_form_points_diff"] <= 3.0).astype(int)
    dataframe["is_close_scoring_match"] = (dataframe["abs_goals_scored_diff"] <= 0.35).astype(int)
    dataframe["is_close_defense_match"] = (dataframe["abs_goals_conceded_diff"] <= 0.35).astype(int)
    dataframe["is_close_goal_pressure_match"] = (dataframe["abs_expected_goal_pressure_diff"] <= 0.35).astype(int)
    dataframe["is_close_strength_match"] = (dataframe["abs_team_strength_diff"] <= 60.0).astype(int)

    dataframe["balance_signal_count"] = (
        dataframe["is_close_form_match"]
        + dataframe["is_close_scoring_match"]
        + dataframe["is_close_defense_match"]
        + dataframe["is_close_goal_pressure_match"]
    )
    dataframe["balance_signal_count_with_strength"] = (
        dataframe["balance_signal_count"] + dataframe["is_close_strength_match"]
    )

    normalized_balance_gap = (
        dataframe["abs_form_points_diff"].fillna(99) / 3.0
        + dataframe["abs_goals_scored_diff"].fillna(99) / 0.35
        + dataframe["abs_goals_conceded_diff"].fillna(99) / 0.35
        + dataframe["abs_expected_goal_pressure_diff"].fillna(99) / 0.35
    )
    normalized_balance_gap_with_strength = normalized_balance_gap + (
        dataframe["abs_team_strength_diff"].fillna(9999) / 60.0
    )

    dataframe["match_balance_score"] = (1 / (1 + normalized_balance_gap)).round(4)
    dataframe["match_balance_score_with_strength"] = (1 / (1 + normalized_balance_gap_with_strength)).round(4)

    dataframe["draw_profile_score"] = (
        dataframe["balance_signal_count"] + dataframe["match_balance_score"]
    ).round(4)
    dataframe["draw_profile_score_with_strength"] = (
        dataframe["balance_signal_count_with_strength"] + dataframe["match_balance_score_with_strength"]
    ).round(4)

    return dataframe


# Calcule le total de points d'une équipe sur une liste de matchs passés.
def calculate_total_points(matches: list[dict], team_name: str) -> float | None:
    if not matches:
        return None

    return float(sum(calculate_points_for_team(match, team_name) for match in matches))


# Calcule les moyennes de buts marqués et encaissés par une équipe sur une liste de matchs passés.
def calculate_goal_averages(matches: list[dict], team_name: str) -> tuple[float | None, float | None]:
    if not matches:
        return None, None

    goals_scored = []
    goals_conceded = []

    for match in matches:
        scored, conceded = get_goals_for_team(match, team_name)
        goals_scored.append(scored)
        goals_conceded.append(conceded)

    return round(sum(goals_scored) / len(goals_scored), 4), round(sum(goals_conceded) / len(goals_conceded), 4)


# Calcule un score de contexte domicile ou extérieur simple et interprétable.
def calculate_context_strength(points_total: float | None, scored_avg: float | None, conceded_avg: float | None) -> float | None:
    if points_total is None or scored_avg is None or conceded_avg is None:
        return None

    points_component = safe_divide(points_total, 30.0)

    if points_component is None:
        return None

    return round((points_component * 100) + (scored_avg * 10) - (conceded_avg * 10), 4)


# Calcule le taux de match nul sur une liste de matchs passés.
def calculate_draw_rate(matches: list[dict]) -> float | None:
    if not matches:
        return None

    draw_count = sum(1 for match in matches if match["result"] == "DRAW")

    return round(draw_count / len(matches), 4)


# Calcule la série récente d'une équipe selon un type de dynamique.
def calculate_streak(matches: list[dict], team_name: str, streak_type: str) -> int:
    streak = 0

    for match in reversed(matches):
        points = calculate_points_for_team(match, team_name)
        is_draw = match["result"] == "DRAW"

        if streak_type == "win" and points == 3:
            streak += 1
        elif streak_type == "unbeaten" and points > 0:
            streak += 1
        elif streak_type == "winless" and points < 3:
            streak += 1
        elif streak_type == "draw" and is_draw:
            streak += 1
        else:
            break

    return streak


# Calcule les écarts-types de points, buts marqués et buts encaissés sur les 10 derniers matchs.
def calculate_stability_stats(matches: list[dict], team_name: str) -> tuple[float | None, float | None, float | None]:
    if not matches:
        return None, None, None

    points = []
    goals_scored = []
    goals_conceded = []

    for match in matches:
        scored, conceded = get_goals_for_team(match, team_name)
        points.append(calculate_points_for_team(match, team_name))
        goals_scored.append(scored)
        goals_conceded.append(conceded)

    if len(matches) == 1:
        return 0.0, 0.0, 0.0

    return round(pstdev(points), 4), round(pstdev(goals_scored), 4), round(pstdev(goals_conceded), 4)


# Calcule le nombre de jours depuis le dernier match d'une équipe.
def calculate_days_since_last_match(matches: list[dict], current_match: dict) -> int | None:
    if not matches:
        return None

    return (current_match["match_date"] - matches[-1]["match_date"]).days


# Compte les matchs joués dans les 14 jours avant la rencontre courante.
def count_matches_last_14_days(matches: list[dict], current_match: dict) -> int:
    current_date = current_match["match_date"]

    return sum(1 for match in matches if 0 < (current_date - match["match_date"]).days <= 14)


# Construit les features V3 d'un match à partir uniquement des matchs déjà joués avant lui.
def build_v3_features_for_match(
    match: dict,
    overall_history: dict,
    home_venue_history: dict,
    away_venue_history: dict,
    league_history: dict,
    season_league_history: dict,
) -> dict:
    league_code = match["league_code"]
    season = match["season"]
    home_team = match["home_team"]
    away_team = match["away_team"]

    home_key = (league_code, home_team)
    away_key = (league_code, away_team)

    home_last_10_overall = overall_history[home_key][-10:]
    away_last_10_overall = overall_history[away_key][-10:]
    home_last_10_home = home_venue_history[home_key][-10:]
    away_last_10_away = away_venue_history[away_key][-10:]

    league_matches_before = league_history[league_code]
    season_matches_before = season_league_history[(league_code, season)]

    home_points_home = calculate_total_points(home_last_10_home, home_team)
    away_points_away = calculate_total_points(away_last_10_away, away_team)

    home_scored_home_avg, home_conceded_home_avg = calculate_goal_averages(home_last_10_home, home_team)
    away_scored_away_avg, away_conceded_away_avg = calculate_goal_averages(away_last_10_away, away_team)

    home_context_strength = calculate_context_strength(
        points_total=home_points_home,
        scored_avg=home_scored_home_avg,
        conceded_avg=home_conceded_home_avg,
    )
    away_context_strength = calculate_context_strength(
        points_total=away_points_away,
        scored_avg=away_scored_away_avg,
        conceded_avg=away_conceded_away_avg,
    )

    home_draw_rate = calculate_draw_rate(home_last_10_overall)
    away_draw_rate = calculate_draw_rate(away_last_10_overall)
    combined_draw_rate = None

    if home_draw_rate is not None and away_draw_rate is not None:
        combined_draw_rate = round((home_draw_rate + away_draw_rate) / 2, 4)

    league_draw_rate = calculate_draw_rate(league_matches_before)
    season_draw_rate = calculate_draw_rate(season_matches_before)

    v3_draw_profile_score = None

    if combined_draw_rate is not None and league_draw_rate is not None and season_draw_rate is not None:
        v3_draw_profile_score = round(
            (combined_draw_rate * 0.5) + (league_draw_rate * 0.25) + (season_draw_rate * 0.25),
            4,
        )

    home_points_std, home_scored_std, home_conceded_std = calculate_stability_stats(home_last_10_overall, home_team)
    away_points_std, away_scored_std, away_conceded_std = calculate_stability_stats(away_last_10_overall, away_team)

    home_total_volatility = None
    away_total_volatility = None

    if home_points_std is not None and home_scored_std is not None and home_conceded_std is not None:
        home_total_volatility = home_points_std + home_scored_std + home_conceded_std

    if away_points_std is not None and away_scored_std is not None and away_conceded_std is not None:
        away_total_volatility = away_points_std + away_scored_std + away_conceded_std

    home_days_since_last_match = calculate_days_since_last_match(overall_history[home_key], match)
    away_days_since_last_match = calculate_days_since_last_match(overall_history[away_key], match)

    return {
        "clean_match_id": match["id"],
        "home_points_home_last_10": home_points_home,
        "away_points_away_last_10": away_points_away,
        "home_goals_scored_home_avg_last_10": home_scored_home_avg,
        "home_goals_conceded_home_avg_last_10": home_conceded_home_avg,
        "away_goals_scored_away_avg_last_10": away_scored_away_avg,
        "away_goals_conceded_away_avg_last_10": away_conceded_away_avg,
        "home_home_context_strength": home_context_strength,
        "away_away_context_strength": away_context_strength,
        "home_away_context_diff": safe_diff(home_context_strength, away_context_strength),
        "home_draw_rate_last_10": home_draw_rate,
        "away_draw_rate_last_10": away_draw_rate,
        "combined_draw_rate_last_10": combined_draw_rate,
        "league_draw_rate_before_match": league_draw_rate,
        "season_draw_rate_before_match": season_draw_rate,
        "v3_draw_profile_score": v3_draw_profile_score,
        "home_win_streak": calculate_streak(home_last_10_overall, home_team, "win"),
        "home_unbeaten_streak": calculate_streak(home_last_10_overall, home_team, "unbeaten"),
        "home_winless_streak": calculate_streak(home_last_10_overall, home_team, "winless"),
        "home_draw_streak": calculate_streak(home_last_10_overall, home_team, "draw"),
        "away_win_streak": calculate_streak(away_last_10_overall, away_team, "win"),
        "away_unbeaten_streak": calculate_streak(away_last_10_overall, away_team, "unbeaten"),
        "away_winless_streak": calculate_streak(away_last_10_overall, away_team, "winless"),
        "away_draw_streak": calculate_streak(away_last_10_overall, away_team, "draw"),
        "home_points_std_last_10": home_points_std,
        "away_points_std_last_10": away_points_std,
        "home_goals_scored_std_last_10": home_scored_std,
        "away_goals_scored_std_last_10": away_scored_std,
        "home_goals_conceded_std_last_10": home_conceded_std,
        "away_goals_conceded_std_last_10": away_conceded_std,
        "stability_diff": safe_diff(home_total_volatility, away_total_volatility),
        "combined_match_volatility": None
        if home_total_volatility is None or away_total_volatility is None
        else round(home_total_volatility + away_total_volatility, 4),
        "home_days_since_last_match": home_days_since_last_match,
        "away_days_since_last_match": away_days_since_last_match,
        "days_rest_diff": safe_diff(home_days_since_last_match, away_days_since_last_match),
        "home_matches_last_14_days": count_matches_last_14_days(overall_history[home_key], match),
        "away_matches_last_14_days": count_matches_last_14_days(overall_history[away_key], match),
        "fixture_congestion_diff": count_matches_last_14_days(overall_history[home_key], match)
        - count_matches_last_14_days(overall_history[away_key], match),
    }


# Met à jour les historiques V3 après le calcul des features du jour.
def update_v3_histories(
    matches_for_date: list[dict],
    overall_history: dict,
    home_venue_history: dict,
    away_venue_history: dict,
    league_history: dict,
    season_league_history: dict,
) -> None:
    for match in matches_for_date:
        league_code = match["league_code"]
        season = match["season"]
        home_team = match["home_team"]
        away_team = match["away_team"]

        overall_history[(league_code, home_team)].append(match)
        overall_history[(league_code, away_team)].append(match)
        home_venue_history[(league_code, home_team)].append(match)
        away_venue_history[(league_code, away_team)].append(match)
        league_history[league_code].append(match)
        season_league_history[(league_code, season)].append(match)


# Construit toutes les features V3 en mémoire sans écrire dans ml.features.
def build_v3_extra_feature_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    rows = []
    overall_history = defaultdict(list)
    home_venue_history = defaultdict(list)
    away_venue_history = defaultdict(list)
    league_history = defaultdict(list)
    season_league_history = defaultdict(list)

    for _, matches_group in groupby(clean_matches, key=lambda row: row["match_date"]):
        matches_for_date = list(matches_group)

        for match in matches_for_date:
            rows.append(
                build_v3_features_for_match(
                    match=match,
                    overall_history=overall_history,
                    home_venue_history=home_venue_history,
                    away_venue_history=away_venue_history,
                    league_history=league_history,
                    season_league_history=season_league_history,
                )
            )

        update_v3_histories(
            matches_for_date=matches_for_date,
            overall_history=overall_history,
            home_venue_history=home_venue_history,
            away_venue_history=away_venue_history,
            league_history=league_history,
            season_league_history=season_league_history,
        )

    return pd.DataFrame(rows)


# Construit le DataFrame complet V3 en réutilisant le socle V2 déjà validé.
def build_v3_feature_dataframe(clean_matches: list[dict]) -> pd.DataFrame:
    base_feature_dataframe = build_feature_dataframe(clean_matches)
    team_strength_dataframe = build_team_strength_dataframe(clean_matches)
    v3_extra_feature_dataframe = build_v3_extra_feature_dataframe(clean_matches)

    merged_dataframe = base_feature_dataframe.merge(team_strength_dataframe, on="clean_match_id", how="left")
    merged_dataframe = add_match_balance_features(merged_dataframe)
    merged_dataframe = merged_dataframe.merge(v3_extra_feature_dataframe, on="clean_match_id", how="left")

    return merged_dataframe


# Prépare les données train/test chronologiques pour un groupe de features.
def prepare_train_test(
    feature_dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame]:
    missing_columns = [column for column in feature_columns if column not in feature_dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes dans le DataFrame : {missing_columns}")

    working_dataframe = feature_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    for column in feature_columns:
        working_dataframe[column] = pd.to_numeric(working_dataframe[column], errors="coerce")

    working_dataframe = working_dataframe.dropna(subset=feature_columns + [TARGET_COLUMN]).copy()

    train_dataframe = working_dataframe[~working_dataframe["season"].isin(TEST_SEASONS)].copy()
    test_dataframe = working_dataframe[working_dataframe["season"].isin(TEST_SEASONS)].copy()

    if train_dataframe.empty or test_dataframe.empty:
        raise RuntimeError("Train ou test vide apres preparation des donnees.")

    return (
        train_dataframe[feature_columns],
        train_dataframe[TARGET_COLUMN],
        test_dataframe[feature_columns],
        test_dataframe[TARGET_COLUMN],
        working_dataframe,
    )


# Prépare les labels numériques nécessaires à XGBoost.
def encode_target_for_xgboost(y_train: pd.Series) -> tuple[pd.Series, dict]:
    label_mapping = {
        "AWAY_WIN": 0,
        "DRAW": 1,
        "HOME_WIN": 2,
    }

    return y_train.map(label_mapping), label_mapping


# Reconvertit les prédictions numériques XGBoost vers les labels métier.
def decode_xgboost_predictions(predictions, label_mapping: dict) -> list[str]:
    reverse_mapping = {value: key for key, value in label_mapping.items()}

    return [reverse_mapping[int(prediction)] for prediction in predictions]


# Calcule les métriques de forte confiance pour un seuil précis.
def calculate_threshold_metrics(
    threshold: float,
    y_test: pd.Series,
    predictions: list[str],
    max_probabilities,
) -> dict:
    selected_mask = max_probabilities >= threshold
    selected_rows = int(selected_mask.sum())

    if selected_rows == 0:
        return {
            "threshold": threshold,
            "selected_rows": 0,
            "coverage": 0.0,
            "accuracy": None,
            "predicted_draw_rows": 0,
        }

    prediction_series = pd.Series(predictions).reset_index(drop=True)
    truth_series = y_test.reset_index(drop=True)

    selected_predictions = prediction_series[selected_mask]
    selected_truth = truth_series[selected_mask]
    selected_distribution = selected_predictions.value_counts().to_dict()

    return {
        "threshold": threshold,
        "selected_rows": selected_rows,
        "coverage": round(selected_rows / len(y_test), 4),
        "accuracy": round(accuracy_score(selected_truth, selected_predictions), 4),
        "predicted_draw_rows": int(selected_distribution.get("DRAW", 0)),
    }


# Sélectionne le meilleur signal de forte confiance disponible pour un modèle.
def calculate_high_confidence_summary(model, x_test: pd.DataFrame, y_test: pd.Series, predictions: list[str]) -> dict:
    if not hasattr(model, "predict_proba"):
        return {
            "high_confidence_threshold": None,
            "high_confidence_accuracy": None,
            "high_confidence_coverage": 0.0,
            "high_confidence_selected_rows": 0,
            "high_confidence_predicted_draw_rows": 0,
            "high_confidence_target_reached": False,
        }

    probabilities = model.predict_proba(x_test)
    max_probabilities = probabilities.max(axis=1)

    threshold_results = [
        calculate_threshold_metrics(
            threshold=threshold,
            y_test=y_test,
            predictions=predictions,
            max_probabilities=max_probabilities,
        )
        for threshold in HIGH_CONFIDENCE_THRESHOLDS
    ]
    threshold_dataframe = pd.DataFrame(threshold_results)

    eligible_target = threshold_dataframe[
        (threshold_dataframe["accuracy"].notna())
        & (threshold_dataframe["accuracy"] >= REFERENCE_HIGH_CONFIDENCE_ACCURACY)
    ].copy()

    if eligible_target.empty:
        usable_thresholds = threshold_dataframe[threshold_dataframe["accuracy"].notna()].copy()
        if usable_thresholds.empty:
            best_row = None
            target_reached = False
        else:
            best_row = usable_thresholds.sort_values(
                by=["accuracy", "coverage"],
                ascending=False,
            ).iloc[0]
            target_reached = False
    else:
        best_row = eligible_target.sort_values(
            by=["coverage", "accuracy"],
            ascending=False,
        ).iloc[0]
        target_reached = True

    if best_row is None:
        return {
            "high_confidence_threshold": None,
            "high_confidence_accuracy": None,
            "high_confidence_coverage": 0.0,
            "high_confidence_selected_rows": 0,
            "high_confidence_predicted_draw_rows": 0,
            "high_confidence_target_reached": False,
        }

    return {
        "high_confidence_threshold": best_row["threshold"],
        "high_confidence_accuracy": best_row["accuracy"],
        "high_confidence_coverage": best_row["coverage"],
        "high_confidence_selected_rows": int(best_row["selected_rows"]),
        "high_confidence_predicted_draw_rows": int(best_row["predicted_draw_rows"]),
        "high_confidence_target_reached": target_reached,
    }


# Entraîne et évalue un modèle sur un groupe de features V3.
def evaluate_model_on_feature_group(
    feature_dataframe: pd.DataFrame,
    feature_group_name: str,
    feature_columns: list[str],
    model_name: str,
    model,
) -> dict:
    x_train, y_train, x_test, y_test, working_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    model_to_train = clone(model)

    if model_name == "XGBoost":
        y_train_encoded, label_mapping = encode_target_for_xgboost(y_train)
        model_to_train.fit(x_train, y_train_encoded)
        raw_predictions = model_to_train.predict(x_test)
        predictions = decode_xgboost_predictions(raw_predictions, label_mapping)
    else:
        model_to_train.fit(x_train, y_train)
        predictions = list(model_to_train.predict(x_test))

    report = classification_report(
        y_test,
        predictions,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )

    high_confidence_summary = calculate_high_confidence_summary(
        model=model_to_train,
        x_test=x_test,
        y_test=y_test,
        predictions=predictions,
    )

    return {
        "feature_group": feature_group_name,
        "model": model_name,
        "feature_count": len(feature_columns),
        "rows_after_cleaning": len(working_dataframe),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "accuracy": round(accuracy_score(y_test, predictions), 4),
        "f1_macro": round(f1_score(y_test, predictions, average="macro"), 4),
        "f1_weighted": round(f1_score(y_test, predictions, average="weighted"), 4),
        "recall_HOME_WIN": round(report["HOME_WIN"]["recall"], 4),
        "recall_DRAW": round(report["DRAW"]["recall"], 4),
        "recall_AWAY_WIN": round(report["AWAY_WIN"]["recall"], 4),
        "precision_HOME_WIN": round(report["HOME_WIN"]["precision"], 4),
        "precision_DRAW": round(report["DRAW"]["precision"], 4),
        "precision_AWAY_WIN": round(report["AWAY_WIN"]["precision"], 4),
        **high_confidence_summary,
        "features": ", ".join(feature_columns),
    }


# Compare tous les groupes V3 avec les modèles retenus.
def run_v3_feature_group_comparison(feature_dataframe: pd.DataFrame) -> pd.DataFrame:
    results = []
    candidate_models = build_candidate_models()

    for feature_group_name, feature_columns in FEATURE_GROUPS.items():
        for model_name, model in candidate_models.items():
            print(f"Evaluation : {model_name} sur {feature_group_name}", flush=True)

            results.append(
                evaluate_model_on_feature_group(
                    feature_dataframe=feature_dataframe,
                    feature_group_name=feature_group_name,
                    feature_columns=feature_columns,
                    model_name=model_name,
                    model=model,
                )
            )

    comparison = pd.DataFrame(results)

    return comparison.sort_values(
        by=["f1_macro", "recall_DRAW", "accuracy"],
        ascending=False,
    )


# Formate une valeur optionnelle pour les rapports texte.
def format_optional_value(value) -> str:
    if value is None or pd.isna(value):
        return "None"

    return str(value)


# Récupère la meilleure ligne de forte confiance disponible.
def get_best_high_confidence_row(comparison: pd.DataFrame):
    eligible = comparison[
        (comparison["high_confidence_accuracy"].notna())
        & (comparison["high_confidence_accuracy"] >= REFERENCE_HIGH_CONFIDENCE_ACCURACY)
    ].copy()

    if eligible.empty:
        return None

    return eligible.sort_values(
        by=["high_confidence_coverage", "high_confidence_accuracy", "f1_macro"],
        ascending=False,
    ).iloc[0]


# Construit la synthèse lisible des résultats V3.
def build_summary(clean_matches: list[dict], feature_dataframe: pd.DataFrame, comparison: pd.DataFrame) -> str:
    best_f1_row = comparison.sort_values(by=["f1_macro", "recall_DRAW", "accuracy"], ascending=False).iloc[0]
    best_draw_row = comparison.sort_values(by=["recall_DRAW", "f1_macro", "accuracy"], ascending=False).iloc[0]
    best_accuracy_row = comparison.sort_values(by=["accuracy", "f1_macro", "recall_DRAW"], ascending=False).iloc[0]
    best_high_confidence_row = get_best_high_confidence_row(comparison)

    display_columns = [
        "feature_group",
        "model",
        "feature_count",
        "train_rows",
        "test_rows",
        "accuracy",
        "f1_macro",
        "f1_weighted",
        "recall_HOME_WIN",
        "recall_DRAW",
        "recall_AWAY_WIN",
        "high_confidence_threshold",
        "high_confidence_accuracy",
        "high_confidence_coverage",
        "high_confidence_selected_rows",
        "high_confidence_predicted_draw_rows",
    ]

    lines = [
        "RubyBets - ML 1X2 V3 feature groups experiment",
        "50 - Synthese des groupes de features V3",
        "",
        "Positionnement :",
        "Cette experimentation teste les familles de features V3 en memoire.",
        "Elle ne modifie pas PostgreSQL, ne remplace pas la baseline officielle, ne modifie pas l'API et ne touche pas au frontend.",
        "Le scoring explicable V1 reste le socle produit.",
        "",
        "References :",
        f"- Baseline officielle accuracy : {OFFICIAL_BASELINE_ACCURACY:.4f}",
        f"- Baseline officielle F1 macro : {OFFICIAL_BASELINE_F1_MACRO:.4f}",
        f"- Candidat V2 accuracy : {V2_CANDIDATE_ACCURACY:.4f}",
        f"- Candidat V2 F1 macro : {V2_CANDIDATE_F1_MACRO:.4f}",
        f"- Candidat V2 DRAW recall : {V2_CANDIDATE_DRAW_RECALL:.4f}",
        f"- Reference high-confidence accuracy cible : {REFERENCE_HIGH_CONFIDENCE_ACCURACY:.4f}",
        f"- Reference high-confidence coverage V2 : {REFERENCE_HIGH_CONFIDENCE_COVERAGE:.4f}",
        "",
        "Dataset :",
        f"- Matchs nettoyes charges : {len(clean_matches)}",
        f"- Lignes de features construites : {len(feature_dataframe)}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Feature groups testes :",
        "- v2_reference",
        "- v2_reference_plus_home_away_context",
        "- v2_reference_plus_draw_rates",
        "- v2_reference_plus_streaks",
        "- v2_reference_plus_stability",
        "- v2_reference_plus_fatigue",
        "- v3_all_feature_groups",
        "",
        "Best F1 macro / compromis global :",
        f"- Feature group : {best_f1_row['feature_group']}",
        f"- Model : {best_f1_row['model']}",
        f"- Accuracy : {best_f1_row['accuracy']}",
        f"- F1 macro : {best_f1_row['f1_macro']}",
        f"- DRAW recall : {best_f1_row['recall_DRAW']}",
        "",
        "Best DRAW recall :",
        f"- Feature group : {best_draw_row['feature_group']}",
        f"- Model : {best_draw_row['model']}",
        f"- Accuracy : {best_draw_row['accuracy']}",
        f"- F1 macro : {best_draw_row['f1_macro']}",
        f"- DRAW recall : {best_draw_row['recall_DRAW']}",
        "",
        "Best accuracy :",
        f"- Feature group : {best_accuracy_row['feature_group']}",
        f"- Model : {best_accuracy_row['model']}",
        f"- Accuracy : {best_accuracy_row['accuracy']}",
        f"- F1 macro : {best_accuracy_row['f1_macro']}",
        f"- DRAW recall : {best_accuracy_row['recall_DRAW']}",
        "",
    ]

    if best_high_confidence_row is None:
        lines.extend(
            [
                "Best high-confidence signal :",
                "- Aucun candidat n'atteint la cible high-confidence accuracy >= 0.70.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Best high-confidence signal :",
                f"- Feature group : {best_high_confidence_row['feature_group']}",
                f"- Model : {best_high_confidence_row['model']}",
                f"- Threshold : {best_high_confidence_row['high_confidence_threshold']}",
                f"- Accuracy : {best_high_confidence_row['high_confidence_accuracy']}",
                f"- Coverage : {best_high_confidence_row['high_confidence_coverage']}",
                f"- Selected rows : {best_high_confidence_row['high_confidence_selected_rows']}",
                f"- Predicted DRAW rows : {best_high_confidence_row['high_confidence_predicted_draw_rows']}",
                "",
            ]
        )

    lines.extend(
        [
            "Comparison table :",
            comparison[display_columns].to_string(index=False),
            "",
            "Generated files :",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(CSV_PATH.relative_to(PROJECT_ROOT)),
            str(DECISION_PATH.relative_to(PROJECT_ROOT)),
            "",
        ]
    )

    return "\n".join(lines)


# Construit la décision V3 à partir des résultats obtenus.
def build_decision(comparison: pd.DataFrame) -> str:
    best_f1_row = comparison.sort_values(by=["f1_macro", "recall_DRAW", "accuracy"], ascending=False).iloc[0]
    best_draw_row = comparison.sort_values(by=["recall_DRAW", "f1_macro", "accuracy"], ascending=False).iloc[0]
    best_high_confidence_row = get_best_high_confidence_row(comparison)

    improves_f1 = best_f1_row["f1_macro"] > V2_CANDIDATE_F1_MACRO
    improves_draw = best_f1_row["recall_DRAW"] > V2_CANDIDATE_DRAW_RECALL
    improves_high_confidence = False

    if best_high_confidence_row is not None:
        improves_high_confidence = (
            best_high_confidence_row["high_confidence_accuracy"] >= REFERENCE_HIGH_CONFIDENCE_ACCURACY
            and best_high_confidence_row["high_confidence_coverage"] > REFERENCE_HIGH_CONFIDENCE_COVERAGE
        )

    if improves_f1 and improves_draw:
        final_decision = (
            "Decision : candidat V3 potentiel. Le meilleur groupe ameliore a la fois le F1 macro "
            "et le DRAW recall par rapport au candidat V2. Il faut conserver cette piste comme candidat V3 experimental."
        )
    elif improves_f1 or improves_draw:
        final_decision = (
            "Decision : amelioration partielle. Une famille V3 apporte un signal utile, "
            "mais elle ne suffit pas encore pour remplacer le candidat V2 ou integrer le modele au produit."
        )
    elif improves_high_confidence:
        final_decision = (
            "Decision : piste utile seulement en forte confiance. Le modele peut aider a selectionner moins de matchs "
            "avec plus de precision, mais il reste insuffisant comme predicteur general 1X2."
        )
    else:
        final_decision = (
            "Decision : pas d'amelioration suffisante par rapport au candidat V2. "
            "Conserver les resultats comme preuve experimentale et ne rien modifier dans l'application."
        )

    lines = [
        "RubyBets - ML 1X2 V3 feature groups decision",
        "52 - Decision apres experimentation V3",
        "",
        "Decision de perimetre :",
        "- Aucun modele officiel n'est remplace automatiquement.",
        "- Aucun candidat V3 n'est sauvegarde automatiquement dans models/ml/1x2/.",
        "- PostgreSQL, ml.features, l'API et le frontend ne sont pas modifies.",
        "- Les resultats restent des preuves experimentales dans reports/evidence/ml_training/.",
        "",
        "Reference V2 a battre :",
        f"- Feature set V2 : {V2_CANDIDATE_FEATURE_SET}",
        f"- Accuracy V2 : {V2_CANDIDATE_ACCURACY:.4f}",
        f"- F1 macro V2 : {V2_CANDIDATE_F1_MACRO:.4f}",
        f"- DRAW recall V2 : {V2_CANDIDATE_DRAW_RECALL:.4f}",
        "",
        "Meilleur compromis F1 macro observe :",
        f"- Feature group : {best_f1_row['feature_group']}",
        f"- Model : {best_f1_row['model']}",
        f"- Accuracy : {best_f1_row['accuracy']}",
        f"- F1 macro : {best_f1_row['f1_macro']}",
        f"- DRAW recall : {best_f1_row['recall_DRAW']}",
        f"- Ameliore F1 macro : {improves_f1}",
        f"- Ameliore DRAW recall : {improves_draw}",
        "",
        "Meilleur DRAW recall observe :",
        f"- Feature group : {best_draw_row['feature_group']}",
        f"- Model : {best_draw_row['model']}",
        f"- Accuracy : {best_draw_row['accuracy']}",
        f"- F1 macro : {best_draw_row['f1_macro']}",
        f"- DRAW recall : {best_draw_row['recall_DRAW']}",
        "",
    ]

    if best_high_confidence_row is None:
        lines.extend(
            [
                "Meilleur signal forte confiance observe :",
                "- Aucun candidat n'atteint la cible high-confidence accuracy >= 0.70.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Meilleur signal forte confiance observe :",
                f"- Feature group : {best_high_confidence_row['feature_group']}",
                f"- Model : {best_high_confidence_row['model']}",
                f"- Threshold : {best_high_confidence_row['high_confidence_threshold']}",
                f"- Accuracy : {best_high_confidence_row['high_confidence_accuracy']}",
                f"- Coverage : {best_high_confidence_row['high_confidence_coverage']}",
                f"- Selected rows : {best_high_confidence_row['high_confidence_selected_rows']}",
                f"- Predicted DRAW rows : {best_high_confidence_row['high_confidence_predicted_draw_rows']}",
                f"- Ameliore le signal forte confiance : {improves_high_confidence}",
                "",
            ]
        )

    lines.extend(
        [
            "Decision finale :",
            final_decision,
            "",
            "Formulation soutenance :",
            "RubyBets a teste une iteration V3 de feature engineering sur les predictions 1X2.",
            "Les nouvelles variables sont evaluees par familles pour eviter d'ajouter de la complexite inutile.",
            "Le scoring explicable V1 reste le socle produit tant qu'un modele ML n'est pas valide globalement.",
            "",
            "Statut de suivi :",
            "- Tache realisee : experimentation V3 des groupes de features 1X2.",
            "- Statut source a mettre a jour : realise si les fichiers 50, 51 et 52 sont generes.",
            "- Fichiers concernes : reports/evidence/ml_training/50, 51 et 52.",
            "",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les rapports de synthèse, résultats CSV et décision.
def save_reports(comparison: pd.DataFrame, summary: str, decision: str) -> None:
    ensure_report_dir()
    comparison.to_csv(CSV_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    DECISION_PATH.write_text(decision, encoding="utf-8")


# Lance toute l'expérimentation V3 en mémoire.
def main() -> None:
    try:
        ensure_report_dir()

        database_url = get_database_url()
        clean_matches = fetch_clean_matches(database_url)

        print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
        print("Construction des features V3 en memoire...", flush=True)

        feature_dataframe = build_v3_feature_dataframe(clean_matches)

        print(f"Lignes de features construites : {len(feature_dataframe)}", flush=True)
        print("Evaluation des groupes de features V3...", flush=True)

        comparison = run_v3_feature_group_comparison(feature_dataframe)
        summary = build_summary(clean_matches, feature_dataframe, comparison)
        decision = build_decision(comparison)

        save_reports(comparison, summary, decision)

        best_f1_row = comparison.sort_values(by=["f1_macro", "recall_DRAW", "accuracy"], ascending=False).iloc[0]

        print("OK - Experimentation V3 feature groups terminee.", flush=True)
        print(f"Best feature group: {best_f1_row['feature_group']}", flush=True)
        print(f"Best model: {best_f1_row['model']}", flush=True)
        print(f"Accuracy: {best_f1_row['accuracy']}", flush=True)
        print(f"F1 macro: {best_f1_row['f1_macro']}", flush=True)
        print(f"DRAW recall: {best_f1_row['recall_DRAW']}", flush=True)
        print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}", flush=True)
        print(f"CSV saved: {CSV_PATH.relative_to(PROJECT_ROOT)}", flush=True)
        print(f"Decision saved: {DECISION_PATH.relative_to(PROJECT_ROOT)}", flush=True)

    except Exception as error:
        print("Erreur pendant l'experimentation V3 feature groups.", flush=True)
        print(error, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# experiment_1x2_v3_feature_groups.py
# ├── lit backend/.env via compare_1x2_feature_sets.py
# ├── lit PostgreSQL : ml.clean_matches
# ├── réutilise le socle V2 : last10 + team_strength + match_balance
# ├── construit en mémoire les groupes V3 : domicile/extérieur, draw rates, streaks, stabilité, fatigue
# ├── entraîne LogisticRegression / RandomForest / GradientBoosting / XGBoost 
# ├── ne modifie pas PostgreSQL, ml.features, API, frontend ou modèle officiel
# └── écrit reports/evidence/ml_training/50, 51 et 52
