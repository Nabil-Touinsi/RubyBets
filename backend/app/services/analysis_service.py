# Ce fichier regroupe le moteur d’analyse et de scoring explicable avant-match de RubyBets.

from typing import Any


def build_context_summary(
    match: dict[str, Any],
    home_standing: dict[str, Any] | None,
    away_standing: dict[str, Any] | None,
) -> dict[str, Any]:
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
    match: dict[str, Any],
    home_standing: dict[str, Any] | None,
    away_standing: dict[str, Any] | None,
) -> dict[str, Any]:
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
    match: dict[str, Any],
    home_standing: dict[str, Any] | None,
    away_standing: dict[str, Any] | None,
) -> dict[str, Any]:
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
