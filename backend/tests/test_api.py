# Ce fichier vérifie automatiquement que les routes API essentielles du MVP RubyBets répondent correctement.

from fastapi.testclient import TestClient

from app.api import competitions as competitions_api
from app.main import app


client = TestClient(app)


def test_health_route_returns_ok_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_competitions_route_returns_mvp_competitions(monkeypatch):
    async def fake_get_football_data(endpoint: str):
        assert endpoint == "/competitions"
        return {
            "competitions": [
                {
                    "id": 2021,
                    "code": "PL",
                    "name": "Premier League",
                    "area": {"name": "England"},
                    "type": "LEAGUE",
                    "emblem": "https://crests.football-data.org/PL.png",
                    "currentSeason": {
                        "id": 2403,
                        "startDate": "2025-08-15",
                        "endDate": "2026-05-24",
                        "currentMatchday": 34,
                    },
                },
                {
                    "id": 2015,
                    "code": "FL1",
                    "name": "Ligue 1",
                    "area": {"name": "France"},
                    "type": "LEAGUE",
                    "emblem": "https://crests.football-data.org/FL1.png",
                    "currentSeason": {
                        "id": 2404,
                        "startDate": "2025-08-15",
                        "endDate": "2026-05-16",
                        "currentMatchday": 32,
                    },
                },
                {
                    "id": 9999,
                    "code": "TEST",
                    "name": "Competition hors MVP",
                    "area": {"name": "Test"},
                    "type": "LEAGUE",
                    "emblem": None,
                    "currentSeason": {},
                },
            ]
        }

    monkeypatch.setattr(competitions_api, "get_football_data", fake_get_football_data)

    response = client.get("/api/competitions")
    data = response.json()

    assert response.status_code == 200
    assert data["count"] == 2
    assert [competition["code"] for competition in data["competitions"]] == ["PL", "FL1"]
    assert data["competitions"][0]["current_season"]["current_matchday"] == 34
