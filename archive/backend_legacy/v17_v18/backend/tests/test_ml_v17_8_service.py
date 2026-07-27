# Role du fichier :
# Ces tests verifient le comportement du service experimental V17.8, de son adaptateur de features
# et de sa route demo API sans modifier le scoring explicable V1.

from fastapi.testclient import TestClient

from app.main import app
from app.services.ml_v17_8_feature_adapter import (
    adapt_and_recommend_with_v17_8,
    build_v17_8_features_from_prepared_match_data,
)
from app.services.ml_v17_8_service import (
    ABSTAIN_STATUS,
    BTTS_TYPE,
    BTTS_YES_VALUE,
    DOUBLE_CHANCE_TYPE,
    GOALS_OVER_15_TYPE,
    RECOMMEND_STATUS,
    recommend_with_v17_8,
)


# Cree un jeu de features BTTS complet et favorable pour V17.8.
def build_valid_btts_features() -> dict:
    return {
        "v17_6_score": 0.61,
        "min_history_count_last_10": 10,
        "expected_home_goals_proxy": 1.25,
        "expected_away_goals_proxy": 1.10,
        "expected_total_goals_proxy": 2.35,
        "combined_btts_rate_last_10": 0.62,
        "combined_over_1_5_rate_last_10": 0.72,
        "home_failed_to_score_rate_last_10": 0.30,
        "away_failed_to_score_rate_last_10": 0.35,
    }


# Cree des donnees de match preparees completes pour tester l'adaptateur V17.8.
def build_complete_prepared_match_data() -> dict:
    return {
        "match": {
            "id": 538143,
            "competition": {
                "code": "PL",
            },
        },
        "btts_signals": build_valid_btts_features(),
        "v17_reference": {
            "status": RECOMMEND_STATUS,
            "type": GOALS_OVER_15_TYPE,
            "value": "OVER_1_5",
            "source": "V17_REFERENCE_TEST",
        },
    }


# Verifie que V17.8 remplace une recommandation OVER_1_5 par BTTS_YES si les signaux BTTS sont forts.
def test_v17_8_recommends_btts_when_gates_are_valid() -> None:
    features = build_valid_btts_features()
    features.update(
        {
            "v17_recommendation_status": RECOMMEND_STATUS,
            "v17_recommendation_type": GOALS_OVER_15_TYPE,
            "v17_recommendation_value": "OVER_1_5",
            "v17_source": "V17_REFERENCE_BASE",
        }
    )

    result = recommend_with_v17_8(features)

    assert result["status"] == RECOMMEND_STATUS
    assert result["recommendation_type"] == BTTS_TYPE
    assert result["recommendation_value"] == BTTS_YES_VALUE
    assert result["is_btts"] is True
    assert result["is_replaced_over15"] is True
    assert result["risk_level"] == "high"


# Verifie que V17.8 conserve la recommandation prudente V17.0 si le signal BTTS est trop faible.
def test_v17_8_keeps_base_recommendation_when_btts_is_too_weak() -> None:
    features = build_valid_btts_features()
    features.update(
        {
            "v17_6_score": 0.40,
            "v17_recommendation_status": RECOMMEND_STATUS,
            "v17_recommendation_type": DOUBLE_CHANCE_TYPE,
            "v17_recommendation_value": "1X",
            "v17_source": "V17_REFERENCE_BASE",
        }
    )

    result = recommend_with_v17_8(features)

    assert result["status"] == RECOMMEND_STATUS
    assert result["recommendation_type"] == DOUBLE_CHANCE_TYPE
    assert result["recommendation_value"] == "1X"
    assert result["is_btts"] is False
    assert result["btts_gate_result"]["is_eligible"] is False
    assert "BTTS_SCORE_TOO_LOW" in result["btts_gate_result"]["reasons"]


# Verifie que V17.8 s'abstient si aucune recommandation de base n'existe et que les features BTTS sont absentes.
def test_v17_8_abstains_when_required_features_are_missing() -> None:
    features = {
        "v17_recommendation_status": ABSTAIN_STATUS,
        "v17_recommendation_type": "ABSTAIN",
        "v17_recommendation_value": "ABSTAIN",
    }

    result = recommend_with_v17_8(features)

    assert result["status"] == ABSTAIN_STATUS
    assert result["recommendation_type"] == "ABSTAIN"
    assert result["recommendation_value"] == "ABSTAIN"
    assert result["risk_level"] == "high"
    assert "MISSING_BTTS_FEATURES" in result["reasons"]
    assert len(result["missing_features"]) > 0


# Verifie que la route API demo V17.8 expose bien une recommandation BTTS experimentale.
def test_v17_8_demo_api_returns_btts_recommendation() -> None:
    client = TestClient(app)

    response = client.get("/api/experimental/ml/v17-8/demo")

    assert response.status_code == 200

    payload = response.json()

    assert payload["source"] == "rubybets_ml_v17_8_api"
    assert payload["scope"] == "experimental"
    assert payload["status"] == "demo_only"
    assert payload["demo_features_profile"] == "controlled_btts_yes_case"

    result = payload["result"]

    assert result["status"] == RECOMMEND_STATUS
    assert result["recommendation_type"] == BTTS_TYPE
    assert result["recommendation_value"] == BTTS_YES_VALUE
    assert result["is_btts"] is True
    assert result["is_replaced_over15"] is True
    assert result["scope"] == "experimental"
    assert result["responsible_note"]

# Verifie que la route API adapter-demo execute bien le flux donnees preparees -> adaptateur -> service.
def test_v17_8_adapter_demo_api_returns_adapted_btts_recommendation() -> None:
    client = TestClient(app)

    response = client.get("/api/experimental/ml/v17-8/adapter-demo")

    assert response.status_code == 200

    payload = response.json()

    assert payload["source"] == "rubybets_ml_v17_8_api"
    assert payload["scope"] == "experimental"
    assert payload["status"] == "adapter_demo_only"
    assert payload["demo_features_profile"] == "controlled_adapter_btts_yes_case"
    assert payload["flow"] == [
        "prepared_match_data",
        "ml_v17_8_feature_adapter.py",
        "ml_v17_8_service.py",
    ]

    adapter_result = payload["result"]
    adapter_metadata = adapter_result["adapter_metadata"]
    recommendation = adapter_result["result"]

    assert adapter_result["source"] == "rubybets_ml_v17_8_feature_adapter"
    assert adapter_result["scope"] == "experimental"
    assert adapter_result["status"] == "adapted"
    assert adapter_metadata["features_status"] == "complete"
    assert adapter_metadata["missing_features"] == []
    assert adapter_metadata["match_id"] == "adapter_demo_match_001"
    assert adapter_metadata["competition_code"] == "PL"
    assert adapter_metadata["base_recommendation_status"] == RECOMMEND_STATUS
    assert adapter_metadata["base_recommendation_type"] == GOALS_OVER_15_TYPE
    assert recommendation["status"] == RECOMMEND_STATUS
    assert recommendation["recommendation_type"] == BTTS_TYPE
    assert recommendation["recommendation_value"] == BTTS_YES_VALUE
    assert recommendation["is_btts"] is True
    assert recommendation["is_replaced_over15"] is True
    assert recommendation["scope"] == "experimental"
    assert recommendation["responsible_note"]


# Verifie que l'adaptateur transforme des donnees preparees completes en recommandation BTTS_YES.
def test_v17_8_adapter_returns_btts_when_prepared_data_is_complete() -> None:
    prepared_match_data = build_complete_prepared_match_data()

    result = adapt_and_recommend_with_v17_8(prepared_match_data)

    assert result["source"] == "rubybets_ml_v17_8_feature_adapter"
    assert result["scope"] == "experimental"
    assert result["status"] == "adapted"

    adapter_metadata = result["adapter_metadata"]
    recommendation = result["result"]

    assert adapter_metadata["features_status"] == "complete"
    assert adapter_metadata["missing_features"] == []
    assert recommendation["status"] == RECOMMEND_STATUS
    assert recommendation["recommendation_type"] == BTTS_TYPE
    assert recommendation["recommendation_value"] == BTTS_YES_VALUE
    assert recommendation["is_replaced_over15"] is True


# Verifie que l'adaptateur signale un etat partial si des features BTTS sont manquantes.
def test_v17_8_adapter_detects_partial_features_when_btts_data_is_missing() -> None:
    prepared_match_data = {
        "match": {
            "id": 538144,
            "competition": {
                "code": "PL",
            },
        },
        "btts_signals": {
            "v17_6_score": 0.61,
        },
        "v17_reference": {
            "status": ABSTAIN_STATUS,
            "type": "ABSTAIN",
            "value": "ABSTAIN",
            "source": "V17_REFERENCE_TEST",
        },
    }

    result = adapt_and_recommend_with_v17_8(prepared_match_data)

    adapter_metadata = result["adapter_metadata"]
    recommendation = result["result"]

    assert adapter_metadata["features_status"] == "partial"
    assert len(adapter_metadata["missing_features"]) > 0
    assert "expected_home_goals_proxy" in adapter_metadata["missing_features"]
    assert recommendation["status"] == ABSTAIN_STATUS
    assert "MISSING_BTTS_FEATURES" in recommendation["reasons"]


# Verifie que l'adaptateur conserve les metadonnees utiles du match et de la recommandation de base.
def test_v17_8_adapter_keeps_match_and_base_recommendation_metadata() -> None:
    btts_features = build_valid_btts_features()
    btts_features["v17_6_score"] = 0.40

    prepared_match_data = {
        "match_id": "match_test_001",
        "competition_code": "F1",
        "features": btts_features,
        "base_recommendation": {
            "status": RECOMMEND_STATUS,
            "type": DOUBLE_CHANCE_TYPE,
            "value": "1X",
            "source": "V17_REFERENCE_BASE_TEST",
        },
    }

    adapted_features = build_v17_8_features_from_prepared_match_data(prepared_match_data)
    result = adapt_and_recommend_with_v17_8(prepared_match_data)

    adapter_metadata = result["adapter_metadata"]
    recommendation = result["result"]

    assert adapted_features["v17_recommendation_type"] == DOUBLE_CHANCE_TYPE
    assert adapted_features["v17_recommendation_value"] == "1X"
    assert adapter_metadata["match_id"] == "match_test_001"
    assert adapter_metadata["competition_code"] == "F1"
    assert adapter_metadata["base_recommendation_status"] == RECOMMEND_STATUS
    assert adapter_metadata["base_recommendation_type"] == DOUBLE_CHANCE_TYPE
    assert recommendation["recommendation_type"] == DOUBLE_CHANCE_TYPE
    assert recommendation["recommendation_value"] == "1X"


# Schema de communication :
# test_ml_v17_8_service.py
#   -> importe backend/app/services/ml_v17_8_service.py
#   -> importe backend/app/services/ml_v17_8_feature_adapter.py
#   -> teste BTTS_YES valide
#   -> teste conservation V17.0 si BTTS est trop faible
#   -> teste abstention si features insuffisantes
#   -> teste la route demo backend/app/api/experimental_ml_v17_8.py
#   -> teste l'adaptation de donnees preparees vers le format V17.8
#   -> prepare la future integration experimentale V17.8 sans modifier le scoring explicable V1
#   -> teste la route adapter-demo backend/app/api/experimental_ml_v17_8.py