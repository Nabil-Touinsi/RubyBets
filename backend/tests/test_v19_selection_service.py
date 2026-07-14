# Rôle du fichier :
# Ces tests valident la composition responsable des sélections multi-matchs RubyBets V19.

from __future__ import annotations

import asyncio

from app.v19.application.v19_selection_service import (
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
) -> ExpertCandidateV1:
    return ExpertCandidateV1(
        expert_id="test-expert",
        expert_version="test-expert.1",
        market_type=market_type,
        recommendation_value="TEST_VALUE",
        status=ExpertCandidateStatus.ELIGIBLE,
        raw_score=0.81,
        calibrated_probability=None,
        confidence_level=None,
        local_risk_level=None,
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
) -> DecisionResultV1:
    candidate = build_candidate(
        market_type=market_type,
        missing_features=missing_features,
        caution_reasons=caution_reasons,
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
            ("target_match_provider_status", "success"),
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
            1: build_decision(match_id=1),
            2: build_decision(
                match_id=2,
                market_flags="LOW_BOOKMAKER_COVERAGE",
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


# Verifie qu'une alerte non bloquante ne rejette pas automatiquement le profil LOW.
def test_low_profile_accepts_non_blocking_caution_reasons() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                caution_reasons=("NON_BLOCKING_WARNING",),
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


# Vérifie que le profil élevé conserve toute décision officielle RECOMMEND.
def test_high_profile_keeps_recommend_and_never_recovers_abstain() -> None:
    predictor = build_predictor(
        {
            1: build_decision(
                match_id=1,
                market_status="UNAVAILABLE",
                history_status="unavailable",
            ),
            2: build_decision(
                match_id=2,
                status=DecisionStatus.ABSTAIN,
            ),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2],
            match_count=2,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.PARTIAL
    assert [item.match_id for item in result.selections] == [1]
    assert result.abstain_count == 1
    assert result.excluded_matches[0].reason is (
        V19SelectionExclusionReason.ABSTAIN
    )


# Vérifie que l'ordre est conservé et que les identifiants dupliqués sont ignorés.
def test_selection_preserves_order_deduplicates_and_stops_at_count() -> None:
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
    assert result.evaluated_count == 2
    assert [item.match_id for item in result.selections] == [3, 1]


# Vérifie qu'une erreur sur un match ne bloque pas l'ensemble de la sélection.
def test_selection_isolates_pipeline_errors() -> None:
    predictor = build_predictor(
        {
            1: RuntimeError("provider unavailable"),
            2: build_decision(match_id=2),
        }
    )

    result = asyncio.run(
        build_v19_selection(
            match_ids=[1, 2],
            match_count=1,
            selection_profile="HIGH",
            predictor=predictor,
        )
    )

    assert result.status is V19SelectionStatus.READY
    assert result.error_count == 1
    assert result.selections[0].match_id == 2
    assert result.excluded_matches[0].reason is (
        V19SelectionExclusionReason.PIPELINE_ERROR
    )


# Schéma de communication :
# test_v19_selection_service.py
#   -> construit des DecisionResultV1 contrôlés
#   -> injecte un prédicteur sans réseau dans v19_selection_service.py
#   -> vérifie LOW / MEDIUM / HIGH, ABSTAIN, ordre, doublons et erreurs
