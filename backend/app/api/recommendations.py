# Ce fichier expose les recommandations multi-matchs générées par RubyBets pour le MVP.

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.constants import MVP_COMPETITION_CODES
from app.services.football_data_client import get_football_data
from app.services.match_service import clean_params
from app.services.recommendation_service import build_multimatch_recommendation_response


router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


class MultiMatchRecommendationRequest(BaseModel):
    competition_code: str = "PL"
    match_count: int = Field(default=3, ge=1, le=5)
    risk_level: Literal["low", "medium", "high"] = "medium"
    date_from: str | None = None
    date_to: str | None = None


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

    return build_multimatch_recommendation_response(
        competition_code=competition_code,
        match_count=request.match_count,
        risk_level=request.risk_level,
        date_from=request.date_from,
        date_to=request.date_to,
        matches=matches,
        standings=standings,
    )
