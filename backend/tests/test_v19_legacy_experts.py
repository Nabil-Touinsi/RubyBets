# Rôle du fichier :
# Ce fichier vérifie la parité des règles V15/V17.8 encapsulées dans les candidats experts RubyBets V19.

from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)
from app.v19.experts.legacy_adapters import (
    build_legacy_expert_candidates,
    build_legacy_expert_features,
)
from app.v19.experts.legacy_btts import build_legacy_btts_candidate
from app.v19.experts.legacy_over_15 import build_legacy_over_15_candidate


# Construit un jeu de features qui satisfait exactement les seuils BTTS V17.8.
def build_btts_features_at_thresholds() -> dict[str, float | int]:
    return {
        "v17_6_score": 0.52,
        "min_history_count_last_10": 8,
        "expected_home_goals_proxy": 0.90,
        "expected_away_goals_proxy": 0.90,
        "expected_total_goals_proxy": 1.80,
        "combined_btts_rate_last_10": 0.55,
        "combined_over_1_5_rate_last_10": 0.50,
        "home_failed_to_score_rate_last_10": 0.45,
        "away_failed_to_score_rate_last_10": 0.45,
    }


# Construit un historique de dix matchs favorables aux marchés Over 1.5 et BTTS.
def build_team_history_response(match_count: int = 10) -> dict[str, object]:
    recent_matches = [
        {
            "goals_for": 2,
            "goals_against": 1,
        }
        for _ in range(match_count)
    ]

    return {
        "match_id": 1813105023365578,
        "source_used": "flashscore",
        "data_status": "complete",
        "home_team_history": {
            "team_name": "Home FC",
            "recent_matches": recent_matches,
        },
        "away_team_history": {
            "team_name": "Away FC",
            "recent_matches": recent_matches,
        },
        "head_to_head": [],
    }


# Vérifie qu'un taux de 0,80 avec dix matchs produit un candidat Over 1.5 éligible.
def test_legacy_over_15_candidate_is_eligible_at_exact_thresholds() -> None:
    candidate = build_legacy_over_15_candidate(
        {
            "combined_over_15_rate_last10": 0.80,
            "min_history_count_last10": 10,
        }
    )

    assert candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert candidate.market_type is ExpertMarketType.OVER_1_5
    assert candidate.recommendation_value == "OVER_1_5"
    assert candidate.raw_score == 0.80
    assert candidate.calibrated_probability is None
    assert candidate.confidence_level == "medium"
    assert candidate.local_risk_level == "medium"


# Vérifie que la politique V15 refuse un taux Over 1.5 inférieur à 0,80.
def test_legacy_over_15_candidate_rejects_low_rate() -> None:
    candidate = build_legacy_over_15_candidate(
        {
            "combined_over_15_rate_last10": 0.79,
            "min_history_count_last10": 10,
        }
    )

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert candidate.recommendation_value is None
    assert "OVER_15_RATE_BELOW_V15_THRESHOLD" in candidate.caution_reasons


# Vérifie que la politique V15 refuse une profondeur inférieure à dix matchs.
def test_legacy_over_15_candidate_rejects_low_history() -> None:
    candidate = build_legacy_over_15_candidate(
        {
            "combined_over_15_rate_last10": 0.90,
            "min_history_count_last10": 9,
        }
    )

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert "HISTORY_DEPTH_BELOW_V15_MINIMUM" in candidate.caution_reasons


# Vérifie que les features V15 absentes sont déclarées dans le contrat.
def test_legacy_over_15_candidate_reports_missing_features() -> None:
    candidate = build_legacy_over_15_candidate({})

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert candidate.missing_features == (
        "combined_over_15_rate_last10",
        "min_history_count_last10",
    )
    assert candidate.caution_reasons == ("MISSING_REQUIRED_FEATURES",)


# Vérifie que les seuils exacts V17.8 rendent le candidat BTTS éligible.
def test_legacy_btts_candidate_is_eligible_at_exact_thresholds() -> None:
    candidate = build_legacy_btts_candidate(build_btts_features_at_thresholds())

    assert candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert candidate.market_type is ExpertMarketType.BTTS
    assert candidate.recommendation_value == "BTTS_YES"
    assert candidate.raw_score == 0.52
    assert candidate.calibrated_probability is None
    assert candidate.confidence_level == "medium"
    assert candidate.local_risk_level == "high"
    assert candidate.positive_reasons == ("BTTS_V17_8_GATES_PASSED",)


# Vérifie que les raisons de rejet proviennent directement des gates V17.8.
def test_legacy_btts_candidate_preserves_v17_8_rejection_reasons() -> None:
    features = build_btts_features_at_thresholds()
    features["combined_btts_rate_last_10"] = 0.54
    features["home_failed_to_score_rate_last_10"] = 0.46

    candidate = build_legacy_btts_candidate(features)

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert candidate.caution_reasons == (
        "BTTS_RATE_TOO_LOW",
        "HOME_FAILED_TO_SCORE_RATE_TOO_HIGH",
    )


# Vérifie que les features BTTS absentes restent visibles pour l'orchestrateur futur.
def test_legacy_btts_candidate_reports_missing_features() -> None:
    candidate = build_legacy_btts_candidate({})

    assert candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert len(candidate.missing_features) == 9
    assert candidate.caution_reasons == ("MISSING_BTTS_FEATURES",)


# Vérifie que l'expert BTTS reste local et ne tranche pas selon un candidat 1X2 externe.
def test_legacy_btts_candidate_does_not_orchestrate_other_markets() -> None:
    features = build_btts_features_at_thresholds()
    features.update(
        {
            "v17_recommendation_status": "RECOMMEND",
            "v17_recommendation_type": "STRICT_1X2",
        }
    )

    candidate = build_legacy_btts_candidate(features)

    assert candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert ("selection_mode", "replace_over15_or_fallback") in candidate.quality_requirements


# Vérifie que l'adapter produit les aliases V15 sans modifier les noms V17.8.
def test_legacy_adapter_builds_v15_and_v17_8_feature_names() -> None:
    features = build_legacy_expert_features(build_team_history_response())

    assert features["combined_over_15_rate_last10"] == 1.0
    assert features["combined_over_1_5_rate_last_10"] == 1.0
    assert features["min_history_count_last10"] == 10
    assert features["min_history_count_last_10"] == 10
    assert features["legacy_zero_defaults_used"] is False


# Vérifie qu'une réponse team-history réelle produit deux candidats indépendants éligibles.
def test_legacy_adapter_builds_over_15_and_btts_candidates() -> None:
    over_candidate, btts_candidate = build_legacy_expert_candidates(
        build_team_history_response()
    )

    assert over_candidate.market_type is ExpertMarketType.OVER_1_5
    assert btts_candidate.market_type is ExpertMarketType.BTTS
    assert over_candidate.status is ExpertCandidateStatus.ELIGIBLE
    assert btts_candidate.status is ExpertCandidateStatus.ELIGIBLE


# Vérifie qu'un historique trop court conduit les deux experts à s'abstenir localement.
def test_legacy_adapter_rejects_insufficient_history() -> None:
    over_candidate, btts_candidate = build_legacy_expert_candidates(
        build_team_history_response(match_count=7)
    )

    assert over_candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert btts_candidate.status is ExpertCandidateStatus.INELIGIBLE
    assert "HISTORY_DEPTH_BELOW_V15_MINIMUM" in over_candidate.caution_reasons
    assert "HISTORY_TOO_LOW" in btts_candidate.caution_reasons


# Vérifie que l'adapter refuse un payload qui n'est pas un dictionnaire team-history.
def test_legacy_adapter_rejects_invalid_payload_type() -> None:
    try:
        build_legacy_expert_features([])  # type: ignore[arg-type]
    except TypeError as error:
        assert str(error) == "team_history_response must be a dict"
    else:
        raise AssertionError("TypeError attendu pour un payload invalide")


# Schéma de communication :
# test_v19_legacy_experts.py
#   -> teste legacy_adapters.py, legacy_over_15.py et legacy_btts.py
#   -> réutilise les seuils historiques exacts V15/V17.8
#   -> protège le contrat ExpertCandidateV1 avant l'ajout de l'orchestrateur
