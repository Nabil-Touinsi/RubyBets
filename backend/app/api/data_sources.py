# Routes de test pour vérifier les sources de données externes utilisées par RubyBets.
# Football-Data.org sert de source principale, FlashScore sert d'enrichissement.

from fastapi import APIRouter, Query

from app.services.football_data_client import get_football_data
from app.services.rapidapi_flashscore_client import get_rapidapi_flashscore_data


router = APIRouter(prefix="/api/sources", tags=["Data sources"])


def clean_params(params: dict) -> dict:
    return {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }


# -------------------------------------------------------------------
# Football-Data.org — source principale du MVP
# -------------------------------------------------------------------

@router.get("/football-data/competitions")
async def get_football_data_competitions(
    competitions: str | None = Query(None),
):
    return await get_football_data(
        "/competitions",
        params=clean_params(
            {
                "competitions": competitions,
            }
        ),
    )


@router.get("/football-data/competitions/{competition_code}")
async def get_football_data_competition_details(
    competition_code: str,
):
    return await get_football_data(f"/competitions/{competition_code}")


@router.get("/football-data/competitions/{competition_code}/matches")
async def get_football_data_competition_matches(
    competition_code: str,
    status: str | None = Query("SCHEDULED"),
    dateFrom: str | None = Query(None),
    dateTo: str | None = Query(None),
    matchday: int | None = Query(None),
    season: int | None = Query(None),
    stage: str | None = Query(None),
):
    return await get_football_data(
        f"/competitions/{competition_code}/matches",
        params=clean_params(
            {
                "status": status,
                "dateFrom": dateFrom,
                "dateTo": dateTo,
                "matchday": matchday,
                "season": season,
                "stage": stage,
            }
        ),
    )


@router.get("/football-data/competitions/{competition_code}/teams")
async def get_football_data_competition_teams(
    competition_code: str,
    season: int | None = Query(None),
):
    return await get_football_data(
        f"/competitions/{competition_code}/teams",
        params=clean_params(
            {
                "season": season,
            }
        ),
    )


@router.get("/football-data/competitions/{competition_code}/standings")
async def get_football_data_competition_standings(
    competition_code: str,
):
    return await get_football_data(
        f"/competitions/{competition_code}/standings"
    )


@router.get("/football-data/competitions/{competition_code}/scorers")
async def get_football_data_competition_scorers(
    competition_code: str,
    limit: int | None = Query(None),
):
    return await get_football_data(
        f"/competitions/{competition_code}/scorers",
        params=clean_params(
            {
                "limit": limit,
            }
        ),
    )


@router.get("/football-data/matches")
async def get_football_data_matches(
    competitions: str | None = Query(None),
    status: str | None = Query(None),
    dateFrom: str | None = Query(None),
    dateTo: str | None = Query(None),
):
    return await get_football_data(
        "/matches",
        params=clean_params(
            {
                "competitions": competitions,
                "status": status,
                "dateFrom": dateFrom,
                "dateTo": dateTo,
            }
        ),
    )


@router.get("/football-data/matches/{match_id}")
async def get_football_data_match_details(
    match_id: int,
):
    return await get_football_data(f"/matches/{match_id}")


@router.get("/football-data/teams/{team_id}")
async def get_football_data_team_details(
    team_id: int,
):
    return await get_football_data(f"/teams/{team_id}")


@router.get("/football-data/teams/{team_id}/matches")
async def get_football_data_team_matches(
    team_id: int,
    competitions: str | None = Query(None),
    status: str | None = Query(None),
    dateFrom: str | None = Query(None),
    dateTo: str | None = Query(None),
    limit: int | None = Query(None),
):
    return await get_football_data(
        f"/teams/{team_id}/matches",
        params=clean_params(
            {
                "competitions": competitions,
                "status": status,
                "dateFrom": dateFrom,
                "dateTo": dateTo,
                "limit": limit,
            }
        ),
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