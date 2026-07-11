# Rôle du fichier :
# Cet adaptateur transforme un match H2H FlashScore déjà normalisé en contrat H2HMeetingV1.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.v19.domain.h2h_contracts import (
    CompetitionContextV1,
    H2HMeetingV1,
    IdentityResolutionV1,
    ScoreContextV1,
    SourceProvenanceV1,
    TargetTeamsV1,
    TeamIdentityV1,
    TieContextV1,
    VenueContextV1,
)
from app.v19.domain.h2h_enums import (
    H2HCacheState,
    H2HCompetitionCategory,
    H2HEntityType,
    H2HIdentityMethod,
    H2HIdentityStatus,
    H2HLegNumber,
    H2HNormalizationState,
    H2HOfficialStatus,
    H2HProvider,
    H2HQualityLevel,
    H2HScoreReliability,
    H2HScoreType,
    H2HTieFormat,
    H2HTriState,
)


FLASHSCORE_H2H_ENDPOINT = "/matches/h2h"
FLASHSCORE_H2H_NORMALIZATION_VERSION = "v19.h2h.flashscore-adapter.1"
FLASHSCORE_H2H_IDENTITY_RESOLVER_VERSION = "v19.h2h.identity.flashscore.1"


# Convertit une valeur non vide en identifiant texte stable pour les contrats V19.
def normalize_optional_identifier(value: Any) -> str | None:
    if value is None:
        return None

    normalized_value = str(value).strip()
    return normalized_value or None


# Normalise un nom uniquement pour comparer des identités sans modifier le nom affiché.
def normalize_identity_name(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


# Convertit une date ISO ou datetime en datetime UTC consciente du fuseau.
def parse_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed_value = value
    elif value:
        try:
            parsed_value = datetime.fromisoformat(
                str(value).strip().replace("Z", "+00:00")
            )
        except ValueError:
            return None
    else:
        return None

    if parsed_value.tzinfo is None:
        parsed_value = parsed_value.replace(tzinfo=timezone.utc)

    return parsed_value.astimezone(timezone.utc)


# Recherche l'identifiant FlashScore déclaré dans une identité d'équipe V19.
def get_flashscore_team_id(team: TeamIdentityV1) -> str | None:
    for provider, provider_id in team.provider_ids:
        if provider == H2HProvider.FLASHSCORE:
            return normalize_optional_identifier(provider_id)

    return None


# Construit une copie traçable d'une identité cible résolue par son identifiant fournisseur.
def build_provider_resolved_identity(
    target_team: TeamIdentityV1,
    provider_team_id: str,
    observed_name: str,
) -> TeamIdentityV1:
    return TeamIdentityV1(
        canonical_team_id=target_team.canonical_team_id,
        entity_type=target_team.entity_type,
        provider_ids=((H2HProvider.FLASHSCORE, provider_team_id),),
        display_name=observed_name or target_team.display_name,
        normalized_name=normalize_identity_name(
            observed_name or target_team.normalized_name
        ),
        country_code=target_team.country_code,
        identity_resolution=IdentityResolutionV1(
            status=H2HIdentityStatus.RESOLVED,
            method=H2HIdentityMethod.PROVIDER_ID_EXACT,
            confidence_score=None,
            resolver_version=FLASHSCORE_H2H_IDENTITY_RESOLVER_VERSION,
            evidence=(("flashscore_team_id", provider_team_id),),
        ),
    )


# Construit une identité traçable lorsque seul le nom normalisé correspond à une cible.
def build_name_resolved_identity(
    target_team: TeamIdentityV1,
    provider_team_id: str | None,
    observed_name: str,
) -> TeamIdentityV1:
    provider_ids = (
        ((H2HProvider.FLASHSCORE, provider_team_id),)
        if provider_team_id is not None
        else ()
    )

    return TeamIdentityV1(
        canonical_team_id=target_team.canonical_team_id,
        entity_type=target_team.entity_type,
        provider_ids=provider_ids,
        display_name=observed_name or target_team.display_name,
        normalized_name=normalize_identity_name(
            observed_name or target_team.normalized_name
        ),
        country_code=target_team.country_code,
        identity_resolution=IdentityResolutionV1(
            status=H2HIdentityStatus.RESOLVED,
            method=H2HIdentityMethod.NORMALIZED_NAME,
            confidence_score=None,
            resolver_version=FLASHSCORE_H2H_IDENTITY_RESOLVER_VERSION,
            evidence=(("normalized_name", normalize_identity_name(observed_name)),),
        ),
    )


# Construit une identité non résolue sans inventer d'identifiant canonique ni de pays.
def build_unresolved_identity(
    provider_team_id: str | None,
    observed_name: str,
    entity_type: H2HEntityType,
) -> TeamIdentityV1:
    provider_ids = (
        ((H2HProvider.FLASHSCORE, provider_team_id),)
        if provider_team_id is not None
        else ()
    )

    return TeamIdentityV1(
        canonical_team_id=None,
        entity_type=entity_type,
        provider_ids=provider_ids,
        display_name=observed_name,
        normalized_name=normalize_identity_name(observed_name),
        country_code=None,
        identity_resolution=IdentityResolutionV1(
            status=H2HIdentityStatus.UNRESOLVED,
            method=H2HIdentityMethod.UNRESOLVED,
            confidence_score=None,
            resolver_version=FLASHSCORE_H2H_IDENTITY_RESOLVER_VERSION,
            evidence=(),
        ),
    )


# Résout une équipe historique contre les deux identités cibles par ID puis par nom.
def resolve_flashscore_team_identity(
    team_data: dict[str, Any],
    target_teams: TargetTeamsV1,
    entity_type: H2HEntityType,
) -> TeamIdentityV1:
    provider_team_id = normalize_optional_identifier(team_data.get("id"))
    observed_name = str(team_data.get("name") or "").strip()

    for target_team in (target_teams.home_team, target_teams.away_team):
        target_provider_id = get_flashscore_team_id(target_team)
        if (
            provider_team_id is not None
            and target_provider_id is not None
            and provider_team_id == target_provider_id
        ):
            return build_provider_resolved_identity(
                target_team=target_team,
                provider_team_id=provider_team_id,
                observed_name=observed_name,
            )

    observed_normalized_name = normalize_identity_name(observed_name)
    if observed_normalized_name:
        for target_team in (target_teams.home_team, target_teams.away_team):
            target_names = {
                normalize_identity_name(target_team.display_name),
                normalize_identity_name(target_team.normalized_name),
            }
            if observed_normalized_name in target_names:
                return build_name_resolved_identity(
                    target_team=target_team,
                    provider_team_id=provider_team_id,
                    observed_name=observed_name,
                )

    return build_unresolved_identity(
        provider_team_id=provider_team_id,
        observed_name=observed_name,
        entity_type=entity_type,
    )


# Construit un contexte de compétition conservateur à partir des champs réellement disponibles.
def build_flashscore_competition_context(
    competition_data: dict[str, Any],
    entity_type: H2HEntityType,
) -> CompetitionContextV1:
    provider_competition_id = normalize_optional_identifier(
        competition_data.get("id")
    )
    provider_ids = (
        ((H2HProvider.FLASHSCORE, provider_competition_id),)
        if provider_competition_id is not None
        else ()
    )
    competition_name = str(
        competition_data.get("name") or competition_data.get("code") or ""
    ).strip()

    return CompetitionContextV1(
        canonical_competition_id=None,
        provider_competition_ids=provider_ids,
        name=competition_name,
        domain=entity_type,
        category=H2HCompetitionCategory.UNKNOWN,
        season=None,
        phase=None,
        round=None,
        official_status=H2HOfficialStatus.UNKNOWN,
    )


# Extrait un score final affiché uniquement lorsque les deux valeurs sont des entiers valides.
def extract_displayed_score(match_data: dict[str, Any]) -> tuple[int, int] | None:
    score_data = match_data.get("score")
    if not isinstance(score_data, dict):
        return None

    full_time = score_data.get("fullTime")
    if not isinstance(full_time, dict):
        return None

    home_score = full_time.get("home")
    away_score = full_time.get("away")

    if isinstance(home_score, bool) or isinstance(away_score, bool):
        return None

    if not isinstance(home_score, int) or not isinstance(away_score, int):
        return None

    if home_score < 0 or away_score < 0:
        return None

    return home_score, away_score


# Construit un score prudent sans déduire le temps réglementaire d'un score final ambigu.
def build_flashscore_score_context(
    match_data: dict[str, Any],
) -> ScoreContextV1:
    displayed_score = extract_displayed_score(match_data)

    return ScoreContextV1(
        score_type=H2HScoreType.UNKNOWN,
        regulation_time=None,
        extra_time=None,
        penalties=None,
        displayed_final_score=displayed_score,
        score_reliability=(
            H2HScoreReliability.PARTIAL
            if displayed_score is not None
            else H2HScoreReliability.UNKNOWN
        ),
    )


# Construit un contexte de terrain inconnu sans transformer une absence en terrain non neutre.
def build_unknown_venue_context() -> VenueContextV1:
    return VenueContextV1(
        neutral_ground=H2HTriState.UNKNOWN,
        venue_name=None,
        venue_country=None,
        source_reliability=H2HQualityLevel.UNKNOWN,
    )


# Construit un contexte aller-retour inconnu tant que la source ne fournit pas cette information.
def build_unknown_tie_context() -> TieContextV1:
    return TieContextV1(
        format=H2HTieFormat.UNKNOWN,
        tie_id=None,
        leg_number=H2HLegNumber.UNKNOWN,
        aggregate_score_before=None,
        aggregate_score_after=None,
        detection_method=None,
    )


# Convertit une valeur de cache optionnelle vers le vocabulaire contrôlé V19.
def normalize_cache_state(value: Any) -> H2HCacheState:
    if isinstance(value, H2HCacheState):
        return value

    try:
        return H2HCacheState(str(value))
    except (TypeError, ValueError):
        return H2HCacheState.UNKNOWN


# Détermine la qualité de mapping à partir des deux résolutions d'identité observées.
def compute_mapping_quality(
    home_team: TeamIdentityV1,
    away_team: TeamIdentityV1,
) -> H2HQualityLevel:
    methods = {
        home_team.identity_resolution.method,
        away_team.identity_resolution.method,
    }
    statuses = {
        home_team.identity_resolution.status,
        away_team.identity_resolution.status,
    }

    if statuses == {H2HIdentityStatus.RESOLVED} and methods == {
        H2HIdentityMethod.PROVIDER_ID_EXACT
    }:
        return H2HQualityLevel.GOOD

    if H2HIdentityStatus.UNRESOLVED in statuses:
        return H2HQualityLevel.POOR

    return H2HQualityLevel.PARTIAL


# Détermine l'état de normalisation sans masquer les contextes absents ou ambigus.
def compute_normalization_state(
    kickoff_utc: datetime | None,
    competition: CompetitionContextV1,
    score_context: ScoreContextV1,
    mapping_quality: H2HQualityLevel,
) -> H2HNormalizationState:
    if kickoff_utc is None or mapping_quality == H2HQualityLevel.POOR:
        return H2HNormalizationState.INVALID

    has_partial_context = (
        not competition.name
        or competition.category == H2HCompetitionCategory.UNKNOWN
        or score_context.score_reliability != H2HScoreReliability.RELIABLE
    )

    if has_partial_context or mapping_quality == H2HQualityLevel.PARTIAL:
        return H2HNormalizationState.PARTIAL

    return H2HNormalizationState.VALID


# Retire uniquement le préfixe technique ajouté par le normaliseur historique RubyBets.
def extract_flashscore_match_id(value: Any) -> str | None:
    normalized_value = normalize_optional_identifier(value)
    if normalized_value is None:
        return None

    prefix = "flashscore_"
    if normalized_value.startswith(prefix):
        return normalized_value[len(prefix) :] or None

    return normalized_value


# Transforme un match normalisé FlashScore en confrontation H2H V19 traçable.
def adapt_flashscore_h2h_match(
    match_data: dict[str, Any],
    target_teams: TargetTeamsV1,
    entity_type: H2HEntityType,
    retrieved_at_utc: datetime,
    cache_state: H2HCacheState = H2HCacheState.UNKNOWN,
) -> H2HMeetingV1:
    home_team_data = match_data.get("homeTeam")
    away_team_data = match_data.get("awayTeam")
    competition_data = match_data.get("competition")

    if not isinstance(home_team_data, dict):
        home_team_data = {}
    if not isinstance(away_team_data, dict):
        away_team_data = {}
    if not isinstance(competition_data, dict):
        competition_data = {}

    home_team = resolve_flashscore_team_identity(
        team_data=home_team_data,
        target_teams=target_teams,
        entity_type=entity_type,
    )
    away_team = resolve_flashscore_team_identity(
        team_data=away_team_data,
        target_teams=target_teams,
        entity_type=entity_type,
    )
    competition = build_flashscore_competition_context(
        competition_data=competition_data,
        entity_type=entity_type,
    )
    kickoff_utc = parse_utc_datetime(match_data.get("utcDate"))
    score_context = build_flashscore_score_context(match_data)
    mapping_quality = compute_mapping_quality(
        home_team=home_team,
        away_team=away_team,
    )
    normalization_state = compute_normalization_state(
        kickoff_utc=kickoff_utc,
        competition=competition,
        score_context=score_context,
        mapping_quality=mapping_quality,
    )
    provider_match_id = extract_flashscore_match_id(match_data.get("id"))
    normalized_retrieved_at_utc = parse_utc_datetime(retrieved_at_utc)
    if normalized_retrieved_at_utc is None:
        normalized_retrieved_at_utc = retrieved_at_utc.replace(tzinfo=timezone.utc)
    provider_match_ids = (
        ((H2HProvider.FLASHSCORE, provider_match_id),)
        if provider_match_id is not None
        else ()
    )
    normalized_status = normalize_optional_identifier(match_data.get("status"))

    return H2HMeetingV1(
        canonical_match_id=None,
        provider_match_ids=provider_match_ids,
        kickoff_utc=kickoff_utc,
        status=(normalized_status, normalized_status),
        competition=competition,
        home_team=home_team,
        away_team=away_team,
        venue_context=build_unknown_venue_context(),
        score_context=score_context,
        tie_context=build_unknown_tie_context(),
        provenance=(
            SourceProvenanceV1(
                provider=H2HProvider.FLASHSCORE,
                endpoint=FLASHSCORE_H2H_ENDPOINT,
                provider_match_id=provider_match_id,
                retrieved_at_utc=normalized_retrieved_at_utc,
                source_priority=1,
                fallback_used=False,
                cache_state=normalize_cache_state(cache_state),
                raw_payload_hash=None,
                normalization_version=FLASHSCORE_H2H_NORMALIZATION_VERSION,
            ),
        ),
        mapping_quality=mapping_quality,
        normalization_state=normalization_state,
        exclusion_reasons=(),
    )


# Schéma de communication :
# rapidapi_flashscore_client.py
#   -> fournit des matchs H2H déjà filtrés et normalisés
# flashscore_h2h_adapter.py
#   -> lit TargetTeamsV1 et le domaine du match cible
#   -> produit H2HMeetingV1 avec identités, score prudent et provenance
# h2h_acquisition_service.py
#   -> assemble les confrontations produites dans H2HModuleInputV1
#   -> aucune feature ni recommandation sportive n'est calculée ici
