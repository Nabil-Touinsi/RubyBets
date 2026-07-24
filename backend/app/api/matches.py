# Ce fichier expose les routes API des matchs RubyBets pour le MVP.
# Il bascule progressivement les matchs vers FlashScore comme source principale, avec Football-Data en fallback temporaire.

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.constants import FOOTBALL_DATA_PROVIDER, MVP_COMPETITION_CODES
from app.services.analysis_service import (
    build_context_summary,
    build_predictions,
    build_prematch_analysis,
)
from app.services.cache_service import (
    build_cache_name,
    build_data_freshness,
    get_cached_football_data,
    is_cache_fresh,
    load_cache,
    save_cache,
)
from app.services.match_advanced_stats_service import build_match_advanced_stats_response
from app.services.match_lineups_service import build_match_lineups_response
from app.services.match_service import (
    clean_params,
    filter_matches_by_team,
    format_match,
    get_match_with_standings,
)
from app.services.persistence_service import try_persist_matches, try_persist_teams
from app.services.rapidapi_flashscore_client import (
    FLASHSCORE_DEFAULT_TIMEZONE,
    FLASHSCORE_SOURCE,
    filter_flashscore_matches_by_competition,
    filter_flashscore_matches_by_status,
    filter_flashscore_matches_by_team,
    get_normalized_flashscore_match_details,
    get_normalized_flashscore_matches_by_day,
)
from app.services.team_history_service import build_team_history_response
from app.services.team_news_context_service import build_match_news_context_response


router = APIRouter(prefix="/api/matches", tags=["Matches"])


MATCHES_CACHE_TTL_MINUTES = 30
MATCH_DETAIL_CACHE_TTL_MINUTES = 30
FLASHSCORE_MATCHES_CACHE_TTL_MINUTES = 30
FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES = 30
FLASHSCORE_DEFAULT_UPCOMING_DAYS = 7


# Cette fonction vérifie qu'une compétition appartient bien au périmètre MVP RubyBets.
def ensure_competition_supported(competition_code: str) -> None:
    if competition_code not in MVP_COMPETITION_CODES:
        raise HTTPException(
            status_code=400,
            detail="Competition not supported in RubyBets MVP.",
        )


# Cette fonction bloque les routes enrichies si le code compétition du match est absent.
def ensure_competition_code_found(competition_code: str | None) -> None:
    if not competition_code:
        raise HTTPException(
            status_code=404,
            detail="Competition code not found for this match.",
        )


# Cette fonction indique si FlashScore peut être appelé dans l'environnement courant.
def is_flashscore_available() -> bool:
    return bool(settings.rapidapi_key.strip())


# Cette fonction calcule le day_offset FlashScore à partir d'une date ISO RubyBets.
def build_flashscore_day_offset_from_date(date_value: str | None) -> int | None:
    if not date_value:
        return None

    try:
        target_date = datetime.fromisoformat(date_value[:10]).date()
    except ValueError:
        return None

    today_utc = datetime.now(UTC).date()
    return (target_date - today_utc).days


# Cette fonction construit la liste des journées FlashScore à interroger selon les filtres reçus.
def build_flashscore_day_offsets_from_filters(
    date_from: str | None,
    date_to: str | None,
) -> list[int]:
    start_offset = build_flashscore_day_offset_from_date(date_from)
    end_offset = build_flashscore_day_offset_from_date(date_to)

    if start_offset is None and end_offset is None:
        return list(range(0, FLASHSCORE_DEFAULT_UPCOMING_DAYS))

    if start_offset is None:
        return [end_offset or 0]

    if end_offset is None:
        return [start_offset]

    safe_start = min(start_offset, end_offset)
    safe_end = max(start_offset, end_offset)
    safe_end = min(safe_end, safe_start + FLASHSCORE_DEFAULT_UPCOMING_DAYS - 1)

    return list(range(safe_start, safe_end + 1))


# Cette fonction construit un nom de cache stable pour une liste de matchs filtrée côté API.
def build_matches_cache_name(
    competition_code: str,
    status: str,
    date_from: str | None,
    date_to: str | None,
) -> str:
    return build_cache_name(
        "matches",
        competition_code,
        status,
        date_from or "all_start_dates",
        date_to or "all_end_dates",
    )


# Cette fonction retourne la date UTC courante pour stabiliser les clés de cache et les tests.
def get_current_utc_date() -> date:
    return datetime.now(UTC).date()


# Cette fonction retourne l'instant UTC courant utilisé pour filtrer les matchs déjà commencés.
def get_current_utc_datetime() -> datetime:
    return datetime.now(UTC)


# Cette fonction calcule la date civile réelle couverte par un day_offset FlashScore.
def build_flashscore_target_date(day_offset: int) -> date:
    return get_current_utc_date() + timedelta(days=day_offset)


# Cette fonction construit une clé de cache partagée entre compétitions pour une date FlashScore réelle.
def build_flashscore_matches_cache_name(
    day_offset: int,
    status: str | None,
    team: str | None,
    timezone: str,
    competition_code: str | None,
) -> str:
    del status, team, competition_code
    return build_cache_name(
        "flashscore_matches",
        build_flashscore_target_date(day_offset).isoformat(),
        timezone,
    )


# Cette fonction transforme une date ISO de match en datetime UTC comparable.
def parse_match_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized_value = value.strip().replace("Z", "+00:00")

    try:
        parsed_value = datetime.fromisoformat(normalized_value)
    except ValueError:
        return None

    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)

    return parsed_value.astimezone(UTC)


# Cette fonction retire les matchs SCHEDULED dont le coup d'envoi est déjà passé.
def filter_matches_before_kickoff(
    matches: list[dict[str, Any]],
    requested_status: str | None,
) -> list[dict[str, Any]]:
    if str(requested_status or "").upper() != "SCHEDULED":
        return matches

    current_time = get_current_utc_datetime()
    upcoming_matches: list[dict[str, Any]] = []

    for match in matches:
        kickoff_time = parse_match_utc_datetime(match.get("utcDate"))

        if kickoff_time is not None and kickoff_time > current_time:
            upcoming_matches.append(match)

    return upcoming_matches


# Cette fonction applique localement les filtres de route sur le cache FlashScore partagé.
def filter_cached_flashscore_matches(
    matches: list[dict[str, Any]],
    status: str | None,
    team: str | None,
    competition_code: str | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    status_filtered_matches = filter_flashscore_matches_by_status(matches, status)
    competition_filtered_matches = filter_flashscore_matches_by_competition(
        status_filtered_matches,
        competition_code,
    )
    team_filtered_matches = filter_flashscore_matches_by_team(
        competition_filtered_matches,
        team,
    )
    upcoming_matches = filter_matches_before_kickoff(
        team_filtered_matches,
        requested_status=status,
    )

    return upcoming_matches, {
        "source_matches_count": len(matches),
        "status_filtered_count": len(status_filtered_matches),
        "competition_filtered_count": len(competition_filtered_matches),
        "team_filtered_count": len(team_filtered_matches),
        "filtered_count": len(upcoming_matches),
    }


# Cette fonction adapte les métadonnées du cache partagé aux filtres de la requête courante.
def build_filtered_flashscore_metadata(
    source_metadata: dict[str, Any],
    matches: list[dict[str, Any]],
    filter_counts: dict[str, int],
    status: str | None,
    team: str | None,
    competition_code: str | None,
) -> dict[str, Any]:
    return {
        **source_metadata,
        "status": "success" if matches else "empty",
        "requested_status": status,
        "requested_competition_code": competition_code,
        "team_filter": team,
        **filter_counts,
    }


# Cette fonction construit un nom de cache stable pour les fiches match FlashScore.
def build_flashscore_match_detail_cache_name(match_id: int) -> str:
    return build_cache_name("flashscore_match", match_id)


# Cette fonction extrait les équipes domicile et extérieur depuis les matchs Football-Data.
def extract_teams_from_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    teams_by_external_id: dict[int, dict[str, Any]] = {}

    for match in matches:
        for team_key in ("homeTeam", "awayTeam"):
            team = match.get(team_key) or {}
            external_id = team.get("id")

            if external_id:
                teams_by_external_id[external_id] = team

    return list(teams_by_external_id.values())


# Cette fonction prépare les métadonnées de fraîcheur visibles dans les réponses liées aux matchs Football-Data.
def build_match_data_freshness(
    data_freshness: dict[str, Any],
    match_last_updated: str | None = None,
) -> dict[str, Any]:
    return {
        **data_freshness,
        "provider": FOOTBALL_DATA_PROVIDER,
        "last_updated": match_last_updated,
    }


# Cette fonction prépare les métadonnées de fraîcheur visibles dans les réponses FlashScore.
def build_flashscore_match_data_freshness(
    data_freshness: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    match_last_updated: str | None = None,
) -> dict[str, Any]:
    return {
        **data_freshness,
        "provider": FLASHSCORE_SOURCE,
        "last_updated": match_last_updated,
        "metadata": metadata or {},
    }


# Cette fonction récupère une journée FlashScore depuis un cache source partagé puis applique les filtres locaux.
def get_cached_flashscore_matches(
    day_offset: int,
    status: str | None,
    team: str | None,
    timezone: str,
    competition_code: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    cache_name = build_flashscore_matches_cache_name(
        day_offset=day_offset,
        status=status,
        team=team,
        timezone=timezone,
        competition_code=competition_code,
    )
    cached_payload = load_cache(cache_name)

    if cached_payload and is_cache_fresh(
        cached_payload,
        ttl_minutes=FLASHSCORE_MATCHES_CACHE_TTL_MINUTES,
    ):
        cached_data = cached_payload.get("data", {})
        source_matches = cached_data.get("matches", [])
        source_metadata = cached_data.get("metadata", {})
        filtered_matches, filter_counts = filter_cached_flashscore_matches(
            source_matches,
            status=status,
            team=team,
            competition_code=competition_code,
        )
        return (
            filtered_matches,
            build_filtered_flashscore_metadata(
                source_metadata=source_metadata,
                matches=filtered_matches,
                filter_counts=filter_counts,
                status=status,
                team=team,
                competition_code=competition_code,
            ),
            build_data_freshness(
                cache_payload=cached_payload,
                from_cache=True,
                ttl_minutes=FLASHSCORE_MATCHES_CACHE_TTL_MINUTES,
            ),
        )

    source_matches, source_metadata = get_normalized_flashscore_matches_by_day(
        day_offset=day_offset,
        status=None,
        team=None,
        timezone=timezone,
        competition_code=None,
    )

    if source_metadata.get("status") not in {"success", "empty"}:
        return source_matches, source_metadata, {
            "source": FLASHSCORE_SOURCE,
            "from_cache": False,
            "updated_at": None,
            "ttl_minutes": FLASHSCORE_MATCHES_CACHE_TTL_MINUTES,
        }

    saved_payload = save_cache(
        cache_name,
        {"matches": source_matches, "metadata": source_metadata},
        source=FLASHSCORE_SOURCE,
    )
    saved_data = saved_payload.get("data", {})
    saved_matches = saved_data.get("matches", [])
    saved_metadata = saved_data.get("metadata", source_metadata)
    filtered_matches, filter_counts = filter_cached_flashscore_matches(
        saved_matches,
        status=status,
        team=team,
        competition_code=competition_code,
    )

    return (
        filtered_matches,
        build_filtered_flashscore_metadata(
            source_metadata=saved_metadata,
            matches=filtered_matches,
            filter_counts=filter_counts,
            status=status,
            team=team,
            competition_code=competition_code,
        ),
        build_data_freshness(
            cache_payload=saved_payload,
            from_cache=False,
            ttl_minutes=FLASHSCORE_MATCHES_CACHE_TTL_MINUTES,
        ),
    )


# Cette fonction extrait une date de fraîcheur exploitable depuis une réponse de cache FlashScore.
def extract_flashscore_freshness_updated_at(freshness: dict[str, Any]) -> str | None:
    updated_at = freshness.get("updated_at")

    if isinstance(updated_at, str) and updated_at:
        return updated_at

    return None


# Cette fonction fusionne plusieurs journées FlashScore sans dupliquer les mêmes matchs.
def merge_flashscore_matches_by_id(
    current_matches: dict[Any, dict[str, Any]],
    matches: list[dict[str, Any]],
) -> None:
    for match in matches:
        match_id = match.get("id") or match.get("sourceMatchId")

        if match_id is not None:
            current_matches[match_id] = match


# Cette fonction trie les matchs FlashScore par date avant de les renvoyer au frontend.
def sort_flashscore_matches_by_date(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(matches, key=lambda match: match.get("utcDate") or "")


# Cette fonction récupère une ou plusieurs journées FlashScore selon la fenêtre demandée par l'API.
def get_cached_flashscore_matches_for_offsets(
    day_offsets: list[int],
    status: str | None,
    team: str | None,
    timezone: str,
    competition_code: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    unique_day_offsets = list(dict.fromkeys(day_offsets or [0]))

    if len(unique_day_offsets) == 1:
        return get_cached_flashscore_matches(
            day_offset=unique_day_offsets[0],
            status=status,
            team=team,
            timezone=timezone,
            competition_code=competition_code,
        )

    matches_by_id: dict[Any, dict[str, Any]] = {}
    day_summaries: list[dict[str, Any]] = []
    freshness_updates: list[str] = []
    from_cache_flags: list[bool] = []
    successful_days = 0
    first_error_metadata: dict[str, Any] | None = None

    for day_offset in unique_day_offsets:
        matches, metadata, freshness = get_cached_flashscore_matches(
            day_offset=day_offset,
            status=status,
            team=team,
            timezone=timezone,
            competition_code=competition_code,
        )
        metadata_status = metadata.get("status")

        day_summaries.append(
            {
                "day_offset": day_offset,
                "status": metadata_status,
                "matches_count": metadata.get("matches_count"),
                "filtered_count": metadata.get("filtered_count"),
            }
        )

        if metadata_status in {"success", "empty"}:
            successful_days += 1
            merge_flashscore_matches_by_id(matches_by_id, matches)
            from_cache_flags.append(bool(freshness.get("from_cache")))
        elif first_error_metadata is None:
            first_error_metadata = metadata

        freshness_updated_at = extract_flashscore_freshness_updated_at(freshness)

        if freshness_updated_at:
            freshness_updates.append(freshness_updated_at)

    merged_matches = sort_flashscore_matches_by_date(list(matches_by_id.values()))

    if successful_days == 0:
        return [], first_error_metadata or {
            "provider": FLASHSCORE_SOURCE,
            "status": "error",
            "endpoint": "/matches/list",
            "mode": "upcoming_range",
        }, {
            "source": FLASHSCORE_SOURCE,
            "from_cache": False,
            "updated_at": None,
            "ttl_minutes": FLASHSCORE_MATCHES_CACHE_TTL_MINUTES,
        }

    metadata = {
        "provider": FLASHSCORE_SOURCE,
        "status": "success" if merged_matches else "empty",
        "endpoint": "/matches/list",
        "mode": "upcoming_range",
        "source": FLASHSCORE_SOURCE,
        "day_offsets": unique_day_offsets,
        "days_requested": len(unique_day_offsets),
        "days_successful": successful_days,
        "days_failed": len(unique_day_offsets) - successful_days,
        "requested_status": status,
        "requested_competition_code": competition_code,
        "team_filter": team,
        "filtered_count": len(merged_matches),
        "day_summaries": day_summaries,
    }
    freshness = {
        "source": FLASHSCORE_SOURCE,
        "from_cache": bool(from_cache_flags) and all(from_cache_flags),
        "updated_at": max(freshness_updates) if freshness_updates else None,
        "ttl_minutes": FLASHSCORE_MATCHES_CACHE_TTL_MINUTES,
    }

    return merged_matches, metadata, freshness


# Cette fonction récupère la fiche match FlashScore depuis le cache ou RapidAPI.
def get_cached_flashscore_match_detail(
    match_id: int,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    cache_name = build_flashscore_match_detail_cache_name(match_id)
    cached_payload = load_cache(cache_name)

    if cached_payload and is_cache_fresh(
        cached_payload,
        ttl_minutes=FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES,
    ):
        cached_data = cached_payload.get("data", {})
        return (
            cached_data.get("match"),
            cached_data.get("metadata", {}),
            build_data_freshness(
                cache_payload=cached_payload,
                from_cache=True,
                ttl_minutes=FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES,
            ),
        )

    match, metadata = get_normalized_flashscore_match_details(match_id)

    if metadata.get("status") != "success" or not match:
        return match, metadata, {
            "source": FLASHSCORE_SOURCE,
            "from_cache": False,
            "updated_at": None,
            "ttl_minutes": FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES,
        }

    saved_payload = save_cache(
        cache_name,
        {"match": match, "metadata": metadata},
        source=FLASHSCORE_SOURCE,
    )

    return (
        saved_payload["data"].get("match"),
        saved_payload["data"].get("metadata", metadata),
        build_data_freshness(
            cache_payload=saved_payload,
            from_cache=False,
            ttl_minutes=FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES,
        ),
    )


# Cette route retourne les matchs à venir avec FlashScore comme source principale et Football-Data en fallback temporaire.
@router.get("")
async def get_matches(
    competition_code: str = Query("PL"),
    status: str = Query("SCHEDULED"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    team: str | None = Query(None),
) -> dict[str, Any]:
    competition_code = competition_code.upper()
    ensure_competition_supported(competition_code)

    flashscore_metadata: dict[str, Any] | None = None

    if is_flashscore_available():
        day_offsets = build_flashscore_day_offsets_from_filters(
            date_from=date_from,
            date_to=date_to,
        )
        matches, flashscore_metadata, flashscore_freshness = get_cached_flashscore_matches_for_offsets(
            day_offsets=day_offsets,
            status=status,
            team=team,
            timezone=FLASHSCORE_DEFAULT_TIMEZONE,
            competition_code=competition_code,
        )

        if flashscore_metadata.get("status") in {"success", "empty"}:
            return {
                "source": FLASHSCORE_SOURCE,
                "source_used": FLASHSCORE_SOURCE,
                "data_source": FLASHSCORE_SOURCE,
                "competition_code": competition_code,
                "filters": {
                    "status": status,
                    "date_from": date_from,
                    "date_to": date_to,
                    "team": team,
                    "day_offsets": day_offsets,
                    "upcoming_window_days": FLASHSCORE_DEFAULT_UPCOMING_DAYS if not date_from and not date_to else None,
                    "timezone": FLASHSCORE_DEFAULT_TIMEZONE,
                },
                "count": len(matches),
                "matches": [format_match(match) for match in matches],
                "data_freshness": build_flashscore_match_data_freshness(
                    data_freshness=flashscore_freshness,
                    metadata=flashscore_metadata,
                ),
                "fallback_available": True,
            }

    params = clean_params(
        {
            "status": status,
            "dateFrom": date_from,
            "dateTo": date_to,
        }
    )
    cache_name = build_matches_cache_name(
        competition_code=competition_code,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )

    data, data_freshness = await get_cached_football_data(
        cache_name=cache_name,
        endpoint=f"/competitions/{competition_code}/matches",
        params=params,
        ttl_minutes=MATCHES_CACHE_TTL_MINUTES,
    )

    raw_matches = data.get("matches", [])
    try_persist_teams(extract_teams_from_matches(raw_matches))
    try_persist_matches(raw_matches)

    filtered_matches = filter_matches_by_team(raw_matches, team)
    formatted_matches = [format_match(match) for match in filtered_matches]

    return {
        "source": FOOTBALL_DATA_PROVIDER,
        "source_used": FOOTBALL_DATA_PROVIDER,
        "fallback_reason": flashscore_metadata,
        "competition_code": competition_code,
        "filters": {
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "team": team,
        },
        "count": len(formatted_matches),
        "matches": formatted_matches,
        "data_freshness": build_match_data_freshness(data_freshness),
    }


# Cette route retourne la fiche détaillée d'un match avec FlashScore comme source principale et Football-Data en fallback temporaire.
@router.get("/{match_id}")
async def get_match_details(match_id: int) -> dict[str, Any]:
    flashscore_metadata: dict[str, Any] | None = None

    if is_flashscore_available():
        match, flashscore_metadata, flashscore_freshness = get_cached_flashscore_match_detail(match_id)

        if match and flashscore_metadata.get("status") == "success":
            return {
                "source": FLASHSCORE_SOURCE,
                "source_used": FLASHSCORE_SOURCE,
                "match": format_match(match),
                "data_freshness": build_flashscore_match_data_freshness(
                    data_freshness=flashscore_freshness,
                    metadata=flashscore_metadata,
                    match_last_updated=match.get("lastUpdated"),
                ),
                "fallback_available": True,
            }

    data, data_freshness = await get_cached_football_data(
        cache_name=build_cache_name("match", match_id),
        endpoint=f"/matches/{match_id}",
        ttl_minutes=MATCH_DETAIL_CACHE_TTL_MINUTES,
    )
    match = data.get("match", data)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
        "source_used": FOOTBALL_DATA_PROVIDER,
        "fallback_reason": flashscore_metadata,
        "match": format_match(match),
        "data_freshness": build_match_data_freshness(
            data_freshness=data_freshness,
            match_last_updated=match.get("lastUpdated"),
        ),
    }

# Cette route retourne les actualités publiques récentes liées aux deux équipes d'un match.
@router.get("/{match_id}/news-context")
async def get_match_news_context(match_id: int) -> dict[str, Any]:
    flashscore_metadata: dict[str, Any] | None = None

    if is_flashscore_available():
        match, flashscore_metadata, flashscore_freshness = get_cached_flashscore_match_detail(match_id)

        if match and flashscore_metadata.get("status") == "success":
            news_context = build_match_news_context_response(
                match_id=match_id,
                match=match,
            )

            return {
                **news_context,
                "source_used": news_context.get("source"),
                "match_source": FLASHSCORE_SOURCE,
                "match": format_match(match),
                "data_used": {
                    "match_details": True,
                    "rss_news": news_context.get("status") in {"available", "partial"},
                    "odds_used": False,
                },
                "data_freshness": {
                    "provider": news_context.get("source"),
                    "generated_at": news_context.get("generated_at"),
                    "match_cache": build_flashscore_match_data_freshness(
                        data_freshness=flashscore_freshness,
                        metadata=flashscore_metadata,
                        match_last_updated=match.get("lastUpdated"),
                    ),
                },
                "fallback_available": True,
            }

    data, data_freshness = await get_cached_football_data(
        cache_name=build_cache_name("match", match_id),
        endpoint=f"/matches/{match_id}",
        ttl_minutes=MATCH_DETAIL_CACHE_TTL_MINUTES,
    )
    match = data.get("match", data)

    news_context = build_match_news_context_response(
        match_id=match_id,
        match=match,
    )

    return {
        **news_context,
        "source_used": news_context.get("source"),
        "match_source": FOOTBALL_DATA_PROVIDER,
        "fallback_reason": flashscore_metadata,
        "match": format_match(match),
        "data_used": {
            "match_details": True,
            "rss_news": news_context.get("status") in {"available", "partial"},
            "odds_used": False,
        },
        "data_freshness": {
            "provider": news_context.get("source"),
            "generated_at": news_context.get("generated_at"),
            "match_cache": build_match_data_freshness(data_freshness),
        },
    }


# Cette route retourne les compositions actuelles puis un fallback historique officiel si la source est vide.
@router.get("/{match_id}/lineups")
async def get_match_lineups(match_id: int) -> dict[str, Any]:
    return await build_match_lineups_response(match_id)


# Cette route retourne l'historique récent des deux équipes et les confrontations directes disponibles.
@router.get("/{match_id}/team-history")
async def get_match_team_history(match_id: int) -> dict[str, Any]:
    return await build_team_history_response(match_id)


# Cette route retourne les moyennes avancées réelles des cinq derniers matchs terminés de chaque équipe.
@router.get("/{match_id}/advanced-stats")
async def get_match_advanced_stats(match_id: int) -> dict[str, Any]:
    return await build_match_advanced_stats_response(match_id)


# Cette fonction construit un résumé de contexte partiel quand le match vient de FlashScore.
def build_flashscore_context_summary(match: dict[str, Any]) -> dict[str, Any]:
    home_team = match.get("homeTeam", {}).get("name")
    away_team = match.get("awayTeam", {}).get("name")

    return {
        "title": f"{home_team} vs {away_team}",
        "main_facts": [
            "Match analysé avant le coup d'envoi.",
            "Fiche match récupérée depuis FlashScore RapidAPI.",
            "Le classement de compétition n'est pas disponible dans ce bloc pendant la migration FlashScore.",
            "RubyBets affiche uniquement les données réellement disponibles, sans inventer d'indicateur.",
        ],
        "home_team_position": None,
        "away_team_position": None,
    }


# Cette fonction construit la réponse de contexte partiel pour un match FlashScore.
def build_flashscore_partial_context_response(
    match_id: int,
    match: dict[str, Any],
    flashscore_freshness: dict[str, Any],
    flashscore_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    formatted_match = format_match(match)

    return {
        "source": FLASHSCORE_SOURCE,
        "source_used": FLASHSCORE_SOURCE,
        "status": "partial",
        "match_id": match_id,
        "match": formatted_match,
        "context": {
            "competition": {
                "code": formatted_match.get("competition", {}).get("code"),
                "name": formatted_match.get("competition", {}).get("name"),
            },
            "home_team_standing": None,
            "away_team_standing": None,
            "summary": build_flashscore_context_summary(match),
            "limits": [
                "Le classement n'est pas disponible pour cette source à cette étape de migration.",
                "Le contexte est donc affiché comme partiel et doit être complété par l'historique récent des équipes.",
            ],
        },
        "data_used": {
            "match_details": True,
            "competition_standings": False,
            "home_team_standing_available": False,
            "away_team_standing_available": False,
        },
        "data_freshness": build_flashscore_match_data_freshness(
            data_freshness=flashscore_freshness,
            metadata=flashscore_metadata,
            match_last_updated=match.get("lastUpdated"),
        ),
        "fallback_available": True,
    }


# Cette route retourne le contexte d'un match avec FlashScore en source principale et Football-Data en fallback temporaire.
@router.get("/{match_id}/context")
async def get_match_context(match_id: int) -> dict[str, Any]:
    flashscore_metadata: dict[str, Any] | None = None

    if is_flashscore_available():
        match, flashscore_metadata, flashscore_freshness = get_cached_flashscore_match_detail(match_id)

        if match and flashscore_metadata.get("status") == "success":
            return build_flashscore_partial_context_response(
                match_id=match_id,
                match=match,
                flashscore_freshness=flashscore_freshness,
                flashscore_metadata=flashscore_metadata,
            )

    match_data = await get_match_with_standings(match_id)
    match = match_data["match"]
    competition_code = match_data["competition_code"]
    home_standing = match_data["home_standing"]
    away_standing = match_data["away_standing"]

    ensure_competition_code_found(competition_code)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
        "source_used": FOOTBALL_DATA_PROVIDER,
        "fallback_reason": flashscore_metadata,
        "status": "available",
        "match": format_match(match),
        "context": {
            "competition": {
                "code": competition_code,
                "name": match.get("competition", {}).get("name"),
            },
            "home_team_standing": home_standing,
            "away_team_standing": away_standing,
            "summary": build_context_summary(
                match=match,
                home_standing=home_standing,
                away_standing=away_standing,
            ),
        },
        "data_freshness": {
            "provider": FOOTBALL_DATA_PROVIDER,
            "match_last_updated": match.get("lastUpdated"),
            "match_cache": match_data.get("data_freshness", {}).get("match"),
            "standings_cache": match_data.get("data_freshness", {}).get("standings"),
        },
    }


# Cette fonction récupère le résumé de forme d'une équipe depuis différents formats possibles de team-history.
def extract_flashscore_form_summary(team_history_block: dict[str, Any]) -> dict[str, Any]:
    form_summary = team_history_block.get("form_summary")

    if isinstance(form_summary, dict) and form_summary:
        return form_summary

    alternative_summary = team_history_block.get("summary")

    if isinstance(alternative_summary, dict) and alternative_summary:
        return alternative_summary

    recent_matches = team_history_block.get("recent_matches_overview", [])

    return {
        "matches_count": len(recent_matches) if isinstance(recent_matches, list) else 0,
        "wins": team_history_block.get("wins", 0),
        "draws": team_history_block.get("draws", 0),
        "losses": team_history_block.get("losses", 0),
        "avg_goals_for": team_history_block.get("avg_goals_for"),
        "avg_goals_against": team_history_block.get("avg_goals_against"),
    }


# Cette fonction formate une moyenne numérique sans inventer de valeur si elle est absente.
def format_optional_average(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value:.2f}"

    return "non disponible"


# Cette fonction transforme le résumé de forme d'une équipe en phrase lisible pour l'analyse FlashScore.
def build_flashscore_team_observed_fact(
    team_name: str | None,
    form_summary: dict[str, Any],
) -> str:
    matches_count = form_summary.get("matches_count", 0)

    if not team_name or not matches_count:
        return "L'historique récent de cette équipe n'est pas disponible avec les données actuelles."

    avg_goals_for = format_optional_average(form_summary.get("avg_goals_for"))
    avg_goals_against = format_optional_average(form_summary.get("avg_goals_against"))

    return (
        f"{team_name} dispose de {matches_count} match(s) récent(s) exploitable(s) : "
        f"{form_summary.get('wins', 0)} victoire(s), "
        f"{form_summary.get('draws', 0)} nul(s), "
        f"{form_summary.get('losses', 0)} défaite(s), "
        f"avec {avg_goals_for} but(s) marqué(s) "
        f"et {avg_goals_against} but(s) encaissé(s) en moyenne."
    )


# Cette fonction construit une analyse pré-match responsable à partir du détail match FlashScore et de team-history.
def build_flashscore_prematch_analysis(
    match: dict[str, Any],
    team_history: dict[str, Any],
) -> dict[str, Any]:
    home_team = match.get("homeTeam", {}).get("name")
    away_team = match.get("awayTeam", {}).get("name")

    home_summary = extract_flashscore_form_summary(
        team_history.get("home_team_history", {})
    )
    away_summary = extract_flashscore_form_summary(
        team_history.get("away_team_history", {})
    )
    head_to_head = team_history.get("head_to_head", [])

    observed_facts = [
        build_flashscore_team_observed_fact(home_team, home_summary),
        build_flashscore_team_observed_fact(away_team, away_summary),
        (
            f"{len(head_to_head)} confrontation(s) directe(s) sont disponible(s)."
            if head_to_head
            else "Aucune confrontation directe exploitable n'est disponible avec les sources actuelles."
        ),
        "Le classement de compétition n'est pas disponible dans ce bloc pendant la migration FlashScore.",
    ]

    key_factors = [
        {
            "label": "Forme récente",
            "value": team_history.get("data_status", "partial"),
            "reading": (
                "RubyBets s'appuie sur les matchs récents disponibles pour comparer les dynamiques, "
                "sans inventer de classement ou de statistique absente."
            ),
        },
        {
            "label": "Buts marqués",
            "value": {
                "home_avg": home_summary.get("avg_goals_for"),
                "away_avg": away_summary.get("avg_goals_for"),
            },
            "reading": "Comparaison des moyennes offensives récentes lorsque les données sont disponibles.",
        },
        {
            "label": "Buts encaissés",
            "value": {
                "home_avg": home_summary.get("avg_goals_against"),
                "away_avg": away_summary.get("avg_goals_against"),
            },
            "reading": "Comparaison des moyennes défensives récentes lorsque les données sont disponibles.",
        },
        {
            "label": "Face-à-face",
            "value": len(head_to_head),
            "reading": (
                "Les confrontations directes sont utilisées comme contexte complémentaire, "
                "pas comme garantie de résultat."
            ),
        },
    ]

    interpretation = [
        (
            "L'analyse repose principalement sur la forme récente, les tendances offensives et défensives, "
            "ainsi que les confrontations directes réellement disponibles."
        ),
        (
            "En l'absence de classement complet fourni par cette source, RubyBets classe cette analyse comme partielle "
            "et conserve une lecture prudente du match."
        ),
    ]

    return {
        "title": f"Analyse pré-match : {home_team} vs {away_team}",
        "context_trend": "flashscore_partial_context",
        "observed_facts": observed_facts,
        "key_factors": key_factors,
        "interpretation": interpretation,
        "limits": [
            "Cette analyse ne constitue pas une prédiction de résultat.",
            "Elle repose uniquement sur les données réellement disponibles via FlashScore RapidAPI et les historiques d'équipes.",
            "Le classement et certaines statistiques avancées restent indisponibles dans ce bloc d'analyse pendant la migration FlashScore.",
            "Aucune cote FlashScore n'est utilisée par RubyBets.",
        ],
    }


# Cette route retourne l'analyse pré-match avec FlashScore en priorité et Football-Data en fallback temporaire.
@router.get("/{match_id}/analysis")
async def get_match_analysis(match_id: int) -> dict[str, Any]:
    flashscore_metadata: dict[str, Any] | None = None

    if is_flashscore_available():
        match, flashscore_metadata, flashscore_freshness = get_cached_flashscore_match_detail(match_id)

        if match and flashscore_metadata.get("status") == "success":
            team_history = await build_team_history_response(match_id)

            return {
                "source": FLASHSCORE_SOURCE,
                "source_used": FLASHSCORE_SOURCE,
                "status": "partial",
                "match_id": match_id,
                "match": format_match(match),
                "analysis": build_flashscore_prematch_analysis(
                    match=match,
                    team_history=team_history,
                ),
                "data_used": {
                    "match_details": True,
                    "team_history": team_history.get("data_status") in {"available", "partial"},
                    "competition_standings": False,
                    "home_team_standing_available": False,
                    "away_team_standing_available": False,
                    "odds_used": False,
                },
                "data_freshness": {
                    **build_flashscore_match_data_freshness(
                        data_freshness=flashscore_freshness,
                        metadata=flashscore_metadata,
                        match_last_updated=match.get("lastUpdated"),
                    ),
                    "team_history": team_history.get("data_freshness"),
                },
                "fallback_available": True,
            }

    match_data = await get_match_with_standings(match_id)
    match = match_data["match"]
    competition_code = match_data["competition_code"]
    home_standing = match_data["home_standing"]
    away_standing = match_data["away_standing"]

    ensure_competition_code_found(competition_code)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
        "source_used": FOOTBALL_DATA_PROVIDER,
        "fallback_reason": flashscore_metadata,
        "status": "available",
        "match_id": match_id,
        "analysis": build_prematch_analysis(
            match=match,
            home_standing=home_standing,
            away_standing=away_standing,
        ),
        "data_used": {
            "match_details": True,
            "competition_standings": True,
            "home_team_standing_available": home_standing is not None,
            "away_team_standing_available": away_standing is not None,
        },
        "data_freshness": {
            "provider": FOOTBALL_DATA_PROVIDER,
            "match_last_updated": match.get("lastUpdated"),
            "match_cache": match_data.get("data_freshness", {}).get("match"),
            "standings_cache": match_data.get("data_freshness", {}).get("standings"),
        },
    }


# Cette fonction convertit une valeur numérique optionnelle en float exploitable sans inventer de donnée.
def get_optional_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)

    return None


# Cette fonction calcule un ratio prudent à partir d'un compteur et d'un total disponible.
def safe_ratio(value: int | float | None, total: int | float | None) -> float | None:
    if value is None or total in (None, 0):
        return None

    return round(float(value) / float(total), 3)


# Cette fonction calcule un score de dynamique simple à partir de l'historique FlashScore disponible.
def build_flashscore_team_signal_score(form_summary: dict[str, Any]) -> float | None:
    matches_count = get_optional_float(form_summary.get("matches_count"))

    if not matches_count:
        return None

    wins_rate = safe_ratio(form_summary.get("wins", 0), matches_count) or 0
    losses_rate = safe_ratio(form_summary.get("losses", 0), matches_count) or 0
    avg_goals_for = get_optional_float(form_summary.get("avg_goals_for"))
    avg_goals_against = get_optional_float(form_summary.get("avg_goals_against"))

    goal_balance = 0.0
    if avg_goals_for is not None and avg_goals_against is not None:
        goal_balance = avg_goals_for - avg_goals_against

    return round((wins_rate - losses_rate) + (goal_balance * 0.25), 3)


# Cette fonction construit le signal 1X2 FlashScore sans transformer la tendance en promesse sportive.
def build_flashscore_one_x_two_prediction(
    home_team: str | None,
    away_team: str | None,
    home_summary: dict[str, Any],
    away_summary: dict[str, Any],
) -> dict[str, Any]:
    home_score = build_flashscore_team_signal_score(home_summary)
    away_score = build_flashscore_team_signal_score(away_summary)

    if home_score is None or away_score is None:
        return {
            "market": "1X2",
            "prediction": "INSUFFICIENT_DATA",
            "label": "Tendance 1X2 non évaluée",
            "confidence": "low",
            "risk": "high",
            "justification": (
                "L'historique récent disponible ne suffit pas à comparer les dynamiques 1X2."
            ),
        }

    score_gap = round(home_score - away_score, 3)

    if score_gap >= 0.35:
        return {
            "market": "1X2",
            "prediction": "HOME_TEAM_TREND",
            "label": f"Tendance favorable à {home_team}",
            "confidence": "medium",
            "risk": "medium",
            "justification": (
                f"{home_team} présente une dynamique récente légèrement supérieure selon les "
                "résultats et la balance de buts disponibles."
            ),
        }

    if score_gap <= -0.35:
        return {
            "market": "1X2",
            "prediction": "AWAY_TEAM_TREND",
            "label": f"Tendance favorable à {away_team}",
            "confidence": "medium",
            "risk": "medium",
            "justification": (
                f"{away_team} présente une dynamique récente légèrement supérieure selon les "
                "résultats et la balance de buts disponibles."
            ),
        }

    return {
        "market": "1X2",
        "prediction": "BALANCED_TREND",
        "label": "Tendance prudente / match à surveiller",
        "confidence": "low",
        "risk": "high",
        "justification": (
            "Les dynamiques récentes disponibles sont proches et ne permettent pas de dégager "
            "un signal 1X2 fort."
        ),
    }


# Cette fonction calcule le contexte moyen de buts à partir des données récentes FlashScore.
def build_flashscore_average_goal_context(
    home_summary: dict[str, Any],
    away_summary: dict[str, Any],
) -> float | None:
    home_goals_for = get_optional_float(home_summary.get("avg_goals_for"))
    home_goals_against = get_optional_float(home_summary.get("avg_goals_against"))
    away_goals_for = get_optional_float(away_summary.get("avg_goals_for"))
    away_goals_against = get_optional_float(away_summary.get("avg_goals_against"))

    if any(
        value is None
        for value in [
            home_goals_for,
            home_goals_against,
            away_goals_for,
            away_goals_against,
        ]
    ):
        return None

    home_match_goal_avg = home_goals_for + home_goals_against
    away_match_goal_avg = away_goals_for + away_goals_against

    return round((home_match_goal_avg + away_match_goal_avg) / 2, 2)


# Cette fonction construit le signal de volume de buts FlashScore à partir des moyennes disponibles.
def build_flashscore_goals_prediction(average_goal_context: float | None) -> dict[str, Any]:
    if average_goal_context is None:
        return {
            "market": "GOALS",
            "prediction": "INSUFFICIENT_DATA",
            "label": "Volume de buts non évalué",
            "confidence": "low",
            "risk": "high",
            "justification": "Les moyennes de buts récentes sont insuffisantes pour produire un signal.",
        }

    if average_goal_context >= 2.8:
        return {
            "market": "GOALS",
            "prediction": "OVER_2_5_TREND",
            "label": "Tendance vers un match avec plusieurs buts",
            "confidence": "medium",
            "risk": "medium",
            "justification": (
                f"La moyenne récente combinée est de {average_goal_context} but(s) par match."
            ),
        }

    if average_goal_context <= 2.3:
        return {
            "market": "GOALS",
            "prediction": "UNDER_2_5_TREND",
            "label": "Tendance vers un match plus fermé",
            "confidence": "medium",
            "risk": "medium",
            "justification": (
                f"La moyenne récente combinée est de {average_goal_context} but(s) par match."
            ),
        }

    return {
        "market": "GOALS",
        "prediction": "NEUTRAL_GOALS_TREND",
        "label": "Volume de buts incertain",
        "confidence": "low",
        "risk": "high",
        "justification": (
            f"La moyenne récente combinée est de {average_goal_context} but(s), "
            "ce qui ne donne pas une tendance assez nette."
        ),
    }


# Cette fonction construit le signal BTTS FlashScore à partir des tendances offensives et défensives disponibles.
def build_flashscore_btts_prediction(
    home_summary: dict[str, Any],
    away_summary: dict[str, Any],
) -> dict[str, Any]:
    home_goals_for = get_optional_float(home_summary.get("avg_goals_for"))
    away_goals_for = get_optional_float(away_summary.get("avg_goals_for"))
    home_goals_against = get_optional_float(home_summary.get("avg_goals_against"))
    away_goals_against = get_optional_float(away_summary.get("avg_goals_against"))

    if home_goals_for is None or away_goals_for is None:
        return {
            "market": "BTTS",
            "prediction": "INSUFFICIENT_DATA",
            "label": "BTTS non évalué",
            "confidence": "low",
            "risk": "high",
            "justification": "Les moyennes offensives récentes sont insuffisantes.",
        }

    if (
        home_goals_for >= 1.2
        and away_goals_for >= 1.2
        and (home_goals_against or 0) >= 0.8
        and (away_goals_against or 0) >= 0.8
    ):
        return {
            "market": "BTTS",
            "prediction": "BTTS_YES_TREND",
            "label": "Tendance : les deux équipes peuvent marquer",
            "confidence": "low",
            "risk": "high",
            "justification": (
                "Les deux équipes présentent des moyennes offensives exploitables, "
                "mais le signal reste prudent sans compositions ni absences."
            ),
        }

    return {
        "market": "BTTS",
        "prediction": "BTTS_NO_CLEAR_TREND",
        "label": "BTTS incertain",
        "confidence": "low",
        "risk": "high",
        "justification": (
            "Les moyennes récentes ne permettent pas de dégager une tendance BTTS forte."
        ),
    }


# Cette fonction construit une réponse de prédictions partielle à partir de FlashScore et de team-history.
def build_flashscore_predictions(
    match: dict[str, Any],
    team_history: dict[str, Any],
) -> dict[str, Any]:
    home_team = match.get("homeTeam", {}).get("name")
    away_team = match.get("awayTeam", {}).get("name")
    home_summary = extract_flashscore_form_summary(
        team_history.get("home_team_history", {})
    )
    away_summary = extract_flashscore_form_summary(
        team_history.get("away_team_history", {})
    )
    average_goal_context = build_flashscore_average_goal_context(
        home_summary=home_summary,
        away_summary=away_summary,
    )
    home_score = build_flashscore_team_signal_score(home_summary)
    away_score = build_flashscore_team_signal_score(away_summary)

    if team_history.get("data_status") == "unavailable":
        return {
            "status": "unavailable",
            "message": (
                "Les historiques récents ne sont pas disponibles pour produire des signaux de prédiction."
            ),
            "method": "flashscore_history_signals_v1",
            "inputs": {
                "home_team_position": None,
                "away_team_position": None,
                "position_gap": None,
                "points_gap": None,
                "goal_difference_gap": None,
                "average_goal_context": None,
                "home_goals_for_avg": None,
                "away_goals_for_avg": None,
            },
            "predictions": None,
            "limits": [
                "RubyBets n'invente pas de prédiction lorsque les données utiles sont absentes.",
                "Aucune cote FlashScore n'est utilisée.",
            ],
        }

    return {
        "status": "partial",
        "message": (
            "Prédictions affichées comme signaux partiels : FlashScore fournit l'historique récent, "
            "mais pas le classement complet dans cette étape de migration."
        ),
        "method": "flashscore_history_signals_v1",
        "inputs": {
            "home_team_position": None,
            "away_team_position": None,
            "position_gap": None,
            "points_gap": None,
            "goal_difference_gap": round(abs(home_score - away_score), 3) if home_score is not None and away_score is not None else None,
            "average_goal_context": average_goal_context,
            "home_goals_for_avg": home_summary.get("avg_goals_for"),
            "away_goals_for_avg": away_summary.get("avg_goals_for"),
        },
        "predictions": {
            "one_x_two": build_flashscore_one_x_two_prediction(
                home_team=home_team,
                away_team=away_team,
                home_summary=home_summary,
                away_summary=away_summary,
            ),
            "goals": build_flashscore_goals_prediction(average_goal_context),
            "btts": build_flashscore_btts_prediction(
                home_summary=home_summary,
                away_summary=away_summary,
            ),
        },
        "limits": [
            "Ces prédictions sont des tendances analytiques partielles, pas des certitudes.",
            "Le moteur utilise uniquement les données FlashScore réellement disponibles et l'historique récent des équipes.",
            "Le classement et certaines statistiques avancées restent indisponibles dans ce bloc d'analyse pendant la migration FlashScore.",
            "Aucune cote FlashScore n'est utilisée par RubyBets.",
        ],
    }


# Cette route retourne les prédictions MVP avec FlashScore en priorité et Football-Data en fallback temporaire.
@router.get("/{match_id}/predictions")
async def get_match_predictions(match_id: int) -> dict[str, Any]:
    flashscore_metadata: dict[str, Any] | None = None

    if is_flashscore_available():
        match, flashscore_metadata, flashscore_freshness = get_cached_flashscore_match_detail(match_id)

        if match and flashscore_metadata.get("status") == "success":
            team_history = await build_team_history_response(match_id)

            return {
                "source": FLASHSCORE_SOURCE,
                "source_used": FLASHSCORE_SOURCE,
                "status": "partial",
                "match_id": match_id,
                "match": format_match(match),
                "predictions": build_flashscore_predictions(
                    match=match,
                    team_history=team_history,
                ),
                "data_used": {
                    "match_details": True,
                    "team_history": team_history.get("data_status") in {"available", "partial"},
                    "competition_standings": False,
                    "home_team_standing_available": False,
                    "away_team_standing_available": False,
                    "odds_used": False,
                },
                "data_freshness": {
                    "provider": FLASHSCORE_SOURCE,
                    "match_last_updated": match.get("lastUpdated"),
                    "match_cache": build_flashscore_match_data_freshness(
                        data_freshness=flashscore_freshness,
                        metadata=flashscore_metadata,
                        match_last_updated=match.get("lastUpdated"),
                    ),
                    "standings_cache": None,
                    "team_history": team_history.get("data_freshness"),
                },
                "fallback_available": True,
            }

    match_data = await get_match_with_standings(match_id)
    match = match_data["match"]
    competition_code = match_data["competition_code"]
    home_standing = match_data["home_standing"]
    away_standing = match_data["away_standing"]

    ensure_competition_code_found(competition_code)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
        "source_used": FOOTBALL_DATA_PROVIDER,
        "fallback_reason": flashscore_metadata,
        "match_id": match_id,
        "predictions": build_predictions(
            match=match,
            home_standing=home_standing,
            away_standing=away_standing,
        ),
        "data_used": {
            "match_details": True,
            "competition_standings": True,
            "home_team_standing_available": home_standing is not None,
            "away_team_standing_available": away_standing is not None,
        },
        "data_freshness": {
            "provider": FOOTBALL_DATA_PROVIDER,
            "match_last_updated": match.get("lastUpdated"),
            "match_cache": match_data.get("data_freshness", {}).get("match"),
            "standings_cache": match_data.get("data_freshness", {}).get("standings"),
        },
    }


# Schéma de communication du fichier :
# matches.py
# ├── utilise rapidapi_flashscore_client.py pour /api/matches, /api/matches/{match_id} et le contexte partiel FlashScore
# ├── interroge au maximum sept journées FlashScore quand aucun filtre de date n’est fourni
# ├── partage le cache source par date réelle entre compétitions puis filtre localement
# ├── retire les matchs SCHEDULED dont le coup d’envoi est déjà passé
# ├── utilise cache_service.py pour le cache FlashScore et le fallback Football-Data temporaire
# ├── utilise match_service.py pour le formatage et le fallback Football-Data temporaire
# ├── utilise team_history_service.py pour produire les historiques récents, face-à-face, l’analyse et les prédictions FlashScore partielles
# ├── utilise match_advanced_stats_service.py pour exposer les agrégats FlashScore réels avec leur couverture
# ├── utilise team_news_context_service.py pour produire les actualités contextuelles publiques par équipe
# ├── délègue les compositions actuelles et le fallback historique à match_lineups_service.py
# ├── utilise analysis_service.py pour générer les synthèses Football-Data et les prédictions explicables
# ├── utilise persistence_service.py uniquement pour le fallback Football-Data temporaire
# └── renvoie les données formatées à app.main puis au frontend
