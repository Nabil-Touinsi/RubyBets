# Rôle du fichier :
# Ce fichier sélectionne les confrontations éligibles et construit H2HModuleResultV1 selon v19.h2h.core.1.

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.v19.domain.h2h_contracts import (
    H2HConsumerReadinessV1,
    H2HFeatureValueV1,
    H2HMeetingSelectionSummaryV1,
    H2HMeetingV1,
    H2HModuleInputV1,
    H2HModuleIssueV1,
    H2HModuleResultV1,
    H2HQualityReportV1,
    H2HResultProvenanceV1,
    SourceProvenanceV1,
    TeamIdentityV1,
)
from app.v19.domain.h2h_enums import (
    H2HCacheState,
    H2HCompetitionCategory,
    H2HConsumerId,
    H2HConsumerReadinessStatus,
    H2HDomainProfile,
    H2HExclusionReason,
    H2HIdentityStatus,
    H2HIssueCode,
    H2HIssueSeverity,
    H2HModuleOutcome,
    H2HModuleStatus,
    H2HNormalizationState,
    H2HOfficialStatus,
    H2HProvider,
    H2HProviderResultStatus,
    H2HQualityFlag,
    H2HQualityLevel,
    H2HScoreReliability,
    H2HTriState,
)
from app.v19.features.h2h_feature_catalog import (
    H2H_CONSUMER_MINIMUM_DEPTH,
    H2H_DEDUPLICATION_POLICY_VERSION,
    H2H_FEATURE_BUILDER_VERSION,
    H2H_FEATURE_NAMES,
    H2H_FEATURE_SET_VERSION,
    H2H_POPULATION_A,
    H2H_POPULATION_U,
    get_h2h_consumer_required_features,
    get_h2h_feature_spec,
    get_h2h_profile_policy,
)


H2H_RESULT_CONTRACT_VERSION = "H2HModuleResultV1"
H2H_MISSING_NO_USABLE_MEETING = "NO_USABLE_MEETING"
H2H_MISSING_NO_DEDUPLICATED_CANDIDATE = "NO_DEDUPLICATED_CANDIDATE"

H2HClock = Callable[[], datetime]


# Transporte une confrontation dédupliquée et l'état de conflit détecté pendant la fusion.
@dataclass(frozen=True)
class DeduplicatedMeetingV1:
    meeting: H2HMeetingV1
    duplicate_conflict: bool


# Regroupe les populations intermédiaires nécessaires au calcul et au diagnostic.
@dataclass(frozen=True)
class H2HSelectionStateV1:
    population_a: tuple[DeduplicatedMeetingV1, ...]
    population_u: tuple[H2HMeetingV1, ...]
    candidate_count: int
    temporally_eligible_count: int
    target_excluded_ids: tuple[str, ...]
    temporal_violation_ids: tuple[str, ...]
    identity_rejected_ids: tuple[str, ...]
    score_rejected_ids: tuple[str, ...]
    duplicate_conflict_ids: tuple[str, ...]
    competition_rejected_ids: tuple[str, ...]
    club_friendly_excluded_count: int
    only_friendlies_selected: bool


# Retourne l'instant courant en UTC pour permettre l'injection d'une horloge de test.
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Convertit une date en UTC sans perdre l'instant représenté.
def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


# Soustrait un nombre d'années calendaires en gérant le 29 février.
def subtract_calendar_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


# Retourne un identifiant de lignée stable sans dépendre de la position du candidat.
def get_meeting_lineage_id(meeting: H2HMeetingV1) -> str:
    if meeting.canonical_match_id:
        return meeting.canonical_match_id

    if meeting.provider_match_ids:
        provider, provider_match_id = meeting.provider_match_ids[0]
        return f"{provider.value}:{provider_match_id}"

    payload = {
        "kickoff": (
            ensure_utc_datetime(meeting.kickoff_utc).isoformat()
            if meeting.kickoff_utc is not None
            else None
        ),
        "home": get_team_identity_tokens(meeting.home_team),
        "away": get_team_identity_tokens(meeting.away_team),
        "score": meeting.score_context.regulation_time,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"derived:{digest}"


# Retourne tous les jetons stables permettant de comparer une identité d'équipe.
def get_team_identity_tokens(team: TeamIdentityV1) -> tuple[str, ...]:
    tokens: list[str] = []

    if team.canonical_team_id:
        tokens.append(f"canonical:{team.canonical_team_id}")

    for provider, provider_id in team.provider_ids:
        tokens.append(f"provider:{provider.value}:{provider_id}")

    if team.normalized_name:
        tokens.append(f"name:{team.normalized_name.casefold().strip()}")

    return tuple(tokens)


# Indique si deux identités décrivent la même équipe à partir de leurs jetons stables.
def identities_match(first: TeamIdentityV1, second: TeamIdentityV1) -> bool:
    return bool(
        set(get_team_identity_tokens(first)).intersection(
            get_team_identity_tokens(second)
        )
    )


# Indique si une confrontation contient exactement les deux équipes cibles.
def meeting_matches_target_pair(
    meeting: H2HMeetingV1,
    module_input: H2HModuleInputV1,
) -> bool:
    target_home = module_input.target_teams.home_team
    target_away = module_input.target_teams.away_team

    direct_orientation = identities_match(
        meeting.home_team, target_home
    ) and identities_match(meeting.away_team, target_away)
    reverse_orientation = identities_match(
        meeting.home_team, target_away
    ) and identities_match(meeting.away_team, target_home)

    return direct_orientation or reverse_orientation


# Indique si les deux identités historiques sont explicitement résolues.
def meeting_identities_are_resolved(meeting: H2HMeetingV1) -> bool:
    return (
        meeting.home_team.identity_resolution.status
        == H2HIdentityStatus.RESOLVED
        and meeting.away_team.identity_resolution.status
        == H2HIdentityStatus.RESOLVED
    )


# Indique si le score réglementaire est complet, fiable et non négatif.
def meeting_has_reliable_regulation_score(meeting: H2HMeetingV1) -> bool:
    score = meeting.score_context.regulation_time
    if score is None or meeting.score_context.score_reliability != H2HScoreReliability.RELIABLE:
        return False

    home_goals, away_goals = score
    return (
        isinstance(home_goals, int)
        and not isinstance(home_goals, bool)
        and isinstance(away_goals, int)
        and not isinstance(away_goals, bool)
        and home_goals >= 0
        and away_goals >= 0
    )


# Indique si le candidat représente le match cible et doit être exclu.
def meeting_is_target_match(
    meeting: H2HMeetingV1,
    module_input: H2HModuleInputV1,
) -> bool:
    target_match = module_input.target_match

    if (
        meeting.canonical_match_id
        and meeting.canonical_match_id == target_match.canonical_match_id
    ):
        return True

    target_provider_ids = set(target_match.provider_match_ids)
    return bool(target_provider_ids.intersection(meeting.provider_match_ids))


# Construit la clé primaire puis secondaire utilisée pour dédupliquer les candidats.
def build_meeting_deduplication_key(meeting: H2HMeetingV1) -> tuple[Any, ...]:
    if meeting.canonical_match_id:
        return ("canonical", meeting.canonical_match_id)

    if meeting.provider_match_ids:
        provider, provider_match_id = meeting.provider_match_ids[0]
        return ("provider", provider.value, provider_match_id)

    team_pair = tuple(
        sorted(
            (
                get_team_identity_tokens(meeting.home_team),
                get_team_identity_tokens(meeting.away_team),
            ),
            key=str,
        )
    )
    return (
        "fallback",
        ensure_utc_datetime(meeting.kickoff_utc).isoformat()
        if meeting.kickoff_utc is not None
        else None,
        team_pair,
    )


# Indique si deux doublons portent des informations sportives incompatibles.
def duplicate_meetings_conflict(
    first: H2HMeetingV1,
    second: H2HMeetingV1,
) -> bool:
    return (
        first.score_context.regulation_time
        != second.score_context.regulation_time
        or not identities_match(first.home_team, second.home_team)
        or not identities_match(first.away_team, second.away_team)
    )


# Fusionne les provenances uniques de plusieurs occurrences d'une même confrontation.
def merge_meeting_provenance(
    meetings: Iterable[H2HMeetingV1],
) -> tuple[SourceProvenanceV1, ...]:
    unique_entries: dict[tuple[Any, ...], SourceProvenanceV1] = {}

    for meeting in meetings:
        for provenance in meeting.provenance:
            key = (
                provenance.provider,
                provenance.endpoint,
                provenance.provider_match_id,
                ensure_utc_datetime(provenance.retrieved_at_utc),
                provenance.raw_payload_hash,
                provenance.normalization_version,
            )
            unique_entries[key] = provenance

    return tuple(unique_entries.values())


# Déduplique les candidats et conserve un diagnostic explicite en cas de conflit.
def deduplicate_meetings(
    meetings: Iterable[H2HMeetingV1],
) -> tuple[DeduplicatedMeetingV1, ...]:
    grouped: dict[tuple[Any, ...], list[H2HMeetingV1]] = {}

    for meeting in meetings:
        grouped.setdefault(build_meeting_deduplication_key(meeting), []).append(
            meeting
        )

    deduplicated: list[DeduplicatedMeetingV1] = []
    for duplicates in grouped.values():
        selected = duplicates[0]
        conflict = any(
            duplicate_meetings_conflict(selected, duplicate)
            for duplicate in duplicates[1:]
        )
        merged = replace(
            selected,
            provenance=merge_meeting_provenance(duplicates),
        )
        deduplicated.append(
            DeduplicatedMeetingV1(
                meeting=merged,
                duplicate_conflict=conflict,
            )
        )

    return tuple(deduplicated)


# Vérifie qu'une compétition officielle appartient aux catégories admises du profil.
def meeting_has_allowed_official_competition(
    meeting: H2HMeetingV1,
    allowed_categories: tuple[H2HCompetitionCategory, ...],
) -> bool:
    return (
        meeting.competition.official_status == H2HOfficialStatus.OFFICIAL
        and meeting.competition.category in allowed_categories
    )


# Sélectionne les rencontres utilisables selon la fenêtre et la politique du profil.
def select_h2h_meetings(
    module_input: H2HModuleInputV1,
) -> H2HSelectionStateV1:
    profile_policy = get_h2h_profile_policy(
        module_input.processing_policy.domain_profile
    )
    cutoff_utc = ensure_utc_datetime(module_input.target_match.cutoff_utc)
    absolute_start = subtract_calendar_years(
        cutoff_utc,
        profile_policy.absolute_window_years,
    )

    temporally_eligible: list[H2HMeetingV1] = []
    temporal_violation_ids: list[str] = []
    target_excluded_ids: list[str] = []

    for meeting in module_input.candidate_meetings:
        meeting_id = get_meeting_lineage_id(meeting)
        if meeting.kickoff_utc is None:
            temporal_violation_ids.append(meeting_id)
            continue

        kickoff_utc = ensure_utc_datetime(meeting.kickoff_utc)
        if kickoff_utc >= cutoff_utc:
            temporal_violation_ids.append(meeting_id)
            continue

        if kickoff_utc < absolute_start:
            continue

        if meeting_is_target_match(meeting, module_input):
            target_excluded_ids.append(meeting_id)
            continue

        temporally_eligible.append(meeting)

    population_a = deduplicate_meetings(temporally_eligible)
    identity_rejected_ids: list[str] = []
    score_rejected_ids: list[str] = []
    duplicate_conflict_ids: list[str] = []
    competition_rejected_ids: list[str] = []
    club_friendly_excluded_count = 0
    identity_and_score_eligible: list[H2HMeetingV1] = []

    for candidate in population_a:
        meeting = candidate.meeting
        meeting_id = get_meeting_lineage_id(meeting)

        if candidate.duplicate_conflict:
            duplicate_conflict_ids.append(meeting_id)
            continue

        if (
            not meeting_identities_are_resolved(meeting)
            or not meeting_matches_target_pair(meeting, module_input)
        ):
            identity_rejected_ids.append(meeting_id)
            continue

        if (
            meeting.normalization_state
            in {H2HNormalizationState.INVALID, H2HNormalizationState.CONFLICTING}
            or not meeting_has_reliable_regulation_score(meeting)
        ):
            score_rejected_ids.append(meeting_id)
            continue

        identity_and_score_eligible.append(meeting)

    selected: list[H2HMeetingV1] = []
    only_friendlies_selected = False

    if profile_policy.domain_profile == H2HDomainProfile.CLUB_H2H_V1:
        official_candidates: list[H2HMeetingV1] = []
        for meeting in identity_and_score_eligible:
            if meeting.competition.official_status == H2HOfficialStatus.FRIENDLY:
                club_friendly_excluded_count += 1
                continue

            if not meeting_has_allowed_official_competition(
                meeting,
                profile_policy.allowed_official_categories,
            ):
                competition_rejected_ids.append(get_meeting_lineage_id(meeting))
                continue

            official_candidates.append(meeting)

        selected = sorted(
            official_candidates,
            key=lambda item: ensure_utc_datetime(item.kickoff_utc),
            reverse=True,
        )[: profile_policy.max_meetings]
    else:
        official_candidates = []
        friendly_candidates = []
        friendly_start = subtract_calendar_years(
            cutoff_utc,
            profile_policy.friendly_supplement_years or 0,
        )

        for meeting in identity_and_score_eligible:
            if meeting_has_allowed_official_competition(
                meeting,
                profile_policy.allowed_official_categories,
            ):
                official_candidates.append(meeting)
                continue

            if (
                meeting.competition.official_status == H2HOfficialStatus.FRIENDLY
                and meeting.competition.category == H2HCompetitionCategory.FRIENDLY
                and meeting.kickoff_utc is not None
                and ensure_utc_datetime(meeting.kickoff_utc) >= friendly_start
            ):
                friendly_candidates.append(meeting)
                continue

            competition_rejected_ids.append(get_meeting_lineage_id(meeting))

        official_candidates.sort(
            key=lambda item: ensure_utc_datetime(item.kickoff_utc),
            reverse=True,
        )
        friendly_candidates.sort(
            key=lambda item: ensure_utc_datetime(item.kickoff_utc),
            reverse=True,
        )

        selected = official_candidates[: profile_policy.max_meetings]
        remaining_slots = profile_policy.max_meetings - len(selected)
        if remaining_slots > 0:
            selected.extend(friendly_candidates[:remaining_slots])

        only_friendlies_selected = bool(selected) and not official_candidates

    return H2HSelectionStateV1(
        population_a=population_a,
        population_u=tuple(selected),
        candidate_count=len(module_input.candidate_meetings),
        temporally_eligible_count=len(temporally_eligible),
        target_excluded_ids=tuple(target_excluded_ids),
        temporal_violation_ids=tuple(temporal_violation_ids),
        identity_rejected_ids=tuple(identity_rejected_ids),
        score_rejected_ids=tuple(score_rejected_ids),
        duplicate_conflict_ids=tuple(duplicate_conflict_ids),
        competition_rejected_ids=tuple(competition_rejected_ids),
        club_friendly_excluded_count=club_friendly_excluded_count,
        only_friendlies_selected=only_friendlies_selected,
    )


# Réoriente le score historique selon les équipes domicile et extérieure du match cible.
def orient_regulation_score(
    meeting: H2HMeetingV1,
    module_input: H2HModuleInputV1,
) -> tuple[int, int]:
    score = meeting.score_context.regulation_time
    if score is None:
        raise ValueError("A usable H2H meeting must contain a regulation score")

    target_home = module_input.target_teams.home_team
    target_away = module_input.target_teams.away_team

    if identities_match(meeting.home_team, target_home) and identities_match(
        meeting.away_team, target_away
    ):
        return score

    if identities_match(meeting.home_team, target_away) and identities_match(
        meeting.away_team, target_home
    ):
        return score[1], score[0]

    raise ValueError("A usable H2H meeting must match the target team pair")


# Retourne les flags de qualité communs aux features sportives calculées sur U.
def build_population_u_quality_flags(
    meeting_count: int,
    only_friendlies_selected: bool,
) -> tuple[H2HQualityFlag, ...]:
    flags: list[H2HQualityFlag] = []

    if only_friendlies_selected:
        flags.append(H2HQualityFlag.H2H_ONLY_FRIENDLIES)

    if 0 < meeting_count < 3:
        flags.append(H2HQualityFlag.H2H_DEPTH_INSUFFICIENT_FOR_EXPERT)
    elif meeting_count == 3:
        flags.append(H2HQualityFlag.H2H_DEPTH_INSUFFICIENT_FOR_BTTS)

    return tuple(flags)


# Calcule les douze valeurs brutes du catalogue à partir des populations A et U.
def calculate_h2h_feature_values(
    module_input: H2HModuleInputV1,
    selection_state: H2HSelectionStateV1,
) -> dict[str, int | float | None]:
    population_a = selection_state.population_a
    population_u = selection_state.population_u
    meeting_count = len(population_u)
    values: dict[str, int | float | None] = {
        "h2h_matches_count": meeting_count,
    }

    if meeting_count == 0:
        for feature_name in H2H_FEATURE_NAMES[1:8]:
            values[feature_name] = None
    else:
        oriented_scores = [
            orient_regulation_score(meeting, module_input)
            for meeting in population_u
        ]
        totals = [home_goals + away_goals for home_goals, away_goals in oriented_scores]
        latest_kickoff = max(
            ensure_utc_datetime(meeting.kickoff_utc)
            for meeting in population_u
            if meeting.kickoff_utc is not None
        )
        cutoff_utc = ensure_utc_datetime(module_input.target_match.cutoff_utc)

        values.update(
            {
                "h2h_total_goals_avg": sum(totals) / meeting_count,
                "h2h_over_15_rate": sum(total >= 2 for total in totals)
                / meeting_count,
                "h2h_over_25_rate": sum(total >= 3 for total in totals)
                / meeting_count,
                "h2h_btts_rate": sum(
                    home_goals >= 1 and away_goals >= 1
                    for home_goals, away_goals in oriented_scores
                )
                / meeting_count,
                "h2h_home_team_scored_rate": sum(
                    home_goals >= 1 for home_goals, _ in oriented_scores
                )
                / meeting_count,
                "h2h_away_team_scored_rate": sum(
                    away_goals >= 1 for _, away_goals in oriented_scores
                )
                / meeting_count,
                "h2h_days_since_last_meeting": int(
                    (cutoff_utc - latest_kickoff).total_seconds() // 86400
                ),
            }
        )

    population_a_count = len(population_a)
    if population_a_count == 0:
        values["h2h_identity_resolved_rate"] = None
        values["h2h_reliable_score_rate"] = None
    else:
        values["h2h_identity_resolved_rate"] = sum(
            meeting_identities_are_resolved(candidate.meeting)
            for candidate in population_a
        ) / population_a_count
        values["h2h_reliable_score_rate"] = sum(
            meeting_has_reliable_regulation_score(candidate.meeting)
            for candidate in population_a
        ) / population_a_count

    if meeting_count == 0:
        values["h2h_official_match_rate"] = None
        values["h2h_neutral_ground_unknown_rate"] = None
    else:
        values["h2h_official_match_rate"] = sum(
            meeting.competition.official_status == H2HOfficialStatus.OFFICIAL
            for meeting in population_u
        ) / meeting_count
        values["h2h_neutral_ground_unknown_rate"] = sum(
            meeting.venue_context.neutral_ground == H2HTriState.UNKNOWN
            for meeting in population_u
        ) / meeting_count

    return values


# Transforme les valeurs brutes en features typées avec lignée et état de manque.
def build_h2h_feature_contracts(
    values: dict[str, int | float | None],
    selection_state: H2HSelectionStateV1,
) -> tuple[H2HFeatureValueV1, ...]:
    population_a_ids = tuple(
        get_meeting_lineage_id(candidate.meeting)
        for candidate in selection_state.population_a
    )
    population_u_ids = tuple(
        get_meeting_lineage_id(meeting)
        for meeting in selection_state.population_u
    )
    population_u_flags = build_population_u_quality_flags(
        meeting_count=len(selection_state.population_u),
        only_friendlies_selected=selection_state.only_friendlies_selected,
    )
    features: list[H2HFeatureValueV1] = []

    for feature_name in H2H_FEATURE_NAMES:
        feature_spec = get_h2h_feature_spec(feature_name)
        source_ids = (
            population_a_ids
            if feature_spec.population == H2H_POPULATION_A
            else population_u_ids
        )
        value = values[feature_name]
        missing_state = None
        if value is None:
            missing_state = (
                H2H_MISSING_NO_DEDUPLICATED_CANDIDATE
                if feature_spec.population == H2H_POPULATION_A
                else H2H_MISSING_NO_USABLE_MEETING
            )

        features.append(
            H2HFeatureValueV1(
                name=feature_name,
                value=value,
                data_type=feature_spec.data_type,
                unit=feature_spec.unit,
                feature_version=H2H_FEATURE_SET_VERSION,
                meeting_count_used=(
                    len(selection_state.population_a)
                    if feature_spec.population == H2H_POPULATION_A
                    else len(selection_state.population_u)
                ),
                source_meeting_ids=source_ids if value is not None else (),
                missing_state=missing_state,
                quality_flags=(
                    population_u_flags
                    if feature_spec.population == H2H_POPULATION_U
                    else ()
                ),
            )
        )

    return tuple(features)


# Construit une anomalie structurée uniquement lorsque des rencontres sont concernées.
def build_issue(
    code: H2HIssueCode,
    severity: H2HIssueSeverity,
    scope: str,
    message: str,
    affected_meeting_ids: tuple[str, ...] = (),
) -> H2HModuleIssueV1:
    return H2HModuleIssueV1(
        code=code,
        severity=severity,
        scope=scope,
        message=message,
        affected_meeting_ids=affected_meeting_ids,
    )


# Construit les anomalies de sélection, de source et de qualité observées.
def build_h2h_issues(
    module_input: H2HModuleInputV1,
    selection_state: H2HSelectionStateV1,
) -> tuple[H2HModuleIssueV1, ...]:
    issues: list[H2HModuleIssueV1] = []

    if selection_state.temporal_violation_ids:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_TEMPORAL_VIOLATION,
                H2HIssueSeverity.MAJOR,
                "selection.temporal",
                "One or more candidate meetings are missing a kickoff or are not strictly before the cutoff.",
                selection_state.temporal_violation_ids,
            )
        )

    if selection_state.target_excluded_ids:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_TARGET_MATCH_INCLUDED,
                H2HIssueSeverity.MAJOR,
                "selection.target_match",
                "The target match was present in the candidate meetings and was excluded.",
                selection_state.target_excluded_ids,
            )
        )

    if selection_state.identity_rejected_ids:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_TEAM_IDENTITY_AMBIGUOUS,
                H2HIssueSeverity.MAJOR,
                "selection.identity",
                "One or more candidates do not contain two resolved target identities.",
                selection_state.identity_rejected_ids,
            )
        )

    if selection_state.score_rejected_ids:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_SCORE_UNRELIABLE,
                H2HIssueSeverity.MAJOR,
                "selection.score",
                "One or more candidates do not expose a reliable regulation-time score.",
                selection_state.score_rejected_ids,
            )
        )

    if selection_state.duplicate_conflict_ids:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_DUPLICATE_CONFLICT,
                H2HIssueSeverity.MAJOR,
                "selection.deduplication",
                "Conflicting duplicate candidates were excluded from the usable population.",
                selection_state.duplicate_conflict_ids,
            )
        )

    if selection_state.competition_rejected_ids:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_COMPETITION_CONTEXT_MISSING,
                H2HIssueSeverity.MAJOR,
                "selection.competition",
                "One or more candidates have an unknown or unsupported competition context.",
                selection_state.competition_rejected_ids,
            )
        )

    neutral_unknown_ids = tuple(
        get_meeting_lineage_id(meeting)
        for meeting in selection_state.population_u
        if meeting.venue_context.neutral_ground == H2HTriState.UNKNOWN
    )
    if neutral_unknown_ids:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_NEUTRAL_GROUND_UNKNOWN,
                H2HIssueSeverity.MINOR,
                "quality.venue",
                "Neutral-ground status is unknown for one or more selected meetings.",
                neutral_unknown_ids,
            )
        )

    unavailable_providers = tuple(
        provider.value
        for provider, status in module_input.acquisition_context.provider_results
        if status
        in {
            H2HProviderResultStatus.UNAVAILABLE,
            H2HProviderResultStatus.ERROR,
        }
    )
    if unavailable_providers:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_SOURCE_UNAVAILABLE,
                H2HIssueSeverity.MAJOR,
                "acquisition.provider",
                "Unavailable H2H providers: " + ", ".join(unavailable_providers),
            )
        )

    if not selection_state.population_u:
        issues.append(
            build_issue(
                H2HIssueCode.H2H_NO_ELIGIBLE_MEETING,
                H2HIssueSeverity.MAJOR,
                "selection.usable_population",
                "No candidate meeting is eligible for the H2H feature population.",
            )
        )

    return tuple(issues)


# Convertit un taux de couverture en niveau de qualité lisible.
def quality_level_from_rate(rate: float | None) -> H2HQualityLevel:
    if rate is None:
        return H2HQualityLevel.UNKNOWN
    if rate == 1.0:
        return H2HQualityLevel.GOOD
    if rate > 0.0:
        return H2HQualityLevel.PARTIAL
    return H2HQualityLevel.POOR


# Évalue la fiabilité des fournisseurs et du cache utilisés par l'entrée.
def build_source_reliability(
    module_input: H2HModuleInputV1,
) -> H2HQualityLevel:
    statuses = tuple(
        status for _, status in module_input.acquisition_context.provider_results
    )
    if not statuses:
        return H2HQualityLevel.UNKNOWN
    if any(
        status in {H2HProviderResultStatus.ERROR, H2HProviderResultStatus.UNAVAILABLE}
        for status in statuses
    ):
        return H2HQualityLevel.POOR
    if (
        any(status == H2HProviderResultStatus.PARTIAL for status in statuses)
        or module_input.acquisition_context.assembled_from_cache
    ):
        return H2HQualityLevel.PARTIAL
    return H2HQualityLevel.GOOD


# Évalue la couverture d'un attribut de contexte sur la population utilisable.
def build_context_coverage(
    known_count: int,
    meeting_count: int,
) -> H2HQualityLevel:
    if meeting_count == 0:
        return H2HQualityLevel.UNKNOWN
    return quality_level_from_rate(known_count / meeting_count)


# Construit le rapport multidimensionnel sans score global non calibré.
def build_h2h_quality_report(
    module_input: H2HModuleInputV1,
    selection_state: H2HSelectionStateV1,
    features: tuple[H2HFeatureValueV1, ...],
    issues: tuple[H2HModuleIssueV1, ...],
) -> H2HQualityReportV1:
    population_a_count = len(selection_state.population_a)
    population_u_count = len(selection_state.population_u)
    identity_rate = (
        sum(
            meeting_identities_are_resolved(candidate.meeting)
            for candidate in selection_state.population_a
        )
        / population_a_count
        if population_a_count
        else None
    )
    reliable_score_rate = (
        sum(
            meeting_has_reliable_regulation_score(candidate.meeting)
            for candidate in selection_state.population_a
        )
        / population_a_count
        if population_a_count
        else None
    )
    competition_known_count = sum(
        meeting.competition.category != H2HCompetitionCategory.UNKNOWN
        and meeting.competition.official_status != H2HOfficialStatus.UNKNOWN
        for meeting in selection_state.population_u
    )
    venue_known_count = sum(
        meeting.venue_context.neutral_ground != H2HTriState.UNKNOWN
        for meeting in selection_state.population_u
    )
    tie_known_count = sum(
        meeting.tie_context.format.value != "UNKNOWN"
        for meeting in selection_state.population_u
    )
    non_null_feature_count = sum(feature.value is not None for feature in features)
    data_completeness = quality_level_from_rate(
        non_null_feature_count / len(features) if features else None
    )
    temporal_integrity = (
        H2HQualityLevel.GOOD
        if not selection_state.temporal_violation_ids
        else H2HQualityLevel.PARTIAL
    )
    identity_quality = quality_level_from_rate(identity_rate)
    score_reliability = quality_level_from_rate(reliable_score_rate)
    source_reliability = build_source_reliability(module_input)
    competition_coverage = build_context_coverage(
        competition_known_count,
        population_u_count,
    )
    venue_coverage = build_context_coverage(
        venue_known_count,
        population_u_count,
    )
    tie_coverage = build_context_coverage(
        tie_known_count,
        population_u_count,
    )

    dimensions = (
        temporal_integrity,
        identity_quality,
        source_reliability,
        score_reliability,
        competition_coverage,
        venue_coverage,
        tie_coverage,
        data_completeness,
    )
    if population_u_count == 0:
        overall_status = (
            H2HQualityLevel.POOR
            if selection_state.candidate_count > 0
            else H2HQualityLevel.UNKNOWN
        )
    elif (
        all(level == H2HQualityLevel.GOOD for level in dimensions)
        and not selection_state.only_friendlies_selected
        and not issues
    ):
        overall_status = H2HQualityLevel.GOOD
    else:
        overall_status = H2HQualityLevel.PARTIAL

    return H2HQualityReportV1(
        overall_status=overall_status,
        overall_score=None,
        temporal_integrity=temporal_integrity,
        identity_quality=identity_quality,
        source_reliability=source_reliability,
        score_reliability=score_reliability,
        competition_context_coverage=competition_coverage,
        venue_context_coverage=venue_coverage,
        tie_context_coverage=tie_coverage,
        data_completeness=data_completeness,
        issues=issues,
    )


# Construit la readiness d'un consommateur sans rendre le H2H obligatoire globalement.
def build_consumer_readiness(
    consumer_id: H2HConsumerId,
    features: tuple[H2HFeatureValueV1, ...],
    quality_report: H2HQualityReportV1,
    issues: tuple[H2HModuleIssueV1, ...],
    meeting_count: int,
) -> H2HConsumerReadinessV1:
    required_features = get_h2h_consumer_required_features(consumer_id)
    feature_map = {feature.name: feature for feature in features}
    available_features = tuple(
        feature_name
        for feature_name in required_features
        if feature_map[feature_name].value is not None
    )
    missing_features = tuple(
        feature_name
        for feature_name in required_features
        if feature_map[feature_name].value is None
    )
    minimum_depth = H2H_CONSUMER_MINIMUM_DEPTH[consumer_id]

    if meeting_count < minimum_depth or missing_features:
        status = H2HConsumerReadinessStatus.NOT_READY
    elif quality_report.overall_status == H2HQualityLevel.GOOD:
        status = H2HConsumerReadinessStatus.READY
    else:
        status = H2HConsumerReadinessStatus.DEGRADED

    blocking_issues = tuple(
        issue
        for issue in issues
        if meeting_count == 0
        and issue.code
        in {
            H2HIssueCode.H2H_NO_ELIGIBLE_MEETING,
            H2HIssueCode.H2H_SOURCE_UNAVAILABLE,
        }
    )
    warnings = tuple(issue for issue in issues if issue not in blocking_issues)

    return H2HConsumerReadinessV1(
        consumer_id=consumer_id,
        status=status,
        available_features=available_features,
        missing_features=missing_features,
        blocking_issues=blocking_issues,
        warnings=warnings,
    )


# Construit le résumé cohérent de toutes les étapes de sélection.
def build_meeting_selection_summary(
    module_input: H2HModuleInputV1,
    selection_state: H2HSelectionStateV1,
) -> H2HMeetingSelectionSummaryV1:
    selected_kickoffs = tuple(
        ensure_utc_datetime(meeting.kickoff_utc)
        for meeting in selection_state.population_u
        if meeting.kickoff_utc is not None
    )
    selected_ids = tuple(
        get_meeting_lineage_id(meeting)
        for meeting in selection_state.population_u
    )
    identity_eligible_count = sum(
        meeting_identities_are_resolved(candidate.meeting)
        and meeting_matches_target_pair(candidate.meeting, module_input)
        for candidate in selection_state.population_a
    )
    excluded_count = max(
        0,
        selection_state.candidate_count - len(selection_state.population_u),
    )
    exclusion_counts: list[tuple[H2HExclusionReason, int]] = []
    if selection_state.club_friendly_excluded_count:
        exclusion_counts.append(
            (
                H2HExclusionReason.H2H_CLUB_FRIENDLY_EXCLUDED,
                selection_state.club_friendly_excluded_count,
            )
        )

    return H2HMeetingSelectionSummaryV1(
        domain_profile=module_input.processing_policy.domain_profile,
        candidate_count=selection_state.candidate_count,
        temporally_eligible_count=selection_state.temporally_eligible_count,
        identity_eligible_count=identity_eligible_count,
        deduplicated_count=len(selection_state.population_a),
        usable_count=len(selection_state.population_u),
        excluded_count=excluded_count,
        exclusion_counts_by_reason=tuple(exclusion_counts),
        newest_meeting_utc=max(selected_kickoffs) if selected_kickoffs else None,
        oldest_meeting_utc=min(selected_kickoffs) if selected_kickoffs else None,
        selected_meeting_ids=selected_ids,
    )


# Transforme récursivement un contrat en structure JSON stable pour son empreinte.
def normalize_for_hash(value: Any) -> Any:
    if is_dataclass(value):
        return normalize_for_hash(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return ensure_utc_datetime(value).isoformat()
    if isinstance(value, dict):
        return {
            str(key): normalize_for_hash(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [normalize_for_hash(item) for item in value]
    return value


# Calcule une empreinte SHA-256 reproductible du contrat d'entrée.
def build_input_contract_hash(module_input: H2HModuleInputV1) -> str:
    payload = json.dumps(
        normalize_for_hash(module_input),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# Construit une valeur versionnée unique ou une trace explicite de versions multiples.
def collapse_versions(versions: Iterable[str], default: str) -> str:
    unique_versions = tuple(sorted({version for version in versions if version}))
    if not unique_versions:
        return default
    if len(unique_versions) == 1:
        return unique_versions[0]
    return "multiple:" + ",".join(unique_versions)


# Construit la provenance complète du résultat à partir des candidats et politiques utilisés.
def build_result_provenance(
    module_input: H2HModuleInputV1,
    selection_state: H2HSelectionStateV1,
) -> H2HResultProvenanceV1:
    all_provenance = tuple(
        provenance
        for candidate in selection_state.population_a
        for provenance in candidate.meeting.provenance
    )
    source_providers = tuple(
        sorted({item.provider for item in all_provenance}, key=lambda item: item.value)
    )
    snapshot_ids = tuple(
        sorted(
            {
                item.raw_payload_hash or item.provider_match_id
                for item in all_provenance
                if item.raw_payload_hash or item.provider_match_id
            }
        )
    )
    identity_versions = tuple(
        team.identity_resolution.resolver_version
        for candidate in selection_state.population_a
        for team in (candidate.meeting.home_team, candidate.meeting.away_team)
    )

    return H2HResultProvenanceV1(
        input_contract_hash=build_input_contract_hash(module_input),
        source_providers=source_providers,
        provider_snapshot_ids=snapshot_ids,
        normalization_version=collapse_versions(
            (item.normalization_version for item in all_provenance),
            default="unknown",
        ),
        identity_resolver_version=collapse_versions(
            identity_versions,
            default="unknown",
        ),
        processing_policy_version=module_input.processing_policy.policy_version,
        deduplication_policy_version=H2H_DEDUPLICATION_POLICY_VERSION,
        feature_builder_version=H2H_FEATURE_BUILDER_VERSION,
    )


# Vérifie les invariants minimaux du contrat avant tout calcul de feature.
def validate_h2h_module_input(
    module_input: H2HModuleInputV1,
) -> tuple[str, ...]:
    errors: list[str] = []
    cutoff_utc = ensure_utc_datetime(module_input.target_match.cutoff_utc)
    kickoff_utc = ensure_utc_datetime(module_input.target_match.kickoff_utc)

    if cutoff_utc > kickoff_utc:
        errors.append("cutoff_utc must be earlier than or equal to target kickoff")

    if identities_match(
        module_input.target_teams.home_team,
        module_input.target_teams.away_team,
    ):
        errors.append("target home and away teams must be distinct")

    if (
        module_input.target_teams.home_team.entity_type
        != module_input.target_match.domain
        or module_input.target_teams.away_team.entity_type
        != module_input.target_match.domain
    ):
        errors.append("target team domains must match the target match domain")

    expected_profile = (
        H2HDomainProfile.NATIONAL_TEAM_H2H_V1
        if module_input.target_match.domain.value == "NATIONAL_TEAM"
        else H2HDomainProfile.CLUB_H2H_V1
    )
    if module_input.processing_policy.domain_profile != expected_profile:
        errors.append("processing profile must match the target match domain")

    return tuple(errors)


# Construit une sortie INVALID traçable sans lever d'exception métier.
def build_invalid_h2h_result(
    module_input: H2HModuleInputV1,
    errors: tuple[str, ...],
    computed_at_utc: datetime,
) -> H2HModuleResultV1:
    selection_state = H2HSelectionStateV1(
        population_a=(),
        population_u=(),
        candidate_count=len(module_input.candidate_meetings),
        temporally_eligible_count=0,
        target_excluded_ids=(),
        temporal_violation_ids=(),
        identity_rejected_ids=(),
        score_rejected_ids=(),
        duplicate_conflict_ids=(),
        competition_rejected_ids=(),
        club_friendly_excluded_count=0,
        only_friendlies_selected=False,
    )
    values = {name: None for name in H2H_FEATURE_NAMES}
    values["h2h_matches_count"] = 0
    features = build_h2h_feature_contracts(values, selection_state)
    issues = tuple(
        build_issue(
            H2HIssueCode.H2H_TEMPORAL_VIOLATION,
            H2HIssueSeverity.BLOCKER,
            "input.contract",
            error,
        )
        for error in errors
    )
    quality_report = H2HQualityReportV1(
        overall_status=H2HQualityLevel.POOR,
        overall_score=None,
        temporal_integrity=H2HQualityLevel.POOR,
        identity_quality=H2HQualityLevel.POOR,
        source_reliability=build_source_reliability(module_input),
        score_reliability=H2HQualityLevel.UNKNOWN,
        competition_context_coverage=H2HQualityLevel.UNKNOWN,
        venue_context_coverage=H2HQualityLevel.UNKNOWN,
        tie_context_coverage=H2HQualityLevel.UNKNOWN,
        data_completeness=H2HQualityLevel.POOR,
        issues=issues,
    )

    readiness = tuple(
        H2HConsumerReadinessV1(
            consumer_id=consumer_id,
            status=H2HConsumerReadinessStatus.NOT_READY,
            available_features=("h2h_matches_count",),
            missing_features=tuple(
                name
                for name in get_h2h_consumer_required_features(consumer_id)
                if name != "h2h_matches_count"
            ),
            blocking_issues=issues,
            warnings=(),
        )
        for consumer_id in (H2HConsumerId.OVER_1_5, H2HConsumerId.BTTS)
    )

    return H2HModuleResultV1(
        contract_version=H2H_RESULT_CONTRACT_VERSION,
        request_id=module_input.request_id,
        target_match_id=module_input.target_match.canonical_match_id,
        computed_at_utc=computed_at_utc,
        cutoff_utc=ensure_utc_datetime(module_input.target_match.cutoff_utc),
        module_status=H2HModuleStatus.INVALID,
        module_outcome=H2HModuleOutcome.H2H_MODULE_ABSTAIN,
        feature_set_version=H2H_FEATURE_SET_VERSION,
        features=features,
        meeting_selection_summary=build_meeting_selection_summary(
            module_input,
            selection_state,
        ),
        quality_report=quality_report,
        readiness_by_consumer=readiness,
        missing_features=tuple(
            feature.name for feature in features if feature.value is None
        ),
        warnings=(),
        abstention_reasons=issues,
        provenance=build_result_provenance(module_input, selection_state),
    )


# Construit le résultat H2H complet sans produire de décision sportive.
def build_h2h_module_result(
    module_input: H2HModuleInputV1,
    clock: H2HClock = utc_now,
) -> H2HModuleResultV1:
    computed_at_utc = ensure_utc_datetime(clock())
    validation_errors = validate_h2h_module_input(module_input)
    if validation_errors:
        return build_invalid_h2h_result(
            module_input=module_input,
            errors=validation_errors,
            computed_at_utc=computed_at_utc,
        )

    selection_state = select_h2h_meetings(module_input)
    values = calculate_h2h_feature_values(module_input, selection_state)
    features = build_h2h_feature_contracts(values, selection_state)
    issues = build_h2h_issues(module_input, selection_state)
    quality_report = build_h2h_quality_report(
        module_input=module_input,
        selection_state=selection_state,
        features=features,
        issues=issues,
    )
    meeting_count = len(selection_state.population_u)

    if meeting_count == 0:
        module_status = H2HModuleStatus.UNAVAILABLE
        module_outcome = H2HModuleOutcome.H2H_MODULE_ABSTAIN
    elif meeting_count >= 4 and quality_report.overall_status == H2HQualityLevel.GOOD:
        module_status = H2HModuleStatus.READY
        module_outcome = H2HModuleOutcome.FEATURES_PRODUCED
    else:
        module_status = H2HModuleStatus.DEGRADED
        module_outcome = H2HModuleOutcome.FEATURES_PRODUCED

    readiness = tuple(
        build_consumer_readiness(
            consumer_id=consumer_id,
            features=features,
            quality_report=quality_report,
            issues=issues,
            meeting_count=meeting_count,
        )
        for consumer_id in (H2HConsumerId.OVER_1_5, H2HConsumerId.BTTS)
    )
    warnings = tuple(
        issue
        for issue in issues
        if module_outcome == H2HModuleOutcome.FEATURES_PRODUCED
        or issue.code not in {
            H2HIssueCode.H2H_NO_ELIGIBLE_MEETING,
            H2HIssueCode.H2H_SOURCE_UNAVAILABLE,
        }
    )
    abstention_reasons = (
        tuple(
            issue
            for issue in issues
            if issue.code
            in {
                H2HIssueCode.H2H_NO_ELIGIBLE_MEETING,
                H2HIssueCode.H2H_SOURCE_UNAVAILABLE,
            }
        )
        if module_outcome == H2HModuleOutcome.H2H_MODULE_ABSTAIN
        else ()
    )

    return H2HModuleResultV1(
        contract_version=H2H_RESULT_CONTRACT_VERSION,
        request_id=module_input.request_id,
        target_match_id=module_input.target_match.canonical_match_id,
        computed_at_utc=computed_at_utc,
        cutoff_utc=ensure_utc_datetime(module_input.target_match.cutoff_utc),
        module_status=module_status,
        module_outcome=module_outcome,
        feature_set_version=H2H_FEATURE_SET_VERSION,
        features=features,
        meeting_selection_summary=build_meeting_selection_summary(
            module_input,
            selection_state,
        ),
        quality_report=quality_report,
        readiness_by_consumer=readiness,
        missing_features=tuple(
            feature.name for feature in features if feature.value is None
        ),
        warnings=warnings,
        abstention_reasons=abstention_reasons,
        provenance=build_result_provenance(module_input, selection_state),
    )


# Schéma de communication :
# h2h_acquisition_service.py
#   -> fournit H2HModuleInputV1 à h2h_feature_builder.py
# h2h_feature_catalog.py
#   -> fournit les 12 features, fenêtres, profondeurs et politiques de profil
# h2h_feature_builder.py
#   -> filtre, déduplique, réoriente les scores et produit H2HModuleResultV1
# backend/tests/test_v19.py
#   -> vérifie formules, profils, qualité, readiness et valeurs manquantes
# futurs experts Over 1.5 et BTTS
#   -> consommeront seulement readiness_by_consumer et les features autorisées
#   -> aucune recommandation sportive n'est produite par ce fichier
