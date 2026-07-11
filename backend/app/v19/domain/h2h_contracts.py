# Rôle du fichier :
# Ce fichier définit les contrats immuables d'entrée et de sortie du module H2H RubyBets V19.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

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


H2HCanonicalId: TypeAlias = str

H2HProviderIdEntries: TypeAlias = tuple[
    tuple[H2HProvider, str],
    ...,
]

H2HEvidenceEntries: TypeAlias = tuple[
    tuple[str, str],
    ...,
]

H2HScorePair: TypeAlias = tuple[int, int]

H2HMatchStatus: TypeAlias = tuple[
    str | None,
    str | None,
]

H2HPolicyScalar: TypeAlias = str | int | float | bool | None

H2HPolicyEntries: TypeAlias = tuple[
    tuple[str, H2HPolicyScalar],
    ...,
]

H2HProviderResults: TypeAlias = tuple[
    tuple[H2HProvider, H2HProviderResultStatus],
    ...,
]

H2HWarningMessages: TypeAlias = tuple[str, ...]

H2HExclusionReasons: TypeAlias = tuple[
    H2HExclusionReason,
    ...,
]

H2HFeatureScalar: TypeAlias = float | int | bool | str | None

H2HFeatureNames: TypeAlias = tuple[str, ...]

H2HMeetingIds: TypeAlias = tuple[str, ...]

H2HExclusionCounts: TypeAlias = tuple[
    tuple[H2HExclusionReason, int],
    ...,
]


# Décrit le résultat traçable de la résolution d'identité d'une équipe.
@dataclass(frozen=True)
class IdentityResolutionV1:
    status: H2HIdentityStatus
    method: H2HIdentityMethod
    confidence_score: float | None
    resolver_version: str
    evidence: H2HEvidenceEntries


# Décrit l'identité stable et les identifiants fournisseurs d'une équipe.
@dataclass(frozen=True)
class TeamIdentityV1:
    canonical_team_id: H2HCanonicalId | None
    entity_type: H2HEntityType
    provider_ids: H2HProviderIdEntries
    display_name: str
    normalized_name: str
    country_code: str | None
    identity_resolution: IdentityResolutionV1


# Regroupe les équipes domicile et extérieure du match cible.
@dataclass(frozen=True)
class TargetTeamsV1:
    home_team: TeamIdentityV1
    away_team: TeamIdentityV1


# Décrit le contexte normalisé d'une compétition.
@dataclass(frozen=True)
class CompetitionContextV1:
    canonical_competition_id: H2HCanonicalId | None
    provider_competition_ids: H2HProviderIdEntries
    name: str
    domain: H2HEntityType
    category: H2HCompetitionCategory
    season: str | None
    phase: str | None
    round: str | None
    official_status: H2HOfficialStatus


# Décrit le terrain et le caractère neutre, connu ou inconnu, du match.
@dataclass(frozen=True)
class VenueContextV1:
    neutral_ground: H2HTriState
    venue_name: str | None
    venue_country: str | None
    source_reliability: H2HQualityLevel


# Sépare les différentes représentations possibles du score d'un match.
@dataclass(frozen=True)
class ScoreContextV1:
    score_type: H2HScoreType
    regulation_time: H2HScorePair | None
    extra_time: H2HScorePair | None
    penalties: H2HScorePair | None
    displayed_final_score: H2HScorePair | None
    score_reliability: H2HScoreReliability


# Décrit le contexte d'un match simple, aller-retour ou multi-manches.
@dataclass(frozen=True)
class TieContextV1:
    format: H2HTieFormat
    tie_id: str | None
    leg_number: H2HLegNumber
    aggregate_score_before: H2HScorePair | None
    aggregate_score_after: H2HScorePair | None
    detection_method: str | None


# Conserve la provenance détaillée d'une confrontation auprès d'une source.
@dataclass(frozen=True)
class SourceProvenanceV1:
    provider: H2HProvider
    endpoint: str
    provider_match_id: str | None
    retrieved_at_utc: datetime
    source_priority: int
    fallback_used: bool
    cache_state: H2HCacheState
    raw_payload_hash: str | None
    normalization_version: str


# Référence le match cible et son cutoff avant-match obligatoire.
@dataclass(frozen=True)
class TargetMatchRefV1:
    canonical_match_id: H2HCanonicalId
    provider_match_ids: H2HProviderIdEntries
    kickoff_utc: datetime
    cutoff_utc: datetime
    domain: H2HEntityType
    competition: CompetitionContextV1
    venue_context: VenueContextV1
    tie_context: TieContextV1
    match_status: H2HMatchStatus


# Décrit une confrontation H2H candidate après normalisation.
@dataclass(frozen=True)
class H2HMeetingV1:
    canonical_match_id: H2HCanonicalId | None
    provider_match_ids: H2HProviderIdEntries
    kickoff_utc: datetime | None
    status: H2HMatchStatus
    competition: CompetitionContextV1
    home_team: TeamIdentityV1
    away_team: TeamIdentityV1
    venue_context: VenueContextV1
    score_context: ScoreContextV1
    tie_context: TieContextV1
    provenance: tuple[SourceProvenanceV1, ...]
    mapping_quality: H2HQualityLevel
    normalization_state: H2HNormalizationState
    exclusion_reasons: H2HExclusionReasons


# Résume les fournisseurs consultés et les conditions d'acquisition.
@dataclass(frozen=True)
class H2HAcquisitionContextV1:
    primary_provider: H2HProvider
    providers_attempted: tuple[H2HProvider, ...]
    provider_results: H2HProviderResults
    fallback_used: bool
    assembled_from_cache: bool
    earliest_retrieved_at_utc: datetime | None
    latest_retrieved_at_utc: datetime | None
    warnings: H2HWarningMessages


# Transporte les politiques versionnées nécessaires au traitement reproductible.
@dataclass(frozen=True)
class H2HProcessingPolicyV1:
    policy_version: str
    domain_profile: H2HDomainProfile
    temporal_policy: H2HPolicyEntries
    exclusion_policy: H2HPolicyEntries
    deduplication_policy: H2HPolicyEntries
    identity_policy: H2HPolicyEntries


# Constitue le contrat racine immuable fourni au module H2H.
@dataclass(frozen=True)
class H2HModuleInputV1:
    contract_version: str
    request_id: str
    assembled_at_utc: datetime
    target_match: TargetMatchRefV1
    target_teams: TargetTeamsV1
    candidate_meetings: tuple[H2HMeetingV1, ...]
    acquisition_context: H2HAcquisitionContextV1
    processing_policy: H2HProcessingPolicyV1


# Décrit une anomalie ou une prudence structurée du module H2H.
@dataclass(frozen=True)
class H2HModuleIssueV1:
    code: H2HIssueCode
    severity: H2HIssueSeverity
    scope: str
    message: str
    affected_meeting_ids: H2HMeetingIds


# Transporte une feature H2H avec sa lignée et sa qualité.
@dataclass(frozen=True)
class H2HFeatureValueV1:
    name: str
    value: H2HFeatureScalar
    data_type: H2HFeatureDataType
    unit: H2HFeatureUnit
    feature_version: str
    meeting_count_used: int
    source_meeting_ids: H2HMeetingIds
    missing_state: str | None
    quality_flags: tuple[H2HQualityFlag, ...]


# Résume toutes les étapes de sélection des confrontations candidates.
@dataclass(frozen=True)
class H2HMeetingSelectionSummaryV1:
    domain_profile: H2HDomainProfile
    candidate_count: int
    temporally_eligible_count: int
    identity_eligible_count: int
    deduplicated_count: int
    usable_count: int
    excluded_count: int
    exclusion_counts_by_reason: H2HExclusionCounts
    newest_meeting_utc: datetime | None
    oldest_meeting_utc: datetime | None
    selected_meeting_ids: H2HMeetingIds


# Regroupe les dimensions de qualité et les anomalies du résultat H2H.
@dataclass(frozen=True)
class H2HQualityReportV1:
    overall_status: H2HQualityLevel
    overall_score: float | None
    temporal_integrity: H2HQualityLevel
    identity_quality: H2HQualityLevel
    source_reliability: H2HQualityLevel
    score_reliability: H2HQualityLevel
    competition_context_coverage: H2HQualityLevel
    venue_context_coverage: H2HQualityLevel
    tie_context_coverage: H2HQualityLevel
    data_completeness: H2HQualityLevel
    issues: tuple[H2HModuleIssueV1, ...]


# Décrit la disponibilité des features pour un consommateur spécialisé.
@dataclass(frozen=True)
class H2HConsumerReadinessV1:
    consumer_id: H2HConsumerId
    status: H2HConsumerReadinessStatus
    available_features: H2HFeatureNames
    missing_features: H2HFeatureNames
    blocking_issues: tuple[H2HModuleIssueV1, ...]
    warnings: tuple[H2HModuleIssueV1, ...]


# Conserve toutes les versions nécessaires à l'audit et au replay du résultat.
@dataclass(frozen=True)
class H2HResultProvenanceV1:
    input_contract_hash: str
    source_providers: tuple[H2HProvider, ...]
    provider_snapshot_ids: tuple[str, ...]
    normalization_version: str
    identity_resolver_version: str
    processing_policy_version: str
    deduplication_policy_version: str
    feature_builder_version: str


# Constitue la sortie racine du module H2H sans décision sportive finale.
@dataclass(frozen=True)
class H2HModuleResultV1:
    contract_version: str
    request_id: str
    target_match_id: H2HCanonicalId
    computed_at_utc: datetime
    cutoff_utc: datetime
    module_status: H2HModuleStatus
    module_outcome: H2HModuleOutcome
    feature_set_version: str
    features: tuple[H2HFeatureValueV1, ...]
    meeting_selection_summary: H2HMeetingSelectionSummaryV1
    quality_report: H2HQualityReportV1
    readiness_by_consumer: tuple[H2HConsumerReadinessV1, ...]
    missing_features: H2HFeatureNames
    warnings: tuple[H2HModuleIssueV1, ...]
    abstention_reasons: tuple[H2HModuleIssueV1, ...]
    provenance: H2HResultProvenanceV1


# Schéma de communication :
# h2h_enums.py
#   -> fournit le vocabulaire contrôlé à h2h_contracts.py
#
# h2h_contracts.py
#   -> est alimenté par acquisition/ et normalization/
#   -> fournit H2HModuleInputV1 à h2h_feature_builder.py
#   -> reçoit H2HModuleResultV1 depuis h2h_feature_builder.py
#   -> sera consommé plus tard par les experts BTTS et Over 1.5
#   -> ne contacte aucun fournisseur et ne produit aucune recommandation