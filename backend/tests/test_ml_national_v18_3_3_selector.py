# Role du fichier :
# Ces tests verifient le selecteur national V18.3.3 cote service, API experimentale
# et adaptateur d'inference depuis une ligne de predictions V18.3.

from fastapi.testclient import TestClient

from app.main import app
from app.services.ml_national_v18_3_3_inference_adapter import (
    select_v18_3_3_from_prediction_row,
)
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


# Verifie que la route par match lit le CSV 348 et retourne match + selector_result.
def test_v18_3_3_match_endpoint_returns_existing_csv_match():
    response = client.get("/api/experimental/ml-national/v18-3-3/matches/7789")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "computed"
    assert data["scope"] == "experimental_backend"
    assert data["data_source_file"] == "348_v18_3_global_multimarket_test_predictions.csv"
    assert "match" in data
    assert "selector_result" in data

    assert data["match"]["clean_match_id"] == "7789"
    assert data["match"]["team_a_name"] == "Slovakia"
    assert data["match"]["team_b_name"] == "Malta"
    assert data["match"]["competition_code"] == "WCQ"

    assert data["selector_result"]["status"] in ["RECOMMEND", "ABSTAIN"]
    assert "selected_market" in data["selector_result"]
    assert "responsible_note" in data


# Verifie que la route par match renvoie une erreur claire si le clean_match_id est absent.
def test_v18_3_3_match_endpoint_returns_404_for_unknown_match():
    response = client.get("/api/experimental/ml-national/v18-3-3/matches/999999999")

    assert response.status_code == 404

    data = response.json()
    detail = data["detail"]

    assert detail["status"] == "MATCH_NOT_FOUND"
    assert detail["clean_match_id"] == "999999999"
    assert detail["data_source_file"] == "348_v18_3_global_multimarket_test_predictions.csv"


# Verifie que l'adaptateur transforme une ligne V18.3 complete en selection V18.3.3.
def test_v18_3_3_adapter_computes_from_prediction_row():
    row = {
        "clean_match_id": 1001,
        "feature_id": 9001,
        "feature_version": "v18_3_global_multimarket",
        "match_date_utc": "2026-06-01T18:00:00Z",
        "season": "2026",
        "competition_code": "WC",
        "competition_name": "World Cup",
        "stage": "Group stage",
        "group_name": "Group A",
        "team_a_name": "Team A",
        "team_b_name": "Team B",
        "1x2_prediction": "TEAM_A_WIN",
        "1x2_prob_TEAM_A_WIN": 0.81,
        "1x2_prob_DRAW": 0.11,
        "1x2_prob_TEAM_B_WIN": 0.08,
        "1x2_max_probability": 0.81,
        "over_1_5_prediction": "YES",
        "over_1_5_prob_YES": 0.79,
        "over_1_5_max_probability": 0.79,
        "over_2_5_prediction": "YES",
        "over_2_5_prob_YES": 0.71,
        "over_2_5_prob_NO": 0.29,
        "over_2_5_max_probability": 0.71,
        "btts_prediction": "NO",
        "btts_prob_YES": 0.24,
        "btts_prob_NO": 0.76,
        "btts_max_probability": 0.76,
    }

    result = select_v18_3_3_from_prediction_row(row)

    assert result["status"] == "computed"
    assert result["match"]["clean_match_id"] == 1001
    assert result["match"]["team_a_name"] == "Team A"
    assert result["match"]["team_b_name"] == "Team B"
    assert result["selector_result"]["status"] == "RECOMMEND"
    assert result["selector_result"]["selected_market"] == "STRICT_1X2"


# Verifie que l'adaptateur refuse une ligne incomplete au lieu de produire une fausse selection.
def test_v18_3_3_adapter_rejects_incomplete_prediction_row():
    row = {
        "clean_match_id": 1002,
        "team_a_name": "Team A",
        "team_b_name": "Team B",
    }

    result = select_v18_3_3_from_prediction_row(row)

    assert result["status"] == "INVALID_INPUT"
    assert "missing_columns" in result
    assert "1x2_prediction" in result["missing_columns"]


# Schema de communication :
# test_ml_national_v18_3_3_selector.py
#   -> teste backend/app/services/ml_national_v18_3_3_selector.py
#   -> teste backend/app/services/ml_national_v18_3_3_inference_adapter.py
#   -> teste backend/app/api/experimental_ml_national_v18_3_3.py
#   -> verifie que la route est bien incluse dans backend/app/main.py
#   -> securise le futur branchement API backend sans toucher au frontend