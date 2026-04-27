from fastapi import APIRouter, Query

from app.services.api_football_client import get_api_football_data
from app.services.rapidapi_flashscore_client import get_rapidapi_flashscore_data

router = APIRouter(prefix="/api/sources", tags=["Data sources"])


@router.get("/api-football/countries")
async def get_api_football_countries():
    return await get_api_football_data("/countries")


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