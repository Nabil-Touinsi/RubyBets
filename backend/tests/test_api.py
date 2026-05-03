# Ce fichier vérifie automatiquement les routes API principales du MVP RubyBets.
# Il contrôle les réponses attendues sans appeler réellement les services externes (pour éviter les appels API pendant les tests, gagner du temps et ne pas polluer le cache local).

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


# Ce test vérifie que la route de santé du backend répond correctement.
def test_health_route_returns_ok_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Ce test vérifie que la route compétitions retourne uniquement les ligues du MVP.
def test_competitions_route_returns_mvp_competitions(monkeypatch):
    # Ce mock simule l'appel à Football-Data pour éviter un appel API réel pendant le test.
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

    # Ce mock empêche le test d'écrire un vrai fichier JSON dans le cache local.
    def fake_save_cache(cache_name: str, data: dict):
        assert cache_name == "competitions"
        return {
            "updated_at": "2026-05-03T00:00:00+00:00",
            "source": "football-data.org",
            "data": data,
        }

    # Ce mock force le test à ignorer tout cache existant.
    def fake_load_cache(cache_name: str):
        assert cache_name == "competitions"
        return None

    monkeypatch.setattr(competitions_api, "load_cache", fake_load_cache)
    monkeypatch.setattr(competitions_api, "save_cache", fake_save_cache)
    monkeypatch.setattr(competitions_api, "get_football_data", fake_get_football_data)

    response = client.get("/api/competitions")
    data = response.json()

    assert response.status_code == 200
    assert data["count"] == 2
    assert [competition["code"] for competition in data["competitions"]] == ["PL", "FL1"]
    assert data["competitions"][0]["current_season"]["current_matchday"] == 34


# Ce test vérifie que la route matchs retourne les rencontres programmées.
def test_matches_route_returns_scheduled_matches(monkeypatch):
    # Ce mock simule l'appel API de récupération des matchs.
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


# Ce test vérifie que la fiche détail d'un match retourne les bonnes informations.
def test_match_details_route_returns_match(monkeypatch):
    # Ce mock simule l'appel API de récupération d'un match précis.
    async def fake_get_football_data(endpoint: str, params=None):
        assert endpoint == "/matches/538122"
        return {"match": FAKE_MATCH}

    monkeypatch.setattr(matches_api, "get_football_data", fake_get_football_data)

    response = client.get("/api/matches/538122")
    data = response.json()

    assert response.status_code == 200
    assert data["match"]["id"] == 538122
    assert data["data_freshness"]["last_updated"] == "2026-04-30T10:00:00Z"


# Ce test vérifie que la route contexte retourne les classements et le résumé du match.
def test_match_context_route_returns_context(monkeypatch):
    # Ce mock simule la récupération d'un match enrichi avec les classements.
    async def fake_get_match_with_standings(match_id: int):
        assert match_id == 538122
        return FAKE_MATCH_WITH_STANDINGS

    # Ce mock simule la génération du résumé de contexte.
    def fake_build_context_summary(match, home_standing, away_standing):
        return "Arsenal possède une dynamique plus favorable."

    monkeypatch.setattr(matches_api, "get_match_with_standings", fake_get_match_with_standings)
    monkeypatch.setattr(matches_api, "build_context_summary", fake_build_context_summary)

    response = client.get("/api/matches/538122/context")
    data = response.json()

    assert response.status_code == 200
    assert data["context"]["competition"]["code"] == "PL"
    assert data["context"]["home_team_standing"]["position"] == 2
    assert data["context"]["away_team_standing"]["position"] == 5
    assert data["context"]["summary"] == "Arsenal possède une dynamique plus favorable."


# Ce test vérifie que la route analyse retourne une analyse pré-match exploitable.
def test_match_analysis_route_returns_analysis(monkeypatch):
    # Ce mock simule la récupération d'un match avec ses classements.
    async def fake_get_match_with_standings(match_id: int):
        assert match_id == 538122
        return FAKE_MATCH_WITH_STANDINGS

    # Ce mock simule la génération d'une analyse pré-match.
    def fake_build_prematch_analysis(match, home_standing, away_standing):
        return {
            "summary": "Analyse pré-match disponible.",
            "key_factors": ["forme récente", "classement", "différence de buts"],
        }

    monkeypatch.setattr(matches_api, "get_match_with_standings", fake_get_match_with_standings)
    monkeypatch.setattr(matches_api, "build_prematch_analysis", fake_build_prematch_analysis)

    response = client.get("/api/matches/538122/analysis")
    data = response.json()

    assert response.status_code == 200
    assert data["match_id"] == 538122
    assert data["analysis"]["summary"] == "Analyse pré-match disponible."
    assert data["data_used"]["home_team_standing_available"] is True
    assert data["data_used"]["away_team_standing_available"] is True


# Ce test vérifie que la route prédictions retourne les trois marchés du MVP.
def test_match_predictions_route_returns_predictions(monkeypatch):
    # Ce mock simule la récupération d'un match avec ses classements.
    async def fake_get_match_with_standings(match_id: int):
        assert match_id == 538122
        return FAKE_MATCH_WITH_STANDINGS

    # Ce mock simule la génération des prédictions MVP.
    def fake_build_predictions(match, home_standing, away_standing):
        return {
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
        }

    monkeypatch.setattr(matches_api, "get_match_with_standings", fake_get_match_with_standings)
    monkeypatch.setattr(matches_api, "build_predictions", fake_build_predictions)

    response = client.get("/api/matches/538122/predictions")
    data = response.json()

    assert response.status_code == 200
    assert data["match_id"] == 538122
    assert data["predictions"]["main_prediction"]["market"] == "1X2"
    assert data["predictions"]["goals_prediction"]["prediction"] == "Over 2.5"
    assert data["predictions"]["btts_prediction"]["prediction"] == "Yes"


# Ce test vérifie que la route glossaire retourne un contenu exploitable.
def test_glossary_route_returns_content():
    response = client.get("/api/glossary")
    data = response.json()

    assert response.status_code == 200
    assert isinstance(data, (dict, list))


# Ce test vérifie que la route informations responsables retourne un contenu exploitable.
def test_responsible_info_route_returns_content():
    response = client.get("/api/responsible-info")
    data = response.json()

    assert response.status_code == 200
    assert isinstance(data, (dict, list))


# Ce test vérifie que la recommandation multi-matchs retourne une sélection cohérente.
def test_multimatch_recommendation_route_returns_selection(monkeypatch):
    # Ce mock simule les appels API nécessaires à la recommandation multi-matchs.
    async def fake_get_football_data(endpoint: str, params=None):
        if endpoint == "/competitions/PL/matches":
            return {"matches": [FAKE_MATCH]}
        if endpoint == "/competitions/PL/standings":
            return {"standings": [{"table": [FAKE_HOME_STANDING, FAKE_AWAY_STANDING]}]}
        raise AssertionError(f"Endpoint inattendu : {endpoint}")

    # Ce mock simule la construction finale de la recommandation multi-matchs.
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


# Ce test vérifie qu'une compétition non supportée est refusée sur la route matchs.
def test_matches_route_rejects_unsupported_competition():
    response = client.get("/api/matches?competition_code=XYZ")

    assert response.status_code == 400
    assert response.json()["detail"] == "Competition not supported in RubyBets MVP."


# Ce test vérifie qu'une compétition non supportée est refusée sur la recommandation multi-matchs.
def test_multimatch_recommendation_rejects_unsupported_competition():
    response = client.post(
        "/api/recommendations/multimatch",
        json={
            "competition_code": "XYZ",
            "match_count": 2,
            "risk_level": "medium",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Competition not supported in RubyBets MVP."


# Ce test vérifie qu'un nombre trop élevé de matchs est refusé.
def test_multimatch_recommendation_rejects_too_large_match_count():
    response = client.post(
        "/api/recommendations/multimatch",
        json={
            "competition_code": "PL",
            "match_count": 10,
            "risk_level": "medium",
        },
    )

    assert response.status_code == 422


# Ce test vérifie qu'un niveau de risque invalide est refusé.
def test_multimatch_recommendation_rejects_invalid_risk_level():
    response = client.post(
        "/api/recommendations/multimatch",
        json={
            "competition_code": "PL",
            "match_count": 2,
            "risk_level": "extreme",
        },
    )

    assert response.status_code == 422


# Schéma de communication du fichier :
# test_api.py
# ├── appelle app.main pour créer le client de test
# ├── simule app.api.competitions pour tester /api/competitions sans cache réel
# ├── simule app.api.matches pour tester les routes matchs, contexte, analyse et prédictions
# └── simule app.api.recommendations pour tester la recommandation multi-matchs