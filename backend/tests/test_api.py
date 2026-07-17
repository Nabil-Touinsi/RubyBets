# Ce fichier vérifie automatiquement les routes API principales du MVP RubyBets.
# Il contrôle les réponses attendues sans appeler réellement les services externes (pour éviter les appels API pendant les tests, gagner du temps et ne pas polluer le cache local).

from datetime import date, datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.api import competitions as competitions_api
from app.api import matches as matches_api
from app.api import recommendations as recommendations_api
from app.main import app


client = TestClient(app)


FAKE_FRESHNESS = {
    "source": "football-data.org",
    "from_cache": False,
    "updated_at": "2026-05-03T00:00:00+00:00",
    "ttl_minutes": 30,
}


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
    "data_freshness": {
        "match": FAKE_FRESHNESS,
        "standings": FAKE_FRESHNESS,
    },
}


# Cette fonction construit un match FlashScore normalisé pour tester le cache et la fraîcheur.
def build_flashscore_cached_match(
    *,
    match_id: int,
    utc_date: str,
    area_name: str,
    competition_name: str,
    status: str = "SCHEDULED",
) -> dict[str, Any]:
    return {
        "id": match_id,
        "sourceMatchId": f"source-{match_id}",
        "source": matches_api.FLASHSCORE_SOURCE,
        "utcDate": utc_date,
        "status": status,
        "area": {"name": area_name, "code": None},
        "competition": {
            "name": competition_name,
            "code": None,
            "sourceCompetitionId": None,
        },
        "homeTeam": {"id": match_id * 10, "name": f"Home {match_id}"},
        "awayTeam": {"id": match_id * 10 + 1, "name": f"Away {match_id}"},
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


# Ce test vérifie le fallback Football-Data pour la liste des matchs programmés.
def test_matches_route_returns_scheduled_matches(monkeypatch):
    monkeypatch.setattr(matches_api, "is_flashscore_available", lambda: False)

    # Ce mock simule le service de cache pour éviter tout appel API réel pendant le test.
    async def fake_get_cached_football_data(
        cache_name: str,
        endpoint: str,
        params=None,
        ttl_minutes: int = 30,
    ):
        assert cache_name == "matches_pl_scheduled_all_start_dates_all_end_dates"
        assert endpoint == "/competitions/PL/matches"
        assert params["status"] == "SCHEDULED"
        assert ttl_minutes == matches_api.MATCHES_CACHE_TTL_MINUTES
        return {"matches": [FAKE_MATCH]}, FAKE_FRESHNESS

    monkeypatch.setattr(matches_api, "get_cached_football_data", fake_get_cached_football_data)

    response = client.get("/api/matches?competition_code=PL&status=SCHEDULED")
    data = response.json()

    assert response.status_code == 200
    assert data["competition_code"] == "PL"
    assert data["count"] == 1


# Ce test vérifie le fallback Football-Data pour la fiche détail d'un match.
def test_match_details_route_returns_match(monkeypatch):
    monkeypatch.setattr(matches_api, "is_flashscore_available", lambda: False)

    # Ce mock simule le service de cache pour la fiche détail d'un match.
    async def fake_get_cached_football_data(
        cache_name: str,
        endpoint: str,
        params=None,
        ttl_minutes: int = 30,
    ):
        assert cache_name == "match_538122"
        assert endpoint == "/matches/538122"
        assert params is None
        assert ttl_minutes == matches_api.MATCH_DETAIL_CACHE_TTL_MINUTES
        return {"match": FAKE_MATCH}, FAKE_FRESHNESS

    monkeypatch.setattr(matches_api, "get_cached_football_data", fake_get_cached_football_data)

    response = client.get("/api/matches/538122")
    data = response.json()

    assert response.status_code == 200
    assert data["source"] == matches_api.FOOTBALL_DATA_PROVIDER
    assert data["match"]["id"] == 538122


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
    # Ce mock simule les lectures cache/API nécessaires à la recommandation multi-matchs.
    async def fake_get_cached_football_data(
        cache_name: str,
        endpoint: str,
        params=None,
        ttl_minutes: int = 30,
    ):
        if endpoint == "/competitions/PL/matches":
            assert cache_name == "matches_pl_scheduled_all_start_dates_all_end_dates"
            assert ttl_minutes == 30
            return {"matches": [FAKE_MATCH]}, FAKE_FRESHNESS
        if endpoint == "/competitions/PL/standings":
            assert cache_name == "standings_pl"
            assert ttl_minutes == 60
            return {"standings": [{"type": "TOTAL", "table": [FAKE_HOME_STANDING, FAKE_AWAY_STANDING]}]}, FAKE_FRESHNESS
        raise AssertionError(f"Endpoint inattendu : {endpoint}")

    # Ce mock simule la construction finale de la recommandation multi-matchs.
    def fake_build_multimatch_recommendation_response(**kwargs):
        return {
            "competition_code": kwargs["competition_code"],
            "match_count": kwargs["match_count"],
            "risk_level": kwargs["risk_level"],
            "data_freshness": {"provider": "football-data.org"},
            "recommendations": [
                {
                    "match_id": 538122,
                    "home_team": "Arsenal FC",
                    "away_team": "Chelsea FC",
                    "recommendation": "Home win",
                }
            ],
        }

    monkeypatch.setattr(recommendations_api, "get_cached_football_data", fake_get_cached_football_data)
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
    assert data["data_freshness"]["matches_cache"]["source"] == "football-data.org"
    assert data["data_freshness"]["standings_cache"]["source"] == "football-data.org"


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


# Ce test vérifie que la fenêtre FlashScore par défaut couvre exactement sept journées.
def test_flashscore_default_window_is_limited_to_seven_days() -> None:
    assert matches_api.build_flashscore_day_offsets_from_filters(None, None) == list(range(7))


# Ce test vérifie que le cache FlashScore est daté, partagé entre compétitions et réutilisé au second appel.
def test_flashscore_cache_is_shared_and_filters_started_matches(monkeypatch) -> None:
    fixed_now = datetime(2026, 7, 17, 16, 0, tzinfo=timezone.utc)
    cache_payloads: dict[str, dict[str, Any]] = {}
    provider_calls: list[int] = []

    future_pl_match = build_flashscore_cached_match(
        match_id=1,
        utc_date="2026-07-18T18:00:00Z",
        area_name="England",
        competition_name="Premier League",
    )
    future_cl_match = build_flashscore_cached_match(
        match_id=2,
        utc_date="2026-07-18T20:00:00Z",
        area_name="Europe",
        competition_name="Champions League",
    )
    started_cl_match = build_flashscore_cached_match(
        match_id=3,
        utc_date="2026-07-17T15:00:00Z",
        area_name="Europe",
        competition_name="Champions League",
    )

    # Ce mock retourne le cache en mémoire utilisé par les appels successifs.
    def fake_load_cache(cache_name: str):
        return cache_payloads.get(cache_name)

    # Ce mock sauvegarde le cache source partagé sans écrire sur disque.
    def fake_save_cache(
        cache_name: str,
        data: dict[str, Any],
        source: str = matches_api.FLASHSCORE_SOURCE,
    ):
        payload = {
            "updated_at": fixed_now.isoformat(),
            "source": source,
            "data": data,
        }
        cache_payloads[cache_name] = payload
        return payload

    # Ce mock considère le cache en mémoire comme frais pendant tout le test.
    def fake_is_cache_fresh(
        cache_payload: dict[str, Any],
        ttl_minutes: int,
    ) -> bool:
        assert cache_payload
        assert ttl_minutes == 30
        return True

    # Ce mock simule une seule récupération source contenant toutes les compétitions de la journée.
    def fake_get_normalized_flashscore_matches_by_day(
        day_offset: int,
        status: str | None,
        team: str | None,
        timezone: str,
        competition_code: str | None,
    ):
        assert status is None
        assert team is None
        assert competition_code is None
        assert timezone == matches_api.FLASHSCORE_DEFAULT_TIMEZONE
        provider_calls.append(day_offset)
        return [future_pl_match, future_cl_match, started_cl_match], {
            "provider": matches_api.FLASHSCORE_SOURCE,
            "status": "success",
            "matches_count": 3,
        }

    monkeypatch.setattr(matches_api, "get_current_utc_date", lambda: date(2026, 7, 17))
    monkeypatch.setattr(matches_api, "get_current_utc_datetime", lambda: fixed_now)
    monkeypatch.setattr(matches_api, "load_cache", fake_load_cache)
    monkeypatch.setattr(matches_api, "save_cache", fake_save_cache)
    monkeypatch.setattr(matches_api, "is_cache_fresh", fake_is_cache_fresh)
    monkeypatch.setattr(
        matches_api,
        "get_normalized_flashscore_matches_by_day",
        fake_get_normalized_flashscore_matches_by_day,
    )

    pl_matches, pl_metadata, pl_freshness = matches_api.get_cached_flashscore_matches(
        day_offset=0,
        status="SCHEDULED",
        team=None,
        timezone=matches_api.FLASHSCORE_DEFAULT_TIMEZONE,
        competition_code="PL",
    )
    cl_matches, cl_metadata, cl_freshness = matches_api.get_cached_flashscore_matches(
        day_offset=0,
        status="SCHEDULED",
        team=None,
        timezone=matches_api.FLASHSCORE_DEFAULT_TIMEZONE,
        competition_code="CL",
    )
    repeated_cl_matches, _, repeated_cl_freshness = matches_api.get_cached_flashscore_matches(
        day_offset=0,
        status="SCHEDULED",
        team=None,
        timezone=matches_api.FLASHSCORE_DEFAULT_TIMEZONE,
        competition_code="CL",
    )

    assert [match["id"] for match in pl_matches] == [1]
    assert [match["id"] for match in cl_matches] == [2]
    assert repeated_cl_matches == cl_matches
    assert pl_metadata["requested_competition_code"] == "PL"
    assert cl_metadata["requested_competition_code"] == "CL"
    assert cl_metadata["team_filtered_count"] == 2
    assert cl_metadata["filtered_count"] == 1
    assert pl_freshness["from_cache"] is False
    assert cl_freshness["from_cache"] is True
    assert repeated_cl_freshness["from_cache"] is True
    assert provider_calls == [0]
    assert len(cache_payloads) == 1
    assert "2026-07-17" in next(iter(cache_payloads))


# Ce test vérifie que les erreurs de journées sans données ne dégradent pas le signal du cache utile.
def test_flashscore_range_cache_flag_uses_successful_days_only(monkeypatch) -> None:
    future_match = build_flashscore_cached_match(
        match_id=4,
        utc_date="2026-07-18T18:00:00Z",
        area_name="Europe",
        competition_name="Champions League",
    )

    # Ce mock simule une journée servie du cache et une journée fournisseur en erreur sans donnée.
    def fake_get_cached_flashscore_matches(
        day_offset: int,
        status: str | None,
        team: str | None,
        timezone: str,
        competition_code: str | None,
    ):
        del status, team, timezone, competition_code
        if day_offset == 0:
            return [future_match], {"status": "success", "filtered_count": 1}, {
                "from_cache": True,
                "updated_at": "2026-07-17T16:00:00+00:00",
            }
        return [], {"status": "error"}, {
            "from_cache": False,
            "updated_at": None,
        }

    monkeypatch.setattr(
        matches_api,
        "get_cached_flashscore_matches",
        fake_get_cached_flashscore_matches,
    )

    matches, metadata, freshness = matches_api.get_cached_flashscore_matches_for_offsets(
        day_offsets=[0, 1],
        status="SCHEDULED",
        team=None,
        timezone=matches_api.FLASHSCORE_DEFAULT_TIMEZONE,
        competition_code="CL",
    )

    assert [match["id"] for match in matches] == [4]
    assert metadata["days_successful"] == 1
    assert metadata["days_failed"] == 1
    assert freshness["from_cache"] is True


# Schéma de communication du fichier :
# test_api.py
# ├── appelle app.main pour créer le client de test
# ├── simule app.api.competitions pour tester /api/competitions sans cache réel
# ├── simule app.api.matches pour tester routes, cache partagé, TTL et fraîcheur avant-match
# └── simule app.api.recommendations pour tester la recommandation multi-matchs sans cache réel
