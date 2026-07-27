# Ce fichier regroupe les tests backend du domaine v19 product selection.
# Les sections sources restent identifiables pour préserver la traçabilité et faciliter la maintenance.

from __future__ import annotations


# ============================================================================
# Section issue de : backend/tests/test_v19_product_pipeline.py
# ============================================================================

# Rôle du fichier :
# Ces tests valident le pipeline produit V19, sa sérialisation API et ses abstentions sans appel réseau réel.


import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import experimental_ml_v19 as v19_product_api
from app.services import archives_service
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
        "competition": {
            "name": "Champions League - Qualification",
        },
        "homeTeam": {
            "id": 101,
            "sourceTeamId": HOME_TEAM_ID,
            "sourceEventParticipantId": HOME_EVENT_PARTICIPANT_ID,
            "name": "Home FC",
            "crest": "https://example.invalid/home.png",
        },
        "awayTeam": {
            "id": 202,
            "sourceTeamId": AWAY_TEAM_ID,
            "sourceEventParticipantId": AWAY_EVENT_PARTICIPANT_ID,
            "name": "Away FC",
            "crest": "https://example.invalid/away.png",
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


# Vérifie que la route expose uniquement le contrat produit public autorisé.
def test_v19_product_api_hides_internal_decision_diagnostics(monkeypatch) -> None:
    expected_result = run_product_service(
        odds_payload=build_market_payload(1.10, 10.0, 10.0),
    )
    archived_results = []

    # Simule l'archivage d'arrière-plan sans ouvrir de connexion PostgreSQL.
    def fake_archive_v19_decision(result):
        archived_results.append(result)
        return {"status": "archived", "archived_count": 1}

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
        "archive_v19_decision",
        fake_archive_v19_decision,
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
    assert "decision" not in payload
    assert "score" not in payload["recommendation"]
    assert "raw_score" not in serialized
    assert "calibrated_probability" not in serialized
    assert "max_probability" not in serialized
    assert '"score":' not in serialized
    assert "odds" not in serialized
    assert "bookmaker test" not in serialized
    assert "ne garantit aucun résultat sportif" in payload["responsible_note"]
    assert len(archived_results) == 1
    assert archived_results[0].match_id == expected_result.match_id
    assert archived_results[0].status is expected_result.status


# Vérifie qu'une décision V19 RECOMMEND produit un payload d'archive unique et responsable.
def test_v19_recommendation_builds_archive_payload() -> None:
    result = run_product_service(
        odds_payload=build_market_payload(1.10, 10.0, 10.0),
    )

    payload = archives_service.build_v19_archived_prediction_payload(result)

    assert payload is not None
    assert payload["rubybets_match_id"] == str(MATCH_ID)
    assert payload["source_match_id"] == "AbC123"
    assert payload["competition_name"] == "Champions League - Qualification"
    assert payload["home_team_name"] == "Home FC"
    assert payload["away_team_name"] == "Away FC"
    assert payload["market_type"] == "1X2"
    assert payload["predicted_value"] == "HOME_WIN"
    assert payload["verdict"] == "pending"
    assert payload["match_status"] == "SCHEDULED"
    assert payload["match_date"] == datetime(2026, 7, 14, 18, 0)

    public_justification = payload["justification"].lower()
    assert "probabilité" not in public_justification
    assert "raw_score" not in public_justification
    assert "odds" not in public_justification
    assert "bookmaker" not in public_justification


# Vérifie que l'archivage V19 remplace la décision active sans dépendre du marché précédent.
def test_archive_v19_recommendation_uses_single_upsert(monkeypatch) -> None:
    result = run_product_service(
        odds_payload=build_market_payload(1.10, 10.0, 10.0),
    )
    captured_payloads = []

    # Capture le payload sans ouvrir de connexion PostgreSQL.
    def fake_upsert(payload):
        captured_payloads.append(payload)
        return 1

    monkeypatch.setattr(
        archives_service,
        "upsert_v19_archived_prediction",
        fake_upsert,
    )

    archive_status = archives_service.archive_v19_decision(result)

    assert archive_status == {
        "status": "archived",
        "archived_count": 1,
        "removed_count": 0,
    }
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["engine_version"] == result.engine_version


# Vérifie qu'une abstention V19 retire seulement une ancienne décision encore en attente.
def test_archive_v19_abstention_removes_pending_decision(monkeypatch) -> None:
    result = run_product_service(odds_payload=None)
    removed_results = []

    # Simule la suppression d'une ancienne recommandation devenue obsolète avant le match.
    def fake_delete_pending(archived_result):
        removed_results.append(archived_result)
        return 1

    monkeypatch.setattr(
        archives_service,
        "delete_pending_v19_archive",
        fake_delete_pending,
    )

    archive_status = archives_service.archive_v19_decision(result)

    assert result.status is DecisionStatus.ABSTAIN
    assert archive_status == {
        "status": "removed",
        "archived_count": 0,
        "removed_count": 1,
    }
    assert removed_results == [result]


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
#   -> teste experimental_ml_v19.py, l'archivage V19 et l'enregistrement dans main.py
#   -> interdit tout appel réseau réel et toute exposition des diagnostics, odds ou payloads fournisseurs

# ============================================================================
# Section issue de : backend/tests/test_v19_selection_api.py
# ============================================================================

# Rôle du fichier :
# Ces tests valident le contrat API public et la stratégie de sélection multi-matchs RubyBets V19.


from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import experimental_ml_v19 as v19_product_api
from app.main import app as main_app
from app.v19.application.v19_selection_service import (
    V19ExcludedMatchV1,
    V19SelectedMatchV1,
    V19SelectionExclusionReason,
    V19SelectionProfile,
    V19SelectionResultV1,
    V19SelectionStatus,
    V19_SELECTION_SERVICE_VERSION,
)
from app.v19.domain.decision_contracts import DecisionResultV1
from app.v19.domain.decision_enums import DecisionStatus
from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


# Construit une décision RECOMMEND contenant volontairement un score interne.
def build_recommend_decision(match_id: int) -> DecisionResultV1:
    candidate = ExpertCandidateV1(
        expert_id="v13-double-chance-test",
        expert_version="v13-double-chance-test.1",
        market_type=ExpertMarketType.DOUBLE_CHANCE,
        recommendation_value="1X",
        status=ExpertCandidateStatus.ELIGIBLE,
        raw_score=0.81,
        calibrated_probability=None,
        confidence_level="HIGH",
        local_risk_level="LOW",
        required_features=(),
        missing_features=(),
        positive_reasons=(
            "TOP2_SUM_AT_OR_ABOVE_V13_1_THRESHOLD",
        ),
        caution_reasons=(),
        quality_requirements=(),
        metadata=(),
    )

    return DecisionResultV1(
        match_id=str(match_id),
        status=DecisionStatus.RECOMMEND,
        selected_candidate=candidate,
        evaluated_candidates=(candidate,),
        rejected_candidates=(),
        missing_features=(),
        abstention_reasons=(),
        engine_version="v19-test-engine",
        expert_versions=(
            ("v13-double-chance-test", "v13-double-chance-test.1"),
        ),
        feature_versions=("v19-test-features.1",),
        metadata=(
            ("target_match_provider_status", "success"),
            ("market_provider_status", "success"),
            ("market_module_status", "READY"),
            ("market_quality_flags", None),
            ("history_provider_status", "success"),
            ("history_data_status", "available"),
            ("history_source_used", "test-history"),
            ("product_service_version", "v19-product-test.1"),
        ),
    )


# Construit un résultat de sélection contrôlé sans appel fournisseur.
def build_ready_selection_result() -> V19SelectionResultV1:
    first_decision = build_recommend_decision(101)
    second_decision = build_recommend_decision(202)

    return V19SelectionResultV1(
        status=V19SelectionStatus.READY,
        profile=V19SelectionProfile.MEDIUM,
        requested_count=2,
        candidate_count=3,
        evaluated_count=3,
        abstain_count=0,
        profile_filtered_count=1,
        error_count=0,
        selections=(
            V19SelectedMatchV1(
                match_id=101,
                result=first_decision,
            ),
            V19SelectedMatchV1(
                match_id=202,
                result=second_decision,
            ),
        ),
        excluded_matches=(
            V19ExcludedMatchV1(
                match_id=303,
                reason=V19SelectionExclusionReason.PROFILE_FILTERED,
                details=("LOW_BOOKMAKER_COVERAGE",),
            ),
        ),
        service_version=V19_SELECTION_SERVICE_VERSION,
    )

# Construit une application FastAPI minimale pour isoler la route de sélection.
def build_v19_selection_test_client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(v19_product_api.router)
    return TestClient(test_app)


# Vérifie le contrat public et l'absence de score ou détail fournisseur exposé.
def test_v19_selection_api_returns_public_contract_without_raw_score(
    monkeypatch,
) -> None:
    expected_result = build_ready_selection_result()

    # Retourne une sélection contrôlée et vérifie les paramètres transmis au service.
    async def fake_build_v19_selection(**kwargs):
        assert kwargs["match_ids"] == [101, 202, 303]
        assert kwargs["match_count"] == 2
        assert kwargs["selection_profile"] is V19SelectionProfile.MEDIUM
        assert kwargs["request_id"] == "v19-selection-test"
        return expected_result

    monkeypatch.setattr(
        v19_product_api,
        "build_v19_selection",
        fake_build_v19_selection,
    )
    monkeypatch.setattr(
        v19_product_api,
        "build_selection_request_id",
        lambda: "v19-selection-test",
    )

    client = build_v19_selection_test_client()
    response = client.post(
        "/api/experimental/ml-v19/selection",
        json={
            "match_ids": [101, 202, 303],
            "match_count": 2,
            "selection_profile": "MEDIUM",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    serialized = response.text.lower()
    recommendation = payload["selections"][0]["recommendation"]

    assert payload["status"] == "READY"
    assert payload["selection_explanation"]["headline"] == (
        "S\u00e9lection V19 constitu\u00e9e"
    )
    assert "ont \u00e9t\u00e9 retenus" in (
        payload["selection_explanation"]["summary"]
    )
    assert "s\u00e9lectivit\u00e9" in (
        payload["selection_explanation"]["summary"]
    )
    assert "\u00e9valuation compl\u00e8te" in (
        payload["selection_explanation"]["summary"]
    )
    assert payload["profile"]["description"] == (
        "Recherche un \u00e9quilibre entre robustesse, diversit\u00e9 "
        "des march\u00e9s et variabilit\u00e9 ma\u00eetris\u00e9e."
    )
    assert payload["contract_version"] == "v19.selection.public.1"
    assert payload["profile"]["value"] == "MEDIUM"
    assert payload["selected_count"] == 2
    assert recommendation == {
        "market_type": "DOUBLE_CHANCE",
        "value": "1X",
    }
    assert payload["excluded_matches"][0]["status"] == "PROFILE_FILTERED"
    assert "raw_score" not in serialized
    assert '"score":' not in serialized
    assert "0.81" not in serialized
    assert "low_bookmaker_coverage" not in serialized
    assert "odds" not in serialized
    assert "bookmaker" not in serialized


# Vérifie qu'une liste vide est rejetée avant tout appel au pipeline V19.
# Verifie que le contrat API respecte le minimum de deux matchs.
def test_v19_selection_api_rejects_match_count_below_interface_minimum() -> None:
    client = build_v19_selection_test_client()
    response = client.post(
        "/api/experimental/ml-v19/selection",
        json={
            "match_ids": [101, 202],
            "match_count": 1,
            "selection_profile": "LOW",
        },
    )

    assert response.status_code == 422


def test_v19_selection_api_rejects_empty_match_ids() -> None:
    client = build_v19_selection_test_client()
    response = client.post(
        "/api/experimental/ml-v19/selection",
        json={
            "match_ids": [],
            "match_count": 3,
            "selection_profile": "LOW",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "V19_SELECTION_MATCH_IDS_REQUIRED"
    )


# Vérifie que la nouvelle route apparaît dans le contrat OpenAPI principal.
def test_v19_selection_route_is_registered_in_main_app() -> None:
    paths = set(main_app.openapi().get("paths", {}))

    assert "/api/experimental/ml-v19/selection" in paths


# Schéma de communication :
# test_v19_selection_api.py
#   -> injecte un V19SelectionResultV1 contrôlé
#   -> teste POST /api/experimental/ml-v19/selection
#   -> vérifie le contrat public et l'absence de score ou données fournisseur
#   -> contrôle l'enregistrement de la route dans backend/app/main.py

# ============================================================================
# Section issue de : backend/tests/test_v19_selection_service.py
# ============================================================================

# Rôle du fichier :
# Ces tests valident la composition responsable et différenciée des sélections multi-matchs RubyBets V19.


import asyncio

from app.v19.application.v19_selection_service import (
    V19_SELECTION_MAX_CONCURRENCY,
    V19SelectionExclusionReason,
    V19SelectionProfile,
    V19SelectionStatus,
    build_v19_selection,
)
from app.v19.domain.decision_contracts import DecisionResultV1
from app.v19.domain.decision_enums import DecisionStatus
from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


# Construit un candidat expert contrôlé pour les tests de profil.
def build_candidate(
    *,
    market_type: ExpertMarketType = ExpertMarketType.DOUBLE_CHANCE,
    missing_features: tuple[str, ...] = (),
    caution_reasons: tuple[str, ...] = (),
    confidence_level: str | None = "MEDIUM",
    local_risk_level: str | None = "MEDIUM",
    raw_score: float = 0.81,
) -> ExpertCandidateV1:
    return ExpertCandidateV1(
        expert_id="test-expert",
        expert_version="test-expert.1",
        market_type=market_type,
        recommendation_value="TEST_VALUE",
        status=ExpertCandidateStatus.ELIGIBLE,
        raw_score=raw_score,
        calibrated_probability=None,
        confidence_level=confidence_level,
        local_risk_level=local_risk_level,
        required_features=(),
        missing_features=missing_features,
        positive_reasons=("TEST_POSITIVE_REASON",),
        caution_reasons=caution_reasons,
        quality_requirements=(),
        metadata=(),
    )


# Construit une décision V19 synthétique sans accès réseau.
def build_decision(
    *,
    match_id: int,
    status: DecisionStatus = DecisionStatus.RECOMMEND,
    market_type: ExpertMarketType = ExpertMarketType.DOUBLE_CHANCE,
    market_status: str = "READY",
    history_status: str = "available",
    market_flags: str | None = None,
    missing_features: tuple[str, ...] = (),
    caution_reasons: tuple[str, ...] = (),
    confidence_level: str | None = "MEDIUM",
    local_risk_level: str | None = "MEDIUM",
    raw_score: float = 0.81,
    target_status: str = "success",
) -> DecisionResultV1:
    candidate = build_candidate(
        market_type=market_type,
        missing_features=missing_features,
        caution_reasons=caution_reasons,
        confidence_level=confidence_level,
        local_risk_level=local_risk_level,
        raw_score=raw_score,
    )

    return DecisionResultV1(
        match_id=str(match_id),
        status=status,
        selected_candidate=(
            candidate
            if status is DecisionStatus.RECOMMEND
            else None
        ),
        evaluated_candidates=(candidate,),
        rejected_candidates=(),
        missing_features=missing_features,
        abstention_reasons=(
            ()
            if status is DecisionStatus.RECOMMEND
            else ("NO_ELIGIBLE_CANDIDATE",)
        ),
        engine_version="v19-test-engine",
        expert_versions=(("test-expert", "test-expert.1"),),
        feature_versions=("test-features.1",),
        metadata=(
            ("target_match_provider_status", target_status),
            ("market_module_status", market_status),
            ("market_quality_flags", market_flags),
            ("history_data_status", history_status),
        ),
    )


# Construit un prédicteur asynchrone contrôlé par identifiant de match.
def build_predictor(results: dict[int, object]):
    async def predictor(
        *,
        match_id: int,
        request_id: str | None = None,
    ) -> DecisionResultV1:
        del request_id

        value = results[match_id]

        if isinstance(value, Exception):
            raise value

        assert isinstance(value, DecisionResultV1)
        return value

    return predictor


# Vérifie que le profil faible conserve uniquement les données les plus complètes.
def test_low_profile_rejects_limited_market_coverage() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                local_risk_level="LOW",
            ),
            2: build_decision(
                match_id=2,
                market_flags="LOW_BOOKMAKER_COVERAGE",
                local_risk_level="LOW",
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2],
            match_count=2,
            selection_profile="LOW",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.PARTIAL
    assert [item.match_id for item in result.selections] == [1]
    assert result.profile_filtered_count == 1
    assert result.excluded_matches[0].reason is (
        V19SelectionExclusionReason.PROFILE_FILTERED
    )


# Vérifie que le profil moyen accepte une décision Market malgré un historique non utilisé.
def test_medium_profile_accepts_market_decision_without_history() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                market_type=ExpertMarketType.DOUBLE_CHANCE,
                history_status="unavailable",
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1],
            match_count=1,
            selection_profile=V19SelectionProfile.MEDIUM,
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.READY
    assert result.selections[0].match_id == 1


# Vérifie que le profil moyen refuse un marché Team sans historique disponible.
def test_medium_profile_rejects_team_market_without_history() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                market_type=ExpertMarketType.OVER_1_5,
                market_status="UNAVAILABLE",
                history_status="unavailable",
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1],
            match_count=1,
            selection_profile="MEDIUM",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.EMPTY
    assert result.profile_filtered_count == 1


# Vérifie qu'une alerte non bloquante ne rejette pas automatiquement le profil LOW.
def test_low_profile_accepts_non_blocking_caution_reasons() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                caution_reasons=("NON_BLOCKING_WARNING",),
                local_risk_level="LOW",
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1],
            match_count=1,
            selection_profile="LOW",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.READY
    assert [item.match_id for item in result.selections] == [1]
    assert result.profile_filtered_count == 0


# Vérifie que le profil élevé accepte la variabilité mais conserve un socle de qualité.
def test_high_profile_keeps_variable_recommend_and_never_recovers_abstain() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                market_type=ExpertMarketType.BTTS,
                local_risk_level="HIGH",
            ),
            2: build_decision(
                match_id=2,
                market_status="UNAVAILABLE",
                history_status="unavailable",
                local_risk_level="HIGH",
            ),
            3: build_decision(
                match_id=3,
                status=DecisionStatus.ABSTAIN,
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3],
            match_count=3,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.PARTIAL
    assert [item.match_id for item in result.selections] == [1]
    assert result.profile_filtered_count == 1
    assert result.abstain_count == 1
    assert {
        item.reason
        for item in result.excluded_matches
    } == {
        V19SelectionExclusionReason.PROFILE_FILTERED,
        V19SelectionExclusionReason.ABSTAIN,
    }


# Vérifie que l'ordre initial sert uniquement de dernier critère d'égalité.
def test_selection_deduplicates_evaluates_all_and_uses_input_order_for_ties() -> None:
    predictor = build_predictor(
        {
            3: build_decision(match_id=3),
            1: build_decision(match_id=1),
            2: build_decision(match_id=2),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[3, 3, 1, 2],
            match_count=2,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.READY
    assert result.candidate_count == 3
    assert result.evaluated_count == 3
    assert [item.match_id for item in result.selections] == [3, 1]


# Vérifie qu'une erreur sur un match ne bloque pas l'ensemble de la sélection.
def test_selection_isolates_pipeline_errors() -> None:
    predictor = build_predictor(
        {
            1: RuntimeError("provider unavailable"),
            2: build_decision(match_id=2),
            3: build_decision(match_id=3),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3],
            match_count=1,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.READY
    assert result.evaluated_count == 3
    assert result.error_count == 1
    assert result.selections[0].match_id == 2
    assert result.excluded_matches[0].reason is (
        V19SelectionExclusionReason.PIPELINE_ERROR
    )


# Vérifie que les trois profils produisent des portefeuilles différents quand le pool le permet.
def test_profiles_prioritize_different_risk_and_market_signals() -> None:
    results = {
        1: build_decision(
            match_id=1,
            market_type=ExpertMarketType.DOUBLE_CHANCE,
            local_risk_level="LOW",
            confidence_level="HIGH",
        ),
        2: build_decision(
            match_id=2,
            market_type=ExpertMarketType.OVER_1_5,
            local_risk_level="MEDIUM",
            confidence_level="HIGH",
        ),
        3: build_decision(
            match_id=3,
            market_type=ExpertMarketType.BTTS,
            local_risk_level="HIGH",
            confidence_level="HIGH",
        ),
        4: build_decision(
            match_id=4,
            market_type=ExpertMarketType.STRICT_1X2,
            local_risk_level="MEDIUM",
            confidence_level="HIGH",
        ),
    }
    predictor = build_predictor(results)

    low_result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3, 4],
            match_count=2,
            selection_profile="LOW",
            predictor=predictor,
        )
    )
    medium_result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3, 4],
            match_count=2,
            selection_profile="MEDIUM",
            predictor=predictor,
        )
    )
    high_result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3, 4],
            match_count=2,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert [item.match_id for item in low_result.selections] == [1, 2]
    assert [item.match_id for item in medium_result.selections] == [2, 4]
    assert [item.match_id for item in high_result.selections] == [3, 4]


# Vérifie que le profil moyen diversifie les marchés quand la qualité est comparable.
def test_medium_profile_diversifies_market_types() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                market_type=ExpertMarketType.OVER_1_5,
            ),
            2: build_decision(
                match_id=2,
                market_type=ExpertMarketType.OVER_1_5,
            ),
            3: build_decision(
                match_id=3,
                market_type=ExpertMarketType.STRICT_1X2,
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3],
            match_count=2,
            selection_profile="MEDIUM",
            predictor=predictor,
        )
    )

    assert [item.match_id for item in result.selections] == [1, 3]


# Vérifie que raw_score n'influence jamais le classement de la sélection.
def test_selection_ignores_raw_score_for_ranking() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                raw_score=0.10,
            ),
            2: build_decision(
                match_id=2,
                raw_score=0.99,
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2],
            match_count=1,
            selection_profile="MEDIUM",
            predictor=predictor,
        )
    )

    assert [item.match_id for item in result.selections] == [1]


# Vérifie que le profil prudent préfère une sélection partielle à un candidat trop risqué.
def test_low_profile_returns_partial_instead_of_using_high_risk_candidate() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                local_risk_level="LOW",
            ),
            2: build_decision(
                match_id=2,
                local_risk_level="HIGH",
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2],
            match_count=2,
            selection_profile="LOW",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.PARTIAL
    assert [item.match_id for item in result.selections] == [1]
    assert result.profile_filtered_count == 1


# Vérifie que MEDIUM privilégie les marchés équilibrés lorsque le risque est absent.
def test_medium_and_high_diverge_with_realistic_missing_risk_signals() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                market_type=ExpertMarketType.BTTS,
                confidence_level="MEDIUM",
                local_risk_level="HIGH",
            ),
            2: build_decision(
                match_id=2,
                market_type=ExpertMarketType.STRICT_1X2,
                confidence_level=None,
                local_risk_level=None,
            ),
            3: build_decision(
                match_id=3,
                market_type=ExpertMarketType.DOUBLE_CHANCE,
                confidence_level=None,
                local_risk_level=None,
            ),
        }
    )

    medium_result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3],
            match_count=2,
            selection_profile="MEDIUM",
            predictor=predictor,
        )
    )
    high_result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3],
            match_count=2,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert [
        item.match_id
        for item in medium_result.selections
    ] == [2, 3]
    assert [
        item.match_id
        for item in high_result.selections
    ] == [1, 2]


# Vérifie que MEDIUM préfère une sélection partielle à une donnée de qualité C.
def test_medium_profile_rejects_grade_c_instead_of_filling_selection() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                market_type=ExpertMarketType.STRICT_1X2,
            ),
            2: build_decision(
                match_id=2,
                market_type=ExpertMarketType.BTTS,
                market_flags="SINGLE_BOOKMAKER_ONLY",
                local_risk_level="HIGH",
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2],
            match_count=2,
            selection_profile="MEDIUM",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.PARTIAL
    assert [
        item.match_id
        for item in result.selections
    ] == [1]
    assert result.profile_filtered_count == 1
    assert result.excluded_matches[0].match_id == 2
    assert result.excluded_matches[0].reason is (
        V19SelectionExclusionReason.PROFILE_FILTERED
    )


# Vérifie que le service ne dépasse jamais quatre pipelines simultanés.
def test_selection_limits_prediction_concurrency_to_four() -> None:
    active_count = 0
    maximum_active_count = 0

    async def predictor(
        *,
        match_id: int,
        request_id: str | None = None,
    ) -> DecisionResultV1:
        nonlocal active_count, maximum_active_count
        del request_id

        active_count += 1
        maximum_active_count = max(
            maximum_active_count,
            active_count,
        )

        try:
            await asyncio.sleep(0.02)
            return build_decision(match_id=match_id)
        finally:
            active_count -= 1

    result = asyncio.run(
        build_v19_selection(
            match_ids=list(range(1, 9)),
            match_count=2,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert result.evaluated_count == 8
    assert maximum_active_count == V19_SELECTION_MAX_CONCURRENCY


# Vérifie que l'ordre final reste déterministe malgré des fins de pipeline inversées.
def test_concurrent_selection_preserves_input_order_for_equal_candidates() -> None:
    delays = {
        1: 0.04,
        2: 0.03,
        3: 0.02,
        4: 0.01,
    }

    async def predictor(
        *,
        match_id: int,
        request_id: str | None = None,
    ) -> DecisionResultV1:
        del request_id
        await asyncio.sleep(delays[match_id])
        return build_decision(match_id=match_id)

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2, 3, 4],
            match_count=3,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert [item.match_id for item in result.selections] == [1, 2, 3]


# Schéma de communication :
# test_v19_selection_service.py
#   -> construit des DecisionResultV1 contrôlés
#   -> injecte un prédicteur sans réseau dans v19_selection_service.py
#   -> vérifie profils LOW/MEDIUM/HIGH, qualité, diversité et ordre déterministe
#   -> garantit que raw_score et ABSTAIN ne participent jamais au classement

# Schéma de communication du fichier :
# backend/tests/test_v19_product_selection.py
#   ├── importe les routes, services et contrats du domaine testé
#   ├── utilise les fixtures partagées de backend/tests/conftest.py
#   └── est collecté par pytest dans la suite backend complète
