# Ce fichier teste la normalisation, le cache, l'orientation, l'agrégation et le contrat API des statistiques avancées.
# Les appels fournisseur sont simulés afin de ne jamais utiliser RapidAPI pendant les tests.

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import matches as matches_api
from app.services import match_advanced_stats_service as advanced_service
from app.services import rapidapi_flashscore_client as flashscore_client


route_app = FastAPI()
route_app.include_router(matches_api.router)
client = TestClient(route_app)


# Cette fonction construit une valeur normalisée simple pour les données de test.
def build_normalized_number(value: int | float) -> dict[str, Any]:
    return {
        "raw": value,
        "value": value,
        "percentage": None,
        "successful": None,
        "attempted": None,
        "value_type": "number",
    }


# Cette fonction construit un match FlashScore terminé orientable par identifiant d'équipe.
def build_finished_match(
    source_match_id: str,
    home_team_id: str,
    away_team_id: str,
    home_score: int = 2,
    away_score: int = 1,
) -> dict[str, Any]:
    return {
        "id": f"flashscore_{source_match_id}",
        "sourceMatchId": source_match_id,
        "utcDate": "2026-07-01T18:00:00Z",
        "status": "FINISHED",
        "homeTeam": {
            "id": home_team_id,
            "sourceTeamId": home_team_id,
            "name": f"Home {home_team_id}",
        },
        "awayTeam": {
            "id": away_team_id,
            "sourceTeamId": away_team_id,
            "name": f"Away {away_team_id}",
        },
        "score": {
            "fullTime": {
                "home": home_score,
                "away": away_score,
            }
        },
    }


# Ce test vérifie la normalisation d'un nombre simple sans le transformer en pourcentage.
def test_normalize_flashscore_stat_value_number():
    normalized = flashscore_client.normalize_flashscore_stat_value(16)

    assert normalized == {
        "raw": 16,
        "value": 16,
        "percentage": None,
        "successful": None,
        "attempted": None,
        "value_type": "number",
    }


# Ce test vérifie l'extraction d'un pourcentage simple.
def test_normalize_flashscore_stat_value_percentage():
    normalized = flashscore_client.normalize_flashscore_stat_value("62%")

    assert normalized is not None
    assert normalized["value"] == 62
    assert normalized["percentage"] == 62
    assert normalized["successful"] is None
    assert normalized["attempted"] is None


# Ce test vérifie l'extraction du pourcentage et des volumes d'une valeur composée.
def test_normalize_flashscore_stat_value_percentage_ratio():
    normalized = flashscore_client.normalize_flashscore_stat_value("91% (518/571)")

    assert normalized is not None
    assert normalized["percentage"] == 91
    assert normalized["successful"] == 518
    assert normalized["attempted"] == 571
    assert normalized["value_type"] == "percentage_ratio"


# Ce test vérifie la déduplication identique et la règle déterministe sur un doublon contradictoire.
def test_deduplicate_flashscore_stats_keeps_last_conflicting_value():
    metrics, limitations = flashscore_client.normalize_and_deduplicate_flashscore_stats(
        [
            {"name": "Total shots", "home_team": 6, "away_team": 16},
            {"name": "Total shots", "home_team": 6, "away_team": 16},
            {"name": "Expected goals (xG)", "home_team": 0.55, "away_team": 2.07},
            {"name": "Expected goals (xG)", "home_team": 0.70, "away_team": 1.95},
        ]
    )

    assert len(metrics) == 2
    assert metrics["total_shots"]["home_team"]["value"] == 6
    assert metrics["expected_goals"]["home_team"]["value"] == 0.7
    assert limitations == [
        {
            "code": "conflicting_duplicate_stat",
            "metric": "expected_goals",
            "message": (
                "Plusieurs valeurs différentes portent le même nom ; "
                "la dernière valeur valide de la section match est conservée."
            ),
            "kept_source_index": 3,
            "discarded_source_index": 2,
        }
    ]


# Ce test vérifie que l'équipe extérieure lit away_team et les données adverses dans home_team.
def test_build_oriented_match_sample_uses_team_ids():
    match = build_finished_match("m1", "home-id", "away-id", home_score=3, away_score=2)
    stats_payload = {
        "metrics": {
            "expected_goals": {
                "home_team": build_normalized_number(1.8),
                "away_team": build_normalized_number(1.2),
            },
            "total_shots": {
                "home_team": build_normalized_number(12),
                "away_team": build_normalized_number(8),
            },
        },
        "limitations": [],
    }

    sample, limitations = advanced_service.build_oriented_match_sample(
        match=match,
        stats_payload=stats_payload,
        source_team_id="away-id",
    )

    assert limitations == []
    assert sample is not None
    assert sample["team_side"] == "away"
    assert sample["goals_for"]["value"] == 2
    assert sample["goals_against"]["value"] == 3
    assert sample["expected_goals_for"]["value"] == 1.2
    assert sample["expected_goals_against"]["value"] == 1.8
    assert sample["total_shots"]["value"] == 8
    assert sample["shots_conceded"]["value"] == 12


# Ce test vérifie l'agrégation sur plusieurs matchs et la couverture propre à chaque métrique.
def test_aggregate_team_samples_uses_only_available_values():
    samples = [
        {
            "goals_for": build_normalized_number(2),
            "goals_against": build_normalized_number(1),
            "expected_goals_for": build_normalized_number(1.5),
            "total_shots": build_normalized_number(10),
            "shots_on_target": build_normalized_number(5),
        },
        {
            "goals_for": build_normalized_number(1),
            "goals_against": build_normalized_number(0),
            "total_shots": build_normalized_number(8),
            "shots_on_target": build_normalized_number(4),
        },
    ]

    metrics, limitations = advanced_service.aggregate_team_samples(samples, matches_requested=5)

    assert limitations == []
    assert metrics["goals_for"]["value"] == 1.5
    assert metrics["goals_for"]["matches_used"] == 2
    assert metrics["expected_goals_for"]["value"] == 1.5
    assert metrics["expected_goals_for"]["matches_used"] == 1
    assert metrics["expected_goals_for"]["coverage"] == 0.2
    assert metrics["shot_conversion"]["value"] == 16.67
    assert metrics["shot_accuracy"]["value"] == 50.0


# Ce test vérifie que les pourcentages accompagnés de volumes sont agrégés de manière pondérée.
def test_aggregate_percentage_metric_weights_successes_and_attempts():
    samples = [
        {
            "pass_accuracy": {
                "value": 80,
                "percentage": 80,
                "successful": 80,
                "attempted": 100,
                "value_type": "percentage_ratio",
            }
        },
        {
            "pass_accuracy": {
                "value": 50,
                "percentage": 50,
                "successful": 5,
                "attempted": 10,
                "value_type": "percentage_ratio",
            }
        },
    ]

    metric = advanced_service.aggregate_percentage_metric(
        samples=samples,
        metric_name="pass_accuracy",
        matches_requested=5,
    )

    assert metric is not None
    assert metric["value"] == 77.27
    assert metric["successful"] == 85
    assert metric["attempted"] == 110
    assert metric["matches_used"] == 2
    assert metric["aggregation"] == "weighted_by_attempts"


# Ce test vérifie qu'une statistique absente ne devient jamais une valeur égale à zéro.
def test_missing_metric_is_not_replaced_with_zero():
    metrics, _ = advanced_service.aggregate_team_samples(
        [{"goals_for": build_normalized_number(1)}],
        matches_requested=5,
    )

    assert "expected_goals_for" not in metrics
    assert "total_shots" not in metrics
    assert "shot_conversion" not in metrics


# Ce test vérifie qu'un appel FlashScore en erreur n'empêche pas l'agrégation des autres matchs.
def test_team_advanced_stats_continues_when_one_match_stats_call_fails(monkeypatch):
    recent_matches = [
        build_finished_match(f"m{index}", "team-1", f"opponent-{index}")
        for index in range(1, 6)
    ]

    # Ce mock fournit cinq résultats terminés sans appel fournisseur réel.
    def fake_get_team_results(
        team_id: str,
        target_utc_date: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        assert team_id == "team-1"
        assert target_utc_date == "2026-07-28T17:00:00Z"
        assert limit == 5
        return recent_matches, {"status": "success", "results": 5}

    # Ce mock simule une erreur isolée sur le troisième match et quatre réponses exploitables.
    def fake_get_match_stats(
        source_match_id: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        if source_match_id == "m3":
            return None, {"status": "error", "match_id": source_match_id}

        return {
            "metrics": {
                "total_shots": {
                    "home_team": build_normalized_number(10),
                    "away_team": build_normalized_number(6),
                },
                "shots_on_target": {
                    "home_team": build_normalized_number(5),
                    "away_team": build_normalized_number(2),
                },
            },
            "limitations": [],
        }, {
            "status": "success",
            "match_id": source_match_id,
            "data_freshness": {
                "from_cache": False,
                "updated_at": "2026-07-23T12:00:00+00:00",
            },
        }

    monkeypatch.setattr(advanced_service, "get_normalized_flashscore_team_results", fake_get_team_results)
    monkeypatch.setattr(advanced_service, "get_flashscore_match_stats", fake_get_match_stats)

    result = asyncio.run(
        advanced_service.build_team_advanced_stats(
            team={"name": "Team 1"},
            source_team_id="team-1",
            target_utc_date="2026-07-28T17:00:00Z",
            semaphore=asyncio.Semaphore(4),
        )
    )

    assert result["matches_found"] == 5
    assert result["matches_with_stats"] == 4
    assert result["metrics"]["total_shots"]["matches_used"] == 4
    assert any(
        limitation.get("code") == "match_stats_unavailable"
        and limitation.get("match_id") == "m3"
        for limitation in result["limitations"]
    )


# Ce test vérifie que le cache individuel évite un second appel à RapidAPI.
def test_flashscore_match_stats_cache_avoids_second_provider_call(monkeypatch):
    cache_store: dict[str, Any] = {}
    provider_calls = 0

    # Ce mock lit le cache mémoire propre au test.
    def fake_load_cache(cache_name: str) -> dict[str, Any] | None:
        return cache_store.get(cache_name)

    # Ce mock sauvegarde le cache mémoire propre au test.
    def fake_save_cache(cache_name: str, data: dict[str, Any], source: str) -> dict[str, Any]:
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "source": source,
            "data": data,
        }
        cache_store[cache_name] = payload
        return payload

    # Ce mock compte le nombre réel d'appels fournisseur demandés par le client.
    def fake_provider_call(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        nonlocal provider_calls
        provider_calls += 1
        assert endpoint == "/matches/match/stats"
        assert params == {"match_id": "fP5Co3V6"}
        return {
            "match": [
                {"name": "Total shots", "home_team": 6, "away_team": 16},
            ]
        }

    monkeypatch.setattr(flashscore_client, "load_cache", fake_load_cache)
    monkeypatch.setattr(flashscore_client, "save_cache", fake_save_cache)
    monkeypatch.setattr(flashscore_client, "get_rapidapi_flashscore_data", fake_provider_call)

    first_payload, first_metadata = flashscore_client.get_flashscore_match_stats("fP5Co3V6")
    second_payload, second_metadata = flashscore_client.get_flashscore_match_stats("fP5Co3V6")

    assert provider_calls == 1
    assert first_payload == second_payload
    assert first_metadata["data_freshness"]["from_cache"] is False
    assert second_metadata["data_freshness"]["from_cache"] is True


# Ce test vérifie que la couverture incomplète produit explicitement le statut partial.
def test_determine_advanced_stats_status_returns_partial():
    complete_core_metrics = {
        metric_name: {"matches_used": 5}
        for metric_name in advanced_service.ADVANCED_STATS_EXPECTED_METRICS
    }
    home_stats = {
        "matches_with_stats": 5,
        "metrics": complete_core_metrics,
    }
    away_stats = {
        "matches_with_stats": 4,
        "metrics": complete_core_metrics,
    }

    assert advanced_service.determine_advanced_stats_status(home_stats, away_stats) == "partial"


# Ce test vérifie le contrat public de la nouvelle route sans appeler FlashScore.
def test_advanced_stats_route_returns_public_contract(monkeypatch):
    # Ce mock remplace le service complet par une réponse contractuelle stable.
    async def fake_build_response(match_id: int) -> dict[str, Any]:
        assert match_id == 123
        return {
            "match_id": 123,
            "status": "partial",
            "sample_size_requested": 5,
            "home_team": {
                "team_id": "home-id",
                "team_name": "KuPS",
                "matches_requested": 5,
                "matches_found": 5,
                "matches_with_stats": 4,
                "metrics": {
                    "total_shots": {
                        "value": 11.2,
                        "unit": "per_match",
                        "matches_used": 4,
                        "matches_requested": 5,
                        "coverage": 0.8,
                    }
                },
            },
            "away_team": {
                "team_id": "away-id",
                "team_name": "Sabah Baku",
                "matches_requested": 5,
                "matches_found": 5,
                "matches_with_stats": 5,
                "metrics": {},
            },
            "data_quality": {
                "status": "partial",
                "limitations": [],
                "metric_coverage": {
                    "home_team": {
                        "total_shots": {
                            "matches_used": 4,
                            "matches_requested": 5,
                            "coverage": 0.8,
                        }
                    },
                    "away_team": {},
                },
            },
            "data_freshness": {
                "source": "flashscore_rapidapi",
                "generated_at": "2026-07-23T12:00:00Z",
            },
        }

    monkeypatch.setattr(matches_api, "build_match_advanced_stats_response", fake_build_response)

    response = client.get("/api/matches/123/advanced-stats")
    data = response.json()

    assert response.status_code == 200
    assert data["match_id"] == 123
    assert data["status"] == "partial"
    assert data["sample_size_requested"] == 5
    assert data["home_team"]["matches_with_stats"] == 4
    assert data["home_team"]["metrics"]["total_shots"]["coverage"] == 0.8
    assert data["data_quality"]["status"] == "partial"


# Flux :
# test_match_advanced_stats.py
#   ├── rapidapi_flashscore_client.py pour normalisation, déduplication et cache
#   ├── match_advanced_stats_service.py pour orientation, agrégation et statuts partiels
#   └── matches.py via TestClient pour vérifier GET /api/matches/{match_id}/advanced-stats
