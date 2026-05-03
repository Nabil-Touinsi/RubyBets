# Ce fichier expose la route de recommandation multi-matchs générée par RubyBets pour le MVP.
# Il met en cache les matchs et les classements utilisés afin de limiter les appels Football-Data répétés.

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.constants import MVP_COMPETITION_CODES
from app.services.cache_service import build_cache_name, get_cached_football_data
from app.services.match_service import clean_params
from app.services.recommendation_service import build_multimatch_recommendation_response


router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


MATCHES_CACHE_TTL_MINUTES = 30
STANDINGS_CACHE_TTL_MINUTES = 60


# Ce modèle décrit les paramètres autorisés pour générer une recommandation multi-matchs.
class MultiMatchRecommendationRequest(BaseModel):
    competition_code: str = "PL"
    match_count: int = Field(default=3, ge=1, le=5)
    risk_level: Literal["low", "medium", "high"] = "medium"
    date_from: str | None = None
    date_to: str | None = None


# Cette fonction vérifie que la compétition demandée appartient au périmètre MVP.
def ensure_competition_supported(competition_code: str) -> None:
    if competition_code not in MVP_COMPETITION_CODES:
        raise HTTPException(
            status_code=400,
            detail="Competition not supported in RubyBets MVP.",
        )


# Cette fonction construit le nom de cache utilisé pour les matchs d'une recommandation.
def build_recommendation_matches_cache_name(
    competition_code: str,
    date_from: str | None,
    date_to: str | None,
) -> str:
    return build_cache_name(
        "matches",
        competition_code,
        "scheduled",
        date_from or "all_start_dates",
        date_to or "all_end_dates",
    )


# Cette fonction ajoute les informations de fraîcheur des données source à la réponse finale.
def add_recommendation_data_freshness(
    response_data: dict[str, Any],
    matches_freshness: dict[str, Any],
    standings_freshness: dict[str, Any],
) -> dict[str, Any]:
    response_data["data_freshness"] = {
        **response_data.get("data_freshness", {}),
        "matches_cache": matches_freshness,
        "standings_cache": standings_freshness,
    }
    return response_data


# Cette route génère une sélection recommandée à partir des matchs et classements mis en cache.
@router.post("/multimatch")
async def generate_multimatch_recommendation(
    request: MultiMatchRecommendationRequest,
) -> dict[str, Any]:
    competition_code = request.competition_code.upper()
    ensure_competition_supported(competition_code)

    matches_data, matches_freshness = await get_cached_football_data(
        cache_name=build_recommendation_matches_cache_name(
            competition_code=competition_code,
            date_from=request.date_from,
            date_to=request.date_to,
        ),
        endpoint=f"/competitions/{competition_code}/matches",
        params=clean_params(
            {
                "status": "SCHEDULED",
                "dateFrom": request.date_from,
                "dateTo": request.date_to,
            }
        ),
        ttl_minutes=MATCHES_CACHE_TTL_MINUTES,
    )

    standings_data, standings_freshness = await get_cached_football_data(
        cache_name=build_cache_name("standings", competition_code),
        endpoint=f"/competitions/{competition_code}/standings",
        ttl_minutes=STANDINGS_CACHE_TTL_MINUTES,
    )

    response_data = build_multimatch_recommendation_response(
        competition_code=competition_code,
        match_count=request.match_count,
        risk_level=request.risk_level,
        date_from=request.date_from,
        date_to=request.date_to,
        matches=matches_data.get("matches", []),
        standings=standings_data.get("standings", []),
    )

    return add_recommendation_data_freshness(
        response_data=response_data,
        matches_freshness=matches_freshness,
        standings_freshness=standings_freshness,
    )


# Schéma de communication du fichier :
# recommendations.py
# ├── reçoit les paramètres du frontend pour /api/recommendations/multimatch
# ├── utilise cache_service.py pour récupérer matchs et classements avec cache
# ├── délègue la sélection explicable à recommendation_service.py
# └── renvoie la sélection recommandée à app.main puis au frontend
