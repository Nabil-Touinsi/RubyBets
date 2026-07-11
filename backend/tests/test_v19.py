# Role du fichier :
# Ces tests protegent les enums et les contrats immuables du domaine RubyBets V19.

from dataclasses import FrozenInstanceError, is_dataclass
from datetime import datetime, timezone

import pytest

from app.v19.domain.h2h_contracts import (
    CompetitionContextV1,
    H2HAcquisitionContextV1,
    H2HConsumerReadinessV1,
    H2HFeatureValueV1,
    H2HMeetingSelectionSummaryV1,
    H2HMeetingV1,
    H2HModuleInputV1,
    H2HModuleIssueV1,
    H2HModuleResultV1,
    H2HProcessingPolicyV1,
    H2HQualityReportV1,
    H2HResultProvenanceV1,
    IdentityResolutionV1,
    ScoreContextV1,
    SourceProvenanceV1,
    TargetMatchRefV1,
    TargetTeamsV1,
    TeamIdentityV1,
    TieContextV1,
    VenueContextV1,
)
from app.v19.domain.h2h_enums import (
    H2HCacheState,
    H2HCompetitionCategory,
    H2HConsumerId,
    H2HConsumerReadinessStatus,
    H2HDomainProfile,
    H2HEntityType,
    H2HFeatureDataType,
    H2HFeatureUnit,
    H2HIdentityMethod,
    H2HIdentityStatus,
    H2HIssueCode,
    H2HLegNumber,
    H2HModuleOutcome,
    H2HModuleStatus,
    H2HNormalizationState,
    H2HOfficialStatus,
    H2HProvider,
    H2HProviderResultStatus,
    H2HQualityFlag,
    H2HQualityLevel,
    H2HScoreReliability,
    H2HScoreType,
    H2HTieFormat,
    H2HTriState,
)


V19_DOMAIN_CONTRACTS = (
    IdentityResolutionV1,
    TeamIdentityV1,
    TargetTeamsV1,
    CompetitionContextV1,
    VenueContextV1,
    ScoreContextV1,
    TieContextV1,
    SourceProvenanceV1,
    TargetMatchRefV1,
    H2HMeetingV1,
    H2HAcquisitionContextV1,
    H2HProcessingPolicyV1,
    H2HModuleInputV1,
    H2HModuleIssueV1,
    H2HFeatureValueV1,
    H2HMeetingSelectionSummaryV1,
    H2HQualityReportV1,
    H2HConsumerReadinessV1,
    H2HResultProvenanceV1,
    H2HModuleResultV1,
)


# Construit une identite d'equipe synthetique et resolue pour les tests V19.
def build_team_identity(
    canonical_team_id: str,
    provider_team_id: str,
    display_name: str,
) -> TeamIdentityV1:
    identity_resolution = IdentityResolutionV1(
        status=H2HIdentityStatus.RESOLVED,
        method=H2HIdentityMethod.PROVIDER_ID_EXACT,
        confidence_score=1.0,
        resolver_version="v19.identity.test",
        evidence=(("provider_id", provider_team_id),),
    )

    return TeamIdentityV1(
        canonical_team_id=canonical_team_id,
        entity_type=H2HEntityType.CLUB,
        provider_ids=((H2HProvider.FLASHSCORE, provider_team_id),),
        display_name=display_name,
        normalized_name=display_name.lower().replace(" ", "-"),
        country_code=None,
        identity_resolution=identity_resolution,
    )


# Construit un contexte de competition synthetique partage par les contrats de test.
def build_competition_context() -> CompetitionContextV1:
    return CompetitionContextV1(
        canonical_competition_id="competition-test",
        provider_competition_ids=(
            (H2HProvider.FLASHSCORE, "competition-provider-test"),
        ),
        name="Competition Test",
        domain=H2HEntityType.CLUB,
        category=H2HCompetitionCategory.DOMESTIC_LEAGUE,
        season="test-season",
        phase=None,
        round=None,
        official_status=H2HOfficialStatus.OFFICIAL,
    )


# Construit un contrat racine H2HModuleInputV1 complet avec des donnees synthetiques.
def build_h2h_module_input() -> H2HModuleInputV1:
    home_team = build_team_identity(
        canonical_team_id="home-team-test",
        provider_team_id="home-provider-test",
        display_name="Home Team Test",
    )
    away_team = build_team_identity(
        canonical_team_id="away-team-test",
        provider_team_id="away-provider-test",
        display_name="Away Team Test",
    )
    competition = build_competition_context()
    venue_context = VenueContextV1(
        neutral_ground=H2HTriState.FALSE,
        venue_name=None,
        venue_country=None,
        source_reliability=H2HQualityLevel.GOOD,
    )
    tie_context = TieContextV1(
        format=H2HTieFormat.SINGLE_MATCH,
        tie_id=None,
        leg_number=H2HLegNumber.UNKNOWN,
        aggregate_score_before=None,
        aggregate_score_after=None,
        detection_method="test-single-match",
    )
    target_match = TargetMatchRefV1(
        canonical_match_id="target-match-test",
        provider_match_ids=(
            (H2HProvider.FLASHSCORE, "target-provider-test"),
        ),
        kickoff_utc=datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc),
        cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
        domain=H2HEntityType.CLUB,
        competition=competition,
        venue_context=venue_context,
        tie_context=tie_context,
        match_status=("SCHEDULED", "SCHEDULED"),
    )
    source_provenance = SourceProvenanceV1(
        provider=H2HProvider.FLASHSCORE,
        endpoint="/test/h2h",
        provider_match_id="meeting-provider-test",
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
        source_priority=1,
        fallback_used=False,
        cache_state=H2HCacheState.MISS,
        raw_payload_hash="payload-hash-test",
        normalization_version="v19.h2h.normalization.test",
    )
    candidate_meeting = H2HMeetingV1(
        canonical_match_id="meeting-test-001",
        provider_match_ids=(
            (H2HProvider.FLASHSCORE, "meeting-provider-test"),
        ),
        kickoff_utc=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc),
        status=("FINISHED", "FINISHED"),
        competition=competition,
        home_team=home_team,
        away_team=away_team,
        venue_context=venue_context,
        score_context=ScoreContextV1(
            score_type=H2HScoreType.REGULATION_90,
            regulation_time=(2, 1),
            extra_time=None,
            penalties=None,
            displayed_final_score=(2, 1),
            score_reliability=H2HScoreReliability.RELIABLE,
        ),
        tie_context=tie_context,
        provenance=(source_provenance,),
        mapping_quality=H2HQualityLevel.GOOD,
        normalization_state=H2HNormalizationState.VALID,
        exclusion_reasons=(),
    )
    acquisition_context = H2HAcquisitionContextV1(
        primary_provider=H2HProvider.FLASHSCORE,
        providers_attempted=(H2HProvider.FLASHSCORE,),
        provider_results=(
            (H2HProvider.FLASHSCORE, H2HProviderResultStatus.AVAILABLE),
        ),
        fallback_used=False,
        assembled_from_cache=False,
        earliest_retrieved_at_utc=source_provenance.retrieved_at_utc,
        latest_retrieved_at_utc=source_provenance.retrieved_at_utc,
        warnings=(),
    )
    processing_policy = H2HProcessingPolicyV1(
        policy_version="v19.h2h.policy.test",
        domain_profile=H2HDomainProfile.CLUB_H2H_V1,
        temporal_policy=(("strict_cutoff", True),),
        exclusion_policy=(("exclude_club_friendlies", True),),
        deduplication_policy=(("provider_priority", "FLASHSCORE"),),
        identity_policy=(("require_resolved_identity", True),),
    )

    return H2HModuleInputV1(
        contract_version="H2HModuleInputV1",
        request_id="request-test-001",
        assembled_at_utc=datetime(2026, 7, 12, 16, 5, tzinfo=timezone.utc),
        target_match=target_match,
        target_teams=TargetTeamsV1(
            home_team=home_team,
            away_team=away_team,
        ),
        candidate_meetings=(candidate_meeting,),
        acquisition_context=acquisition_context,
        processing_policy=processing_policy,
    )


# Construit un contrat racine H2HModuleResultV1 complet avec une feature synthetique.
def build_h2h_module_result() -> H2HModuleResultV1:
    feature = H2HFeatureValueV1(
        name="h2h_btts_rate",
        value=0.5,
        data_type=H2HFeatureDataType.FLOAT,
        unit=H2HFeatureUnit.RATE,
        feature_version="v19.h2h.feature.test",
        meeting_count_used=1,
        source_meeting_ids=("meeting-test-001",),
        missing_state=None,
        quality_flags=(),
    )
    selection_summary = H2HMeetingSelectionSummaryV1(
        domain_profile=H2HDomainProfile.CLUB_H2H_V1,
        candidate_count=1,
        temporally_eligible_count=1,
        identity_eligible_count=1,
        deduplicated_count=1,
        usable_count=1,
        excluded_count=0,
        exclusion_counts_by_reason=(),
        newest_meeting_utc=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc),
        oldest_meeting_utc=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc),
        selected_meeting_ids=("meeting-test-001",),
    )
    quality_report = H2HQualityReportV1(
        overall_status=H2HQualityLevel.GOOD,
        overall_score=1.0,
        temporal_integrity=H2HQualityLevel.GOOD,
        identity_quality=H2HQualityLevel.GOOD,
        source_reliability=H2HQualityLevel.GOOD,
        score_reliability=H2HQualityLevel.GOOD,
        competition_context_coverage=H2HQualityLevel.GOOD,
        venue_context_coverage=H2HQualityLevel.GOOD,
        tie_context_coverage=H2HQualityLevel.GOOD,
        data_completeness=H2HQualityLevel.GOOD,
        issues=(),
    )
    readiness = H2HConsumerReadinessV1(
        consumer_id=H2HConsumerId.BTTS,
        status=H2HConsumerReadinessStatus.READY,
        available_features=(feature.name,),
        missing_features=(),
        blocking_issues=(),
        warnings=(),
    )
    provenance = H2HResultProvenanceV1(
        input_contract_hash="input-contract-hash-test",
        source_providers=(H2HProvider.FLASHSCORE,),
        provider_snapshot_ids=("snapshot-test-001",),
        normalization_version="v19.h2h.normalization.test",
        identity_resolver_version="v19.identity.test",
        processing_policy_version="v19.h2h.policy.test",
        deduplication_policy_version="v19.h2h.deduplication.test",
        feature_builder_version="v19.h2h.feature-builder.test",
    )

    return H2HModuleResultV1(
        contract_version="H2HModuleResultV1",
        request_id="request-test-001",
        target_match_id="target-match-test",
        computed_at_utc=datetime(2026, 7, 12, 16, 10, tzinfo=timezone.utc),
        cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
        module_status=H2HModuleStatus.READY,
        module_outcome=H2HModuleOutcome.FEATURES_PRODUCED,
        feature_set_version="v19.h2h.core.test",
        features=(feature,),
        meeting_selection_summary=selection_summary,
        quality_report=quality_report,
        readiness_by_consumer=(readiness,),
        missing_features=(),
        warnings=(),
        abstention_reasons=(),
        provenance=provenance,
    )


# Verifie que les vingt contrats V19 sont des dataclasses immuables.
def test_v19_domain_contracts_are_frozen_dataclasses() -> None:
    assert len(V19_DOMAIN_CONTRACTS) == 20

    for contract in V19_DOMAIN_CONTRACTS:
        assert is_dataclass(contract)
        assert contract.__dataclass_params__.frozen is True


# Verifie quelques valeurs critiques du vocabulaire controle H2H V19.
def test_v19_h2h_enums_keep_expected_values() -> None:
    assert H2HModuleStatus.READY.value == "READY"
    assert H2HModuleOutcome.H2H_MODULE_ABSTAIN.value == "H2H_MODULE_ABSTAIN"
    assert H2HConsumerId.BTTS.value == "BTTS"
    assert H2HIssueCode.H2H_TEMPORAL_VIOLATION.value == "H2H_TEMPORAL_VIOLATION"
    assert (
        H2HQualityFlag.H2H_DEPTH_INSUFFICIENT_FOR_BTTS.value
        == "H2H_DEPTH_INSUFFICIENT_FOR_BTTS"
    )


# Verifie que le contrat racine d'entree V19 peut etre compose avec ses objets imbriques.
def test_v19_h2h_module_input_can_be_composed() -> None:
    module_input = build_h2h_module_input()

    assert module_input.contract_version == "H2HModuleInputV1"
    assert module_input.target_match.canonical_match_id == "target-match-test"
    assert module_input.target_teams.home_team.canonical_team_id == "home-team-test"
    assert len(module_input.candidate_meetings) == 1
    assert isinstance(module_input.candidate_meetings, tuple)


# Verifie que le contrat racine d'entree V19 refuse toute mutation apres creation.
def test_v19_h2h_module_input_is_immutable() -> None:
    module_input = build_h2h_module_input()

    with pytest.raises(FrozenInstanceError):
        setattr(module_input, "request_id", "request-modified")


# Verifie que le contrat racine de sortie V19 conserve la feature et la readiness composees.
def test_v19_h2h_module_result_can_be_composed() -> None:
    module_result = build_h2h_module_result()

    assert module_result.contract_version == "H2HModuleResultV1"
    assert module_result.module_status == H2HModuleStatus.READY
    assert module_result.module_outcome == H2HModuleOutcome.FEATURES_PRODUCED
    assert module_result.features[0].name == "h2h_btts_rate"
    assert module_result.readiness_by_consumer[0].consumer_id == H2HConsumerId.BTTS


# Verifie que le resultat V19 est immuable et conserve ses collections sous forme de tuples.
def test_v19_h2h_module_result_is_immutable_and_keeps_tuples() -> None:
    module_result = build_h2h_module_result()

    assert isinstance(module_result.features, tuple)
    assert isinstance(module_result.missing_features, tuple)
    assert isinstance(module_result.warnings, tuple)
    assert isinstance(module_result.abstention_reasons, tuple)

    with pytest.raises(FrozenInstanceError):
        setattr(module_result, "module_status", H2HModuleStatus.DEGRADED)


# Schema de communication :
# test_v19.py
#   -> importe backend/app/v19/domain/h2h_enums.py
#   -> importe backend/app/v19/domain/h2h_contracts.py
#   -> verifie le vocabulaire controle du domaine V19
#   -> verifie la composition de H2HModuleInputV1 et H2HModuleResultV1
#   -> verifie l'immutabilite des vingt dataclasses V19
#   -> ne contacte aucune API et ne teste aucune recommandation sportive