# Rôle du fichier :
# Ces tests valident le pipeline produit V19, sa sérialisation API et ses abstentions sans appel réseau réel.

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import experimental_ml_v19 as v19_product_api
from app.main import app as main_app
from app.v19.application.v19_prediction_service import (
    V19_PRODUCT_SERVICE_VERSION,
    V19ProductMatchInvalidError,
    V19ProductMatchNotFoundError,
    V19ProductMatchProviderError,
    build_v19_prediction_for_match,
)
from app.v19.domain.decision_enums import (
    CandidateRejectionReason,
    DecisionStatus,
)
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


MATCH_ID = 1813105023365578
FIXED_NOW = datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc)
HOME_TEAM_ID = "home-team-1"
AWAY_TEAM_ID = "away-team-2"
HOME_EVENT_PARTICIPANT_ID = "home-participant-1"
AWAY_EVENT_PARTICIPANT_ID = "away-participant-2"


# Retourne une horloge fixe pour stabiliser les métadonnées temporelles des tests.
def fixed_clock() -> datetime:
    return FIXED_NOW


# Construit un match FlashScore normalisé contenant les identités nécessaires au Market Module.
def build_target_match() -> dict[str, Any]:
    return {
        "id": MATCH_ID,
        "sourceMatchId": "AbC123",
        "source": "flashscore_rapidapi",
        "status": "SCHEDULED",
        "utcDate": "2026-07-14T18:00:00Z",
        "homeTeam": {
            "id": 101,
            "sourceTeamId": HOME_TEAM_ID,
            "sourceEventParticipantId": HOME_EVENT_PARTICIPANT_ID,
            "name": "Home FC",
        },
        "awayTeam": {
            "id": 202,
            "sourceTeamId": AWAY_TEAM_ID,
            "sourceEventParticipantId": AWAY_EVENT_PARTICIPANT_ID,
            "name": "Away FC",
        },
    }


# Construit les trois sélections HOME/DRAW/AWAY attendues par l'adapter FlashScore.
def build_market_options(
    home_odd: float,
    draw_odd: float,
    away_odd: float,
) -> list[dict[str, Any]]:
    return [
        {
            "eventParticipantId": HOME_EVENT_PARTICIPANT_ID,
            "value": home_odd,
            "opening": None,
            "active": True,
        },
        {
            "eventParticipantId": None,
            "value": draw_odd,
            "opening": None,
            "active": True,
        },
        {
            "eventParticipantId": AWAY_EVENT_PARTICIPANT_ID,
            "value": away_odd,
            "opening": None,
            "active": True,
        },
    ]


# Construit un payload Market complet pour un seul bookmaker de test.
def build_market_payload(
    home_odd: float,
    draw_odd: float,
    away_odd: float,
) -> list[dict[str, Any]]:
    options = build_market_options(
        home_odd,
        draw_odd,
        away_odd,
    )
    return [
        {
            "name": "Bookmaker Test",
            "image": "https://example.invalid/bookmaker.png",
            "odds": [
                {
                    "bettingType": "HOME_DRAW_AWAY",
                    "bettingScope": "FULL_TIME",
                    "hasLiveBettingOffers": False,
                    "odds": [options[2], options[0], options[1]],
                }
            ],
        }
    ]


# Construit un historique de dix matchs selon les buts choisis pour chaque équipe.
def build_history_response(
    *,
    home_goals_for: int,
    home_goals_against: int,
    away_goals_for: int,
    away_goals_against: int,
    match_count: int = 10,
) -> dict[str, Any]:
    home_matches = [
        {
            "goals_for": home_goals_for,
            "goals_against": home_goals_against,
        }
        for _ in range(match_count)
    ]
    away_matches = [
        {
            "goals_for": away_goals_for,
            "goals_against": away_goals_against,
        }
        for _ in range(match_count)
    ]

    return {
        "match_id": MATCH_ID,
        "source_used": "flashscore_rapidapi",
        "data_status": "available",
        "home_team_history": {
            "team_name": "Home FC",
            "recent_matches": home_matches,
        },
        "away_team_history": {
            "team_name": "Away FC",
            "recent_matches": away_matches,
        },
        "head_to_head": [],
    }


# Exécute le service asynchrone avec des chargeurs contrôlés et sans accès réseau.
def run_product_service(
    *,
    odds_payload: Any | None,
    odds_status: str = "success",
    history_response: dict[str, Any] | None = None,
):
    # Retourne le match cible normalisé contrôlé.
    def match_loader(match_id: int | str | None):
        assert int(match_id) == MATCH_ID
        return build_target_match(), {"status": "success"}

    # Retourne le payload odds contrôlé ou une indisponibilité maîtrisée.
    def odds_loader(match_id: int | str | None):
        assert int(match_id) == MATCH_ID
        return odds_payload, {"status": odds_status}

    # Retourne l'historique contrôlé ou une réponse indisponible explicite.
    async def history_loader(match_id: int):
        assert match_id == MATCH_ID
        return history_response or {
            "match_id": MATCH_ID,
            "source_used": "unavailable",
            "data_status": "unavailable",
            "home_team_history": {},
            "away_team_history": {},
            "head_to_head": [],
        }

    return asyncio.run(
        build_v19_prediction_for_match(
            match_id=MATCH_ID,
            request_id="v19-product-test",
            match_loader=match_loader,
            odds_loader=odds_loader,
            history_loader=history_loader,
            clock=fixed_clock,
        )
    )


# Retrouve un candidat évalué par son marché dans la décision finale.
def candidate_for(result, market_type: ExpertMarketType):
    return next(
        candidate
        for candidate in result.evaluated_candidates
        if candidate.market_type is market_type
    )


# Retrouve le motif de rejet associé à un marché évalué.
def rejection_reason_for(result, market_type: ExpertMarketType):
    return next(
        rejected.reason
        for rejected in result.rejected_candidates
        if rejected.candidate.market_type is market_type
    )


# Vérifie que le strict 1X2 gagne l'orchestration lorsque le consensus Market est dominant.
def test_product_pipeline_selects_strict_1x2() -> None:
    result = run_product_service(
        odds_payload=build_market_payload(1.10, 10.0, 10.0),
    )

    assert result.status is DecisionStatus.RECOMMEND
    assert result.selected_candidate is not None
    assert result.selected_candidate.market_type is ExpertMarketType.STRICT_1X2
    assert result.selected_candidate.recommendation_value == "HOME_WIN"
    assert len(result.evaluated_candidates) == 4


# Vérifie que Double Chance est retenue lorsque le strict échoue mais que le marché reste concentré.
def test_product_pipeline_selects_double_chance_after_strict() -> None:
    result = run_product_service(
        odds_payload=build_market_payload(1.40, 4.0, 8.0),
    )

    assert result.selected_candidate is not None
    assert result.selected_candidate.market_type is ExpertMarketType.DOUBLE_CHANCE
    assert candidate_for(result, ExpertMarketType.STRICT_1X2).status is ExpertCandidateStatus.INELIGIBLE


# Vérifie qu'Over 1.5 reste sélectionnable lorsque les odds sont indisponibles et BTTS trop faible.
def test_product_pipeline_selects_over_15_without_market() -> None:
    history = build_history_response(
        home_goals_for=2,
        home_goals_against=0,
        away_goals_for=2,
        away_goals_against=0,
    )
    result = run_product_service(
        odds_payload=None,
        odds_status="error",
        history_response=history,
    )

    assert result.selected_candidate is not None
    assert result.selected_candidate.market_type is ExpertMarketType.OVER_1_5
    assert candidate_for(result, ExpertMarketType.BTTS).status is ExpertCandidateStatus.INELIGIBLE
    assert candidate_for(result, ExpertMarketType.STRICT_1X2).status is ExpertCandidateStatus.INELIGIBLE


# Vérifie que BTTS remplace Over 1.5 conformément à la politique V17.8 historique.
def test_product_pipeline_btts_replaces_over_15() -> None:
    history = build_history_response(
        home_goals_for=2,
        home_goals_against=1,
        away_goals_for=2,
        away_goals_against=1,
    )
    result = run_product_service(
        odds_payload=None,
        odds_status="error",
        history_response=history,
    )

    assert result.selected_candidate is not None
    assert result.selected_candidate.market_type is ExpertMarketType.BTTS
    assert rejection_reason_for(
        result,
        ExpertMarketType.OVER_1_5,
    ) is CandidateRejectionReason.REPLACED_BY_BTTS_POLICY


# Vérifie que l'absence de toutes les sources produit une abstention et quatre diagnostics locaux.
def test_product_pipeline_abstains_when_all_sources_are_unavailable() -> None:
    result = run_product_service(
        odds_payload=None,
        odds_status="error",
    )

    assert result.status is DecisionStatus.ABSTAIN
    assert result.selected_candidate is None
    assert len(result.evaluated_candidates) == 4
    assert all(
        candidate.status is ExpertCandidateStatus.INELIGIBLE
        for candidate in result.evaluated_candidates
    )
    assert result.missing_features
    assert result.abstention_reasons[0] == "NO_ELIGIBLE_CANDIDATE"


# Vérifie qu'un historique indisponible ne bloque pas une décision Market valide.
def test_product_pipeline_keeps_market_decision_when_history_is_unavailable() -> None:
    result = run_product_service(
        odds_payload=build_market_payload(1.10, 10.0, 10.0),
    )

    assert result.selected_candidate is not None
    assert result.selected_candidate.market_type is ExpertMarketType.STRICT_1X2
    assert candidate_for(result, ExpertMarketType.OVER_1_5).missing_features
    assert candidate_for(result, ExpertMarketType.BTTS).missing_features


# Vérifie la conservation des versions, sources et statuts sans payload fournisseur dans les métadonnées.
def test_product_pipeline_preserves_traceability_metadata() -> None:
    result = run_product_service(
        odds_payload=None,
        odds_status="error",
    )
    metadata = dict(result.metadata)

    assert metadata["request_id"] == "v19-product-test"
    assert metadata["product_service_version"] == V19_PRODUCT_SERVICE_VERSION
    assert metadata["market_provider_status"] == "error"
    assert metadata["market_module_status"] == "UNAVAILABLE"
    assert metadata["history_data_status"] == "unavailable"
    assert result.feature_versions
    assert len(result.expert_versions) == 4


# Vérifie que le service distingue une absence réelle de match d'une panne fournisseur.
def test_product_pipeline_maps_target_match_absence() -> None:
    # Simule une absence reconnue par les métadonnées fournisseur.
    def missing_match_loader(match_id: int | str | None):
        del match_id
        return None, {"status": "not_flashscore_match_id"}

    with pytest.raises(V19ProductMatchNotFoundError):
        asyncio.run(
            build_v19_prediction_for_match(
                match_id=MATCH_ID,
                match_loader=missing_match_loader,
                clock=fixed_clock,
            )
        )


# Vérifie que le service refuse un match sans équipes exploitables.
def test_product_pipeline_rejects_invalid_target_match() -> None:
    # Retourne un match présent mais incomplet pour le contrat produit V19.
    def invalid_match_loader(match_id: int | str | None):
        del match_id
        return {"id": MATCH_ID}, {"status": "success"}

    with pytest.raises(
        V19ProductMatchInvalidError,
        match="target_match_teams_missing",
    ):
        asyncio.run(
            build_v19_prediction_for_match(
                match_id=MATCH_ID,
                match_loader=invalid_match_loader,
                clock=fixed_clock,
            )
        )


# Construit une application FastAPI minimale pour tester uniquement la route produit V19.
def build_v19_product_test_client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(v19_product_api.router)
    return TestClient(test_app)


# Vérifie la sérialisation complète de la route et l'absence d'odds ou de bookmakers exposés.
def test_v19_product_api_serializes_decision_without_odds(monkeypatch) -> None:
    expected_result = run_product_service(
        odds_payload=build_market_payload(1.10, 10.0, 10.0),
    )

    # Retourne une décision contrôlée et reporte l'identifiant de requête transmis par la route.
    async def fake_build_v19_prediction_for_match(**kwargs):
        return replace(
            expected_result,
            metadata=tuple(
                (key, kwargs.get("request_id") if key == "request_id" else value)
                for key, value in expected_result.metadata
            ),
        )

    monkeypatch.setattr(
        v19_product_api,
        "build_v19_prediction_for_match",
        fake_build_v19_prediction_for_match,
    )
    monkeypatch.setattr(
        v19_product_api,
        "build_request_id",
        lambda match_id: f"v19-product-{match_id}-test",
    )

    client = build_v19_product_test_client()
    response = client.get(
        f"/api/experimental/ml-v19/rubybets-matches/{MATCH_ID}"
    )

    assert response.status_code == 200
    payload = response.json()
    serialized = response.text.lower()

    assert payload["source"] == "rubybets_v19_product_api"
    assert payload["scope"] == "experimental_clubs_product_pipeline"
    assert payload["status"] == "RECOMMEND"
    assert payload["recommendation"]["market_type"] == "STRICT_1X2"
    assert len(payload["decision"]["evaluated_candidates"]) == 4
    assert "odds" not in serialized
    assert "bookmaker test" not in serialized
    assert "ne garantit aucun résultat sportif" in payload["responsible_note"]


# Vérifie la traduction HTTP stable des erreurs applicatives du pipeline produit V19.
@pytest.mark.parametrize(
    ("application_error", "expected_status", "expected_code"),
    (
        (
            V19ProductMatchNotFoundError("target_match_not_found"),
            404,
            "V19_PRODUCT_TARGET_MATCH_NOT_FOUND",
        ),
        (
            V19ProductMatchInvalidError("target_match_teams_missing"),
            422,
            "V19_PRODUCT_TARGET_MATCH_INVALID",
        ),
        (
            V19ProductMatchProviderError("target_provider_unavailable"),
            503,
            "V19_PRODUCT_TARGET_PROVIDER_UNAVAILABLE",
        ),
    ),
)
def test_v19_product_api_maps_application_errors(
    monkeypatch,
    application_error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    # Relève l'erreur applicative contrôlée sans appeler les fournisseurs réels.
    async def fake_build_v19_prediction_for_match(**kwargs):
        del kwargs
        raise application_error

    monkeypatch.setattr(
        v19_product_api,
        "build_v19_prediction_for_match",
        fake_build_v19_prediction_for_match,
    )

    client = build_v19_product_test_client()
    response = client.get(
        f"/api/experimental/ml-v19/rubybets-matches/{MATCH_ID}"
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert response.json()["detail"]["match_id"] == MATCH_ID


# Vérifie que les routes V19 sont exposées dans le contrat OpenAPI public de l'application principale.
def test_v19_product_route_is_registered_in_main_app() -> None:
    paths = set(main_app.openapi().get("paths", {}))

    assert "/api/experimental/ml-v19/rubybets-matches/{match_id}" in paths
    assert "/api/experimental/ml-v19/h2h/rubybets-matches/{match_id}" in paths


# Vérifie qu'un match déjà commencé est rejeté avant tout appel aux marchés ou aux historiques.
def test_product_pipeline_rejects_started_match_before_downstream_calls() -> None:
    downstream_calls = {"odds": 0, "history": 0}
    started_match = {
        **build_target_match(),
        "status": "SCHEDULED",
        "utcDate": "2026-07-13T07:59:00Z",
    }

    # Retourne un match dont le coup d'envoi est antérieur à l'horloge du pipeline.
    def match_loader(match_id: int | str | None):
        assert int(match_id) == MATCH_ID
        return started_match, {"status": "success"}

    # Compte tout appel marché qui ne devrait jamais être exécuté.
    def odds_loader(match_id: int | str | None):
        del match_id
        downstream_calls["odds"] += 1
        return None, {"status": "unexpected"}

    # Compte tout appel historique qui ne devrait jamais être exécuté.
    async def history_loader(match_id: int):
        del match_id
        downstream_calls["history"] += 1
        return {}

    with pytest.raises(
        V19ProductMatchInvalidError,
        match="target_match_kickoff_not_future",
    ):
        asyncio.run(
            build_v19_prediction_for_match(
                match_id=MATCH_ID,
                request_id="v19-started-match-test",
                match_loader=match_loader,
                odds_loader=odds_loader,
                history_loader=history_loader,
                clock=fixed_clock,
            )
        )

    assert downstream_calls == {"odds": 0, "history": 0}


# Schéma de communication :
# test_v19_product_pipeline.py
#   -> injecte match, odds et historiques contrôlés dans v19_prediction_service.py
#   -> valide les quatre experts, l'orchestrateur et les cas RECOMMEND / ABSTAIN
#   -> vérifie le rejet avant appel aval des matchs déjà commencés
#   -> teste experimental_ml_v19.py et l'enregistrement dans main.py
#   -> interdit tout appel réseau réel et toute exposition des odds ou payloads fournisseurs
