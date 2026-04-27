# Ce fichier expose les recommandations multi-matchs générées par RubyBets pour le MVP.

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.football_data_client import get_football_data
from app.api.matches import (
    MVP_COMPETITION_CODES,
    build_predictions,
    clean_params,
    find_team_standing,
    format_match,
)


router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


class MultiMatchRecommendationRequest(BaseModel):
    competition_code: str = "PL"
    match_count: int = Field(default=3, ge=1, le=5)
    risk_level: Literal["low", "medium", "high"] = "medium"
    date_from: str | None = None
    date_to: str | None = None


def score_prediction_for_risk(prediction: dict, risk_level: str) -> int:
    score = 0

    confidence = prediction.get("confidence")
    risk = prediction.get("risk")
    market = prediction.get("market")
    prediction_value = prediction.get("prediction")

    if prediction_value == "INSUFFICIENT_DATA":
        return 0

    if confidence == "high":
        score += 50
    elif confidence == "medium":
        score += 35
    elif confidence == "low":
        score += 15

    if risk_level == "low":
        if risk == "low":
            score += 50
        elif risk == "medium":
            score += 35
        elif risk == "high":
            score += 5

        if market == "1X2":
            score += 10

    elif risk_level == "medium":
        if risk == "medium":
            score += 45
        elif risk == "low":
            score += 35
        elif risk == "high":
            score += 20

        if market in ["1X2", "GOALS"]:
            score += 5

    elif risk_level == "high":
        if risk == "high":
            score += 45
        elif risk == "medium":
            score += 35
        elif risk == "low":
            score += 20

        if market == "BTTS":
            score += 10

    return score


def choose_best_prediction_for_match(
    prediction_result: dict,
    risk_level: str,
) -> dict | None:
    if prediction_result.get("status") != "available":
        return None

    predictions = prediction_result.get("predictions", {})

    candidates = []

    for prediction_key, prediction in predictions.items():
        score = score_prediction_for_risk(
            prediction=prediction,
            risk_level=risk_level,
        )

        if score > 0:
            candidates.append(
                {
                    "prediction_key": prediction_key,
                    "score": score,
                    "recommendation": prediction,
                }
            )

    if not candidates:
        return None

    candidates.sort(key=lambda item: item["score"], reverse=True)

    return candidates[0]


@router.post("/multimatch")
async def generate_multimatch_recommendation(
    request: MultiMatchRecommendationRequest,
):
    competition_code = request.competition_code.upper()

    if competition_code not in MVP_COMPETITION_CODES:
        raise HTTPException(
            status_code=400,
            detail="Competition not supported in RubyBets MVP.",
        )

    matches_data = await get_football_data(
        f"/competitions/{competition_code}/matches",
        params=clean_params(
            {
                "status": "SCHEDULED",
                "dateFrom": request.date_from,
                "dateTo": request.date_to,
            }
        ),
    )

    standings_data = await get_football_data(
        f"/competitions/{competition_code}/standings"
    )

    matches = matches_data.get("matches", [])
    standings = standings_data.get("standings", [])

    recommendations = []

    for match in matches:
        home_team_id = match.get("homeTeam", {}).get("id")
        away_team_id = match.get("awayTeam", {}).get("id")

        home_standing = find_team_standing(standings, home_team_id)
        away_standing = find_team_standing(standings, away_team_id)

        prediction_result = build_predictions(
            match=match,
            home_standing=home_standing,
            away_standing=away_standing,
        )

        selected_prediction = choose_best_prediction_for_match(
            prediction_result=prediction_result,
            risk_level=request.risk_level,
        )

        if selected_prediction:
            recommendations.append(
                {
                    "match": format_match(match),
                    "selected_prediction": selected_prediction["recommendation"],
                    "selection_score": selected_prediction["score"],
                    "prediction_key": selected_prediction["prediction_key"],
                    "method": prediction_result.get("method"),
                    "data_used": {
                        "match_details": True,
                        "competition_standings": True,
                        "home_team_standing_available": home_standing is not None,
                        "away_team_standing_available": away_standing is not None,
                    },
                }
            )

    recommendations.sort(
        key=lambda item: item["selection_score"],
        reverse=True,
    )

    selected_recommendations = recommendations[: request.match_count]

    return {
        "source": "football-data.org",
        "method": "rules_based_multimatch_selection_v1",
        "request": {
            "competition_code": competition_code,
            "match_count": request.match_count,
            "risk_level": request.risk_level,
            "date_from": request.date_from,
            "date_to": request.date_to,
        },
        "available_matches_count": len(matches),
        "selected_count": len(selected_recommendations),
        "recommendations": selected_recommendations,
        "selection_logic": {
            "description": (
                "RubyBets sélectionne les matchs dont les prédictions sont les plus cohérentes "
                "avec le niveau de risque demandé. Cette sélection repose sur un scoring explicable "
                "basé sur la confiance, le risque, le marché analysé et les données réelles disponibles."
            ),
            "risk_levels": {
                "low": "Priorité aux recommandations plus prudentes et aux tendances 1X2.",
                "medium": "Équilibre entre prudence, lisibilité et potentiel analytique.",
                "high": "Acceptation de recommandations plus incertaines, notamment sur BTTS.",
            },
        },
        "limits": [
            "Cette sélection recommandée ne constitue pas une incitation au pari.",
            "RubyBets ne permet aucun pari réel.",
            "Le moteur actuel est une première version explicable basée sur des règles et des données réelles.",
            "Les absences, compositions probables, actualités et forme détaillée ne sont pas encore intégrées.",
        ],
        "data_freshness": {
            "provider": "football-data.org",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }