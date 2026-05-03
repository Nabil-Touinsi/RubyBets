# Ce fichier centralise le formatage et la récupération enrichie des données match utilisées par RubyBets.
# Il prépare des objets propres pour les routes API et réutilise le cache pour les détails match et classements.

from typing import Any

from app.services.cache_service import build_cache_name, get_cached_football_data


MATCH_DETAIL_CACHE_TTL_MINUTES = 30
STANDINGS_CACHE_TTL_MINUTES = 60


# Cette fonction supprime les paramètres vides avant un appel API.
def clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }


# Cette fonction formate les données d'une équipe dans une structure stable pour le frontend.
def format_team(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": team.get("id"),
        "name": team.get("name"),
        "short_name": team.get("shortName"),
        "tla": team.get("tla"),
        "crest": team.get("crest"),
    }


# Cette fonction formate un match Football-Data dans une structure homogène pour RubyBets.
def format_match(match: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": match.get("id"),
        "utc_date": match.get("utcDate"),
        "status": match.get("status"),
        "matchday": match.get("matchday"),
        "stage": match.get("stage"),
        "group": match.get("group"),
        "last_updated": match.get("lastUpdated"),
        "area": {
            "id": match.get("area", {}).get("id"),
            "name": match.get("area", {}).get("name"),
            "code": match.get("area", {}).get("code"),
            "flag": match.get("area", {}).get("flag"),
        },
        "competition": {
            "id": match.get("competition", {}).get("id"),
            "code": match.get("competition", {}).get("code"),
            "name": match.get("competition", {}).get("name"),
            "type": match.get("competition", {}).get("type"),
            "emblem": match.get("competition", {}).get("emblem"),
        },
        "season": {
            "id": match.get("season", {}).get("id"),
            "start_date": match.get("season", {}).get("startDate"),
            "end_date": match.get("season", {}).get("endDate"),
            "current_matchday": match.get("season", {}).get("currentMatchday"),
            "winner": match.get("season", {}).get("winner"),
        },
        "home_team": format_team(match.get("homeTeam", {})),
        "away_team": format_team(match.get("awayTeam", {})),
        "score": {
            "winner": match.get("score", {}).get("winner"),
            "duration": match.get("score", {}).get("duration"),
            "full_time": match.get("score", {}).get("fullTime"),
            "half_time": match.get("score", {}).get("halfTime"),
        },
        "referees": [
            {
                "id": referee.get("id"),
                "name": referee.get("name"),
                "type": referee.get("type"),
                "nationality": referee.get("nationality"),
            }
            for referee in match.get("referees", [])
        ],
    }


# Cette fonction filtre localement une liste de matchs à partir d'un nom d'équipe.
def filter_matches_by_team(
    matches: list[dict[str, Any]],
    team: str | None,
) -> list[dict[str, Any]]:
    if not team:
        return matches

    searched_team = team.lower()

    return [
        match
        for match in matches
        if searched_team in match.get("homeTeam", {}).get("name", "").lower()
        or searched_team in match.get("awayTeam", {}).get("name", "").lower()
    ]


# Cette fonction retrouve la ligne de classement correspondant à une équipe donnée.
def find_team_standing(
    standings: list[dict[str, Any]],
    team_id: int | None,
) -> dict[str, Any] | None:
    if not team_id:
        return None

    for standing_group in standings:
        if standing_group.get("type") != "TOTAL":
            continue

        for row in standing_group.get("table", []):
            team = row.get("team", {})

            if team.get("id") == team_id:
                return {
                    "position": row.get("position"),
                    "team": format_team(team),
                    "played_games": row.get("playedGames"),
                    "won": row.get("won"),
                    "draw": row.get("draw"),
                    "lost": row.get("lost"),
                    "points": row.get("points"),
                    "goals_for": row.get("goalsFor"),
                    "goals_against": row.get("goalsAgainst"),
                    "goal_difference": row.get("goalDifference"),
                }

    return None


# Cette fonction récupère un match et son classement associé en utilisant le cache local.
async def get_match_with_standings(match_id: int) -> dict[str, Any]:
    match_data, match_freshness = await get_cached_football_data(
        cache_name=build_cache_name("match", match_id),
        endpoint=f"/matches/{match_id}",
        ttl_minutes=MATCH_DETAIL_CACHE_TTL_MINUTES,
    )
    match = match_data.get("match", match_data)

    competition_code = match.get("competition", {}).get("code")
    home_team_id = match.get("homeTeam", {}).get("id")
    away_team_id = match.get("awayTeam", {}).get("id")

    standings: list[dict[str, Any]] = []
    standings_freshness: dict[str, Any] | None = None

    if competition_code:
        standings_data, standings_freshness = await get_cached_football_data(
            cache_name=build_cache_name("standings", competition_code),
            endpoint=f"/competitions/{competition_code}/standings",
            ttl_minutes=STANDINGS_CACHE_TTL_MINUTES,
        )
        standings = standings_data.get("standings", [])

    return {
        "match": match,
        "competition_code": competition_code,
        "home_standing": find_team_standing(standings, home_team_id),
        "away_standing": find_team_standing(standings, away_team_id),
        "data_freshness": {
            "match": match_freshness,
            "standings": standings_freshness,
        },
    }


# Schéma de communication du fichier :
# match_service.py
# ├── utilise cache_service.py pour récupérer les matchs et classements avec cache
# ├── fournit des données formatées à matches.py et recommendation_service.py
# ├── dépend des réponses Football-Data structurées par football_data_client.py
# └── alimente les blocs contexte, analyse, prédictions et recommandation multi-matchs
