# Ce fichier expose les matchs RubyBets que le frontend utilisera dans le MVP.

from fastapi import APIRouter, HTTPException, Query

from app.services.football_data_client import get_football_data


router = APIRouter(prefix="/api/matches", tags=["Matches"])


MVP_COMPETITION_CODES = {
    "PL",    # Premier League
    "FL1",   # Ligue 1
    "BL1",   # Bundesliga
    "SA",    # Serie A
    "PD",    # La Liga
    "CL",    # Champions League
}


def clean_params(params: dict) -> dict:
    return {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }


def format_team(team: dict) -> dict:
    return {
        "id": team.get("id"),
        "name": team.get("name"),
        "short_name": team.get("shortName"),
        "tla": team.get("tla"),
        "crest": team.get("crest"),
    }


def format_match(match: dict) -> dict:
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


def filter_matches_by_team(matches: list[dict], team: str | None) -> list[dict]:
    if not team:
        return matches

    searched_team = team.lower()

    return [
        match
        for match in matches
        if searched_team in match.get("homeTeam", {}).get("name", "").lower()
        or searched_team in match.get("awayTeam", {}).get("name", "").lower()
    ]

def find_team_standing(standings: list[dict], team_id: int | None) -> dict | None:
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


def build_context_summary(
    match: dict,
    home_standing: dict | None,
    away_standing: dict | None,
) -> dict:
    home_team = match.get("homeTeam", {}).get("name")
    away_team = match.get("awayTeam", {}).get("name")

    return {
        "title": f"{home_team} vs {away_team}",
        "main_facts": [
            "Match analysé avant le coup d'envoi.",
            "Classement récupéré depuis Football-Data.org.",
            "Les données affichées servent uniquement à préparer l'analyse avant-match.",
        ],
        "home_team_position": home_standing.get("position") if home_standing else None,
        "away_team_position": away_standing.get("position") if away_standing else None,
    }

def build_prematch_analysis(
    match: dict,
    home_standing: dict | None,
    away_standing: dict | None,
) -> dict:
    home_team = match.get("homeTeam", {}).get("name")
    away_team = match.get("awayTeam", {}).get("name")

    observed_facts = []
    key_factors = []
    interpretation = []

    if home_standing:
        observed_facts.append(
            f"{home_team} est classé {home_standing.get('position')} avec "
            f"{home_standing.get('points')} points et une différence de buts de "
            f"{home_standing.get('goal_difference')}."
        )

    if away_standing:
        observed_facts.append(
            f"{away_team} est classé {away_standing.get('position')} avec "
            f"{away_standing.get('points')} points et une différence de buts de "
            f"{away_standing.get('goal_difference')}."
        )

    if home_standing and away_standing:
        position_gap = away_standing.get("position") - home_standing.get("position")
        points_gap = home_standing.get("points") - away_standing.get("points")
        goal_difference_gap = home_standing.get("goal_difference") - away_standing.get("goal_difference")

        key_factors.append(
            {
                "label": "Écart au classement",
                "value": abs(position_gap),
                "reading": (
                    f"{home_team} est mieux placé au classement."
                    if position_gap > 0
                    else f"{away_team} est mieux placé au classement."
                    if position_gap < 0
                    else "Les deux équipes sont proches au classement."
                ),
            }
        )

        key_factors.append(
            {
                "label": "Écart de points",
                "value": abs(points_gap),
                "reading": (
                    f"{home_team} possède plus de points."
                    if points_gap > 0
                    else f"{away_team} possède plus de points."
                    if points_gap < 0
                    else "Les deux équipes ont le même nombre de points."
                ),
            }
        )

        key_factors.append(
            {
                "label": "Différence de buts",
                "value": abs(goal_difference_gap),
                "reading": (
                    f"{home_team} présente une meilleure différence de buts."
                    if goal_difference_gap > 0
                    else f"{away_team} présente une meilleure différence de buts."
                    if goal_difference_gap < 0
                    else "Les deux équipes ont une différence de buts équivalente."
                ),
            }
        )

        if points_gap >= 8 and goal_difference_gap > 0:
            interpretation.append(
                f"Les données disponibles donnent un contexte plus favorable à {home_team}, "
                "notamment grâce à l'écart de points et à une différence de buts supérieure."
            )
            context_trend = "home_context_advantage"
        elif points_gap <= -8 and goal_difference_gap < 0:
            interpretation.append(
                f"Les données disponibles donnent un contexte plus favorable à {away_team}, "
                "notamment grâce à l'écart de points et à une différence de buts supérieure."
            )
            context_trend = "away_context_advantage"
        else:
            interpretation.append(
                "Les données disponibles montrent un contexte relativement équilibré. "
                "L'écart observé ne suffit pas à produire une lecture fortement orientée."
            )
            context_trend = "balanced_context"
    else:
        context_trend = "insufficient_data"
        interpretation.append(
            "Le classement complet des deux équipes n'est pas disponible. "
            "L'analyse reste donc partielle."
        )

    return {
        "title": f"Analyse pré-match : {home_team} vs {away_team}",
        "context_trend": context_trend,
        "observed_facts": observed_facts,
        "key_factors": key_factors,
        "interpretation": interpretation,
        "limits": [
            "Cette analyse ne constitue pas une prédiction de résultat.",
            "Elle repose uniquement sur les données réellement disponibles via Football-Data.org.",
            "Les absences, compositions probables et signaux d'actualité ne sont pas encore intégrés dans cette première version.",
        ],
    }

def safe_divide(value: int | float | None, divider: int | float | None) -> float | None:
    if value is None or divider in (None, 0):
        return None

    return round(value / divider, 2)


def build_predictions(
    match: dict,
    home_standing: dict | None,
    away_standing: dict | None,
) -> dict:
    home_team = match.get("homeTeam", {}).get("name")
    away_team = match.get("awayTeam", {}).get("name")

    if not home_standing or not away_standing:
        return {
            "status": "partial",
            "message": "Les données de classement sont insuffisantes pour produire des prédictions fiables.",
            "predictions": None,
        }

    points_gap = home_standing.get("points", 0) - away_standing.get("points", 0)
    goal_difference_gap = home_standing.get("goal_difference", 0) - away_standing.get("goal_difference", 0)
    position_gap = away_standing.get("position", 0) - home_standing.get("position", 0)

    home_goals_for_avg = safe_divide(
        home_standing.get("goals_for"),
        home_standing.get("played_games"),
    )
    home_goals_against_avg = safe_divide(
        home_standing.get("goals_against"),
        home_standing.get("played_games"),
    )
    away_goals_for_avg = safe_divide(
        away_standing.get("goals_for"),
        away_standing.get("played_games"),
    )
    away_goals_against_avg = safe_divide(
        away_standing.get("goals_against"),
        away_standing.get("played_games"),
    )

    average_goal_context = None
    if all(
        value is not None
        for value in [
            home_goals_for_avg,
            home_goals_against_avg,
            away_goals_for_avg,
            away_goals_against_avg,
        ]
    ):
        home_match_goal_avg = home_goals_for_avg + home_goals_against_avg
        away_match_goal_avg = away_goals_for_avg + away_goals_against_avg
        average_goal_context = round((home_match_goal_avg + away_match_goal_avg) / 2, 2)

    if points_gap >= 8 and goal_difference_gap >= 5:
        one_x_two_prediction = {
            "market": "1X2",
            "prediction": "HOME_TEAM_TREND",
            "label": f"Tendance favorable à {home_team}",
            "confidence": "medium",
            "risk": "medium",
            "justification": (
                f"{home_team} possède un avantage au classement, en points "
                "et en différence de buts."
            ),
        }
    elif points_gap <= -8 and goal_difference_gap <= -5:
        one_x_two_prediction = {
            "market": "1X2",
            "prediction": "AWAY_TEAM_TREND",
            "label": f"Tendance favorable à {away_team}",
            "confidence": "medium",
            "risk": "medium",
            "justification": (
                f"{away_team} possède un avantage au classement, en points "
                "et en différence de buts."
            ),
        }
    else:
        one_x_two_prediction = {
            "market": "1X2",
            "prediction": "BALANCED_TREND",
            "label": "Tendance prudente / match à surveiller",
            "confidence": "low",
            "risk": "high",
            "justification": (
                "Les écarts disponibles ne sont pas assez nets pour orienter fortement "
                "la lecture du match."
            ),
        }

    if average_goal_context is None:
        goals_prediction = {
            "market": "GOALS",
            "prediction": "INSUFFICIENT_DATA",
            "label": "Volume de buts non évalué",
            "confidence": "low",
            "risk": "high",
            "justification": "Les moyennes de buts disponibles sont insuffisantes.",
        }
    elif average_goal_context >= 2.8:
        goals_prediction = {
            "market": "GOALS",
            "prediction": "OVER_2_5_TREND",
            "label": "Tendance vers un match avec plusieurs buts",
            "confidence": "medium",
            "risk": "medium",
            "justification": (
                f"La moyenne combinée des buts observés est de {average_goal_context} "
                "par match."
            ),
        }
    elif average_goal_context <= 2.3:
        goals_prediction = {
            "market": "GOALS",
            "prediction": "UNDER_2_5_TREND",
            "label": "Tendance vers un match plus fermé",
            "confidence": "medium",
            "risk": "medium",
            "justification": (
                f"La moyenne combinée des buts observés est de {average_goal_context} "
                "par match."
            ),
        }
    else:
        goals_prediction = {
            "market": "GOALS",
            "prediction": "NEUTRAL_GOALS_TREND",
            "label": "Volume de buts incertain",
            "confidence": "low",
            "risk": "high",
            "justification": (
                f"La moyenne combinée des buts observés est de {average_goal_context}, "
                "ce qui ne donne pas une tendance assez nette."
            ),
        }

    if home_goals_for_avg is None or away_goals_for_avg is None:
        btts_prediction = {
            "market": "BTTS",
            "prediction": "INSUFFICIENT_DATA",
            "label": "BTTS non évalué",
            "confidence": "low",
            "risk": "high",
            "justification": "Les moyennes offensives disponibles sont insuffisantes.",
        }
    elif home_goals_for_avg >= 1.3 and away_goals_for_avg >= 1.2:
        btts_prediction = {
            "market": "BTTS",
            "prediction": "BTTS_YES_TREND",
            "label": "Tendance : les deux équipes peuvent marquer",
            "confidence": "low",
            "risk": "high",
            "justification": (
                "Les deux équipes présentent une moyenne offensive suffisante, "
                "mais cette lecture reste prudente sans données de compositions ou d'absences."
            ),
        }
    else:
        btts_prediction = {
            "market": "BTTS",
            "prediction": "BTTS_NO_CLEAR_TREND",
            "label": "BTTS incertain",
            "confidence": "low",
            "risk": "high",
            "justification": (
                "Les moyennes offensives disponibles ne permettent pas de dégager "
                "une tendance forte."
            ),
        }

    return {
        "status": "available",
        "method": "rules_based_scoring_v1",
        "inputs": {
            "home_team_position": home_standing.get("position"),
            "away_team_position": away_standing.get("position"),
            "position_gap": abs(position_gap),
            "points_gap": abs(points_gap),
            "goal_difference_gap": abs(goal_difference_gap),
            "average_goal_context": average_goal_context,
            "home_goals_for_avg": home_goals_for_avg,
            "away_goals_for_avg": away_goals_for_avg,
        },
        "predictions": {
            "one_x_two": one_x_two_prediction,
            "goals": goals_prediction,
            "btts": btts_prediction,
        },
        "limits": [
            "Ces prédictions sont des tendances analytiques, pas des certitudes.",
            "Le moteur actuel est une première version explicable basée sur des règles et des données réelles.",
            "Les absences, compositions probables, forme détaillée et actualités ne sont pas encore intégrées.",
        ],
    }

@router.get("")
async def get_matches(
    competition_code: str = Query("PL"),
    status: str = Query("SCHEDULED"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    team: str | None = Query(None),
):
    competition_code = competition_code.upper()

    if competition_code not in MVP_COMPETITION_CODES:
        raise HTTPException(
            status_code=400,
            detail="Competition not supported in RubyBets MVP.",
        )

    data = await get_football_data(
        f"/competitions/{competition_code}/matches",
        params=clean_params(
            {
                "status": status,
                "dateFrom": date_from,
                "dateTo": date_to,
            }
        ),
    )

    raw_matches = data.get("matches", [])
    filtered_matches = filter_matches_by_team(raw_matches, team)

    formatted_matches = [
        format_match(match)
        for match in filtered_matches
    ]

    return {
        "source": "football-data.org",
        "competition_code": competition_code,
        "filters": {
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "team": team,
        },
        "count": len(formatted_matches),
        "matches": formatted_matches,
    }


@router.get("/{match_id}")
async def get_match_details(match_id: int):
    data = await get_football_data(f"/matches/{match_id}")

    match = data.get("match", data)

    return {
        "source": "football-data.org",
        "match": format_match(match),
        "data_freshness": {
            "last_updated": match.get("lastUpdated"),
            "provider": "football-data.org",
        },
    }

@router.get("/{match_id}/context")
async def get_match_context(match_id: int):
    match_data = await get_football_data(f"/matches/{match_id}")
    match = match_data.get("match", match_data)

    competition_code = match.get("competition", {}).get("code")
    home_team_id = match.get("homeTeam", {}).get("id")
    away_team_id = match.get("awayTeam", {}).get("id")

    if not competition_code:
        raise HTTPException(
            status_code=404,
            detail="Competition code not found for this match.",
        )

    standings_data = await get_football_data(
        f"/competitions/{competition_code}/standings"
    )

    standings = standings_data.get("standings", [])

    home_standing = find_team_standing(standings, home_team_id)
    away_standing = find_team_standing(standings, away_team_id)

    return {
        "source": "football-data.org",
        "match": format_match(match),
        "context": {
            "competition": {
                "code": competition_code,
                "name": match.get("competition", {}).get("name"),
            },
            "home_team_standing": home_standing,
            "away_team_standing": away_standing,
            "summary": build_context_summary(
                match=match,
                home_standing=home_standing,
                away_standing=away_standing,
            ),
        },
        "data_freshness": {
            "match_last_updated": match.get("lastUpdated"),
            "provider": "football-data.org",
        },
    }

@router.get("/{match_id}/analysis")
async def get_match_analysis(match_id: int):
    match_data = await get_football_data(f"/matches/{match_id}")
    match = match_data.get("match", match_data)

    competition_code = match.get("competition", {}).get("code")
    home_team_id = match.get("homeTeam", {}).get("id")
    away_team_id = match.get("awayTeam", {}).get("id")

    if not competition_code:
        raise HTTPException(
            status_code=404,
            detail="Competition code not found for this match.",
        )

    standings_data = await get_football_data(
        f"/competitions/{competition_code}/standings"
    )

    standings = standings_data.get("standings", [])

    home_standing = find_team_standing(standings, home_team_id)
    away_standing = find_team_standing(standings, away_team_id)

    return {
        "source": "football-data.org",
        "match_id": match_id,
        "analysis": build_prematch_analysis(
            match=match,
            home_standing=home_standing,
            away_standing=away_standing,
        ),
        "data_used": {
            "match_details": True,
            "competition_standings": True,
            "home_team_standing_available": home_standing is not None,
            "away_team_standing_available": away_standing is not None,
        },
        "data_freshness": {
            "match_last_updated": match.get("lastUpdated"),
            "provider": "football-data.org",
        },
    }

@router.get("/{match_id}/predictions")
async def get_match_predictions(match_id: int):
    match_data = await get_football_data(f"/matches/{match_id}")
    match = match_data.get("match", match_data)

    competition_code = match.get("competition", {}).get("code")
    home_team_id = match.get("homeTeam", {}).get("id")
    away_team_id = match.get("awayTeam", {}).get("id")

    if not competition_code:
        raise HTTPException(
            status_code=404,
            detail="Competition code not found for this match.",
        )

    standings_data = await get_football_data(
        f"/competitions/{competition_code}/standings"
    )

    standings = standings_data.get("standings", [])

    home_standing = find_team_standing(standings, home_team_id)
    away_standing = find_team_standing(standings, away_team_id)

    return {
        "source": "football-data.org",
        "match_id": match_id,
        "predictions": build_predictions(
            match=match,
            home_standing=home_standing,
            away_standing=away_standing,
        ),
        "data_used": {
            "match_details": True,
            "competition_standings": True,
            "home_team_standing_available": home_standing is not None,
            "away_team_standing_available": away_standing is not None,
        },
        "data_freshness": {
            "match_last_updated": match.get("lastUpdated"),
            "provider": "football-data.org",
        },
    }