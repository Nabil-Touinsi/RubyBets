# Ce fichier centralise le formatage et la récupération des données match utilisées par RubyBets.

from typing import Any

from app.services.football_data_client import get_football_data


def clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }


def format_team(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": team.get("id"),
        "name": team.get("name"),
        "short_name": team.get("shortName"),
        "tla": team.get("tla"),
        "crest": team.get("crest"),
    }


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


async def get_match_with_standings(match_id: int) -> dict[str, Any]:
    match_data = await get_football_data(f"/matches/{match_id}")
    match = match_data.get("match", match_data)

    competition_code = match.get("competition", {}).get("code")
    home_team_id = match.get("homeTeam", {}).get("id")
    away_team_id = match.get("awayTeam", {}).get("id")

    standings: list[dict[str, Any]] = []

    if competition_code:
        standings_data = await get_football_data(
            f"/competitions/{competition_code}/standings"
        )
        standings = standings_data.get("standings", [])

    return {
        "match": match,
        "competition_code": competition_code,
        "home_standing": find_team_standing(standings, home_team_id),
        "away_standing": find_team_standing(standings, away_team_id),
    }
