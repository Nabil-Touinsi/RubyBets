# Rôle du fichier :
# Ces tests protègent le vocabulaire et le contrat commun des candidats experts V19.

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


# Construit un candidat expert synthétique complet pour les tests de contrat.
def build_eligible_expert_candidate() -> ExpertCandidateV1:
    return ExpertCandidateV1(
        expert_id="expert-test-strict-1x2",
        expert_version="v19.expert.test.1",
        market_type=ExpertMarketType.STRICT_1X2,
        recommendation_value="HOME_WIN",
        status=ExpertCandidateStatus.ELIGIBLE,
        raw_score=0.8,
        calibrated_probability=None,
        confidence_level="high",
        local_risk_level="low",
        required_features=("market_home_prob_avg", "market_entropy"),
        missing_features=(),
        positive_reasons=("TEST_SIGNAL_AVAILABLE",),
        caution_reasons=(),
        quality_requirements=(("market_snapshot_available", True),),
        metadata=(("policy_mode", "TEST"),),
    )


# Vérifie que le contrat commun est une dataclass immuable.
def test_v19_expert_candidate_is_a_frozen_dataclass() -> None:
    assert is_dataclass(ExpertCandidateV1)
    assert ExpertCandidateV1.__dataclass_params__.frozen is True


# Vérifie les valeurs exactes du vocabulaire contrôlé des experts V19.
def test_v19_expert_enums_keep_expected_values() -> None:
    assert [status.value for status in ExpertCandidateStatus] == [
        "ELIGIBLE",
        "INELIGIBLE",
        "ERROR",
    ]
    assert [market.value for market in ExpertMarketType] == [
        "STRICT_1X2",
        "DOUBLE_CHANCE",
        "OVER_1_5",
        "BTTS",
    ]


# Vérifie qu'un candidat éligible conserve toutes ses informations standardisées.
def test_v19_eligible_expert_candidate_can_be_composed() -> None:
    candidate = build_eligible_expert_candidate()

    assert candidate.expert_id == "expert-test-strict-1x2"
    assert candidate.market_type == ExpertMarketType.STRICT_1X2
    assert candidate.recommendation_value == "HOME_WIN"
    assert candidate.status == ExpertCandidateStatus.ELIGIBLE
    assert candidate.required_features == (
        "market_home_prob_avg",
        "market_entropy",
    )
    assert candidate.quality_requirements == (
        ("market_snapshot_available", True),
    )


# Vérifie qu'un candidat inéligible peut déclarer ses features manquantes.
def test_v19_ineligible_expert_candidate_preserves_missing_features() -> None:
    candidate = ExpertCandidateV1(
        expert_id="expert-test-over-15",
        expert_version="v19.expert.test.1",
        market_type=ExpertMarketType.OVER_1_5,
        recommendation_value=None,
        status=ExpertCandidateStatus.INELIGIBLE,
        raw_score=None,
        calibrated_probability=None,
        confidence_level=None,
        local_risk_level=None,
        required_features=("combined_over_15_rate_last10",),
        missing_features=("combined_over_15_rate_last10",),
        positive_reasons=(),
        caution_reasons=("TEST_FEATURE_MISSING",),
        quality_requirements=(),
        metadata=(),
    )

    assert candidate.status == ExpertCandidateStatus.INELIGIBLE
    assert candidate.recommendation_value is None
    assert candidate.missing_features == (
        "combined_over_15_rate_last10",
    )
    assert candidate.caution_reasons == ("TEST_FEATURE_MISSING",)


# Vérifie qu'un expert peut signaler une erreur sans inventer de recommandation.
def test_v19_error_expert_candidate_can_be_composed() -> None:
    candidate = ExpertCandidateV1(
        expert_id="expert-test-btts",
        expert_version="v19.expert.test.1",
        market_type=ExpertMarketType.BTTS,
        recommendation_value=None,
        status=ExpertCandidateStatus.ERROR,
        raw_score=None,
        calibrated_probability=None,
        confidence_level=None,
        local_risk_level=None,
        required_features=(),
        missing_features=(),
        positive_reasons=(),
        caution_reasons=("TEST_EXPERT_ERROR",),
        quality_requirements=(),
        metadata=(("error_code", "TEST_ERROR"),),
    )

    assert candidate.status == ExpertCandidateStatus.ERROR
    assert candidate.recommendation_value is None
    assert candidate.metadata == (("error_code", "TEST_ERROR"),)


# Vérifie que le candidat refuse toute mutation après sa création.
def test_v19_expert_candidate_is_immutable() -> None:
    candidate = build_eligible_expert_candidate()

    with pytest.raises(FrozenInstanceError):
        setattr(candidate, "status", ExpertCandidateStatus.INELIGIBLE)


# Vérifie que les collections mutables sont refusées par le contrat.
def test_v19_expert_candidate_rejects_mutable_collections() -> None:
    with pytest.raises(TypeError, match="required_features must be a tuple"):
        ExpertCandidateV1(
            expert_id="expert-test-double-chance",
            expert_version="v19.expert.test.1",
            market_type=ExpertMarketType.DOUBLE_CHANCE,
            recommendation_value=None,
            status=ExpertCandidateStatus.INELIGIBLE,
            raw_score=None,
            calibrated_probability=None,
            confidence_level=None,
            local_risk_level=None,
            required_features=["market_top2_sum"],  # type: ignore[arg-type]
            missing_features=(),
            positive_reasons=(),
            caution_reasons=(),
            quality_requirements=(),
            metadata=(),
        )


# Schéma de communication :
# test_v19_expert_contracts.py
#   -> valide expert_enums.py et expert_contracts.py
#   -> protège le futur branchement des experts et de l'orchestrateur V19
#   -> ne dépend d'aucune API externe ni d'aucune donnée sportive réelle
