# Role du fichier :
# Ces tests protègent les contrats et la chaîne interne H2H du domaine RubyBets V19.

from collections.abc import Callable
from dataclasses import FrozenInstanceError, is_dataclass, replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import experimental_ml_v19_h2h as v19_h2h_api

from app.v19.acquisition.flashscore_h2h_adapter import (
    adapt_flashscore_h2h_match,
)
from app.v19.acquisition.h2h_acquisition_service import (
    H2H_ACQUISITION_CANDIDATE_LIMIT,
    acquire_h2h_module_input,
)
from app.v19.acquisition.target_match_adapter import (
    TargetMatchAdapterError,
    adapt_normalized_target_match,
)
from app.v19.application.h2h_service import (
    H2HTargetMatchInvalidError,
    H2HTargetMatchNotFoundError,
    H2HTargetMatchProviderError,
    build_h2h_result_for_match,
)
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
from app.v19.features.h2h_feature_builder import (
    build_h2h_module_result as build_h2h_feature_result,
)
from app.v19.features.h2h_feature_catalog import (
    H2H_FEATURE_NAMES,
    H2H_FEATURE_SET_VERSION,
    get_h2h_profile_policy,
)
from app.v19.domain.h2h_enums import (
    H2HCacheState,
    H2HCompetitionCategory,
    H2HConsumerId,
    H2HConsumerReadinessStatus,
    H2HDomainProfile,
    H2HEntityType,
    H2HExclusionReason,
    H2HFeatureDataType,
    H2HFeatureUnit,
    H2HIdentityMethod,
    H2HIdentityStatus,
    H2HIssueCode,
    H2HIssueSeverity,
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


# Construit une horloge de test qui retourne toujours le meme instant UTC.
def build_static_clock(value: datetime) -> Callable[[], datetime]:
    # Retourne l'instant fixe fourni lors de la construction de l'horloge.
    def static_clock() -> datetime:
        return value

    return static_clock


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


# Construit un match H2H FlashScore normalise pour tester la couche d'acquisition V19.
def build_normalized_flashscore_h2h_match(
    match_id: str,
    home_team_id: str,
    home_team_name: str,
    away_team_id: str,
    away_team_name: str,
    utc_date: str = "2026-06-01T18:00:00Z",
) -> dict:
    return {
        "id": f"flashscore_{match_id}",
        "utcDate": utc_date,
        "status": "FINISHED",
        "competition": {
            "id": None,
            "code": "TEST",
            "name": "Competition Test",
            "type": None,
            "emblem": None,
        },
        "homeTeam": {
            "id": home_team_id,
            "name": home_team_name,
            "shortName": None,
            "tla": None,
            "crest": None,
        },
        "awayTeam": {
            "id": away_team_id,
            "name": away_team_name,
            "shortName": None,
            "tla": None,
            "crest": None,
        },
        "score": {
            "winner": None,
            "duration": "REGULAR",
            "fullTime": {
                "home": 2,
                "away": 1,
            },
            "halfTime": {
                "home": None,
                "away": None,
            },
        },
        "data_source": "flashscore_rapidapi",
    }


# Verifie que l'acquisition demande huit candidats et assemble un contrat V19 complet.
def test_v19_h2h_acquisition_uses_limit_eight_and_builds_input() -> None:
    reference_input = build_h2h_module_input()
    received_call: dict[str, object] = {}

    # Simule une source FlashScore qui retourne dix confrontations controlees.
    def fake_client(
        match_id: str | None,
        home_team_name: str,
        away_team_name: str,
        limit: int,
    ) -> tuple[list[dict], dict]:
        received_call.update(
            {
                "match_id": match_id,
                "home_team_name": home_team_name,
                "away_team_name": away_team_name,
                "limit": limit,
            }
        )
        matches = [
            build_normalized_flashscore_h2h_match(
                match_id=f"meeting-{index}",
                home_team_id="home-provider-test",
                home_team_name="Home Team Test",
                away_team_id="away-provider-test",
                away_team_name="Away Team Test",
                utc_date=f"2026-06-{index + 1:02d}T18:00:00Z",
            )
            for index in range(10)
        ]
        return matches, {
            "provider": "flashscore_rapidapi",
            "status": "success",
            "endpoint": "/matches/h2h",
            "results": len(matches),
        }

    fixed_time = datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc)
    module_input = acquire_h2h_module_input(
        request_id="request-acquisition-test",
        target_match=reference_input.target_match,
        target_teams=reference_input.target_teams,
        client=fake_client,
        clock=build_static_clock(fixed_time),
    )

    assert received_call["match_id"] == "target-provider-test"
    assert received_call["home_team_name"] == "Home Team Test"
    assert received_call["away_team_name"] == "Away Team Test"
    assert received_call["limit"] == H2H_ACQUISITION_CANDIDATE_LIMIT
    assert len(module_input.candidate_meetings) == 8
    assert module_input.contract_version == "H2HModuleInputV1"
    assert module_input.processing_policy.domain_profile == H2HDomainProfile.CLUB_H2H_V1
    assert module_input.acquisition_context.provider_results == (
        (H2HProvider.FLASHSCORE, H2HProviderResultStatus.AVAILABLE),
    )


# Verifie que les identifiants fournisseur resolvent les equipes dans leur orientation historique directe.
def test_v19_flashscore_adapter_resolves_direct_orientation_by_provider_id() -> None:
    reference_input = build_h2h_module_input()
    meeting = adapt_flashscore_h2h_match(
        match_data=build_normalized_flashscore_h2h_match(
            match_id="meeting-direct",
            home_team_id="home-provider-test",
            home_team_name="Observed Home Name",
            away_team_id="away-provider-test",
            away_team_name="Observed Away Name",
        ),
        target_teams=reference_input.target_teams,
        entity_type=H2HEntityType.CLUB,
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
    )

    assert meeting.home_team.canonical_team_id == "home-team-test"
    assert meeting.away_team.canonical_team_id == "away-team-test"
    assert meeting.home_team.identity_resolution.method == H2HIdentityMethod.PROVIDER_ID_EXACT
    assert meeting.away_team.identity_resolution.method == H2HIdentityMethod.PROVIDER_ID_EXACT
    assert meeting.mapping_quality == H2HQualityLevel.GOOD


# Verifie que l'adaptateur conserve les roles home/away reellement joues lors d'un H2H inverse.
def test_v19_flashscore_adapter_keeps_reversed_historical_orientation() -> None:
    reference_input = build_h2h_module_input()
    meeting = adapt_flashscore_h2h_match(
        match_data=build_normalized_flashscore_h2h_match(
            match_id="meeting-reversed",
            home_team_id="away-provider-test",
            home_team_name="Away Team Test",
            away_team_id="home-provider-test",
            away_team_name="Home Team Test",
        ),
        target_teams=reference_input.target_teams,
        entity_type=H2HEntityType.CLUB,
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
    )

    assert meeting.home_team.canonical_team_id == "away-team-test"
    assert meeting.away_team.canonical_team_id == "home-team-test"


# Vérifie que le fallback nominal retire uniquement les suffixes pays finaux du match cible.
def test_v19_flashscore_adapter_resolves_country_suffix_names_without_h2h_ids() -> None:
    target_data = build_normalized_target_match()
    target_data["homeTeam"]["name"] = "Iberia 1999 (GEO)"
    target_data["awayTeam"]["name"] = "Flora (EST)"
    _, target_teams = adapt_normalized_target_match(
        match_data=target_data,
        cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
        entity_type=H2HEntityType.CLUB,
    )

    meeting = adapt_flashscore_h2h_match(
        match_data=build_normalized_flashscore_h2h_match(
            match_id="meeting-country-suffix",
            home_team_id=None,
            home_team_name="Iberia 1999",
            away_team_id=None,
            away_team_name="Flora",
        ),
        target_teams=target_teams,
        entity_type=H2HEntityType.CLUB,
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
    )

    assert target_teams.home_team.normalized_name == "iberia 1999"
    assert target_teams.away_team.normalized_name == "flora"
    assert meeting.home_team.canonical_team_id == "501"
    assert meeting.away_team.canonical_team_id == "502"
    assert meeting.home_team.identity_resolution.method == H2HIdentityMethod.NORMALIZED_NAME
    assert meeting.away_team.identity_resolution.method == H2HIdentityMethod.NORMALIZED_NAME
    assert meeting.mapping_quality == H2HQualityLevel.PARTIAL


# Vérifie que le fallback nominal conserve l'orientation historique inversée sans IDs H2H.
def test_v19_flashscore_adapter_resolves_reversed_country_suffix_names_without_ids() -> None:
    target_data = build_normalized_target_match()
    target_data["homeTeam"]["name"] = "Iberia 1999 (GEO)"
    target_data["awayTeam"]["name"] = "Flora (EST)"
    _, target_teams = adapt_normalized_target_match(
        match_data=target_data,
        cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
        entity_type=H2HEntityType.CLUB,
    )

    meeting = adapt_flashscore_h2h_match(
        match_data=build_normalized_flashscore_h2h_match(
            match_id="meeting-country-suffix-reversed",
            home_team_id=None,
            home_team_name="Flora",
            away_team_id=None,
            away_team_name="Iberia 1999",
        ),
        target_teams=target_teams,
        entity_type=H2HEntityType.CLUB,
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
    )

    assert meeting.home_team.canonical_team_id == "502"
    assert meeting.away_team.canonical_team_id == "501"
    assert meeting.mapping_quality == H2HQualityLevel.PARTIAL


# Vérifie qu'un identifiant fournisseur exact reste prioritaire sur un nom historique contradictoire.
def test_v19_flashscore_adapter_prioritizes_provider_id_over_name() -> None:
    reference_input = build_h2h_module_input()
    meeting = adapt_flashscore_h2h_match(
        match_data=build_normalized_flashscore_h2h_match(
            match_id="meeting-id-priority",
            home_team_id="away-provider-test",
            home_team_name="Home Team Test",
            away_team_id="home-provider-test",
            away_team_name="Away Team Test",
        ),
        target_teams=reference_input.target_teams,
        entity_type=H2HEntityType.CLUB,
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
    )

    assert meeting.home_team.canonical_team_id == "away-team-test"
    assert meeting.away_team.canonical_team_id == "home-team-test"
    assert meeting.home_team.identity_resolution.method == H2HIdentityMethod.PROVIDER_ID_EXACT
    assert meeting.away_team.identity_resolution.method == H2HIdentityMethod.PROVIDER_ID_EXACT


# Vérifie qu'un ID fournisseur inconnu bloque le fallback nominal pour éviter un rapprochement contradictoire.
def test_v19_flashscore_adapter_rejects_conflicting_provider_id_and_name() -> None:
    reference_input = build_h2h_module_input()
    meeting = adapt_flashscore_h2h_match(
        match_data=build_normalized_flashscore_h2h_match(
            match_id="meeting-id-conflict",
            home_team_id="unknown-provider-test",
            home_team_name="Home Team Test",
            away_team_id="away-provider-test",
            away_team_name="Away Team Test",
        ),
        target_teams=reference_input.target_teams,
        entity_type=H2HEntityType.CLUB,
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
    )

    assert meeting.home_team.canonical_team_id is None
    assert meeting.home_team.identity_resolution.status == H2HIdentityStatus.UNRESOLVED
    assert meeting.away_team.canonical_team_id == "away-team-test"
    assert meeting.mapping_quality == H2HQualityLevel.POOR


# Vérifie qu'un nom réellement différent reste non résolu lorsque le H2H ne fournit aucun ID.
def test_v19_flashscore_adapter_keeps_different_name_unresolved() -> None:
    reference_input = build_h2h_module_input()
    meeting = adapt_flashscore_h2h_match(
        match_data=build_normalized_flashscore_h2h_match(
            match_id="meeting-name-unresolved",
            home_team_id=None,
            home_team_name="Different Club",
            away_team_id=None,
            away_team_name="Away Team Test",
        ),
        target_teams=reference_input.target_teams,
        entity_type=H2HEntityType.CLUB,
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
    )

    assert meeting.home_team.canonical_team_id is None
    assert meeting.home_team.identity_resolution.status == H2HIdentityStatus.UNRESOLVED
    assert meeting.away_team.canonical_team_id == "away-team-test"


# Verifie que la provenance FlashScore et l'etat de cache restent attaches a la confrontation.
def test_v19_h2h_acquisition_preserves_flashscore_provenance() -> None:
    reference_input = build_h2h_module_input()
    fixed_time = datetime(2026, 7, 12, 16, 30, tzinfo=timezone.utc)

    # Simule une source FlashScore qui declare un resultat issu du cache frais.
    def fake_client(
        match_id: str | None,
        home_team_name: str,
        away_team_name: str,
        limit: int,
    ) -> tuple[list[dict], dict]:
        del match_id, home_team_name, away_team_name, limit
        return [
            build_normalized_flashscore_h2h_match(
                match_id="meeting-provenance",
                home_team_id="home-provider-test",
                home_team_name="Home Team Test",
                away_team_id="away-provider-test",
                away_team_name="Away Team Test",
            )
        ], {
            "provider": "flashscore_rapidapi",
            "status": "success",
            "endpoint": "/matches/h2h",
            "cache_state": "HIT_FRESH",
            "results": 1,
        }

    module_input = acquire_h2h_module_input(
        request_id="request-provenance-test",
        target_match=reference_input.target_match,
        target_teams=reference_input.target_teams,
        client=fake_client,
        clock=build_static_clock(fixed_time),
    )
    provenance = module_input.candidate_meetings[0].provenance[0]

    assert provenance.provider == H2HProvider.FLASHSCORE
    assert provenance.endpoint == "/matches/h2h"
    assert provenance.provider_match_id == "meeting-provenance"
    assert provenance.retrieved_at_utc == fixed_time
    assert provenance.cache_state == H2HCacheState.HIT_FRESH
    assert module_input.acquisition_context.assembled_from_cache is True


# Verifie qu'une erreur fournisseur produit une entree vide et un statut ERROR sans lever d'exception.
def test_v19_h2h_acquisition_handles_unavailable_source() -> None:
    reference_input = build_h2h_module_input()

    # Simule une erreur fournisseur controlee sans appel reseau.
    def failing_client(
        match_id: str | None,
        home_team_name: str,
        away_team_name: str,
        limit: int,
    ) -> tuple[list[dict], dict]:
        del match_id, home_team_name, away_team_name, limit
        raise RuntimeError("controlled provider failure")

    module_input = acquire_h2h_module_input(
        request_id="request-provider-error-test",
        target_match=reference_input.target_match,
        target_teams=reference_input.target_teams,
        client=failing_client,
        clock=build_static_clock(
            datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc)
        ),
    )

    assert module_input.candidate_meetings == ()
    assert module_input.acquisition_context.provider_results == (
        (H2HProvider.FLASHSCORE, H2HProviderResultStatus.ERROR),
    )
    assert "flashscore_h2h_status:error" in module_input.acquisition_context.warnings


# Verifie que l'adaptateur laisse inconnus les contextes absents au lieu d'inventer des valeurs.
def test_v19_flashscore_adapter_keeps_missing_context_unknown() -> None:
    reference_input = build_h2h_module_input()
    match_data = build_normalized_flashscore_h2h_match(
        match_id="meeting-missing-context",
        home_team_id="home-provider-test",
        home_team_name="Home Team Test",
        away_team_id="away-provider-test",
        away_team_name="Away Team Test",
    )
    match_data["competition"] = {}

    meeting = adapt_flashscore_h2h_match(
        match_data=match_data,
        target_teams=reference_input.target_teams,
        entity_type=H2HEntityType.CLUB,
        retrieved_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
    )

    assert meeting.competition.canonical_competition_id is None
    assert meeting.competition.category == H2HCompetitionCategory.UNKNOWN
    assert meeting.competition.official_status == H2HOfficialStatus.UNKNOWN
    assert meeting.venue_context.neutral_ground == H2HTriState.UNKNOWN
    assert meeting.tie_context.format == H2HTieFormat.UNKNOWN
    assert meeting.score_context.score_type == H2HScoreType.REGULATION_90
    assert meeting.score_context.regulation_time == (2, 1)
    assert meeting.score_context.displayed_final_score == (2, 1)
    assert meeting.score_context.score_reliability == H2HScoreReliability.RELIABLE
    assert meeting.normalization_state == H2HNormalizationState.PARTIAL


# Verifie que le domaine selection nationale active le profil H2H national sans changer le contrat.
def test_v19_h2h_acquisition_selects_national_team_profile() -> None:
    reference_input = build_h2h_module_input()
    national_target_match = TargetMatchRefV1(
        canonical_match_id=reference_input.target_match.canonical_match_id,
        provider_match_ids=reference_input.target_match.provider_match_ids,
        kickoff_utc=reference_input.target_match.kickoff_utc,
        cutoff_utc=reference_input.target_match.cutoff_utc,
        domain=H2HEntityType.NATIONAL_TEAM,
        competition=reference_input.target_match.competition,
        venue_context=reference_input.target_match.venue_context,
        tie_context=reference_input.target_match.tie_context,
        match_status=reference_input.target_match.match_status,
    )

    # Simule une source disponible qui ne retourne aucune confrontation.
    def empty_client(
        match_id: str | None,
        home_team_name: str,
        away_team_name: str,
        limit: int,
    ) -> tuple[list[dict], dict]:
        del match_id, home_team_name, away_team_name, limit
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "empty",
            "endpoint": "/matches/h2h",
            "results": 0,
        }

    module_input = acquire_h2h_module_input(
        request_id="request-national-profile-test",
        target_match=national_target_match,
        target_teams=reference_input.target_teams,
        client=empty_client,
        clock=build_static_clock(
            datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc)
        ),
    )

    assert (
        module_input.processing_policy.domain_profile
        == H2HDomainProfile.NATIONAL_TEAM_H2H_V1
    )
    assert module_input.acquisition_context.provider_results == (
        (H2HProvider.FLASHSCORE, H2HProviderResultStatus.AVAILABLE),
    )




# Construit une identité de test adaptée au domaine club ou sélection nationale.
def build_feature_team_identity(
    canonical_team_id: str,
    provider_team_id: str,
    display_name: str,
    entity_type: H2HEntityType,
    identity_status: H2HIdentityStatus = H2HIdentityStatus.RESOLVED,
) -> TeamIdentityV1:
    identity = build_team_identity(
        canonical_team_id=canonical_team_id,
        provider_team_id=provider_team_id,
        display_name=display_name,
    )
    return replace(
        identity,
        entity_type=entity_type,
        identity_resolution=replace(
            identity.identity_resolution,
            status=identity_status,
            method=(
                H2HIdentityMethod.PROVIDER_ID_EXACT
                if identity_status == H2HIdentityStatus.RESOLVED
                else H2HIdentityMethod.UNRESOLVED
            ),
        ),
    )


# Construit une confrontation contrôlée pour vérifier les formules et politiques H2H.
def build_feature_meeting(
    meeting_id: str,
    kickoff_utc: datetime,
    target_home: TeamIdentityV1,
    target_away: TeamIdentityV1,
    score: tuple[int, int] = (2, 1),
    reverse_orientation: bool = False,
    official_status: H2HOfficialStatus = H2HOfficialStatus.OFFICIAL,
    category: H2HCompetitionCategory = H2HCompetitionCategory.DOMESTIC_LEAGUE,
    neutral_ground: H2HTriState = H2HTriState.FALSE,
    identity_status: H2HIdentityStatus = H2HIdentityStatus.RESOLVED,
    score_reliability: H2HScoreReliability = H2HScoreReliability.RELIABLE,
    raw_payload_hash: str | None = None,
) -> H2HMeetingV1:
    entity_type = target_home.entity_type
    home_source = target_away if reverse_orientation else target_home
    away_source = target_home if reverse_orientation else target_away
    home_team = replace(
        home_source,
        identity_resolution=replace(
            home_source.identity_resolution,
            status=identity_status,
            method=(
                H2HIdentityMethod.PROVIDER_ID_EXACT
                if identity_status == H2HIdentityStatus.RESOLVED
                else H2HIdentityMethod.UNRESOLVED
            ),
        ),
    )
    away_team = replace(
        away_source,
        identity_resolution=replace(
            away_source.identity_resolution,
            status=identity_status,
            method=(
                H2HIdentityMethod.PROVIDER_ID_EXACT
                if identity_status == H2HIdentityStatus.RESOLVED
                else H2HIdentityMethod.UNRESOLVED
            ),
        ),
    )
    competition = CompetitionContextV1(
        canonical_competition_id=f"competition-{meeting_id}",
        provider_competition_ids=(
            (H2HProvider.FLASHSCORE, f"provider-competition-{meeting_id}"),
        ),
        name=f"Competition {meeting_id}",
        domain=entity_type,
        category=category,
        season="2025-2026",
        phase=None,
        round=None,
        official_status=official_status,
    )
    provenance = SourceProvenanceV1(
        provider=H2HProvider.FLASHSCORE,
        endpoint="/matches/h2h",
        provider_match_id=meeting_id,
        retrieved_at_utc=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        source_priority=1,
        fallback_used=False,
        cache_state=H2HCacheState.MISS,
        raw_payload_hash=raw_payload_hash or f"hash-{meeting_id}",
        normalization_version="v19.h2h.normalization.test",
    )
    score_context = ScoreContextV1(
        score_type=H2HScoreType.REGULATION_90,
        regulation_time=score,
        extra_time=None,
        penalties=None,
        displayed_final_score=score,
        score_reliability=score_reliability,
    )

    return H2HMeetingV1(
        canonical_match_id=meeting_id,
        provider_match_ids=((H2HProvider.FLASHSCORE, meeting_id),),
        kickoff_utc=kickoff_utc,
        status=("FINISHED", "FINISHED"),
        competition=competition,
        home_team=home_team,
        away_team=away_team,
        venue_context=VenueContextV1(
            neutral_ground=neutral_ground,
            venue_name=None,
            venue_country=None,
            source_reliability=H2HQualityLevel.GOOD,
        ),
        score_context=score_context,
        tie_context=TieContextV1(
            format=H2HTieFormat.SINGLE_MATCH,
            tie_id=None,
            leg_number=H2HLegNumber.UNKNOWN,
            aggregate_score_before=None,
            aggregate_score_after=None,
            detection_method="test-single-match",
        ),
        provenance=(provenance,),
        mapping_quality=(
            H2HQualityLevel.GOOD
            if identity_status == H2HIdentityStatus.RESOLVED
            else H2HQualityLevel.POOR
        ),
        normalization_state=(
            H2HNormalizationState.VALID
            if score_reliability == H2HScoreReliability.RELIABLE
            else H2HNormalizationState.PARTIAL
        ),
        exclusion_reasons=(),
    )


# Construit une entrée de feature engineering avec un domaine et des candidats contrôlés.
def build_feature_module_input(
    meetings: tuple[H2HMeetingV1, ...],
    entity_type: H2HEntityType = H2HEntityType.CLUB,
    provider_status: H2HProviderResultStatus = H2HProviderResultStatus.AVAILABLE,
) -> H2HModuleInputV1:
    target_home = build_feature_team_identity(
        canonical_team_id="feature-home-team",
        provider_team_id="feature-home-provider",
        display_name="Feature Home Team",
        entity_type=entity_type,
    )
    target_away = build_feature_team_identity(
        canonical_team_id="feature-away-team",
        provider_team_id="feature-away-provider",
        display_name="Feature Away Team",
        entity_type=entity_type,
    )
    target_competition_category = (
        H2HCompetitionCategory.INTERNATIONAL_TOURNAMENT
        if entity_type == H2HEntityType.NATIONAL_TEAM
        else H2HCompetitionCategory.DOMESTIC_LEAGUE
    )
    target_competition = CompetitionContextV1(
        canonical_competition_id="feature-target-competition",
        provider_competition_ids=(
            (H2HProvider.FLASHSCORE, "feature-target-competition-provider"),
        ),
        name="Feature Target Competition",
        domain=entity_type,
        category=target_competition_category,
        season="2025-2026",
        phase=None,
        round=None,
        official_status=H2HOfficialStatus.OFFICIAL,
    )
    cutoff_utc = datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc)
    target_match = TargetMatchRefV1(
        canonical_match_id="feature-target-match",
        provider_match_ids=(
            (H2HProvider.FLASHSCORE, "feature-target-provider-match"),
        ),
        kickoff_utc=datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc),
        cutoff_utc=cutoff_utc,
        domain=entity_type,
        competition=target_competition,
        venue_context=VenueContextV1(
            neutral_ground=H2HTriState.FALSE,
            venue_name=None,
            venue_country=None,
            source_reliability=H2HQualityLevel.GOOD,
        ),
        tie_context=TieContextV1(
            format=H2HTieFormat.SINGLE_MATCH,
            tie_id=None,
            leg_number=H2HLegNumber.UNKNOWN,
            aggregate_score_before=None,
            aggregate_score_after=None,
            detection_method="test-single-match",
        ),
        match_status=("SCHEDULED", "SCHEDULED"),
    )
    profile = (
        H2HDomainProfile.NATIONAL_TEAM_H2H_V1
        if entity_type == H2HEntityType.NATIONAL_TEAM
        else H2HDomainProfile.CLUB_H2H_V1
    )

    return H2HModuleInputV1(
        contract_version="H2HModuleInputV1",
        request_id="feature-request-test",
        assembled_at_utc=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc),
        target_match=target_match,
        target_teams=TargetTeamsV1(
            home_team=target_home,
            away_team=target_away,
        ),
        candidate_meetings=meetings,
        acquisition_context=H2HAcquisitionContextV1(
            primary_provider=H2HProvider.FLASHSCORE,
            providers_attempted=(H2HProvider.FLASHSCORE,),
            provider_results=((H2HProvider.FLASHSCORE, provider_status),),
            fallback_used=False,
            assembled_from_cache=False,
            earliest_retrieved_at_utc=datetime(
                2026, 7, 1, 12, 0, tzinfo=timezone.utc
            ),
            latest_retrieved_at_utc=datetime(
                2026, 7, 1, 12, 0, tzinfo=timezone.utc
            ),
            warnings=(),
        ),
        processing_policy=H2HProcessingPolicyV1(
            policy_version="v19.h2h.processing-policy.test",
            domain_profile=profile,
            temporal_policy=(("strict_cutoff", True),),
            exclusion_policy=(("profile", profile.value),),
            deduplication_policy=(("provider_priority", "FLASHSCORE"),),
            identity_policy=(("require_resolved_identity", True),),
        ),
    )


# Retourne un dictionnaire simple des features d'un résultat H2H.
def get_feature_values(result: H2HModuleResultV1) -> dict[str, object]:
    return {feature.name: feature.value for feature in result.features}


# Retourne la readiness associée au consommateur demandé.
def get_consumer_readiness(
    result: H2HModuleResultV1,
    consumer_id: H2HConsumerId,
) -> H2HConsumerReadinessV1:
    return next(
        readiness
        for readiness in result.readiness_by_consumer
        if readiness.consumer_id == consumer_id
    )


# Vérifie que le catalogue expose exactement les douze features et les profils verrouillés.
def test_v19_h2h_feature_catalog_matches_core_1_specification() -> None:
    assert H2H_FEATURE_SET_VERSION == "v19.h2h.core.1"
    assert len(H2H_FEATURE_NAMES) == 12
    assert H2H_FEATURE_NAMES == (
        "h2h_matches_count",
        "h2h_total_goals_avg",
        "h2h_over_15_rate",
        "h2h_over_25_rate",
        "h2h_btts_rate",
        "h2h_home_team_scored_rate",
        "h2h_away_team_scored_rate",
        "h2h_days_since_last_meeting",
        "h2h_identity_resolved_rate",
        "h2h_reliable_score_rate",
        "h2h_official_match_rate",
        "h2h_neutral_ground_unknown_rate",
    )

    club_policy = get_h2h_profile_policy(H2HDomainProfile.CLUB_H2H_V1)
    national_policy = get_h2h_profile_policy(
        H2HDomainProfile.NATIONAL_TEAM_H2H_V1
    )

    assert club_policy.absolute_window_years == 6
    assert club_policy.max_meetings == 5
    assert national_policy.absolute_window_years == 12
    assert national_policy.friendly_supplement_years == 6
    assert national_policy.max_meetings == 8


# Vérifie les huit formules sportives et la réorientation des scores historiques.
def test_v19_h2h_feature_builder_calculates_oriented_core_features() -> None:
    empty_input = build_feature_module_input(())
    target_home = empty_input.target_teams.home_team
    target_away = empty_input.target_teams.away_team
    cutoff = empty_input.target_match.cutoff_utc
    meetings = (
        build_feature_meeting(
            "feature-meeting-1",
            cutoff - timedelta(days=10),
            target_home,
            target_away,
            score=(2, 1),
        ),
        build_feature_meeting(
            "feature-meeting-2",
            cutoff - timedelta(days=20),
            target_home,
            target_away,
            score=(3, 0),
            reverse_orientation=True,
        ),
        build_feature_meeting(
            "feature-meeting-3",
            cutoff - timedelta(days=30),
            target_home,
            target_away,
            score=(0, 0),
        ),
        build_feature_meeting(
            "feature-meeting-4",
            cutoff - timedelta(days=40),
            target_home,
            target_away,
            score=(1, 2),
        ),
    )
    module_input = replace(empty_input, candidate_meetings=meetings)

    result = build_h2h_feature_result(
        module_input,
        clock=build_static_clock(
            datetime(2026, 7, 12, 17, 5, tzinfo=timezone.utc)
        ),
    )
    values = get_feature_values(result)

    assert result.module_status == H2HModuleStatus.READY
    assert result.module_outcome == H2HModuleOutcome.FEATURES_PRODUCED
    assert values["h2h_matches_count"] == 4
    assert values["h2h_total_goals_avg"] == pytest.approx(2.25)
    assert values["h2h_over_15_rate"] == pytest.approx(0.75)
    assert values["h2h_over_25_rate"] == pytest.approx(0.75)
    assert values["h2h_btts_rate"] == pytest.approx(0.5)
    assert values["h2h_home_team_scored_rate"] == pytest.approx(0.5)
    assert values["h2h_away_team_scored_rate"] == pytest.approx(0.75)
    assert values["h2h_days_since_last_meeting"] == 10
    assert values["h2h_identity_resolved_rate"] == pytest.approx(1.0)
    assert values["h2h_reliable_score_rate"] == pytest.approx(1.0)
    assert values["h2h_official_match_rate"] == pytest.approx(1.0)
    assert values["h2h_neutral_ground_unknown_rate"] == pytest.approx(0.0)
    assert result.quality_report.overall_score is None
    assert get_consumer_readiness(
        result, H2HConsumerId.OVER_1_5
    ).status == H2HConsumerReadinessStatus.READY
    assert get_consumer_readiness(
        result, H2HConsumerId.BTTS
    ).status == H2HConsumerReadinessStatus.READY


# Vérifie la fenêtre clubs, l'exclusion des amicaux et la limite des cinq plus récentes.
def test_v19_h2h_club_profile_filters_and_caps_selected_meetings() -> None:
    empty_input = build_feature_module_input(())
    target_home = empty_input.target_teams.home_team
    target_away = empty_input.target_teams.away_team
    cutoff = empty_input.target_match.cutoff_utc
    official_meetings = tuple(
        build_feature_meeting(
            f"club-official-{index}",
            cutoff - timedelta(days=index * 30),
            target_home,
            target_away,
        )
        for index in range(1, 7)
    )
    friendly = build_feature_meeting(
        "club-friendly",
        cutoff - timedelta(days=5),
        target_home,
        target_away,
        official_status=H2HOfficialStatus.FRIENDLY,
        category=H2HCompetitionCategory.FRIENDLY,
    )
    too_old = build_feature_meeting(
        "club-too-old",
        datetime(2019, 1, 1, 12, 0, tzinfo=timezone.utc),
        target_home,
        target_away,
    )
    module_input = replace(
        empty_input,
        candidate_meetings=official_meetings + (friendly, too_old),
    )

    result = build_h2h_feature_result(module_input)
    summary = result.meeting_selection_summary

    assert summary.candidate_count == 8
    assert summary.usable_count == 5
    assert summary.selected_meeting_ids == tuple(
        f"club-official-{index}" for index in range(1, 6)
    )
    assert summary.exclusion_counts_by_reason == (
        (H2HExclusionReason.H2H_CLUB_FRIENDLY_EXCLUDED, 1),
    )


# Vérifie que les sélections priorisent les matchs officiels puis complètent avec les amicaux récents.
def test_v19_h2h_national_profile_prioritizes_official_then_friendlies() -> None:
    empty_input = build_feature_module_input(
        (),
        entity_type=H2HEntityType.NATIONAL_TEAM,
    )
    target_home = empty_input.target_teams.home_team
    target_away = empty_input.target_teams.away_team
    cutoff = empty_input.target_match.cutoff_utc
    official_meetings = tuple(
        build_feature_meeting(
            f"national-official-{index}",
            cutoff - timedelta(days=index * 60),
            target_home,
            target_away,
            category=H2HCompetitionCategory.INTERNATIONAL_QUALIFIER,
        )
        for index in range(1, 4)
    )
    friendly_meetings = tuple(
        build_feature_meeting(
            f"national-friendly-{index}",
            cutoff - timedelta(days=index * 45),
            target_home,
            target_away,
            official_status=H2HOfficialStatus.FRIENDLY,
            category=H2HCompetitionCategory.FRIENDLY,
        )
        for index in range(1, 8)
    )
    module_input = replace(
        empty_input,
        candidate_meetings=official_meetings + friendly_meetings,
    )

    result = build_h2h_feature_result(module_input)
    selected_ids = result.meeting_selection_summary.selected_meeting_ids

    assert len(selected_ids) == 8
    assert selected_ids[:3] == tuple(
        f"national-official-{index}" for index in range(1, 4)
    )
    assert selected_ids[3:] == tuple(
        f"national-friendly-{index}" for index in range(1, 6)
    )
    assert get_feature_values(result)["h2h_official_match_rate"] == pytest.approx(
        3 / 8
    )


# Vérifie que des amicaux seuls restent utilisables mais dégradent explicitement la qualité.
def test_v19_h2h_national_only_friendlies_adds_quality_flag() -> None:
    empty_input = build_feature_module_input(
        (),
        entity_type=H2HEntityType.NATIONAL_TEAM,
    )
    target_home = empty_input.target_teams.home_team
    target_away = empty_input.target_teams.away_team
    cutoff = empty_input.target_match.cutoff_utc
    meetings = tuple(
        build_feature_meeting(
            f"only-friendly-{index}",
            cutoff - timedelta(days=index * 40),
            target_home,
            target_away,
            official_status=H2HOfficialStatus.FRIENDLY,
            category=H2HCompetitionCategory.FRIENDLY,
        )
        for index in range(1, 5)
    )
    result = build_h2h_feature_result(
        replace(empty_input, candidate_meetings=meetings)
    )

    assert result.module_status == H2HModuleStatus.DEGRADED
    assert result.quality_report.overall_status == H2HQualityLevel.PARTIAL
    assert all(
        H2HQualityFlag.H2H_ONLY_FRIENDLIES in feature.quality_flags
        for feature in result.features
        if feature.name in H2H_FEATURE_NAMES[:8]
    )
    assert get_consumer_readiness(
        result, H2HConsumerId.BTTS
    ).status == H2HConsumerReadinessStatus.DEGRADED


# Vérifie les valeurs manquantes normatives et l'abstention locale lorsque N vaut zéro.
def test_v19_h2h_no_usable_meeting_returns_unavailable_and_null_features() -> None:
    module_input = build_feature_module_input(
        (),
        provider_status=H2HProviderResultStatus.UNAVAILABLE,
    )

    result = build_h2h_feature_result(module_input)
    values = get_feature_values(result)

    assert result.module_status == H2HModuleStatus.UNAVAILABLE
    assert result.module_outcome == H2HModuleOutcome.H2H_MODULE_ABSTAIN
    assert values["h2h_matches_count"] == 0
    assert all(values[name] is None for name in H2H_FEATURE_NAMES[1:])
    assert set(result.missing_features) == set(H2H_FEATURE_NAMES[1:])
    assert get_consumer_readiness(
        result, H2HConsumerId.OVER_1_5
    ).status == H2HConsumerReadinessStatus.NOT_READY
    assert get_consumer_readiness(
        result, H2HConsumerId.BTTS
    ).status == H2HConsumerReadinessStatus.NOT_READY
    assert {
        issue.code for issue in result.abstention_reasons
    } == {
        H2HIssueCode.H2H_SOURCE_UNAVAILABLE,
        H2HIssueCode.H2H_NO_ELIGIBLE_MEETING,
    }


# Vérifie les seuils distincts de readiness Over 1.5 et BTTS à trois confrontations.
def test_v19_h2h_three_meetings_ready_for_over15_only() -> None:
    empty_input = build_feature_module_input(())
    target_home = empty_input.target_teams.home_team
    target_away = empty_input.target_teams.away_team
    cutoff = empty_input.target_match.cutoff_utc
    meetings = tuple(
        build_feature_meeting(
            f"depth-three-{index}",
            cutoff - timedelta(days=index * 20),
            target_home,
            target_away,
        )
        for index in range(1, 4)
    )

    result = build_h2h_feature_result(
        replace(empty_input, candidate_meetings=meetings)
    )

    assert result.module_status == H2HModuleStatus.DEGRADED
    assert get_consumer_readiness(
        result, H2HConsumerId.OVER_1_5
    ).status == H2HConsumerReadinessStatus.READY
    assert get_consumer_readiness(
        result, H2HConsumerId.BTTS
    ).status == H2HConsumerReadinessStatus.NOT_READY
    assert all(
        H2HQualityFlag.H2H_DEPTH_INSUFFICIENT_FOR_BTTS
        in feature.quality_flags
        for feature in result.features
        if feature.name in H2H_FEATURE_NAMES[:8]
    )


# Vérifie que les identités et scores rejetés restent visibles dans les ratios de la population A.
def test_v19_h2h_quality_features_use_population_a_before_mandatory_exclusions() -> None:
    empty_input = build_feature_module_input(())
    target_home = empty_input.target_teams.home_team
    target_away = empty_input.target_teams.away_team
    cutoff = empty_input.target_match.cutoff_utc
    valid = build_feature_meeting(
        "quality-valid",
        cutoff - timedelta(days=10),
        target_home,
        target_away,
    )
    unresolved = build_feature_meeting(
        "quality-unresolved",
        cutoff - timedelta(days=20),
        target_home,
        target_away,
        identity_status=H2HIdentityStatus.UNRESOLVED,
    )
    unreliable = build_feature_meeting(
        "quality-unreliable",
        cutoff - timedelta(days=30),
        target_home,
        target_away,
        score_reliability=H2HScoreReliability.PARTIAL,
    )

    result = build_h2h_feature_result(
        replace(
            empty_input,
            candidate_meetings=(valid, unresolved, unreliable),
        )
    )
    values = get_feature_values(result)

    assert result.meeting_selection_summary.deduplicated_count == 3
    assert result.meeting_selection_summary.usable_count == 1
    assert values["h2h_identity_resolved_rate"] == pytest.approx(2 / 3)
    assert values["h2h_reliable_score_rate"] == pytest.approx(2 / 3)
    assert {
        issue.code for issue in result.quality_report.issues
    }.issuperset(
        {
            H2HIssueCode.H2H_TEAM_IDENTITY_AMBIGUOUS,
            H2HIssueCode.H2H_SCORE_UNRELIABLE,
        }
    )


# Vérifie qu'un doublon conflictuel est diagnostiqué et exclu de la population U.
def test_v19_h2h_conflicting_duplicate_is_not_used() -> None:
    empty_input = build_feature_module_input(())
    target_home = empty_input.target_teams.home_team
    target_away = empty_input.target_teams.away_team
    kickoff = empty_input.target_match.cutoff_utc - timedelta(days=10)
    first = build_feature_meeting(
        "duplicate-meeting",
        kickoff,
        target_home,
        target_away,
        score=(2, 1),
        raw_payload_hash="duplicate-hash-a",
    )
    conflicting = build_feature_meeting(
        "duplicate-meeting",
        kickoff,
        target_home,
        target_away,
        score=(0, 0),
        raw_payload_hash="duplicate-hash-b",
    )

    result = build_h2h_feature_result(
        replace(empty_input, candidate_meetings=(first, conflicting))
    )

    assert result.meeting_selection_summary.deduplicated_count == 1
    assert result.meeting_selection_summary.usable_count == 0
    assert result.module_status == H2HModuleStatus.UNAVAILABLE
    assert H2HIssueCode.H2H_DUPLICATE_CONFLICT in {
        issue.code for issue in result.quality_report.issues
    }


# Vérifie que la provenance et l'empreinte du contrat restent déterministes.
def test_v19_h2h_result_provenance_is_versioned_and_deterministic() -> None:
    empty_input = build_feature_module_input(())
    meeting = build_feature_meeting(
        "provenance-meeting",
        empty_input.target_match.cutoff_utc - timedelta(days=10),
        empty_input.target_teams.home_team,
        empty_input.target_teams.away_team,
    )
    module_input = replace(empty_input, candidate_meetings=(meeting,))
    static_clock = build_static_clock(
        datetime(2026, 7, 12, 17, 5, tzinfo=timezone.utc)
    )

    first_result = build_h2h_feature_result(module_input, clock=static_clock)
    second_result = build_h2h_feature_result(module_input, clock=static_clock)

    assert (
        first_result.provenance.input_contract_hash
        == second_result.provenance.input_contract_hash
    )
    assert len(first_result.provenance.input_contract_hash) == 64
    assert first_result.provenance.source_providers == (
        H2HProvider.FLASHSCORE,
    )
    assert first_result.provenance.provider_snapshot_ids == (
        "hash-provenance-meeting",
    )
    assert first_result.provenance.feature_builder_version
    assert first_result.feature_set_version == H2H_FEATURE_SET_VERSION


# Vérifie qu'un contrat incohérent produit INVALID sans exception ni recommandation.
def test_v19_h2h_invalid_input_returns_structured_invalid_result() -> None:
    module_input = build_feature_module_input(())
    invalid_target = replace(
        module_input.target_match,
        cutoff_utc=module_input.target_match.kickoff_utc + timedelta(minutes=1),
    )

    result = build_h2h_feature_result(
        replace(module_input, target_match=invalid_target)
    )

    assert result.module_status == H2HModuleStatus.INVALID
    assert result.module_outcome == H2HModuleOutcome.H2H_MODULE_ABSTAIN
    assert result.abstention_reasons
    assert all(
        issue.severity == H2HIssueSeverity.BLOCKER
        for issue in result.abstention_reasons
    )




# Construit un match cible FlashScore normalisé pour tester l'orchestration applicative V19.
def build_normalized_target_match() -> dict:
    return {
        "id": 1813105023365578,
        "sourceMatchId": "Target01",
        "source": "flashscore_rapidapi",
        "utcDate": "2026-07-12T18:00:00Z",
        "status": "SCHEDULED",
        "stage": "QUALIFICATION",
        "matchday": 1,
        "competition": {
            "id": 1001,
            "code": "CL",
            "name": "Champions League - Qualification",
            "type": None,
            "sourceCompetitionId": "CL001",
        },
        "season": {
            "id": 2026,
            "sourceSeasonId": "2026-2027",
        },
        "homeTeam": {
            "id": 501,
            "sourceTeamId": "Home01",
            "name": "Home Club",
        },
        "awayTeam": {
            "id": 502,
            "sourceTeamId": "Away01",
            "name": "Away Club",
        },
    }


# Construit quatre confrontations FlashScore exploitables par le pipeline complet.
def build_application_h2h_meetings() -> list[dict]:
    meetings = []
    scores = ((2, 1), (1, 1), (0, 2), (3, 2))

    for index, score in enumerate(scores, start=1):
        meeting = build_normalized_flashscore_h2h_match(
            match_id=f"AppH2H{index}",
            home_team_id=("Home01" if index % 2 else "Away01"),
            home_team_name=("Home Club" if index % 2 else "Away Club"),
            away_team_id=("Away01" if index % 2 else "Home01"),
            away_team_name=("Away Club" if index % 2 else "Home Club"),
            utc_date=f"2026-0{index + 1}-01T18:00:00Z",
        )
        meeting["competition"]["code"] = "CL"
        meeting["competition"]["name"] = "Champions League"
        meeting["score"]["fullTime"] = {
            "home": score[0],
            "away": score[1],
        }
        meetings.append(meeting)

    return meetings


# Vérifie que l'adaptateur cible conserve IDs, cutoff et contextes explicitement connus ou inconnus.
def test_v19_target_match_adapter_builds_traceable_contracts() -> None:
    cutoff = datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc)

    target_match, target_teams = adapt_normalized_target_match(
        match_data=build_normalized_target_match(),
        cutoff_utc=cutoff,
        entity_type=H2HEntityType.CLUB,
    )

    assert target_match.canonical_match_id == "1813105023365578"
    assert target_match.provider_match_ids == (
        (H2HProvider.FLASHSCORE, "Target01"),
    )
    assert target_match.cutoff_utc == cutoff
    assert target_match.domain == H2HEntityType.CLUB
    assert (
        target_match.competition.category
        == H2HCompetitionCategory.CONTINENTAL_CLUB_COMPETITION
    )
    assert target_match.competition.official_status == H2HOfficialStatus.OFFICIAL
    assert target_match.venue_context.neutral_ground == H2HTriState.UNKNOWN
    assert target_match.tie_context.format == H2HTieFormat.UNKNOWN
    assert target_teams.home_team.provider_ids == (
        (H2HProvider.FLASHSCORE, "Home01"),
    )
    assert target_teams.away_team.provider_ids == (
        (H2HProvider.FLASHSCORE, "Away01"),
    )


# Vérifie que le domaine national est explicite et n'est pas déduit silencieusement du nom des équipes.
def test_v19_target_match_adapter_applies_explicit_national_domain() -> None:
    match_data = build_normalized_target_match()
    match_data["competition"]["name"] = "World Championship - Qualification"

    target_match, target_teams = adapt_normalized_target_match(
        match_data=match_data,
        cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
        entity_type=H2HEntityType.NATIONAL_TEAM,
    )

    assert target_match.domain == H2HEntityType.NATIONAL_TEAM
    assert (
        target_match.competition.category
        == H2HCompetitionCategory.INTERNATIONAL_QUALIFIER
    )
    assert target_teams.home_team.entity_type == H2HEntityType.NATIONAL_TEAM
    assert target_teams.away_team.entity_type == H2HEntityType.NATIONAL_TEAM


# Vérifie qu'un cutoff postérieur au coup d'envoi est rejeté avant toute acquisition.
def test_v19_target_match_adapter_rejects_cutoff_after_kickoff() -> None:
    with pytest.raises(
        TargetMatchAdapterError,
        match="target_match_cutoff_after_kickoff",
    ):
        adapt_normalized_target_match(
            match_data=build_normalized_target_match(),
            cutoff_utc=datetime(2026, 7, 12, 18, 1, tzinfo=timezone.utc),
            entity_type=H2HEntityType.CLUB,
        )


# Vérifie le flux match cible -> acquisition -> features avec des dépendances injectées.
def test_v19_h2h_application_service_runs_end_to_end() -> None:
    fixed_time = datetime(2026, 7, 12, 16, 30, tzinfo=timezone.utc)

    # Retourne un match cible contrôlé sans appel fournisseur réel.
    def fake_match_loader(match_id: int | str | None) -> tuple[dict, dict]:
        assert match_id == 1813105023365578
        return build_normalized_target_match(), {
            "status": "success",
            "provider": "flashscore_rapidapi",
        }

    # Retourne quatre confrontations contrôlées et vérifie les entrées d'acquisition.
    def fake_h2h_client(
        match_id: str | None,
        home_team_name: str,
        away_team_name: str,
        limit: int,
    ) -> tuple[list[dict], dict]:
        assert match_id == "Target01"
        assert home_team_name == "Home Club"
        assert away_team_name == "Away Club"
        assert limit == H2H_ACQUISITION_CANDIDATE_LIMIT
        return build_application_h2h_meetings(), {
            "status": "success",
            "provider": "flashscore_rapidapi",
            "endpoint": "/matches/h2h",
            "results": 4,
        }

    result = build_h2h_result_for_match(
        match_id=1813105023365578,
        request_id="v19-application-test",
        cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
        entity_type=H2HEntityType.CLUB,
        match_loader=fake_match_loader,
        h2h_client=fake_h2h_client,
        clock=build_static_clock(fixed_time),
    )
    values = get_feature_values(result)

    assert result.request_id == "v19-application-test"
    assert result.target_match_id == "1813105023365578"
    assert result.module_outcome == H2HModuleOutcome.FEATURES_PRODUCED
    assert result.module_status == H2HModuleStatus.DEGRADED
    assert values["h2h_matches_count"] == 4
    assert values["h2h_total_goals_avg"] == pytest.approx(3.0)
    assert values["h2h_over_15_rate"] == pytest.approx(1.0)
    assert values["h2h_btts_rate"] == pytest.approx(0.75)
    assert get_consumer_readiness(
        result,
        H2HConsumerId.OVER_1_5,
    ).status == H2HConsumerReadinessStatus.DEGRADED
    assert get_consumer_readiness(
        result,
        H2HConsumerId.BTTS,
    ).status == H2HConsumerReadinessStatus.DEGRADED


# Vérifie le cas réel où le match cible porte des suffixes pays mais le H2H ne fournit aucun ID équipe.
def test_v19_h2h_application_service_uses_country_suffix_name_fallback() -> None:
    # Retourne un match cible FlashScore avec les suffixes pays observés dans le flux réel.
    def fake_match_loader(match_id: int | str | None) -> tuple[dict, dict]:
        del match_id
        match_data = build_normalized_target_match()
        match_data["homeTeam"].update(
            {
                "id": 272448811140462,
                "sourceTeamId": "dhfRkskl",
                "name": "Iberia 1999 (GEO)",
            }
        )
        match_data["awayTeam"].update(
            {
                "id": 60886512433049,
                "sourceTeamId": "zLFV5ykn",
                "name": "Flora (EST)",
            }
        )
        return match_data, {"status": "success"}

    # Retourne la confrontation réelle normalisée sans identifiants d'équipes H2H.
    def fake_h2h_client(
        match_id: str | None,
        home_team_name: str,
        away_team_name: str,
        limit: int,
    ) -> tuple[list[dict], dict]:
        del match_id, home_team_name, away_team_name, limit
        meeting = build_normalized_flashscore_h2h_match(
            match_id="jwbWPU57",
            home_team_id=None,
            home_team_name="Flora",
            away_team_id=None,
            away_team_name="Iberia 1999",
            utc_date="2025-07-15T18:00:00Z",
        )
        meeting["competition"]["code"] = "CL"
        meeting["competition"]["name"] = "Champions League"
        return [meeting], {
            "provider": "flashscore_rapidapi",
            "status": "success",
            "endpoint": "/matches/h2h",
            "results": 1,
        }

    result = build_h2h_result_for_match(
        match_id=1813105023365578,
        request_id="v19-country-suffix-live-shape-test",
        cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
        entity_type=H2HEntityType.CLUB,
        match_loader=fake_match_loader,
        h2h_client=fake_h2h_client,
        clock=build_static_clock(
            datetime(2026, 7, 12, 16, 30, tzinfo=timezone.utc)
        ),
    )
    values = get_feature_values(result)

    assert result.module_status == H2HModuleStatus.DEGRADED
    assert result.module_outcome == H2HModuleOutcome.FEATURES_PRODUCED
    assert result.meeting_selection_summary.identity_eligible_count == 1
    assert result.meeting_selection_summary.usable_count == 1
    assert values["h2h_matches_count"] == 1
    assert values["h2h_identity_resolved_rate"] == pytest.approx(1.0)


# Vérifie qu'une panne H2H produit une abstention structurée sans masquer le match cible valide.
def test_v19_h2h_application_service_handles_h2h_provider_failure() -> None:
    # Retourne un match cible contrôlé sans appel réseau.
    def fake_match_loader(match_id: int | str | None) -> tuple[dict, dict]:
        del match_id
        return build_normalized_target_match(), {"status": "success"}

    # Simule une panne fournisseur absorbée par la couche d'acquisition.
    def failing_h2h_client(
        match_id: str | None,
        home_team_name: str,
        away_team_name: str,
        limit: int,
    ) -> tuple[list[dict], dict]:
        del match_id, home_team_name, away_team_name, limit
        raise RuntimeError("controlled h2h failure")

    result = build_h2h_result_for_match(
        match_id=1813105023365578,
        request_id="v19-h2h-provider-error-test",
        cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
        entity_type=H2HEntityType.CLUB,
        match_loader=fake_match_loader,
        h2h_client=failing_h2h_client,
        clock=build_static_clock(
            datetime(2026, 7, 12, 16, 30, tzinfo=timezone.utc)
        ),
    )

    assert result.module_status == H2HModuleStatus.UNAVAILABLE
    assert result.module_outcome == H2HModuleOutcome.H2H_MODULE_ABSTAIN
    assert H2HIssueCode.H2H_SOURCE_UNAVAILABLE in {
        issue.code for issue in result.abstention_reasons
    }


# Vérifie qu'un match absent est distingué d'une panne fournisseur du chargeur cible.
def test_v19_h2h_application_service_distinguishes_target_match_errors() -> None:
    # Simule un identifiant qui ne correspond pas à un match FlashScore.
    def missing_loader(match_id: int | str | None) -> tuple[None, dict]:
        del match_id
        return None, {"status": "not_flashscore_match_id"}

    # Simule une panne du fournisseur du match cible.
    def failing_loader(match_id: int | str | None) -> tuple[dict, dict]:
        del match_id
        raise TimeoutError("controlled target timeout")

    with pytest.raises(H2HTargetMatchNotFoundError):
        build_h2h_result_for_match(
            match_id=1,
            request_id="v19-target-missing-test",
            cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
            entity_type=H2HEntityType.CLUB,
            match_loader=missing_loader,
        )

    with pytest.raises(
        H2HTargetMatchProviderError,
        match="target_match_provider_error:TimeoutError",
    ):
        build_h2h_result_for_match(
            match_id=2,
            request_id="v19-target-provider-test",
            cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
            entity_type=H2HEntityType.CLUB,
            match_loader=failing_loader,
        )


# Vérifie qu'un match cible partiel devient une erreur applicative stable et testable.
def test_v19_h2h_application_service_rejects_invalid_target_match() -> None:
    # Retourne un match sans date de coup d'envoi.
    def invalid_loader(match_id: int | str | None) -> tuple[dict, dict]:
        del match_id
        match_data = build_normalized_target_match()
        match_data["utcDate"] = None
        return match_data, {"status": "success"}

    with pytest.raises(
        H2HTargetMatchInvalidError,
        match="target_match_kickoff_missing",
    ):
        build_h2h_result_for_match(
            match_id=1813105023365578,
            request_id="v19-invalid-target-test",
            cutoff_utc=datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc),
            entity_type=H2HEntityType.CLUB,
            match_loader=invalid_loader,
        )


# Construit une application FastAPI minimale pour tester uniquement la route H2H V19.
def build_v19_h2h_test_client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(v19_h2h_api.router)
    return TestClient(test_app)


# Vérifie que la route H2H V19 expose un contrat JSON stable sans recommandation sportive.
def test_v19_h2h_api_returns_experimental_module_result(monkeypatch) -> None:
    captured_arguments: dict[str, object] = {}
    expected_cutoff = datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc)
    expected_result = build_h2h_feature_result(build_h2h_module_input())

    # Retourne un résultat H2H contrôlé et conserve les arguments transmis par la route.
    def fake_build_h2h_result_for_match(**kwargs) -> H2HModuleResultV1:
        captured_arguments.update(kwargs)
        return replace(
            expected_result,
            request_id=str(kwargs["request_id"]),
            cutoff_utc=kwargs["cutoff_utc"],
        )

    monkeypatch.setattr(
        v19_h2h_api,
        "build_h2h_result_for_match",
        fake_build_h2h_result_for_match,
    )
    monkeypatch.setattr(
        v19_h2h_api,
        "build_request_id",
        lambda match_id: f"v19-h2h-{match_id}-test",
    )

    client = build_v19_h2h_test_client()
    response = client.get(
        "/api/experimental/ml-v19/h2h/rubybets-matches/1813105023365578",
        params={
            "entity_type": "CLUB",
            "cutoff_utc": expected_cutoff.isoformat(),
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["source"] == "rubybets_v19_h2h_api"
    assert payload["scope"] == "experimental_h2h_module"
    assert payload["match_id"] == 1813105023365578
    assert payload["entity_type"] == "CLUB"
    assert payload["request_id"] == "v19-h2h-1813105023365578-test"
    assert payload["module_status"] == expected_result.module_status.value
    assert payload["module_outcome"] == expected_result.module_outcome.value
    assert payload["feature_set_version"] == H2H_FEATURE_SET_VERSION
    assert len(payload["result"]["features"]) == len(H2H_FEATURE_NAMES)
    assert payload["result"]["cutoff_utc"] == expected_cutoff.isoformat()
    assert "recommendation" not in payload
    assert "ne constitue pas une recommandation sportive" in payload["responsible_note"]
    assert captured_arguments["match_id"] == 1813105023365578
    assert captured_arguments["cutoff_utc"] == expected_cutoff
    assert captured_arguments["entity_type"] == H2HEntityType.CLUB


# Vérifie la traduction HTTP stable des erreurs applicatives du service H2H V19.
@pytest.mark.parametrize(
    ("application_error", "expected_status", "expected_code"),
    (
        (
            H2HTargetMatchNotFoundError("target_match_not_found"),
            404,
            "V19_H2H_TARGET_MATCH_NOT_FOUND",
        ),
        (
            H2HTargetMatchInvalidError("target_match_kickoff_missing"),
            422,
            "V19_H2H_TARGET_MATCH_INVALID",
        ),
        (
            H2HTargetMatchProviderError("target_match_provider_unavailable"),
            503,
            "V19_H2H_TARGET_PROVIDER_UNAVAILABLE",
        ),
    ),
)
def test_v19_h2h_api_maps_application_errors(
    monkeypatch,
    application_error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    # Relève l'erreur applicative contrôlée attendue sans appeler les fournisseurs réels.
    def fake_build_h2h_result_for_match(**kwargs) -> H2HModuleResultV1:
        del kwargs
        raise application_error

    monkeypatch.setattr(
        v19_h2h_api,
        "build_h2h_result_for_match",
        fake_build_h2h_result_for_match,
    )

    client = build_v19_h2h_test_client()
    response = client.get(
        "/api/experimental/ml-v19/h2h/rubybets-matches/1813105023365578",
        params={"cutoff_utc": "2026-07-12T17:00:00Z"},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert response.json()["detail"]["match_id"] == 1813105023365578


# Schema de communication :
# test_v19.py
#   -> importe backend/app/v19/domain/h2h_enums.py
#   -> importe backend/app/v19/acquisition/flashscore_h2h_adapter.py
#   -> importe backend/app/v19/acquisition/h2h_acquisition_service.py
#   -> importe backend/app/v19/acquisition/target_match_adapter.py
#   -> importe backend/app/v19/application/h2h_service.py
#   -> importe backend/app/api/experimental_ml_v19_h2h.py
#   -> importe backend/app/v19/domain/h2h_contracts.py
#   -> importe backend/app/v19/features/h2h_feature_catalog.py
#   -> importe backend/app/v19/features/h2h_feature_builder.py
#   -> verifie le vocabulaire controle du domaine V19
#   -> verifie la composition de H2HModuleInputV1 et H2HModuleResultV1
#   -> verifie l'immutabilite des vingt dataclasses V19
#   -> verifie acquisition, identites, orientation, suffixes pays, provenance et donnees manquantes
#   -> verifie la chaîne match cible -> acquisition -> features et ses erreurs contrôlées
#   -> verifie la sérialisation et les statuts HTTP de la route expérimentale H2H V19
#   -> verifie formules, profils, qualite, readiness et abstention locale H2H
#   -> injecte des clients controles et ne contacte aucune API reelle
#   -> ne teste aucune recommandation sportive
