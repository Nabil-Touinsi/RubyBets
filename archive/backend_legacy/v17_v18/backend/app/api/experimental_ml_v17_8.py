# Role du fichier :
# Cette route expose des demonstrations controlees du selecteur experimental V17.8 sans modifier le scoring explicable V1.

from typing import Any

from fastapi import APIRouter

from app.services.ml_v17_8_feature_adapter import adapt_and_recommend_with_v17_8
from app.services.ml_v17_8_service import (
    GOALS_OVER_15_TYPE,
    RECOMMEND_STATUS,
    recommend_with_v17_8,
)


router = APIRouter(
    prefix="/api/experimental/ml/v17-8",
    tags=["Experimental ML V17.8"],
)


# Construit un exemple controle de features favorables pour tester V17.8 sans utiliser les matchs reels.
def build_v17_8_demo_features() -> dict[str, Any]:
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
        "v17_recommendation_status": RECOMMEND_STATUS,
        "v17_recommendation_type": GOALS_OVER_15_TYPE,
        "v17_recommendation_value": "OVER_1_5",
        "v17_source": "V17_REFERENCE_BASE_DEMO",
    }


# Construit des donnees match preparees pour tester le flux adaptateur -> service sans utiliser les vrais matchs RubyBets.
def build_v17_8_adapter_demo_prepared_match_data() -> dict[str, Any]:
    return {
        "match": {
            "id": "adapter_demo_match_001",
            "competition": {
                "code": "PL",
            },
            "home_team": {
                "name": "Ruby FC",
            },
            "away_team": {
                "name": "Bets United",
            },
        },
        "btts_signals": {
            "v17_6_score": 0.61,
            "min_history_count_last_10": 10,
            "expected_home_goals_proxy": 1.25,
            "expected_away_goals_proxy": 1.10,
            "expected_total_goals_proxy": 2.35,
            "combined_btts_rate_last_10": 0.62,
            "combined_over_1_5_rate_last_10": 0.72,
            "home_failed_to_score_rate_last_10": 0.30,
            "away_failed_to_score_rate_last_10": 0.35,
        },
        "v17_reference": {
            "status": RECOMMEND_STATUS,
            "type": GOALS_OVER_15_TYPE,
            "value": "OVER_1_5",
            "source": "V17_REFERENCE_ADAPTER_DEMO",
        },
    }


# Expose une demonstration controlee de V17.8 pour valider le format API avant tout branchement produit.
@router.get("/demo")
async def get_v17_8_demo_recommendation() -> dict[str, Any]:
    demo_features = build_v17_8_demo_features()
    recommendation = recommend_with_v17_8(demo_features)

    return {
        "source": "rubybets_ml_v17_8_api",
        "scope": "experimental",
        "status": "demo_only",
        "message": "Demo controlee du selecteur V17.8. Cette route ne remplace pas le scoring explicable V1 et n'utilise pas encore les matchs reels.",
        "demo_features_profile": "controlled_btts_yes_case",
        "result": recommendation,
    }


# Expose une demonstration controlee du flux donnees preparees -> adaptateur V17.8 -> service V17.8.
@router.get("/adapter-demo")
async def get_v17_8_adapter_demo_recommendation() -> dict[str, Any]:
    prepared_match_data = build_v17_8_adapter_demo_prepared_match_data()
    adapter_result = adapt_and_recommend_with_v17_8(prepared_match_data)

    return {
        "source": "rubybets_ml_v17_8_api",
        "scope": "experimental",
        "status": "adapter_demo_only",
        "message": "Demo controlee du flux adaptateur V17.8. Cette route ne remplace pas le scoring explicable V1 et n'utilise pas encore les matchs reels.",
        "demo_features_profile": "controlled_adapter_btts_yes_case",
        "flow": [
            "prepared_match_data",
            "ml_v17_8_feature_adapter.py",
            "ml_v17_8_service.py",
        ],
        "result": adapter_result,
    }


# Schema de communication :
# experimental_ml_v17_8.py
#   -> construit un jeu de features demo controle pour /demo
#   -> construit des donnees match preparees demo pour /adapter-demo
#   -> appelle backend/app/services/ml_v17_8_feature_adapter.py pour tester le flux d'adaptation
#   -> appelle backend/app/services/ml_v17_8_service.py pour produire recommandation ou abstention
#   -> retourne une recommandation experimentale V17.8
#   -> reste separe des routes officielles /predictions, du frontend, de PostgreSQL, de ml.features et du scoring V1