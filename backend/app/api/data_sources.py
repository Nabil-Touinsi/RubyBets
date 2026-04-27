# Routes de test pour vérifier les sources de données externes utilisées par RubyBets.
# Football-Data.org sert de source principale, FlashScore sert d'enrichissement.

from fastapi import APIRouter, Query

from app.services.football_data_client import get_football_data

from app.services.rapidapi_flashscore_client import get_rapidapi_flashscore_data


router = APIRouter(prefix="/api/sources", tags=["Data sources"])

# -------------------------------------------------------------------
# Football-Data.org — source principale du MVP
# -------------------------------------------------------------------

@router.get("/football-data/competitions")
async def get_football_data_competitions():
    return await get_football_data("/competitions")

@router.get("/football-data/competitions/{competition_code}/matches")
async def get_football_data_competition_matches(
    competition_code: str,
    status: str = Query("SCHEDULED"),
):
    return await get_football_data(
        f"/competitions/{competition_code}/matches",
        params={
            "status": status,
        },
    )

# -------------------------------------------------------------------
# RapidAPI / FlashScore — source active après retrait d'API-Football
# -------------------------------------------------------------------

@router.get("/rapidapi-flashscore/match-details")
async def get_flashscore_match_details(
    match_id: str = Query(...),
):
    return get_rapidapi_flashscore_data(
        endpoint="/matches/details",
        params={"match_id": match_id},
    )


@router.get("/rapidapi-flashscore/match-summary")
async def get_flashscore_match_summary(
    match_id: str = Query(...),
):
    return get_rapidapi_flashscore_data(
        endpoint="/matches/match/summary",
        params={"match_id": match_id},
    )


@router.get("/rapidapi-flashscore/match-statistics")
async def get_flashscore_match_statistics(
    match_id: str = Query(...),
):
    return get_rapidapi_flashscore_data(
        endpoint="/matches/match/stats",
        params={"match_id": match_id},
    )


@router.get("/rapidapi-flashscore/lineups")
async def get_flashscore_lineups(
    match_id: str = Query(...),
):
    return get_rapidapi_flashscore_data(
        endpoint="/matches/match/lineups",
        params={"match_id": match_id},
    )


@router.get("/rapidapi-flashscore/h2h")
async def get_flashscore_h2h(
    match_id: str = Query(...),
):
    return get_rapidapi_flashscore_data(
        endpoint="/matches/h2h",
        params={"match_id": match_id},
    )


@router.get("/rapidapi-flashscore/standings")
async def get_flashscore_standings(
    match_id: str = Query(...),
    type: str = Query("overall"),
):
    return get_rapidapi_flashscore_data(
        endpoint="/matches/standings",
        params={
            "match_id": match_id,
            "type": type,
        },
    )