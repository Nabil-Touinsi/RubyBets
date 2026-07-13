# Rôle du fichier :
# Ce fichier protège la politique de parité et les contrats de décision finale RubyBets V19.

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from app.v19.application.decision_orchestrator import (
    LEGACY_DECISION_ENGINE_VERSION,
    orchestrate_legacy_decision,
)
from app.v19.domain.decision_contracts import (
    DecisionResultV1,
    RejectedExpertCandidateV1,
)
from app.v19.domain.decision_enums import (
    CandidateRejectionReason,
    DecisionAbstentionReason,
    DecisionStatus,
)
from app.v19.domain.expert_contracts import ExpertCandidateV1
from app.v19.domain.expert_enums import (
    ExpertCandidateStatus,
    ExpertMarketType,
)


# Construit un candidat minimal pour tester l'arbitrage sans dépendre des builders sportifs.
def build_candidate(
    market_type: ExpertMarketType,
    status: ExpertCandidateStatus,
    recommendation_value: str | None,
    *,
    missing_features: tuple[str, ...] = (),
    caution_reasons: tuple[str, ...] = (),
) -> ExpertCandidateV1:
    return ExpertCandidateV1(
        expert_id=f"expert-{market_type.value.lower()}",
        expert_version=f"{market_type.value.lower()}.1",
        market_type=market_type,
        recommendation_value=recommendation_value,
        status=status,
        raw_score=0.80 if status is ExpertCandidateStatus.ELIGIBLE else None,
        calibrated_probability=None,
        confidence_level="high" if status is ExpertCandidateStatus.ELIGIBLE else None,
        local_risk_level="low" if status is ExpertCandidateStatus.ELIGIBLE else None,
        required_features=missing_features,
        missing_features=missing_features,
        positive_reasons=("TEST_ELIGIBLE",) if status is ExpertCandidateStatus.ELIGIBLE else (),
        caution_reasons=caution_reasons,
        quality_requirements=(),
        metadata=(),
    )


# Retourne le motif de rejet associé au marché demandé.
def rejection_reason_for(
    result: DecisionResultV1,
    market_type: ExpertMarketType,
) -> CandidateRejectionReason:
    return next(
        rejected.reason
        for rejected in result.rejected_candidates
        if rejected.candidate.market_type is market_type
    )


# Vérifie les valeurs exactes du vocabulaire de décision V19.
def test_decision_enums_keep_expected_values() -> None:
    assert [status.value for status in DecisionStatus] == ["RECOMMEND", "ABSTAIN"]
    assert [reason.value for reason in CandidateRejectionReason] == [
        "HIGHER_PRIORITY_CANDIDATE_SELECTED",
        "REPLACED_BY_BTTS_POLICY",
        "CANDIDATE_INELIGIBLE",
        "CANDIDATE_ERROR",
    ]


# Vérifie que les contrats de décision sont des dataclasses immuables.
def test_decision_contracts_are_frozen_dataclasses() -> None:
    assert is_dataclass(DecisionResultV1)
    assert DecisionResultV1.__dataclass_params__.frozen is True
    assert is_dataclass(RejectedExpertCandidateV1)
    assert RejectedExpertCandidateV1.__dataclass_params__.frozen is True


# Vérifie que le 1X2 strict conserve la priorité sur tous les autres marchés.
def test_orchestrator_prioritizes_strict_1x2() -> None:
    strict = build_candidate(ExpertMarketType.STRICT_1X2, ExpertCandidateStatus.ELIGIBLE, "HOME_WIN")
    double = build_candidate(ExpertMarketType.DOUBLE_CHANCE, ExpertCandidateStatus.ELIGIBLE, "1X")
    over = build_candidate(ExpertMarketType.OVER_1_5, ExpertCandidateStatus.ELIGIBLE, "OVER_1_5")
    btts = build_candidate(ExpertMarketType.BTTS, ExpertCandidateStatus.ELIGIBLE, "BTTS_YES")

    result = orchestrate_legacy_decision(match_id=123, candidates=(strict, double, over, btts))

    assert result.status is DecisionStatus.RECOMMEND
    assert result.selected_candidate is strict
    assert all(
        rejected.reason is CandidateRejectionReason.HIGHER_PRIORITY_CANDIDATE_SELECTED
        for rejected in result.rejected_candidates
    )


# Vérifie que Double Chance est retenue lorsque le strict est inéligible.
def test_orchestrator_selects_double_chance_after_strict_abstention() -> None:
    strict = build_candidate(
        ExpertMarketType.STRICT_1X2,
        ExpertCandidateStatus.INELIGIBLE,
        None,
        caution_reasons=("STRICT_GATE_FAILED",),
    )
    double = build_candidate(ExpertMarketType.DOUBLE_CHANCE, ExpertCandidateStatus.ELIGIBLE, "X2")
    over = build_candidate(ExpertMarketType.OVER_1_5, ExpertCandidateStatus.ELIGIBLE, "OVER_1_5")

    result = orchestrate_legacy_decision(match_id="match-1", candidates=(strict, double, over))

    assert result.selected_candidate is double
    assert rejection_reason_for(result, ExpertMarketType.STRICT_1X2) is CandidateRejectionReason.CANDIDATE_INELIGIBLE
    assert rejection_reason_for(result, ExpertMarketType.OVER_1_5) is CandidateRejectionReason.HIGHER_PRIORITY_CANDIDATE_SELECTED


# Vérifie qu'Over 1.5 reste la base lorsque BTTS est inéligible.
def test_orchestrator_keeps_over_15_when_btts_is_ineligible() -> None:
    over = build_candidate(ExpertMarketType.OVER_1_5, ExpertCandidateStatus.ELIGIBLE, "OVER_1_5")
    btts = build_candidate(
        ExpertMarketType.BTTS,
        ExpertCandidateStatus.INELIGIBLE,
        None,
        caution_reasons=("BTTS_SCORE_TOO_LOW",),
    )

    result = orchestrate_legacy_decision(match_id=456, candidates=(over, btts))

    assert result.selected_candidate is over
    assert rejection_reason_for(result, ExpertMarketType.BTTS) is CandidateRejectionReason.CANDIDATE_INELIGIBLE


# Vérifie que BTTS remplace Over 1.5 lorsque les deux candidats sont éligibles.
def test_orchestrator_replaces_over_15_with_btts() -> None:
    over = build_candidate(ExpertMarketType.OVER_1_5, ExpertCandidateStatus.ELIGIBLE, "OVER_1_5")
    btts = build_candidate(ExpertMarketType.BTTS, ExpertCandidateStatus.ELIGIBLE, "BTTS_YES")

    result = orchestrate_legacy_decision(match_id=789, candidates=(over, btts))

    assert result.selected_candidate is btts
    assert rejection_reason_for(result, ExpertMarketType.OVER_1_5) is CandidateRejectionReason.REPLACED_BY_BTTS_POLICY


# Vérifie que BTTS peut intervenir en fallback lorsqu'aucune base n'est éligible.
def test_orchestrator_uses_btts_as_fallback() -> None:
    over = build_candidate(
        ExpertMarketType.OVER_1_5,
        ExpertCandidateStatus.INELIGIBLE,
        None,
        caution_reasons=("OVER_15_RATE_BELOW_V15_THRESHOLD",),
    )
    btts = build_candidate(ExpertMarketType.BTTS, ExpertCandidateStatus.ELIGIBLE, "BTTS_YES")

    result = orchestrate_legacy_decision(match_id=999, candidates=(over, btts))

    assert result.selected_candidate is btts
    assert rejection_reason_for(result, ExpertMarketType.OVER_1_5) is CandidateRejectionReason.CANDIDATE_INELIGIBLE


# Vérifie qu'une absence totale de candidat éligible produit une abstention expliquée.
def test_orchestrator_abstains_when_no_candidate_is_eligible() -> None:
    strict = build_candidate(
        ExpertMarketType.STRICT_1X2,
        ExpertCandidateStatus.INELIGIBLE,
        None,
        caution_reasons=("FAVORITE_PROBABILITY_BELOW_THRESHOLD",),
    )
    btts = build_candidate(
        ExpertMarketType.BTTS,
        ExpertCandidateStatus.INELIGIBLE,
        None,
        caution_reasons=("BTTS_RATE_TOO_LOW",),
    )

    result = orchestrate_legacy_decision(match_id=1000, candidates=(strict, btts))

    assert result.status is DecisionStatus.ABSTAIN
    assert result.selected_candidate is None
    assert result.abstention_reasons == (
        DecisionAbstentionReason.NO_ELIGIBLE_CANDIDATE.value,
        "FAVORITE_PROBABILITY_BELOW_THRESHOLD",
        "BTTS_RATE_TOO_LOW",
    )


# Vérifie l'agrégation stable et sans doublon des features manquantes.
def test_orchestrator_aggregates_missing_features() -> None:
    strict = build_candidate(
        ExpertMarketType.STRICT_1X2,
        ExpertCandidateStatus.INELIGIBLE,
        None,
        missing_features=("market_favorite_prob", "market_entropy"),
        caution_reasons=("MISSING_REQUIRED_FEATURES",),
    )
    double = build_candidate(
        ExpertMarketType.DOUBLE_CHANCE,
        ExpertCandidateStatus.INELIGIBLE,
        None,
        missing_features=("market_entropy", "market_top2_sum"),
        caution_reasons=("MISSING_REQUIRED_FEATURES",),
    )

    result = orchestrate_legacy_decision(match_id=1001, candidates=(strict, double))

    assert result.missing_features == (
        "market_favorite_prob",
        "market_entropy",
        "market_top2_sum",
    )


# Vérifie qu'un candidat en erreur reste traçable sans bloquer une recommandation valide.
def test_orchestrator_records_error_candidate_without_blocking_selection() -> None:
    strict_error = build_candidate(
        ExpertMarketType.STRICT_1X2,
        ExpertCandidateStatus.ERROR,
        None,
        caution_reasons=("STRICT_EXPERT_ERROR",),
    )
    over = build_candidate(ExpertMarketType.OVER_1_5, ExpertCandidateStatus.ELIGIBLE, "OVER_1_5")

    result = orchestrate_legacy_decision(match_id=1002, candidates=(strict_error, over))

    assert result.selected_candidate is over
    assert rejection_reason_for(result, ExpertMarketType.STRICT_1X2) is CandidateRejectionReason.CANDIDATE_ERROR


# Vérifie la conservation des versions moteur, experts, features et métadonnées.
def test_orchestrator_preserves_version_traceability() -> None:
    over = build_candidate(ExpertMarketType.OVER_1_5, ExpertCandidateStatus.ELIGIBLE, "OVER_1_5")

    result = orchestrate_legacy_decision(
        match_id=1003,
        candidates=(over,),
        feature_versions=("v19.market.core.1", "v19.team.legacy.1"),
        metadata=(("policy_mode", "LEGACY_PARITY"),),
    )

    assert result.engine_version == LEGACY_DECISION_ENGINE_VERSION
    assert result.expert_versions == ((over.expert_id, over.expert_version),)
    assert result.feature_versions == ("v19.market.core.1", "v19.team.legacy.1")
    assert result.metadata == (("policy_mode", "LEGACY_PARITY"),)
    assert result.match_id == "1003"


# Vérifie que le résultat final refuse toute mutation après sa création.
def test_decision_result_is_immutable() -> None:
    over = build_candidate(ExpertMarketType.OVER_1_5, ExpertCandidateStatus.ELIGIBLE, "OVER_1_5")
    result = orchestrate_legacy_decision(match_id=1004, candidates=(over,))

    with pytest.raises(FrozenInstanceError):
        setattr(result, "status", DecisionStatus.ABSTAIN)


# Vérifie que le contrat refuse un résultat RECOMMEND sans candidat sélectionné.
def test_decision_result_rejects_inconsistent_recommend_state() -> None:
    with pytest.raises(ValueError, match="RECOMMEND requires"):
        DecisionResultV1(
            match_id="1005",
            status=DecisionStatus.RECOMMEND,
            selected_candidate=None,
            evaluated_candidates=(),
            rejected_candidates=(),
            missing_features=(),
            abstention_reasons=(),
            engine_version=LEGACY_DECISION_ENGINE_VERSION,
            expert_versions=(),
            feature_versions=(),
            metadata=(),
        )


# Schéma de communication :
# test_v19_decision_orchestrator.py
#   -> valide decision_enums.py, decision_contracts.py et decision_orchestrator.py
#   -> protège la priorité V13.1 / V15 / V17 / V17.8 et les motifs de rejet
#   -> ne dépend d'aucune API externe, base de données ou donnée sportive réelle
