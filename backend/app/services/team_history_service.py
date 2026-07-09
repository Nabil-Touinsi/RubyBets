# Ce fichier construit l'historique recent des equipes pour alimenter la fiche detail match RubyBets.
# Il utilise FlashScore comme source principale et garde Football-Data en fallback sans inventer de donnees.

from typing import Any
import unicodedata

from app.core.constants import FOOTBALL_DATA_PROVIDER
from app.services.api_football_client import get_normalized_api_football_team_history
from app.services.rapidapi_flashscore_client import (
    get_flashscore_head_to_head,
    get_flashscore_histories_for_match,
    get_normalized_flashscore_match_details,
    get_normalized_flashscore_team_results,
)
from app.services.cache_service import (
    build_cache_name,
    build_data_freshness,
    get_cached_football_data,
    is_cache_fresh,
    load_cache,
    save_cache,
)
from app.services.match_service import format_team, get_match_with_standings


TEAM_HISTORY_CACHE_TTL_MINUTES = 720
TEAM_HISTORY_LIMIT = 20
OVERVIEW_RECENT_MATCHES_LIMIT = 5
CLUB_ANALYSIS_RECENT_MATCHES_MIN = 8
API_FOOTBALL_HISTORY_LIMIT = 20
FLASHSCORE_HISTORY_LIMIT = 20
TEAM_HISTORY_RESPONSE_CACHE_TTL_MINUTES = 720


# Cette fonction construit une cle de cache stable pour les matchs termines d'une equipe toutes competitions confondues.
def build_team_matches_cache_name(
    team_id: int,
    limit: int = TEAM_HISTORY_LIMIT,
) -> str:
    return build_cache_name(
        "team_matches",
        team_id,
        "all_competitions",
        "finished",
        f"limit_{limit}",
    )


# Cette fonction construit une cle de cache stable pour la reponse complete d'historique d'un match.
def build_team_history_response_cache_name(match_id: int) -> str:
    return build_cache_name(
        "team_history_response",
        match_id,
        "flashscore_first",
        "v4",
        f"ttl_{TEAM_HISTORY_RESPONSE_CACHE_TTL_MINUTES}",
    )


# Cette fonction ajoute les metadonnees du cache de reponse dans une reponse team-history.
def attach_team_history_response_cache_metadata(
    response: dict[str, Any],
    cache_payload: dict[str, Any],
    from_cache: bool,
) -> dict[str, Any]:
    data_freshness = response.get("data_freshness", {}) or {}

    return {
        **response,
        "data_freshness": {
            **data_freshness,
            "team_history_response_cache": build_data_freshness(
                cache_payload=cache_payload,
                from_cache=from_cache,
                ttl_minutes=TEAM_HISTORY_RESPONSE_CACHE_TTL_MINUTES,
            ),
        },
    }


# Cette fonction normalise un nom d'équipe pour comparer des sources différentes malgré les suffixes pays.
def normalize_team_name(value: str | None) -> str:
    raw_value = str(value or "").strip().lower()

    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", raw_value)
        if not unicodedata.combining(char)
    )

    without_country_suffix = without_accents
    if without_country_suffix.endswith(")") and "(" in without_country_suffix:
        without_country_suffix = without_country_suffix.rsplit("(", 1)[0]

    normalized = (
        without_country_suffix
        .replace(".", " ")
        .replace("-", " ")
        .replace("_", " ")
    )

    return " ".join(normalized.split())


# Cette fonction construit une liste de noms possibles pour reconnaitre une equipe entre plusieurs sources.
def build_team_name_candidates(
    team: dict[str, Any],
    extra_names: list[str | None] | None = None,
) -> list[str]:
    candidates = [
        team.get("name"),
        team.get("shortName"),
        team.get("tla"),
        *(extra_names or []),
    ]

    normalized_candidates: list[str] = []

    for candidate in candidates:
        normalized_candidate = normalize_team_name(candidate)

        if normalized_candidate and normalized_candidate not in normalized_candidates:
            normalized_candidates.append(normalized_candidate)

    return normalized_candidates


# Cette fonction verifie si le nom d'une equipe source correspond a l'un des noms attendus.
def does_team_name_match(team_data: dict[str, Any], team_names: list[str]) -> bool:
    return normalize_team_name(team_data.get("name")) in team_names


# Cette fonction securise la lecture des scores plein temps d'un match.
def get_full_time_score(match: dict[str, Any]) -> tuple[int | None, int | None]:
    full_time = match.get("score", {}).get("fullTime", {}) or {}
    return full_time.get("home"), full_time.get("away")


# Cette fonction verifie qu'un match possede un score final exploitable.
def has_usable_score(match: dict[str, Any]) -> bool:
    home_score, away_score = get_full_time_score(match)
    return home_score is not None and away_score is not None


# Cette fonction indique si l'equipe analysee jouait a domicile sur un match donne.
def is_team_home(
    match: dict[str, Any],
    team_id: int | None,
    team_names: list[str],
) -> bool:
    home_team = match.get("homeTeam", {}) or {}

    if team_id and home_team.get("id") == team_id:
        return True

    return does_team_name_match(home_team, team_names)


# Cette fonction indique si l'equipe analysee est presente dans un match donne.
def is_team_in_match(
    match: dict[str, Any],
    team_id: int | None,
    team_names: list[str],
) -> bool:
    home_team = match.get("homeTeam", {}) or {}
    away_team = match.get("awayTeam", {}) or {}

    if team_id and (home_team.get("id") == team_id or away_team.get("id") == team_id):
        return True

    return does_team_name_match(home_team, team_names) or does_team_name_match(
        away_team,
        team_names,
    )


# Cette fonction verifie qu'un match d'historique est strictement anterieur au match analyse.
def is_match_before_target(
    match: dict[str, Any],
    target_utc_date: str | None,
) -> bool:
    if not target_utc_date:
        return True

    match_utc_date = match.get("utcDate")

    if not match_utc_date:
        return False

    return match_utc_date < target_utc_date


# Cette fonction exclut le match analyse et les matchs joues apres lui pour respecter la logique avant-match.
def filter_matches_before_target(
    matches: list[dict[str, Any]],
    excluded_match_id: int,
    target_utc_date: str | None,
) -> list[dict[str, Any]]:
    return [
        match
        for match in matches
        if match.get("id") != excluded_match_id
        and is_match_before_target(match, target_utc_date)
    ]


# Cette fonction calcule le resultat W/D/L d'une equipe sur un match termine.
def get_team_result(
    match: dict[str, Any],
    team_id: int | None,
    team_names: list[str],
) -> str | None:
    if not is_team_in_match(match, team_id, team_names) or not has_usable_score(match):
        return None

    home_score, away_score = get_full_time_score(match)

    if home_score == away_score:
        return "D"

    if is_team_home(match, team_id, team_names):
        return "W" if home_score > away_score else "L"

    return "W" if away_score > home_score else "L"


# Cette fonction calcule les buts marques et encaisses par l'equipe analysee.
def get_team_goals_for_against(
    match: dict[str, Any],
    team_id: int | None,
    team_names: list[str],
) -> tuple[int | None, int | None]:
    if not is_team_in_match(match, team_id, team_names) or not has_usable_score(match):
        return None, None

    home_score, away_score = get_full_time_score(match)

    if is_team_home(match, team_id, team_names):
        return home_score, away_score

    return away_score, home_score


# Cette fonction normalise un match termine dans un format stable pour le front RubyBets.
def format_recent_match(
    match: dict[str, Any],
    team_id: int | None,
    team_names: list[str],
) -> dict[str, Any] | None:
    team_result = get_team_result(match, team_id, team_names)
    goals_for, goals_against = get_team_goals_for_against(match, team_id, team_names)
    home_score, away_score = get_full_time_score(match)

    if team_result is None or goals_for is None or goals_against is None:
        return None

    return {
        "match_id": match.get("id"),
        "utc_date": match.get("utcDate"),
        "competition_name": match.get("competition", {}).get("name"),
        "home_team": match.get("homeTeam", {}).get("name"),
        "away_team": match.get("awayTeam", {}).get("name"),
        "home_score": home_score,
        "away_score": away_score,
        "team_result": team_result,
        "is_home": is_team_home(match, team_id, team_names),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "data_source": match.get("data_source", "football_data"),
    }


# Cette fonction trie les matchs bruts du plus recent au plus ancien selon la date UTC.
def sort_matches_by_recent_date(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        matches,
        key=lambda match: match.get("utcDate") or "",
        reverse=True,
    )


# Cette fonction trie les matchs normalises du plus recent au plus ancien selon la date UTC.
def sort_formatted_matches_by_recent_date(
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        matches,
        key=lambda match: match.get("utc_date") or "",
        reverse=True,
    )


# Cette fonction construit une cle de dedoublonnage entre sources pour eviter les doublons visibles.
def build_match_dedup_key(match: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(match.get("utc_date") or match.get("utcDate") or "")[:10],
        normalize_team_name(match.get("home_team") or match.get("homeTeam", {}).get("name")),
        normalize_team_name(match.get("away_team") or match.get("awayTeam", {}).get("name")),
        f"{match.get('home_score') or match.get('score', {}).get('fullTime', {}).get('home')}-"
        f"{match.get('away_score') or match.get('score', {}).get('fullTime', {}).get('away')}",
    )


# Cette fonction supprime les doublons apres normalisation des matchs recents.
def deduplicate_formatted_matches(
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen_keys: set[tuple[str, str, str, str]] = set()
    unique_matches = []

    for match in matches:
        key = build_match_dedup_key(match)

        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_matches.append(match)

    return unique_matches


# Cette fonction fusionne des matchs deja normalises sans afficher de doublons entre plusieurs sources.
def merge_formatted_matches(
    primary_matches: list[dict[str, Any]],
    secondary_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return deduplicate_formatted_matches(
        sort_formatted_matches_by_recent_date(
            [
                *primary_matches,
                *secondary_matches,
            ]
        )
    )


# Cette fonction reconstruit un bloc historique apres ajout d'une source complementaire.
def rebuild_history_with_matches(
    history: dict[str, Any],
    formatted_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **history,
        "recent_matches": formatted_matches,
        "recent_matches_overview": formatted_matches[:OVERVIEW_RECENT_MATCHES_LIMIT],
        "form_summary": build_form_summary(formatted_matches),
    }


# Cette fonction indique si un historique possede assez de matchs pour l'aperçu MVP.
def has_enough_recent_overview_matches(history: dict[str, Any]) -> bool:
    return len(history.get("recent_matches_overview", [])) >= OVERVIEW_RECENT_MATCHES_LIMIT


# Cette fonction indique si un historique possède assez de matchs pour alimenter un moteur clubs.
def has_enough_analysis_matches(history: dict[str, Any]) -> bool:
    return len(history.get("recent_matches", [])) >= CLUB_ANALYSIS_RECENT_MATCHES_MIN


# Cette fonction calcule la synthese de forme d'une equipe a partir de ses matchs normalises.
def build_form_summary(recent_matches: list[dict[str, Any]]) -> dict[str, Any]:
    matches_count = len(recent_matches)
    wins = sum(1 for match in recent_matches if match.get("team_result") == "W")
    draws = sum(1 for match in recent_matches if match.get("team_result") == "D")
    losses = sum(1 for match in recent_matches if match.get("team_result") == "L")
    goals_for = sum(match.get("goals_for") or 0 for match in recent_matches)
    goals_against = sum(match.get("goals_against") or 0 for match in recent_matches)

    return {
        "matches_count": matches_count,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "avg_goals_for": round(goals_for / matches_count, 2) if matches_count else 0,
        "avg_goals_against": round(goals_against / matches_count, 2) if matches_count else 0,
        "recent_series": [match.get("team_result") for match in recent_matches],
    }


# Cette fonction recupere les matchs termines d'une equipe via le cache RubyBets puis Football-Data.
async def get_team_finished_matches(
    team_id: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data, freshness = await get_cached_football_data(
        cache_name=build_team_matches_cache_name(team_id),
        endpoint=f"/teams/{team_id}/matches",
        params={
            "status": "FINISHED",
            "limit": TEAM_HISTORY_LIMIT,
        },
        ttl_minutes=TEAM_HISTORY_CACHE_TTL_MINUTES,
    )

    if data.get("status") == "error":
        return [], freshness

    matches = data.get("matches", [])

    for match in matches:
        match["data_source"] = "football_data"

    return matches, freshness


# Cette fonction recupere les matchs termines d'une equipe via API-Football si Football-Data est insuffisant.
async def get_api_football_finished_matches(
    team_name: str,
    target_utc_date: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    matches, metadata = await get_normalized_api_football_team_history(
        team_name=team_name,
        target_date=target_utc_date,
        limit=API_FOOTBALL_HISTORY_LIMIT,
    )

    return matches, {
        "provider": "api_football",
        "from_cache": False,
        "status": metadata.get("status"),
        "api_team_id": metadata.get("api_team_id"),
        "api_team_name": metadata.get("api_team_name"),
        "results": metadata.get("results", 0),
        "raw_results": metadata.get("raw_results"),
        "message": metadata.get("message"),
    }


# Cette fonction formate une liste de matchs bruts pour une equipe donnee.
def format_team_matches(
    matches: list[dict[str, Any]],
    team_id: int | None,
    team_names: list[str],
) -> list[dict[str, Any]]:
    return [
        formatted_match
        for match in sort_matches_by_recent_date(matches)
        if (formatted_match := format_recent_match(match, team_id, team_names)) is not None
    ]


# Cette fonction construit l'historique normalise initial d'une equipe avec Football-Data.
async def build_team_history(
    team: dict[str, Any],
    excluded_match_id: int,
    target_utc_date: str | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    team_id = team.get("id")
    team_name = team.get("name")

    if not team_id and not team_name:
        return {
            "team_id": None,
            "team_name": None,
            "recent_matches": [],
            "recent_matches_overview": [],
            "form_summary": build_form_summary([]),
        }, {}, []

    football_data_matches: list[dict[str, Any]] = []
    football_data_freshness: dict[str, Any] = {}

    if team_id:
        football_data_matches, football_data_freshness = await get_team_finished_matches(
            team_id=team_id,
        )

    football_data_eligible_matches = filter_matches_before_target(
        matches=football_data_matches,
        excluded_match_id=excluded_match_id,
        target_utc_date=target_utc_date,
    )

    api_football_freshness: dict[str, Any] = {
        "provider": "api_football",
        "status": "not_called",
        "reason": "flashscore_rapidapi_used_as_priority_fallback",
        "results": 0,
    }
    team_names = build_team_name_candidates(team)

    all_eligible_matches = [
        *football_data_eligible_matches,
    ]
    formatted_matches = deduplicate_formatted_matches(
        sort_formatted_matches_by_recent_date(
            format_team_matches(
                matches=all_eligible_matches,
                team_id=team_id,
                team_names=team_names,
            )
        )
    )

    freshness = {
        "provider": "multi_source_team_history",
        "football_data": football_data_freshness,
        "api_football": api_football_freshness,
        "sources_used": sorted(
            {
                match.get("data_source", "football_data")
                for match in formatted_matches
            }
        ),
    }

    return {
        "team_id": team_id,
        "team_name": team_name,
        "team": format_team(team),
        "recent_matches": formatted_matches,
        "recent_matches_overview": formatted_matches[:OVERVIEW_RECENT_MATCHES_LIMIT],
        "form_summary": build_form_summary(formatted_matches),
    }, freshness, all_eligible_matches


# Cette fonction construit un historique vide en conservant les informations de l'equipe.
def build_empty_team_history(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_id": team.get("id"),
        "team_name": team.get("name"),
        "team": format_team(team),
        "recent_matches": [],
        "recent_matches_overview": [],
        "form_summary": build_form_summary([]),
    }


# Cette fonction construit des metadonnees standard quand une source n'est pas appelee.
def build_not_called_freshness(provider: str, reason: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "status": "not_called",
        "reason": reason,
        "results": 0,
    }


# Cette fonction extrait l'identifiant equipe FlashScore conserve dans un match normalise RubyBets.
def get_flashscore_source_team_id(team: dict[str, Any]) -> str | None:
    source_team_id = team.get("sourceTeamId") or team.get("source_team_id")
    return str(source_team_id) if source_team_id else None


# Cette fonction indique si un match normalise provient de FlashScore et contient les identifiants utiles.
def is_flashscore_match_payload(match: dict[str, Any]) -> bool:
    return bool(
        match.get("sourceMatchId")
        or match.get("source") == "flashscore_rapidapi"
        or match.get("data_source") == "flashscore_rapidapi"
    )


# Cette fonction construit un match_data compatible team-history depuis /matches/details FlashScore.
def build_flashscore_match_data_for_team_history(
    match_id: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    flashscore_match, metadata = get_normalized_flashscore_match_details(match_id)

    if not flashscore_match:
        return None, metadata

    return {
        "match": flashscore_match,
        "competition_code": flashscore_match.get("competition", {}).get("code"),
        "home_standing": None,
        "away_standing": None,
        "data_freshness": {
            "match": {
                "source": "flashscore_rapidapi",
                "provider": "flashscore_rapidapi",
                "from_cache": False,
                "updated_at": flashscore_match.get("lastUpdated"),
                "last_updated": flashscore_match.get("lastUpdated"),
                "ttl_minutes": None,
                "metadata": metadata,
            },
            "standings": None,
        },
    }, metadata


# Cette fonction recupere le match cible pour team-history en priorisant FlashScore puis Football-Data.
async def get_match_data_for_team_history(match_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    flashscore_match_data, flashscore_metadata = build_flashscore_match_data_for_team_history(match_id)

    if flashscore_match_data:
        return flashscore_match_data, {
            "provider": "flashscore_rapidapi",
            "status": "success",
            "strategy": "flashscore_details_primary",
            "flashscore": flashscore_metadata,
        }

    football_data_match_data = await get_match_with_standings(match_id)

    return football_data_match_data, {
        "provider": FOOTBALL_DATA_PROVIDER,
        "status": "fallback_used",
        "strategy": "football_data_fallback_after_flashscore_details",
        "flashscore": flashscore_metadata,
    }


# Cette fonction fusionne un historique principal avec un historique de fallback sans casser la source prioritaire.
def merge_history_with_fallback(
    primary_history: dict[str, Any],
    fallback_history: dict[str, Any],
) -> dict[str, Any]:
    merged_matches = merge_formatted_matches(
        primary_matches=primary_history.get("recent_matches", []),
        secondary_matches=fallback_history.get("recent_matches", []),
    )

    return rebuild_history_with_matches(primary_history, merged_matches)



# Cette fonction complete les historiques a partir des identifiants FlashScore deja presents dans le detail match.
async def enrich_histories_with_known_flashscore_match(
    home_history: dict[str, Any],
    away_history: dict[str, Any],
    match: dict[str, Any],
    home_team: dict[str, Any],
    away_team: dict[str, Any],
    target_utc_date: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    home_team_name = home_team.get("name")
    away_team_name = away_team.get("name")
    flashscore_match_id = match.get("sourceMatchId")
    home_source_team_id = get_flashscore_source_team_id(home_team)
    away_source_team_id = get_flashscore_source_team_id(away_team)

    if not home_team_name or not away_team_name:
        return home_history, away_history, {
            "provider": "flashscore_rapidapi",
            "status": "not_called",
            "reason": "missing_team_name",
        }, [], []

    if not home_source_team_id or not away_source_team_id or not flashscore_match_id:
        return await enrich_histories_with_flashscore(
            home_history=home_history,
            away_history=away_history,
            home_team=home_team,
            away_team=away_team,
            target_utc_date=target_utc_date,
        )

    home_results, home_metadata = get_normalized_flashscore_team_results(
        team_id=home_source_team_id,
        target_utc_date=target_utc_date,
        limit=FLASHSCORE_HISTORY_LIMIT,
    )
    away_results, away_metadata = get_normalized_flashscore_team_results(
        team_id=away_source_team_id,
        target_utc_date=target_utc_date,
        limit=FLASHSCORE_HISTORY_LIMIT,
    )
    head_to_head_results, head_to_head_metadata = get_flashscore_head_to_head(
        flashscore_match_id=flashscore_match_id,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )

    home_team_names = build_team_name_candidates(home_team)
    away_team_names = build_team_name_candidates(away_team)

    home_flashscore_formatted = format_team_matches(
        matches=home_results,
        team_id=None,
        team_names=home_team_names,
    )
    away_flashscore_formatted = format_team_matches(
        matches=away_results,
        team_id=None,
        team_names=away_team_names,
    )

    should_enrich_home = not has_enough_analysis_matches(home_history)
    should_enrich_away = not has_enough_analysis_matches(away_history)

    enriched_home_matches = (
        merge_formatted_matches(
            primary_matches=home_history.get("recent_matches", []),
            secondary_matches=home_flashscore_formatted,
        )
        if should_enrich_home
        else home_history.get("recent_matches", [])
    )
    enriched_away_matches = (
        merge_formatted_matches(
            primary_matches=away_history.get("recent_matches", []),
            secondary_matches=away_flashscore_formatted,
        )
        if should_enrich_away
        else away_history.get("recent_matches", [])
    )

    return (
        rebuild_history_with_matches(home_history, enriched_home_matches),
        rebuild_history_with_matches(away_history, enriched_away_matches),
        {
            "provider": "flashscore_rapidapi",
            "status": "success" if home_results or away_results or head_to_head_results else "empty",
            "strategy": "details_ids_primary",
            "match_id": flashscore_match_id,
            "home_team_id": home_source_team_id,
            "away_team_id": away_source_team_id,
            "home_team_results": home_metadata,
            "away_team_results": away_metadata,
            "head_to_head": head_to_head_metadata,
        },
        home_results,
        head_to_head_results,
    )


# Cette fonction complete les historiques avec FlashScore et recupere les confrontations directes filtrees.
async def enrich_histories_with_flashscore(
    home_history: dict[str, Any],
    away_history: dict[str, Any],
    home_team: dict[str, Any],
    away_team: dict[str, Any],
    target_utc_date: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    home_team_name = home_team.get("name")
    away_team_name = away_team.get("name")

    if not home_team_name or not away_team_name:
        return home_history, away_history, {
            "provider": "flashscore_rapidapi",
            "status": "not_called",
            "reason": "missing_team_name",
        }, [], []

    flashscore_histories, flashscore_metadata = get_flashscore_histories_for_match(
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        target_utc_date=target_utc_date,
        limit=FLASHSCORE_HISTORY_LIMIT,
    )

    home_team_names = build_team_name_candidates(home_team)
    away_team_names = build_team_name_candidates(away_team)

    home_flashscore_formatted = format_team_matches(
        matches=flashscore_histories.get("home", []),
        team_id=None,
        team_names=home_team_names,
    )
    away_flashscore_formatted = format_team_matches(
        matches=flashscore_histories.get("away", []),
        team_id=None,
        team_names=away_team_names,
    )

    should_enrich_home = not has_enough_analysis_matches(home_history)
    should_enrich_away = not has_enough_analysis_matches(away_history)

    enriched_home_matches = (
        merge_formatted_matches(
            primary_matches=home_history.get("recent_matches", []),
            secondary_matches=home_flashscore_formatted,
        )
        if should_enrich_home
        else home_history.get("recent_matches", [])
    )
    enriched_away_matches = (
        merge_formatted_matches(
            primary_matches=away_history.get("recent_matches", []),
            secondary_matches=away_flashscore_formatted,
        )
        if should_enrich_away
        else away_history.get("recent_matches", [])
    )

    return (
        rebuild_history_with_matches(home_history, enriched_home_matches),
        rebuild_history_with_matches(away_history, enriched_away_matches),
        flashscore_metadata,
        flashscore_histories.get("home", []),
        flashscore_histories.get("head_to_head", []),
    )


# Cette fonction formate une confrontation directe passee entre les deux equipes.
def format_head_to_head_match(match: dict[str, Any]) -> dict[str, Any] | None:
    if not has_usable_score(match):
        return None

    home_score, away_score = get_full_time_score(match)

    if home_score == away_score:
        result_label = "Match nul"
    elif home_score > away_score:
        result_label = f"Victoire {match.get('homeTeam', {}).get('name')}"
    else:
        result_label = f"Victoire {match.get('awayTeam', {}).get('name')}"

    return {
        "match_id": match.get("id"),
        "utc_date": match.get("utcDate"),
        "competition_name": match.get("competition", {}).get("name"),
        "home_team": match.get("homeTeam", {}).get("name"),
        "away_team": match.get("awayTeam", {}).get("name"),
        "home_score": home_score,
        "away_score": away_score,
        "result_label": result_label,
        "data_source": match.get("data_source", "football_data"),
    }


# Cette fonction verifie si un match oppose les deux equipes analysees.
def is_match_between_teams(
    match: dict[str, Any],
    home_team_id: int | None,
    away_team_id: int | None,
    home_team_names: list[str],
    away_team_names: list[str],
) -> bool:
    first_team_present = is_team_in_match(match, home_team_id, home_team_names)
    second_team_present = is_team_in_match(match, away_team_id, away_team_names)
    return first_team_present and second_team_present


# Cette fonction extrait les confrontations directes disponibles depuis l'historique toutes competitions confondues.
def build_head_to_head(
    home_team_matches: list[dict[str, Any]],
    home_team: dict[str, Any],
    away_team: dict[str, Any],
) -> list[dict[str, Any]]:
    home_team_id = home_team.get("id")
    away_team_id = away_team.get("id")
    home_team_names = build_team_name_candidates(home_team)
    away_team_names = build_team_name_candidates(away_team)
    h2h_matches = []

    for match in sort_matches_by_recent_date(home_team_matches):
        if not is_match_between_teams(
            match=match,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_team_names=home_team_names,
            away_team_names=away_team_names,
        ):
            continue

        formatted_match = format_head_to_head_match(match)

        if formatted_match:
            h2h_matches.append(formatted_match)

    return deduplicate_formatted_matches(h2h_matches)[:OVERVIEW_RECENT_MATCHES_LIMIT]


# Cette fonction produit un libelle prudent pour qualifier une forme recente.
def build_form_label(form_summary: dict[str, Any]) -> str:
    matches_count = form_summary.get("matches_count", 0)

    if matches_count == 0:
        return "Forme recente indisponible"

    wins = form_summary.get("wins", 0)
    losses = form_summary.get("losses", 0)

    if wins > losses:
        return "Forme recente plutot favorable"

    if losses > wins:
        return "Forme recente plus fragile"

    return "Forme recente equilibree"


# Cette fonction construit une synthese prudente qui ne promet jamais un resultat sportif.
def build_history_summary(
    home_history: dict[str, Any],
    away_history: dict[str, Any],
    head_to_head: list[dict[str, Any]],
) -> dict[str, Any]:
    home_summary = home_history.get("form_summary", {})
    away_summary = away_history.get("form_summary", {})

    return {
        "home_recent_form_label": build_form_label(home_summary),
        "away_recent_form_label": build_form_label(away_summary),
        "comparison_note": (
            "La lecture de forme repose sur les matchs termines disponibles "
            "dans les sources gratuites ou limitees, toutes competitions confondues lorsque la source le permet. "
            "Elle aide a situer les dynamiques recentes sans constituer une certitude sportive."
        ),
        "head_to_head_note": (
            "Confrontations directes disponibles dans l'historique recent."
            if head_to_head
            else "Aucune confrontation directe disponible avec les sources actuelles."
        ),
        "responsible_note": (
            "Lecture analytique basee sur les donnees disponibles, "
            "sans garantie de resultat."
        ),
    }


# Cette fonction determine le statut global de disponibilite des donnees d'historique.
def resolve_data_status(
    home_history: dict[str, Any],
    away_history: dict[str, Any],
) -> str:
    home_count = len(home_history.get("recent_matches_overview", []))
    away_count = len(away_history.get("recent_matches_overview", []))

    if home_count >= OVERVIEW_RECENT_MATCHES_LIMIT and away_count >= OVERVIEW_RECENT_MATCHES_LIMIT:
        return "available"

    if home_count or away_count:
        return "partial"

    return "unavailable"


# Cette fonction determine les sources reellement utilisees pour construire l'historique.
def resolve_source_used(
    data_status: str,
    home_history: dict[str, Any],
    away_history: dict[str, Any],
) -> str:
    if data_status == "unavailable":
        return "unavailable"

    sources = {
        match.get("data_source")
        for history in (home_history, away_history)
        for match in history.get("recent_matches", [])
        if match.get("data_source")
    }

    if len(sources) > 1:
        return "mixed"

    if sources:
        return next(iter(sources))

    return "unavailable"


# Cette fonction prepare une synthese lisible de fraicheur et de limites pour l'interface.
def build_team_history_freshness(
    source_used: str,
    match_data: dict[str, Any],
    home_freshness: dict[str, Any],
    away_freshness: dict[str, Any],
    flashscore_freshness: dict[str, Any],
    match_lookup_freshness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "last_updated_at": match_data.get("match", {}).get("lastUpdated"),
        "source_label": "FlashScore RapidAPI + Football-Data.org fallback",
        "is_cache": source_used == "cache",
        "match_cache": match_data.get("data_freshness", {}).get("match"),
        "home_team_history_cache": home_freshness,
        "away_team_history_cache": away_freshness,
        "flashscore_team_history": flashscore_freshness,
        "match_lookup": match_lookup_freshness or {},
        "source_strategy": "flashscore_first",
        "limitations": [
            (
                "FlashScore RapidAPI est utilisee comme source principale pour les derniers matchs "
                "et les confrontations directes lorsque le match peut etre rapproche."
            ),
            (
                "Football-Data.org reste utilise en fallback si FlashScore ne fournit pas assez "
                "de matchs recents exploitables."
            ),
            (
                "Les cotes eventuellement presentes dans les reponses FlashScore ne sont pas utilisees "
                "par RubyBets pour cette section."
            ),
            (
                "Certaines rencontres peuvent rester absentes si les noms d'equipes different entre les sources "
                "ou si aucune source disponible ne les expose."
            ),
            (
                "Aucune donnee n'est inventee pour combler les limites de couverture."
            ),
        ],
    }


# Cette fonction construit la reponse complete de la route produit /team-history avec cache 12h et priorite FlashScore.
async def build_team_history_response(match_id: int) -> dict[str, Any]:
    response_cache_name = build_team_history_response_cache_name(match_id)
    cached_response = load_cache(response_cache_name)

    if cached_response and is_cache_fresh(
        cached_response,
        ttl_minutes=TEAM_HISTORY_RESPONSE_CACHE_TTL_MINUTES,
    ):
        return attach_team_history_response_cache_metadata(
            response=cached_response.get("data", {}),
            cache_payload=cached_response,
            from_cache=True,
        )

    match_data, match_lookup_freshness = await get_match_data_for_team_history(match_id)
    match = match_data["match"]
    home_team = match.get("homeTeam", {})
    away_team = match.get("awayTeam", {})
    target_utc_date = match.get("utcDate")

    home_history = build_empty_team_history(home_team)
    away_history = build_empty_team_history(away_team)
    home_freshness = build_not_called_freshness(
        provider=FOOTBALL_DATA_PROVIDER,
        reason="flashscore_rapidapi_used_as_primary_source",
    )
    away_freshness = build_not_called_freshness(
        provider=FOOTBALL_DATA_PROVIDER,
        reason="flashscore_rapidapi_used_as_primary_source",
    )
    home_eligible_matches: list[dict[str, Any]] = []

    if is_flashscore_match_payload(match):
        (
            home_history,
            away_history,
            flashscore_freshness,
            flashscore_home_eligible_matches,
            flashscore_head_to_head_matches,
        ) = await enrich_histories_with_known_flashscore_match(
            home_history=home_history,
            away_history=away_history,
            match=match,
            home_team=home_team,
            away_team=away_team,
            target_utc_date=target_utc_date,
        )
    else:
        (
            home_history,
            away_history,
            flashscore_freshness,
            flashscore_home_eligible_matches,
            flashscore_head_to_head_matches,
        ) = await enrich_histories_with_flashscore(
            home_history=home_history,
            away_history=away_history,
            home_team=home_team,
            away_team=away_team,
            target_utc_date=target_utc_date,
        )

    if not has_enough_analysis_matches(home_history):
        fallback_home_history, home_freshness, home_eligible_matches = await build_team_history(
            team=home_team,
            excluded_match_id=match_id,
            target_utc_date=target_utc_date,
        )
        home_history = merge_history_with_fallback(
            primary_history=home_history,
            fallback_history=fallback_home_history,
        )

    if not has_enough_analysis_matches(away_history):
        fallback_away_history, away_freshness, _ = await build_team_history(
            team=away_team,
            excluded_match_id=match_id,
            target_utc_date=target_utc_date,
        )
        away_history = merge_history_with_fallback(
            primary_history=away_history,
            fallback_history=fallback_away_history,
        )

    head_to_head = build_head_to_head(
        home_team_matches=[
            *flashscore_head_to_head_matches,
            *flashscore_home_eligible_matches,
            *home_eligible_matches,
        ],
        home_team=home_team,
        away_team=away_team,
    )

    data_status = resolve_data_status(home_history, away_history)
    source_used = resolve_source_used(
        data_status=data_status,
        home_history=home_history,
        away_history=away_history,
    )

    response = {
        "match_id": match_id,
        "source_used": source_used,
        "data_status": data_status,
        "home_team_history": home_history,
        "away_team_history": away_history,
        "head_to_head": head_to_head,
        "summary": build_history_summary(home_history, away_history, head_to_head),
        "data_freshness": build_team_history_freshness(
            source_used=source_used,
            match_data=match_data,
            home_freshness=home_freshness,
            away_freshness=away_freshness,
            flashscore_freshness=flashscore_freshness,
            match_lookup_freshness=match_lookup_freshness,
        ),
    }

    saved_response = save_cache(
        cache_name=response_cache_name,
        data=response,
        source="rubybets_team_history_flashscore_first",
    )

    return attach_team_history_response_cache_metadata(
        response=response,
        cache_payload=saved_response,
        from_cache=False,
    )


# Schema de communication du fichier :
# team_history_service.py
# ├── utilise match_service.py pour recuperer le match cible et ses equipes
# ├── utilise rapidapi_flashscore_client.py en priorite pour retrouver le match FlashScore, les derniers resultats et le H2H
# ├── utilise cache_service.py pour conserver la reponse team-history pendant 12h
# ├── utilise Football-Data en fallback si FlashScore ne fournit pas assez de matchs
# ├── filtre uniquement par date pour garder une logique avant-match toutes competitions confondues
# ├── normalise les historiques, statistiques de forme et confrontations directes
# └── fournit une reponse produit a app/api/matches.py pour le frontend RubyBets