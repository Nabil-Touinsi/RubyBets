# Role du fichier :
# Ces tests verifient le selecteur national V18.3.3 cote service et cote API experimentale.
# Ils securisent STRICT_1X2, OVER_1_5, DOUBLE_CHANCE, ABSTAIN et les routes FastAPI.

from fastapi.testclient import TestClient

from app.main import app
from app.services.ml_national_v18_3_3_selector import (
    ABSTAIN_STATUS,
    DOUBLE_CHANCE_MARKET,
    OVER_1_5_MARKET,
    RECOMMEND_STATUS,
    STRICT_1X2_MARKET,
    select_market_with_v18_3_3,
)


client = TestClient(app)


# Verifie que le selecteur choisit STRICT_1X2 quand la confiance 1X2 est suffisante.
def test_v18_3_3_selects_strict_1x2_when_confidence_is_high():
    features = {
        "1x2_prediction": "TEAM_A_WIN",
        "1x2_max_probability": 0.81,
        "1x2_prob_TEAM_A_WIN": 0.81,
        "1x2_prob_DRAW": 0.11,
        "1x2_prob_TEAM_B_WIN": 0.08,
    }

    result = select_market_with_v18_3_3(features)

    assert result["status"] == RECOMMEND_STATUS
    assert result["selected_market"] == STRICT_1X2_MARKET
    assert result["selected_prediction"] == "TEAM_A_WIN"
    assert result["selected_confidence"] == 0.81


# Verifie que le selecteur passe a OVER_1_5 si STRICT_1X2 ne respecte pas le seuil.
def test_v18_3_3_selects_over_1_5_when_1x2_is_not_strong_enough():
    features = {
        "1x2_prediction": "TEAM_A_WIN",
        "1x2_max_probability": 0.70,
        "over_1_5_prediction": "YES",
        "over_1_5_prob_YES": 0.80,
        "1x2_prob_TEAM_A_WIN": 0.70,
        "1x2_prob_DRAW": 0.18,
        "1x2_prob_TEAM_B_WIN": 0.12,
    }

    result = select_market_with_v18_3_3(features)

    assert result["status"] == RECOMMEND_STATUS
    assert result["selected_market"] == OVER_1_5_MARKET
    assert result["selected_prediction"] == "YES"
    assert result["selected_confidence"] == 0.80


# Verifie que DOUBLE_CHANCE est derivee du 1X2 quand les marches directs echouent.
def test_v18_3_3_selects_double_chance_from_1x2_probabilities():
    features = {
        "1x2_prediction": "TEAM_A_WIN",
        "1x2_max_probability": 0.70,
        "over_1_5_prediction": "NO",
        "over_1_5_prob_YES": 0.40,
        "over_2_5_prediction": "UNDER",
        "over_2_5_max_probability": 0.60,
        "btts_prediction": "YES",
        "btts_prob_NO": 0.30,
        "1x2_prob_TEAM_A_WIN": 0.45,
        "1x2_prob_DRAW": 0.42,
        "1x2_prob_TEAM_B_WIN": 0.13,
    }

    result = select_market_with_v18_3_3(features)

    assert result["status"] == RECOMMEND_STATUS
    assert result["selected_market"] == DOUBLE_CHANCE_MARKET
    assert result["selected_prediction"] == "TEAM_A_OR_DRAW"
    assert result["excluded_outcome"] == "TEAM_B_WIN"


# Verifie que le selecteur s'abstient quand aucun signal ne passe les seuils.
def test_v18_3_3_abstains_when_no_signal_is_strong_enough():
    features = {
        "1x2_prediction": "DRAW",
        "1x2_max_probability": 0.40,
        "over_1_5_prediction": "NO",
        "over_1_5_prob_YES": 0.45,
        "over_2_5_prediction": "OVER",
        "over_2_5_max_probability": 0.55,
        "btts_prediction": "YES",
        "btts_prob_NO": 0.35,
        "1x2_prob_TEAM_A_WIN": 0.36,
        "1x2_prob_DRAW": 0.34,
        "1x2_prob_TEAM_B_WIN": 0.30,
    }

    result = select_market_with_v18_3_3(features)

    assert result["status"] == ABSTAIN_STATUS
    assert result["selected_market"] == "ABSTAIN"
    assert result["selected_confidence"] is None


# Verifie que le endpoint status du selecteur V18.3.3 est disponible.
def test_v18_3_3_status_endpoint_is_available():
    response = client.get("/api/experimental/ml-national/v18-3-3/status")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "available"
    assert data["selector_version"] == "v18.3.3"
    assert data["selector_profile"] == "strict_reliability"
    assert data["scope"] == "experimental_backend"


# Verifie que la demo controlee retourne une recommandation STRICT_1X2.
def test_v18_3_3_demo_endpoint_returns_controlled_result():
    response = client.get("/api/experimental/ml-national/v18-3-3/demo")

    assert response.status_code == 200

    data = response.json()
    result = data["result"]

    assert data["status"] == "demo_only"
    assert result["status"] == "RECOMMEND"
    assert result["selected_market"] == "STRICT_1X2"
    assert result["selector_version"] == "v18.3.3"


# Verifie que le endpoint select applique le selecteur sur un payload manuel.
def test_v18_3_3_select_endpoint_computes_manual_payload():
    payload = {
        "one_x_two_prediction": "TEAM_A_WIN",
        "one_x_two_max_probability": 0.70,
        "one_x_two_prob_team_a_win": 0.45,
        "one_x_two_prob_draw": 0.42,
        "one_x_two_prob_team_b_win": 0.13,
        "over_1_5_prediction": "NO",
        "over_1_5_prob_yes": 0.40,
        "over_2_5_prediction": "UNDER",
        "over_2_5_max_probability": 0.60,
        "btts_prediction": "YES",
        "btts_prob_no": 0.30,
    }

    response = client.post(
        "/api/experimental/ml-national/v18-3-3/select",
        json=payload,
    )

    assert response.status_code == 200

    data = response.json()
    result = data["result"]

    assert data["status"] == "computed"
    assert result["status"] == "RECOMMEND"
    assert result["selected_market"] == "DOUBLE_CHANCE"
    assert result["selected_prediction"] == "TEAM_A_OR_DRAW"
    assert result["excluded_outcome"] == "TEAM_B_WIN"


# Schema de communication :
# test_ml_national_v18_3_3_selector.py
#   -> teste backend/app/services/ml_national_v18_3_3_selector.py
#   -> teste backend/app/api/experimental_ml_national_v18_3_3.py
#   -> verifie que la route est bien incluse dans backend/app/main.py
#   -> securise le futur branchement API backend sans toucher au frontend
