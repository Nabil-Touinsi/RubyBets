# Ce fichier expose les compétitions RubyBets utilisées par le frontend dans le MVP.
# Il ajoute une première couche de cache pour tracer la fraîcheur des données Football-Data.

from fastapi import APIRouter

from app.services.cache_service import is_cache_fresh, load_cache, save_cache
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


CACHE_NAME = "competitions"
CACHE_TTL_MINUTES = 60


# Cette fonction formate la réponse des compétitions et ajoute les informations de fraîcheur.
def format_competitions_response(
    data: dict,
    from_cache: bool,
    updated_at: str | None,
) -> dict:
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
        "data_freshness": {
            "source": "football-data.org",
            "from_cache": from_cache,
            "updated_at": updated_at,
            "ttl_minutes": CACHE_TTL_MINUTES,
        },
    }


# Cette route retourne les compétitions du MVP en utilisant le cache si les données sont encore fraîches.
@router.get("")
async def get_competitions() -> dict:
    cached_payload = load_cache(CACHE_NAME)

    if cached_payload and is_cache_fresh(cached_payload, ttl_minutes=CACHE_TTL_MINUTES):
        return format_competitions_response(
            data=cached_payload.get("data", {}),
            from_cache=True,
            updated_at=cached_payload.get("updated_at"),
        )

    data = await get_football_data("/competitions")
    saved_payload = save_cache(CACHE_NAME, data)

    return format_competitions_response(
        data=saved_payload["data"],
        from_cache=False,
        updated_at=saved_payload["updated_at"],
    )


# Schéma de communication du fichier :
# competitions.py
# ├── utilise cache_service.py pour lire ou écrire le cache competitions
# ├── appelle football_data_client.py si le cache est absent ou expiré
# └── renvoie les compétitions formatées à app.main puis au frontend
