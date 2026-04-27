# Ce fichier expose les compétitions RubyBets que le frontend utilisera dans le MVP.

from fastapi import APIRouter

from app.services.football_data_client import get_football_data


router = APIRouter(prefix="/api/competitions", tags=["Competitions"])


MVP_COMPETITION_CODES = {
    "PL",    # Premier League
    "FL1",   # Ligue 1
    "BL1",   # Bundesliga
    "SA",    # Serie A
    "PD",    # La Liga
    "CL",    # Champions League
}


@router.get("")
async def get_competitions():
    data = await get_football_data("/competitions")

    competitions = data.get("competitions", [])

    filtered_competitions = [
        {
            "id": competition.get("id"),
            "code": competition.get("code"),
            "name": competition.get("name"),
            "country": competition.get("area", {}).get("name"),
            "type": competition.get("type"),
            "emblem": competition.get("emblem"),
            "current_season": {
                "id": competition.get("currentSeason", {}).get("id"),
                "start_date": competition.get("currentSeason", {}).get("startDate"),
                "end_date": competition.get("currentSeason", {}).get("endDate"),
                "current_matchday": competition.get("currentSeason", {}).get("currentMatchday"),
            },
        }
        for competition in competitions
        if competition.get("code") in MVP_COMPETITION_CODES
    ]

    return {
        "count": len(filtered_competitions),
        "competitions": filtered_competitions,
    }