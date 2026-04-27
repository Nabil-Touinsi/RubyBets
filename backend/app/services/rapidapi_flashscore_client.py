import httpx

from app.core.config import settings


def get_rapidapi_flashscore_data(endpoint: str, params: dict | None = None) -> dict:
    """
    Appelle RapidAPI / FlashScore et retourne la réponse JSON.

    Ce service centralise les appels vers la source secondaire RapidAPI / FlashScore.
    API-Football reste la source principale du MVP.
    """

    base_url = settings.rapidapi_flashscore_base_url.rstrip("/")
    clean_endpoint = endpoint.lstrip("/")
    url = f"{base_url}/{clean_endpoint}"

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                url,
                headers=settings.get_rapidapi_headers(),
                params=params,
            )

            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as error:
        return {
            "source": "rapidapi_flashscore",
            "status": "error",
            "status_code": error.response.status_code,
            "message": error.response.text,
        }

    except httpx.RequestError as error:
        return {
            "source": "rapidapi_flashscore",
            "status": "error",
            "message": str(error),
        }