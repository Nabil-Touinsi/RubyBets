# Rôle du fichier :
# Ce module calcule les signaux historiques BTTS nécessaires aux experts legacy V19.
# Il ne construit plus de payload autonome pour les anciennes routes V17/V18.

from __future__ import annotations

from typing import Any

BUILDER_SOURCE = "rubybets_ml_clubs_v17_8_feature_builder"
RECENT_MATCHES_LIMIT = 10
MIN_USEFUL_HISTORY_COUNT = 8


# Recupere les derniers matchs exploitables d'une equipe avec une limite prudente.
def get_recent_matches(history: dict[str, Any], limit: int = RECENT_MATCHES_LIMIT) -> list[dict[str, Any]]:
    matches = history.get("recent_matches", [])

    if not isinstance(matches, list):
        return []

    return matches[:limit]


# Convertit une valeur numerique en float sans faire planter le builder.
def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


# Calcule une moyenne simple sur une liste de matchs.
def average_match_value(matches: list[dict[str, Any]], key: str) -> float:
    if not matches:
        return 0.0

    total = sum(safe_float(match.get(key)) for match in matches)

    return round(total / len(matches), 3)


# Calcule un taux simple sur une liste de matchs.
def rate_matches(matches: list[dict[str, Any]], condition_key: str) -> float:
    if not matches:
        return 0.0

    if condition_key == "btts":
        count = sum(
            1
            for match in matches
            if safe_float(match.get("goals_for")) > 0
            and safe_float(match.get("goals_against")) > 0
        )
    elif condition_key == "over_1_5":
        count = sum(
            1
            for match in matches
            if safe_float(match.get("goals_for")) + safe_float(match.get("goals_against")) >= 2
        )
    elif condition_key == "failed_to_score":
        count = sum(
            1
            for match in matches
            if safe_float(match.get("goals_for")) == 0
        )
    else:
        count = 0

    return round(count / len(matches), 3)


# Calcule un score proxy BTTS clair cote RubyBets Clubs.
def compute_btts_score_proxy(
    combined_btts_rate: float,
    combined_over_15_rate: float,
    expected_total_goals: float,
    home_failed_to_score_rate: float,
    away_failed_to_score_rate: float,
) -> float:
    expected_component = min(expected_total_goals / 3.0, 1.0)
    failed_to_score_component = 1 - (
        (home_failed_to_score_rate + away_failed_to_score_rate) / 2
    )

    score = (
        (0.35 * combined_btts_rate)
        + (0.25 * combined_over_15_rate)
        + (0.25 * expected_component)
        + (0.15 * failed_to_score_component)
    )

    return round(score, 3)


# Calcule les signaux clubs attendus par V17.8 a partir de team-history.
def compute_clubs_btts_features(team_history_response: dict[str, Any]) -> dict[str, Any]:
    home_history = team_history_response.get("home_team_history", {})
    away_history = team_history_response.get("away_team_history", {})

    home_matches = get_recent_matches(home_history)
    away_matches = get_recent_matches(away_history)
    all_matches = [*home_matches, *away_matches]

    home_avg_goals_for = average_match_value(home_matches, "goals_for")
    home_avg_goals_against = average_match_value(home_matches, "goals_against")
    away_avg_goals_for = average_match_value(away_matches, "goals_for")
    away_avg_goals_against = average_match_value(away_matches, "goals_against")

    expected_home_goals_proxy = round(
        (home_avg_goals_for + away_avg_goals_against) / 2,
        3,
    )
    expected_away_goals_proxy = round(
        (away_avg_goals_for + home_avg_goals_against) / 2,
        3,
    )
    expected_total_goals_proxy = round(
        expected_home_goals_proxy + expected_away_goals_proxy,
        3,
    )

    combined_btts_rate = rate_matches(all_matches, "btts")
    combined_over_15_rate = rate_matches(all_matches, "over_1_5")
    home_failed_to_score_rate = rate_matches(home_matches, "failed_to_score")
    away_failed_to_score_rate = rate_matches(away_matches, "failed_to_score")

    btts_score_proxy = compute_btts_score_proxy(
        combined_btts_rate=combined_btts_rate,
        combined_over_15_rate=combined_over_15_rate,
        expected_total_goals=expected_total_goals_proxy,
        home_failed_to_score_rate=home_failed_to_score_rate,
        away_failed_to_score_rate=away_failed_to_score_rate,
    )

    return {
        "btts_score_proxy": btts_score_proxy,
        "v17_6_score": btts_score_proxy,
        "min_history_count_last_10": min(len(home_matches), len(away_matches)),
        "expected_home_goals_proxy": expected_home_goals_proxy,
        "expected_away_goals_proxy": expected_away_goals_proxy,
        "expected_total_goals_proxy": expected_total_goals_proxy,
        "combined_btts_rate_last_10": combined_btts_rate,
        "combined_over_1_5_rate_last_10": combined_over_15_rate,
        "home_failed_to_score_rate_last_10": home_failed_to_score_rate,
        "away_failed_to_score_rate_last_10": away_failed_to_score_rate,
        "home_recent_count": len(home_matches),
        "away_recent_count": len(away_matches),
        "home_avg_goals_for": home_avg_goals_for,
        "home_avg_goals_against": home_avg_goals_against,
        "away_avg_goals_for": away_avg_goals_for,
        "away_avg_goals_against": away_avg_goals_against,
    }


# Schéma de communication :
# team_history_service.py
#   -> fournit les historiques domicile et extérieur
# ml_clubs_v17_8_feature_builder.py
#   -> calcule compute_clubs_btts_features
# backend/app/v19/experts/legacy_adapters.py
#   -> adapte ces signaux au contrat expert V19
