from fastapi import APIRouter

from app.services.api_football_client import get_api_football_data

router = APIRouter(prefix="/api/sources", tags=["Data sources"])


@router.get("/api-football/countries")
async def get_api_football_countries():
    return await get_api_football_data("/countries")