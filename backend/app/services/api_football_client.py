from typing import Any

import httpx

from app.core.config import settings


async def get_api_football_data(
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{settings.api_football_base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            url,
            headers=settings.get_api_football_headers(),
            params=params,
        )

    response.raise_for_status()
    return response.json()