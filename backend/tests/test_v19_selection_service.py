# Rôle du fichier :
# Ces tests valident la composition responsable et différenciée des sélections multi-matchs RubyBets V19.

from __future__ import annotations

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