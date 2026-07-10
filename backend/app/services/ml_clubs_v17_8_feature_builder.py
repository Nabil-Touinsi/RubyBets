# Role du fichier :
# Ce builder transforme un historique clubs RubyBets reel en signaux compatibles avec le moteur experimental V17.8.
# Il ne modifie pas le moteur national, les Archives, PostgreSQL, ni les routes de demo V17.8.

from __future__ import annotations

from typing import Any

from app.services.ml_v17_8_service import ABSTAIN_STATUS, ABSTAIN_VALUE


BUILDER_SOURCE = "rubybets_ml_clubs_v17_8_feature_builder"
BUILDER_SCOPE = "experimental_clubs"
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


# Produit un statut qualite simple pour savoir si la route peut etre analysee proprement.
def resolve_clubs_feature_status(features: dict[str, Any]) -> str:
    if features.get("min_history_count_last_10", 0) >= MIN_USEFUL_HISTORY_COUNT:
        return "complete"

    if features.get("min_history_count_last_10", 0) > 0:
        return "partial"

    return "unavailable"


# Construit la recommandation de base par defaut lorsque V17.8 clubs n'a pas de fallback.
def build_default_base_recommendation() -> dict[str, Any]:
    return {
        "status": ABSTAIN_STATUS,
        "type": ABSTAIN_VALUE,
        "value": ABSTAIN_VALUE,
        "source": "RUBYBETS_CLUBS_V17_8_NO_BASE_RECOMMENDATION",
    }


# Construit les metadonnees utiles pour tracer la preparation des features clubs.
def build_clubs_feature_metadata(
    team_history_response: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    home_history = team_history_response.get("home_team_history", {})
    away_history = team_history_response.get("away_team_history", {})
    head_to_head = team_history_response.get("head_to_head", [])

    return {
        "builder_source": BUILDER_SOURCE,
        "builder_scope": BUILDER_SCOPE,
        "features_status": resolve_clubs_feature_status(features),
        "match_id": team_history_response.get("match_id"),
        "source_used": team_history_response.get("source_used"),
        "data_status": team_history_response.get("data_status"),
        "home_team": home_history.get("team_name"),
        "away_team": away_history.get("team_name"),
        "home_recent_count": features.get("home_recent_count"),
        "away_recent_count": features.get("away_recent_count"),
        "head_to_head_count": len(head_to_head) if isinstance(head_to_head, list) else 0,
        "recent_matches_limit": RECENT_MATCHES_LIMIT,
        "score_formula": (
            "0.35*btts_rate + 0.25*over_1_5_rate "
            "+ 0.25*expected_total_component + 0.15*failed_to_score_component"
        ),
        "technical_note": (
            "btts_score_proxy est mappe vers v17_6_score uniquement parce que "
            "le service V17.8 attend ce nom de feature."
        ),
    }


# Construit le payload final compatible avec ml_v17_8_feature_adapter.py.
def build_clubs_v17_8_prepared_match_data(
    team_history_response: dict[str, Any],
) -> dict[str, Any]:
    features = compute_clubs_btts_features(team_history_response)
    metadata = build_clubs_feature_metadata(team_history_response, features)

    return {
        "source": BUILDER_SOURCE,
        "scope": BUILDER_SCOPE,
        "match": {
            "id": team_history_response.get("match_id"),
            "data_status": team_history_response.get("data_status"),
            "source_used": team_history_response.get("source_used"),
        },
        "btts_signals": {
            "v17_6_score": features.get("v17_6_score"),
            "min_history_count_last_10": features.get("min_history_count_last_10"),
            "expected_home_goals_proxy": features.get("expected_home_goals_proxy"),
            "expected_away_goals_proxy": features.get("expected_away_goals_proxy"),
            "expected_total_goals_proxy": features.get("expected_total_goals_proxy"),
            "combined_btts_rate_last_10": features.get("combined_btts_rate_last_10"),
            "combined_over_1_5_rate_last_10": features.get("combined_over_1_5_rate_last_10"),
            "home_failed_to_score_rate_last_10": features.get("home_failed_to_score_rate_last_10"),
            "away_failed_to_score_rate_last_10": features.get("away_failed_to_score_rate_last_10"),
        },
        "base_recommendation": build_default_base_recommendation(),
        "clubs_features_debug": features,
        "feature_metadata": metadata,
    }


# Schema de communication :
# ml_clubs_v17_8_feature_builder.py
#   -> recoit la reponse produit build_team_history_response(match_id)
#   -> lit home_team_history.recent_matches et away_team_history.recent_matches
#   -> calcule les signaux clubs BTTS sur les 10 derniers matchs
#   -> mappe btts_score_proxy vers v17_6_score pour compatibilite V17.8
#   -> construit un prepared_match_data compatible avec ml_v17_8_feature_adapter.py
#   -> ne modifie pas team_history_service.py, les Archives ou le moteur national