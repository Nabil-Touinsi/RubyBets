# Rôle du fichier :
# Ces tests valident le contrat API public de la sélection multi-matchs RubyBets V19.

from __future__ import annotations

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
        confidence_level=None,
        local_risk_level=None,
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
