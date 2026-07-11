# Rôle du fichier :
# Cet adaptateur transforme un match RubyBets normalisé en contrats cibles H2H V19 traçables.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.rapidapi_flashscore_client import decode_flashscore_match_id
from app.v19.acquisition.flashscore_h2h_adapter import (
    classify_flashscore_competition,
    normalize_identity_name,
    normalize_optional_identifier,
    parse_utc_datetime,
)
from app.v19.domain.h2h_contracts import (
    CompetitionContextV1,
    IdentityResolutionV1,
    TargetMatchRefV1,
    TargetTeamsV1,
    TeamIdentityV1,
    TieContextV1,
    VenueContextV1,
)
from app.v19.domain.h2h_enums import (
    H2HEntityType,
    H2HIdentityMethod,
    H2HIdentityStatus,
    H2HLegNumber,
    H2HProvider,
    H2HQualityLevel,
    H2HTieFormat,
    H2HTriState,
)


TARGET_MATCH_ADAPTER_VERSION = "v19.h2h.target-match-adapter.1"
TARGET_MATCH_IDENTITY_RESOLVER_VERSION = "v19.h2h.target-identity.1"


# Signale qu'un match normalisé ne contient pas les informations minimales du contrat cible.
class TargetMatchAdapterError(ValueError):
    pass


# Retourne la première valeur disponible parmi plusieurs clés compatibles.
def get_first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value

    return None


# Retourne le premier sous-dictionnaire disponible parmi plusieurs clés compatibles.
def get_first_mapping(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    value = get_first_value(data, *keys)
    return value if isinstance(value, dict) else {}


# Convertit un datetime technique en UTC sans dépendre de l'heure système.
def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


# Construit une identité cible à partir des identifiants RubyBets et FlashScore réellement disponibles.
def build_target_team_identity(
    team_data: dict[str, Any],
    entity_type: H2HEntityType,
) -> TeamIdentityV1:
    canonical_team_id = normalize_optional_identifier(team_data.get("id"))
    provider_team_id = normalize_optional_identifier(
        get_first_value(team_data, "sourceTeamId", "source_team_id", "team_id")
    )
    display_name = str(
        get_first_value(team_data, "name", "display_name") or ""
    ).strip()

    if not display_name:
        raise TargetMatchAdapterError("target_team_name_missing")

    provider_ids = (
        ((H2HProvider.FLASHSCORE, provider_team_id),)
        if provider_team_id is not None
        else ()
    )

    if provider_team_id is not None:
        identity_status = H2HIdentityStatus.RESOLVED
        identity_method = H2HIdentityMethod.PROVIDER_ID_EXACT
        evidence = (("flashscore_team_id", provider_team_id),)
    elif canonical_team_id is not None:
        identity_status = H2HIdentityStatus.RESOLVED
        identity_method = H2HIdentityMethod.CANONICAL_ID_EXACT
        evidence = (("rubybets_team_id", canonical_team_id),)
    else:
        identity_status = H2HIdentityStatus.UNRESOLVED
        identity_method = H2HIdentityMethod.UNRESOLVED
        evidence = ()

    return TeamIdentityV1(
        canonical_team_id=canonical_team_id,
        entity_type=entity_type,
        provider_ids=provider_ids,
        display_name=display_name,
        normalized_name=normalize_identity_name(display_name),
        country_code=normalize_optional_identifier(
            get_first_value(team_data, "countryCode", "country_code")
        ),
        identity_resolution=IdentityResolutionV1(
            status=identity_status,
            method=identity_method,
            confidence_score=None,
            resolver_version=TARGET_MATCH_IDENTITY_RESOLVER_VERSION,
            evidence=evidence,
        ),
    )


# Construit le contexte de compétition cible sans inventer de saison, phase ou statut fournisseur absent.
def build_target_competition_context(
    match_data: dict[str, Any],
    entity_type: H2HEntityType,
) -> CompetitionContextV1:
    competition_data = get_first_mapping(match_data, "competition")
    season_data = get_first_mapping(match_data, "season")
    canonical_competition_id = normalize_optional_identifier(
        competition_data.get("id")
    )
    provider_competition_id = normalize_optional_identifier(
        get_first_value(
            competition_data,
            "sourceCompetitionId",
            "source_competition_id",
            "tournament_id",
        )
    )
    provider_ids = (
        ((H2HProvider.FLASHSCORE, provider_competition_id),)
        if provider_competition_id is not None
        else ()
    )
    competition_name = str(
        get_first_value(competition_data, "name", "code") or ""
    ).strip()
    category, official_status = classify_flashscore_competition(
        competition_data=competition_data,
        entity_type=entity_type,
    )
    phase = normalize_optional_identifier(
        get_first_value(match_data, "stage", "group")
    )
    round_value = normalize_optional_identifier(
        get_first_value(match_data, "matchday", "round")
    )
    season = normalize_optional_identifier(
        get_first_value(
            season_data,
            "sourceSeasonId",
            "source_season_id",
            "id",
        )
    )

    return CompetitionContextV1(
        canonical_competition_id=canonical_competition_id,
        provider_competition_ids=provider_ids,
        name=competition_name,
        domain=entity_type,
        category=category,
        season=season,
        phase=phase,
        round=round_value,
        official_status=official_status,
    )


# Construit un contexte de terrain inconnu lorsque le match normalisé ne transporte pas cette information.
def build_target_venue_context(match_data: dict[str, Any]) -> VenueContextV1:
    venue_data = get_first_mapping(match_data, "venue", "venue_context")
    neutral_value = get_first_value(
        venue_data,
        "neutralGround",
        "neutral_ground",
        "isNeutral",
        "is_neutral",
    )

    if neutral_value is True:
        neutral_ground = H2HTriState.TRUE
    elif neutral_value is False:
        neutral_ground = H2HTriState.FALSE
    else:
        neutral_ground = H2HTriState.UNKNOWN

    return VenueContextV1(
        neutral_ground=neutral_ground,
        venue_name=normalize_optional_identifier(
            get_first_value(venue_data, "name", "venue_name")
        ),
        venue_country=normalize_optional_identifier(
            get_first_value(venue_data, "country", "venue_country")
        ),
        source_reliability=(
            H2HQualityLevel.PARTIAL
            if venue_data
            else H2HQualityLevel.UNKNOWN
        ),
    )


# Construit un contexte aller-retour inconnu tant que la source du match cible ne le précise pas.
def build_target_tie_context(match_data: dict[str, Any]) -> TieContextV1:
    del match_data
    return TieContextV1(
        format=H2HTieFormat.UNKNOWN,
        tie_id=None,
        leg_number=H2HLegNumber.UNKNOWN,
        aggregate_score_before=None,
        aggregate_score_after=None,
        detection_method=None,
    )


# Extrait l'identifiant FlashScore source du match sans le confondre avec l'identifiant numérique RubyBets.
def extract_target_flashscore_match_id(match_data: dict[str, Any]) -> str | None:
    provider_match_id = normalize_optional_identifier(
        get_first_value(
            match_data,
            "sourceMatchId",
            "source_match_id",
            "flashscore_match_id",
        )
    )
    if provider_match_id is not None:
        return provider_match_id

    return normalize_optional_identifier(
        decode_flashscore_match_id(get_first_value(match_data, "id", "match_id"))
    )


# Transforme le match normalisé en TargetMatchRefV1 et TargetTeamsV1 avec un cutoff explicite.
def adapt_normalized_target_match(
    match_data: dict[str, Any],
    cutoff_utc: datetime,
    entity_type: H2HEntityType,
) -> tuple[TargetMatchRefV1, TargetTeamsV1]:
    if not isinstance(match_data, dict) or not match_data:
        raise TargetMatchAdapterError("target_match_missing")

    canonical_match_id = normalize_optional_identifier(
        get_first_value(match_data, "id", "match_id")
    )
    if canonical_match_id is None:
        raise TargetMatchAdapterError("target_match_id_missing")

    kickoff_utc = parse_utc_datetime(
        get_first_value(match_data, "utcDate", "utc_date", "kickoff_utc")
    )
    if kickoff_utc is None:
        raise TargetMatchAdapterError("target_match_kickoff_missing")

    normalized_cutoff = ensure_utc_datetime(cutoff_utc)
    if normalized_cutoff > kickoff_utc:
        raise TargetMatchAdapterError("target_match_cutoff_after_kickoff")

    home_team_data = get_first_mapping(match_data, "homeTeam", "home_team")
    away_team_data = get_first_mapping(match_data, "awayTeam", "away_team")
    home_team = build_target_team_identity(home_team_data, entity_type)
    away_team = build_target_team_identity(away_team_data, entity_type)
    target_teams = TargetTeamsV1(
        home_team=home_team,
        away_team=away_team,
    )
    provider_match_id = extract_target_flashscore_match_id(match_data)
    provider_match_ids = (
        ((H2HProvider.FLASHSCORE, provider_match_id),)
        if provider_match_id is not None
        else ()
    )
    normalized_status = normalize_optional_identifier(
        get_first_value(match_data, "status", "match_status")
    )
    raw_status = normalize_optional_identifier(
        get_first_value(match_data, "rawStatus", "raw_status")
    )

    target_match = TargetMatchRefV1(
        canonical_match_id=canonical_match_id,
        provider_match_ids=provider_match_ids,
        kickoff_utc=kickoff_utc,
        cutoff_utc=normalized_cutoff,
        domain=entity_type,
        competition=build_target_competition_context(
            match_data=match_data,
            entity_type=entity_type,
        ),
        venue_context=build_target_venue_context(match_data),
        tie_context=build_target_tie_context(match_data),
        match_status=(normalized_status, raw_status),
    )

    return target_match, target_teams


# Schéma de communication :
# rapidapi_flashscore_client.py
#   -> fournit le décodage de l'identifiant numérique RubyBets vers FlashScore
# flashscore_h2h_adapter.py
#   -> fournit les normalisations communes des noms, dates et compétitions
# target_match_adapter.py
#   -> produit TargetMatchRefV1 et TargetTeamsV1 à partir d'un match normalisé
# h2h_service.py
#   -> consomme ces contrats pour lancer acquisition puis feature engineering
# backend/tests/test_v19.py
#   -> vérifie IDs, cutoff, domaines, données manquantes et erreurs contrôlées
