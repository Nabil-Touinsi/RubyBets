# Ce fichier teste les compositions actuelles, le cache vide court et le fallback historique officiel.
# Tous les appels RapidAPI et team-history sont simulés pour garantir des tests reproductibles.

import asyncio
from typing import Any

from app.services import match_lineups_service as lineups_service


# Cette fonction construit un joueur FlashScore minimal pour les scénarios de test.
def build_raw_player(name: str, number: str = "1") -> dict[str, Any]:
    return {
        "name": name,
        "fieldName": name.split()[0],
        "number": number,
        "player_id": f"id-{name}",
        "country_name": "France",
        "country_image_path": "https://example.test/france.png",
    }


# Cette fonction construit une réponse brute FlashScore pour les deux côtés d'un match.
def build_raw_lineups(
    home_official: bool = True,
    away_official: bool = True,
) -> list[dict[str, Any]]:
    return [
        {
            "side": "home",
            "formation": "4-3-3" if home_official else None,
            "startingLineups": [build_raw_player("Home Player")] if home_official else [],
            "substitutes": [],
            "predictedLineups": [],
            "missingPlayers": [build_raw_player("Old Home Missing")],
            "unsureMissingPlayers": [],
        },
        {
            "side": "away",
            "formation": "4-2-3-1" if away_official else None,
            "startingLineups": [build_raw_player("Away Player")] if away_official else [],
            "substitutes": [],
            "predictedLineups": [],
            "missingPlayers": [build_raw_player("Old Away Missing")],
            "unsureMissingPlayers": [],
        },
    ]


# Cette fonction construit un historique où les deux équipes partagent le même dernier match officiel.
def build_team_history_payload() -> dict[str, Any]:
    shared_match = {
        "match_id": "flashscore_zJBsmMqm",
        "utc_date": "2026-07-21T18:00:00Z",
        "competition_name": "Champions League",
        "home_team": "Thun",
        "away_team": "Dinamo Zagreb",
        "home_score": 1,
        "away_score": 1,
        "data_source": "flashscore_rapidapi",
    }

    return {
        "home_team_history": {
            "recent_matches": [{**shared_match, "is_home": False}],
        },
        "away_team_history": {
            "recent_matches": [{**shared_match, "is_home": True}],
        },
        "data_freshness": {"source_used": "flashscore_rapidapi"},
    }


# Ce test vérifie qu'une réponse vide utilise un cache court de dix minutes.
def test_resolve_current_lineups_cache_ttl_uses_short_ttl_for_empty_payload():
    payload = {
        "source_match_id": "abc123",
        "lineups": [{"side": "home"}, {"side": "away"}],
        "status": "empty",
    }

    assert lineups_service.resolve_current_lineups_cache_ttl(payload) == 10


# Ce test vérifie qu'une composition existante conserve le TTL normal d'une heure.
def test_resolve_current_lineups_cache_ttl_uses_normal_ttl_for_available_payload():
    payload = {
        "source_match_id": "abc123",
        "lineups": build_raw_lineups(),
        "status": "available",
    }

    assert lineups_service.resolve_current_lineups_cache_ttl(payload) == 60


# Ce test vérifie que la nationalité n'est plus exposée à tort comme nom de club.
def test_normalize_player_separates_country_from_club():
    player = lineups_service.normalize_flashscore_lineup_player(
        {
            "name": "Player A",
            "country_name": "Switzerland",
            "country_image_path": "country.png",
        }
    )

    assert player["country_name"] == "Switzerland"
    assert player["country_logo"] == "country.png"
    assert player["club_name"] is None
    assert player["club_logo"] is None


# Ce test vérifie qu'une composition actuelle officielle est renvoyée sans lancer le fallback historique.
def test_current_official_lineups_skip_historical_fallback(monkeypatch):
    monkeypatch.setattr(lineups_service.settings, "rapidapi_key", "test-key")

    # Ce mock fournit une composition officielle actuelle sans appel réseau.
    def fake_current_lineups(match_id: int):
        assert match_id == 123
        return {
            "source_match_id": "current1",
            "lineups": build_raw_lineups(),
            "status": "available",
        }, {"source": "flashscore_rapidapi", "ttl_minutes": 60}

    # Ce mock échoue volontairement si un fallback inutile est lancé.
    async def forbidden_history(match_id: int):
        raise AssertionError(f"Fallback historique inattendu pour {match_id}")

    monkeypatch.setattr(
        lineups_service,
        "get_cached_current_flashscore_lineups",
        fake_current_lineups,
    )
    monkeypatch.setattr(lineups_service, "build_team_history_response", forbidden_history)

    response = asyncio.run(lineups_service.build_match_lineups_response(123))

    assert response["status"] == "available"
    assert response["lineups"]["composition_status"] == "official_available"
    assert response["lineups"]["composition_origin"] == "current_official"
    assert response["fallback_checked"] is False
    assert response["fallback_available"] is False


# Ce test vérifie que le fallback fournit la dernière composition officielle de chaque équipe sans la présenter comme probable.
def test_empty_current_lineups_use_complete_historical_fallback(monkeypatch):
    monkeypatch.setattr(lineups_service.settings, "rapidapi_key", "test-key")

    # Ce mock simule un match actuel sans composition mais avec une absence actuelle à domicile.
    def fake_current_lineups(match_id: int):
        assert match_id == 456
        return {
            "source_match_id": "future1",
            "lineups": [
                {
                    "side": "home",
                    "missingPlayers": [build_raw_player("Current Missing")],
                },
                {"side": "away"},
            ],
            "status": "empty",
            "reason": "lineups_not_published",
        }, {"source": "flashscore_rapidapi", "ttl_minutes": 10}

    # Ce mock fournit l'historique récent des deux équipes.
    async def fake_history(match_id: int):
        assert match_id == 456
        return build_team_history_payload()

    # Ce mock fournit la composition officielle du dernier match commun.
    def fake_historical_lineups(source_match_id: str):
        assert source_match_id == "zJBsmMqm"
        return {
            "source_match_id": source_match_id,
            "lineups": build_raw_lineups(),
            "status": "available",
        }, {"source": "flashscore_rapidapi", "ttl_minutes": 43200}

    monkeypatch.setattr(
        lineups_service,
        "get_cached_current_flashscore_lineups",
        fake_current_lineups,
    )
    monkeypatch.setattr(lineups_service, "build_team_history_response", fake_history)
    monkeypatch.setattr(
        lineups_service,
        "get_cached_historical_flashscore_lineups",
        fake_historical_lineups,
    )

    response = asyncio.run(lineups_service.build_match_lineups_response(456))

    assert response["status"] == "available"
    assert response["fallback_checked"] is True
    assert response["fallback_available"] is True
    assert response["fallback"]["status"] == "complete"
    assert response["lineups"]["composition_status"] == "historical_official_fallback_available"
    assert response["lineups"]["composition_origin"] == "historical_official"
    assert response["lineups"]["official_available"] is False
    assert response["lineups"]["predicted_available"] is False
    assert response["lineups"]["historical_fallback_complete"] is True
    assert response["lineups"]["home"]["starting_lineups"][0]["name"] == "Away Player"
    assert response["lineups"]["away"]["starting_lineups"][0]["name"] == "Home Player"
    assert response["lineups"]["home"]["missing_players"][0]["name"] == "Current Missing"
    assert response["lineups"]["home"]["reference_match"]["source_match_id"] == "zJBsmMqm"
    assert "ne constituent pas les compositions probables" in response["lineups"]["fallback_label"]
    assert response["data_used"]["historical_official_lineups"] is True


# Ce test vérifie qu'un fallback disponible pour une seule équipe reste explicitement partiel.
def test_historical_fallback_can_be_partial(monkeypatch):
    monkeypatch.setattr(lineups_service.settings, "rapidapi_key", "test-key")

    # Ce mock simule une réponse actuelle entièrement vide.
    def fake_current_lineups(match_id: int):
        return {
            "source_match_id": "future2",
            "lineups": [],
            "status": "empty",
            "reason": "lineups_not_published",
        }, {"source": "flashscore_rapidapi", "ttl_minutes": 10}

    # Ce mock fournit deux historiques distincts afin de contrôler la couverture par équipe.
    async def fake_history(match_id: int):
        return {
            "home_team_history": {
                "recent_matches": [
                    {
                        "match_id": "flashscore_home123",
                        "is_home": True,
                        "utc_date": "2026-07-20T18:00:00Z",
                    }
                ]
            },
            "away_team_history": {
                "recent_matches": [
                    {
                        "match_id": "flashscore_away123",
                        "is_home": False,
                        "utc_date": "2026-07-19T18:00:00Z",
                    }
                ]
            },
            "data_freshness": {},
        }

    # Ce mock ne fournit une composition officielle que pour l'équipe domicile.
    def fake_historical_lineups(source_match_id: str):
        return {
            "source_match_id": source_match_id,
            "lineups": build_raw_lineups(
                home_official=source_match_id == "home123",
                away_official=False,
            ),
            "status": "available",
        }, {"source": "flashscore_rapidapi"}

    monkeypatch.setattr(
        lineups_service,
        "get_cached_current_flashscore_lineups",
        fake_current_lineups,
    )
    monkeypatch.setattr(lineups_service, "build_team_history_response", fake_history)
    monkeypatch.setattr(
        lineups_service,
        "get_cached_historical_flashscore_lineups",
        fake_historical_lineups,
    )

    response = asyncio.run(lineups_service.build_match_lineups_response(789))

    assert response["status"] == "partial"
    assert response["fallback"]["status"] == "partial"
    assert response["lineups"]["composition_status"] == "historical_official_fallback_partial"
    assert response["lineups"]["home"]["historical_official_available"] is True
    assert response["lineups"]["away"]["historical_official_available"] is False


# Ce test vérifie que les textes français du contrat backend ne contiennent pas de mojibake.
def test_lineups_limits_have_clean_utf8_text():
    limits = lineups_service.build_lineups_limits()

    assert any("composition officielle" in message for message in limits)
    assert any("remplaçant" in message for message in limits)
    assert all("Ã" not in message for message in limits)


# Schéma de communication du fichier :
# test_match_lineups.py
# ├── teste app/services/match_lineups_service.py sans appel réseau
# └── valide le contrat actuel, le fallback historique, les TTL et l'encodage des messages
