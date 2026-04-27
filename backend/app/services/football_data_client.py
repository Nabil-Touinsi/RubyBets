# Service client pour Football-Data.org.
# Ce fichier centralise les appels HTTP vers la source principale de données football de RubyBets.

from typing import Any

import httpx

from app.core.config import settings


async def get_football_data(
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Appelle Football-Data.org et retourne la réponse JSON.
    """

    base_url = settings.football_data_base_url.rstrip("/")
    clean_endpoint = endpoint.lstrip("/")
    url = f"{base_url}/{clean_endpoint}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers=settings.get_football_data_headers(),
                params=params,
            )

        response.raise_for_status()
        return response.json()

    except httpx.HTTPStatusError as error:
        return {
            "source": "football_data",
            "status": "error",
            "status_code": error.response.status_code,
            "message": error.response.text,
        }

    except httpx.RequestError as error:
        return {
            "source": "football_data",
            "status": "error",
            "message": str(error),
        }