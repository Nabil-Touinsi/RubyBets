# Role du fichier :
# Ce fichier centralise les appels vers API-Football / API-Sports.
# Il sert de source secondaire pour enrichir l historique récent des équipes RubyBets.

from typing import Any

import httpx

from app.core.config import settings


# Cette fonction vérifie si la clé API-Football est disponible dans la configuration.
def has_api_football_key() -> bool:
    return bool(settings.api_football_key)


# Cette fonction appelle API-Football et retourne une réponse JSON sécurisée.
async def get_api_football_data(
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not has_api_football_key():
        return {
            "source": "api_football",
            "status": "disabled",
            "message": "API_FOOTBALL_KEY absente de la configuration.",
            "response": [],
        }

    base_url = settings.api_football_base_url.rstrip("/")
    clean_endpoint = endpoint.lstrip("/")
    url = f"{base_url}/{clean_endpoint}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers=settings.get_api_football_headers(),
                params=params,
            )

        response.raise_for_status()
        data = response.json()
        data["source"] = "api_football"
        data["status"] = "success"
        return data

    except httpx.HTTPStatusError as error:
        return {
            "source": "api_football",
            "status": "error",
            "status_code": error.response.status_code,
            "message": error.response.text,
            "response": [],
        }

    except httpx.RequestError as error:
        return {
            "source": "api_football",
            "status": "error",
            "message": str(error),
            "response": [],
        }


# Cette fonction recherche les équipes API-Football correspondant à un nom d'équipe.
async def search_api_football_teams(team_name: str) -> dict[str, Any]:
    if not team_name:
        return {
            "source": "api_football",
            "status": "error",
            "message": "Nom d'équipe manquant.",
            "response": [],
        }

    return await get_api_football_data(
        endpoint="/teams",
        params={"search": team_name},
    )


# Cette fonction choisit le meilleur candidat API-Football à partir d'un nom d'équipe.
async def find_api_football_team_candidate(team_name: str) -> dict[str, Any] | None:
    data = await search_api_football_teams(team_name)
    candidates = data.get("response", [])

    if not candidates:
        return None

    normalized_team_name = team_name.strip().lower()

    for candidate in candidates:
        candidate_team = candidate.get("team", {})
        candidate_name = str(candidate_team.get("name", "")).strip().lower()

        if candidate_name == normalized_team_name:
            return candidate

    return candidates[0]


# Cette fonction récupère les derniers matchs terminés d'une équipe API-Football avant une date donnée.
async def get_api_football_team_finished_fixtures(
    api_team_id: int,
    target_date: str | None,
    limit: int = 10,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "team": api_team_id,
        "last": limit,
        "status": "FT-AET-PEN",
    }

    if target_date:
        params["to"] = target_date[:10]

    return await get_api_football_data(
        endpoint="/fixtures",
        params=params,
    )


# Cette fonction extrait un score final exploitable depuis une fixture API-Football.
def extract_api_football_full_time_score(
    fixture_item: dict[str, Any],
) -> tuple[int | None, int | None]:
    goals = fixture_item.get("goals", {}) or {}
    home_goals = goals.get("home")
    away_goals = goals.get("away")

    if home_goals is not None and away_goals is not None:
        return home_goals, away_goals

    score = fixture_item.get("score", {}) or {}
    full_time = score.get("fulltime", {}) or {}

    return full_time.get("home"), full_time.get("away")


# Cette fonction transforme une fixture API-Football en format proche de Football-Data.
def normalize_api_football_fixture(fixture_item: dict[str, Any]) -> dict[str, Any] | None:
    fixture = fixture_item.get("fixture", {}) or {}
    league = fixture_item.get("league", {}) or {}
    teams = fixture_item.get("teams", {}) or {}
    home_team = teams.get("home", {}) or {}
    away_team = teams.get("away", {}) or {}

    home_score, away_score = extract_api_football_full_time_score(fixture_item)

    if not fixture.get("id") or home_score is None or away_score is None:
        return None

    return {
        "id": fixture.get("id"),
        "utcDate": fixture.get("date"),
        "status": fixture.get("status", {}).get("short"),
        "competition": {
            "id": league.get("id"),
            "name": league.get("name"),
            "code": None,
            "type": None,
            "emblem": league.get("logo"),
        },
        "homeTeam": {
            "id": home_team.get("id"),
            "name": home_team.get("name"),
            "shortName": home_team.get("name"),
            "tla": None,
            "crest": home_team.get("logo"),
        },
        "awayTeam": {
            "id": away_team.get("id"),
            "name": away_team.get("name"),
            "shortName": away_team.get("name"),
            "tla": None,
            "crest": away_team.get("logo"),
        },
        "score": {
            "winner": None,
            "duration": "REGULAR",
            "fullTime": {
                "home": home_score,
                "away": away_score,
            },
            "halfTime": None,
        },
        "data_source": "api_football",
    }


# Cette fonction récupère et normalise les derniers matchs terminés d'une équipe par son nom.
async def get_normalized_api_football_team_history(
    team_name: str,
    target_date: str | None,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidate = await find_api_football_team_candidate(team_name)

    if not candidate:
        return [], {
            "source": "api_football",
            "status": "unavailable",
            "team_name": team_name,
            "message": "Aucune équipe API-Football correspondante trouvée.",
        }

    api_team = candidate.get("team", {})
    api_team_id = api_team.get("id")

    if not api_team_id:
        return [], {
            "source": "api_football",
            "status": "unavailable",
            "team_name": team_name,
            "message": "Équipe API-Football trouvée sans identifiant exploitable.",
        }

    fixtures_data = await get_api_football_team_finished_fixtures(
        api_team_id=api_team_id,
        target_date=target_date,
        limit=limit,
    )

    normalized_fixtures = [
        normalized_fixture
        for fixture_item in fixtures_data.get("response", [])
        if (normalized_fixture := normalize_api_football_fixture(fixture_item)) is not None
    ]

    return normalized_fixtures, {
        "source": "api_football",
        "status": fixtures_data.get("status", "unknown"),
        "api_team_id": api_team_id,
        "api_team_name": api_team.get("name"),
        "results": len(normalized_fixtures),
        "raw_results": fixtures_data.get("results"),
    }


# Schema de communication :
# backend/.env
#     ↓
# backend/app/core/config.py
#     ↓
# backend/app/services/api_football_client.py
#     ↓
# backend/app/services/team_history_service.py
#     ↓
# backend/app/api/matches.py
#     ↓
# frontend/src/screens/MatchDetailsScreen.tsx