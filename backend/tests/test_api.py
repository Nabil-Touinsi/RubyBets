# Ce fichier vérifie automatiquement que les routes API essentielles du MVP RubyBets répondent correctement.

from fastapi.testclient import TestClient

from app.api import competitions as competitions_api
from app.api import matches as matches_api
from app.api import recommendations as recommendations_api
from app.main import app


client = TestClient(app)


FAKE_MATCH = {
    "area": {
        "id": 2072,
        "name": "England",
        "code": "ENG",
        "flag": "https://crests.football-data.org/770.svg",
    },
    "competition": {
        "id": 2021,
        "name": "Premier League",
        "code": "PL",
        "type": "LEAGUE",
        "emblem": "https://crests.football-data.org/PL.png",
    },
    "season": {
        "id": 2403,
        "startDate": "2025-08-15",
        "endDate": "2026-05-24",
        "currentMatchday": 34,
        "winner": None,
    },
    "id": 538122,
    "utcDate": "2026-05-01T19:00:00Z",
    "status": "TIMED",
    "matchday": 34,
    "stage": "REGULAR_SEASON",
    "group": None,
    "lastUpdated": "2026-04-30T10:00:00Z",
    "homeTeam": {
        "id": 57,
        "name": "Arsenal FC",
        "shortName": "Arsenal",
        "tla": "ARS",
        "crest": "https://crests.football-data.org/57.png",
    },
    "awayTeam": {
        "id": 61,
        "name": "Chelsea FC",
        "shortName": "Chelsea",
        "tla": "CHE",
        "crest": "https://crests.football-data.org/61.png",
    },
    "score": {
        "winner": None,
        "duration": "REGULAR",
        "fullTime": {"home": None, "away": None},
        "halfTime": {"home": None, "away": None},
    },
}


FAKE_HOME_STANDING = {
    "position": 2,
    "team": FAKE_MATCH["homeTeam"],
    "playedGames": 34,
    "won": 22,
    "draw": 6,
    "lost": 6,
    "points": 72,
    "goalsFor": 72,
    "goalsAgainst": 31,
    "goalDifference": 41,
}


FAKE_AWAY_STANDING = {
    "position": 5,
    "team": FAKE_MATCH["awayTeam"],
    "playedGames": 34,
    "won": 18,
    "draw": 8,
    "lost": 8,
    "points": 62,
    "goalsFor": 61,
    "goalsAgainst": 42,
    "goalDifference": 19,
}


FAKE_MATCH_WITH_STANDINGS = {
    "match": FAKE_MATCH,
    "competition_code": "PL",
    "home_standing": FAKE_HOME_STANDING,
    "away_standing": FAKE_AWAY_STANDING,
}


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


def test_matches_route_returns_scheduled_matches(monkeypatch):
    async def fake_get_football_data(endpoint: str, params=None):
        assert endpoint == "/competitions/PL/matches"
        assert params["status"] == "SCHEDULED"
        return {"matches": [FAKE_MATCH]}

    monkeypatch.setattr(matches_api, "get_football_data", fake_get_football_data)

    response = client.get("/api/matches?competition_code=PL&status=SCHEDULED")
    data = response.json()

    assert response.status_code == 200
    assert data["competition_code"] == "PL"
    assert data["count"] == 1
    assert len(data["matches"]) == 1


def test_match_details_route_returns_match(monkeypatch):
    async def fake_get_football_data(endpoint: str, params=None):
        assert endpoint == "/matches/538122"
        return {"match": FAKE_MATCH}

    monkeypatch.setattr(matches_api, "get_football_data", fake_get_football_data)

    response = client.get("/api/matches/538122")
    data = response.json()

    assert response.status_code == 200
    assert data["match"]["id"] == 538122
    assert data["data_freshness"]["last_updated"] == "2026-04-30T10:00:00Z"


def test_match_context_route_returns_context(monkeypatch):
    async def fake_get_match_with_standings(match_id: int):
        assert match_id == 538122
        return FAKE_MATCH_WITH_STANDINGS

    monkeypatch.setattr(matches_api, "get_match_with_standings", fake_get_match_with_standings)
    monkeypatch.setattr(
        matches_api,
        "build_context_summary",
        lambda match, home_standing, away_standing: "Arsenal possède une dynamique plus favorable.",
    )

    response = client.get("/api/matches/538122/context")
    data = response.json()

    assert response.status_code == 200
    assert data["context"]["competition"]["code"] == "PL"
    assert data["context"]["home_team_standing"]["position"] == 2
    assert data["context"]["away_team_standing"]["position"] == 5
    assert data["context"]["summary"] == "Arsenal possède une dynamique plus favorable."


def test_match_analysis_route_returns_analysis(monkeypatch):
    async def fake_get_match_with_standings(match_id: int):
        assert match_id == 538122
        return FAKE_MATCH_WITH_STANDINGS

    monkeypatch.setattr(matches_api, "get_match_with_standings", fake_get_match_with_standings)
    monkeypatch.setattr(
        matches_api,
        "build_prematch_analysis",
        lambda match, home_standing, away_standing: {
            "summary": "Analyse pré-match disponible.",
            "key_factors": ["forme récente", "classement", "différence de buts"],
        },
    )

    response = client.get("/api/matches/538122/analysis")
    data = response.json()

    assert response.status_code == 200
    assert data["match_id"] == 538122
    assert data["analysis"]["summary"] == "Analyse pré-match disponible."
    assert data["data_used"]["home_team_standing_available"] is True
    assert data["data_used"]["away_team_standing_available"] is True


def test_match_predictions_route_returns_predictions(monkeypatch):
    async def fake_get_match_with_standings(match_id: int):
        assert match_id == 538122
        return FAKE_MATCH_WITH_STANDINGS

    monkeypatch.setattr(matches_api, "get_match_with_standings", fake_get_match_with_standings)
    monkeypatch.setattr(
        matches_api,
        "build_predictions",
        lambda match, home_standing, away_standing: {
            "main_prediction": {
                "market": "1X2",
                "prediction": "Home win",
                "confidence": "medium",
                "risk": "medium",
            },
            "goals_prediction": {
                "market": "Goals",
                "prediction": "Over 2.5",
                "confidence": "medium",
                "risk": "medium",
            },
            "btts_prediction": {
                "market": "BTTS",
                "prediction": "Yes",
                "confidence": "medium",
                "risk": "medium",
            },
        },
    )

    response = client.get("/api/matches/538122/predictions")
    data = response.json()

    assert response.status_code == 200
    assert data["match_id"] == 538122
    assert data["predictions"]["main_prediction"]["market"] == "1X2"
    assert data["predictions"]["goals_prediction"]["prediction"] == "Over 2.5"
    assert data["predictions"]["btts_prediction"]["prediction"] == "Yes"


def test_glossary_route_returns_content():
    response = client.get("/api/glossary")
    data = response.json()

    assert response.status_code == 200
    assert isinstance(data, (dict, list))


def test_responsible_info_route_returns_content():
    response = client.get("/api/responsible-info")
    data = response.json()

    assert response.status_code == 200
    assert isinstance(data, (dict, list))


def test_multimatch_recommendation_route_returns_selection(monkeypatch):
    async def fake_get_football_data(endpoint: str, params=None):
        if endpoint == "/competitions/PL/matches":
            return {"matches": [FAKE_MATCH]}
        if endpoint == "/competitions/PL/standings":
            return {"standings": [{"table": [FAKE_HOME_STANDING, FAKE_AWAY_STANDING]}]}
        raise AssertionError(f"Endpoint inattendu : {endpoint}")

    def fake_build_multimatch_recommendation_response(**kwargs):
        return {
            "competition_code": kwargs["competition_code"],
            "match_count": kwargs["match_count"],
            "risk_level": kwargs["risk_level"],
            "recommendations": [
                {
                    "match_id": 538122,
                    "home_team": "Arsenal FC",
                    "away_team": "Chelsea FC",
                    "recommendation": "Home win",
                }
            ],
        }

    monkeypatch.setattr(recommendations_api, "get_football_data", fake_get_football_data)
    monkeypatch.setattr(
        recommendations_api,
        "build_multimatch_recommendation_response",
        fake_build_multimatch_recommendation_response,
    )

    response = client.post(
        "/api/recommendations/multimatch",
        json={
            "competition_code": "PL",
            "match_count": 1,
            "risk_level": "low",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["competition_code"] == "PL"
    assert data["match_count"] == 1
    assert data["risk_level"] == "low"
    assert len(data["recommendations"]) == 1