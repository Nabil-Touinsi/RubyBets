# Ce fichier construit les compositions du match et un fallback historique transparent quand la source actuelle est vide.
# Il ne déduit jamais une composition probable : il réutilise uniquement des compositions officielles réellement publiées.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.config import settings
from app.services.cache_service import (
    build_cache_name,
    build_data_freshness,
    is_cache_fresh,
    load_cache,
    save_cache,
)
from app.services.rapidapi_flashscore_client import (
    FLASHSCORE_SOURCE,
    decode_flashscore_match_id,
    encode_flashscore_match_id,
    get_rapidapi_flashscore_data,
)
from app.services.team_history_service import build_team_history_response


CURRENT_LINEUPS_CACHE_TTL_MINUTES = 60
EMPTY_LINEUPS_CACHE_TTL_MINUTES = 10
HISTORICAL_LINEUPS_CACHE_TTL_MINUTES = 30 * 24 * 60
HISTORICAL_LINEUPS_MATCH_LIMIT = 5


# Cette fonction indique si FlashScore RapidAPI est configuré dans l'environnement courant.
def is_flashscore_lineups_available() -> bool:
    return bool(settings.rapidapi_key.strip())


# Cette fonction construit la clé de cache des compositions du match actuellement analysé.
def build_current_lineups_cache_name(match_id: int) -> str:
    return build_cache_name("flashscore_lineups", match_id)


# Cette fonction construit la clé de cache longue durée d'une composition officielle historique.
def build_historical_lineups_cache_name(source_match_id: str) -> str:
    return build_cache_name("flashscore_historical_lineups", source_match_id)


# Cette fonction extrait une liste de compositions depuis les différents formats possibles de FlashScore.
def extract_flashscore_lineups_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    lineups = payload.get("lineups")

    if isinstance(lineups, list):
        return [item for item in lineups if isinstance(item, dict)]

    if isinstance(lineups, dict):
        nested_data = lineups.get("data")
        if isinstance(nested_data, list):
            return [item for item in nested_data if isinstance(item, dict)]

    data = payload.get("data")

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


# Cette fonction vérifie qu'une réponse brute contient au moins une composition, une formation ou une absence exploitable.
def has_any_raw_lineup_signal(payload: Any) -> bool:
    for lineup_side in extract_flashscore_lineups_list(payload):
        if any(
            lineup_side.get(field)
            for field in (
                "startingLineups",
                "substitutes",
                "predictedLineups",
                "missingPlayers",
                "unsureMissingPlayers",
                "formation",
                "predictedFormation",
            )
        ):
            return True

    return False


# Cette fonction choisit un TTL court pour les réponses vides et un TTL normal pour les données présentes.
def resolve_current_lineups_cache_ttl(payload: dict[str, Any]) -> int:
    return (
        CURRENT_LINEUPS_CACHE_TTL_MINUTES
        if has_any_raw_lineup_signal(payload)
        else EMPTY_LINEUPS_CACHE_TTL_MINUTES
    )


# Cette fonction appelle la route FlashScore de composition pour un identifiant source précis.
def fetch_flashscore_lineups(source_match_id: str) -> dict[str, Any]:
    raw_lineups = get_rapidapi_flashscore_data(
        endpoint="/matches/match/lineups",
        params={"match_id": source_match_id},
    )

    if isinstance(raw_lineups, dict) and raw_lineups.get("status") == "error":
        return {
            "source_match_id": source_match_id,
            "lineups": [],
            "status": "error",
            "reason": "flashscore_request_failed",
            "error": raw_lineups,
        }

    return {
        "source_match_id": source_match_id,
        "lineups": raw_lineups,
        "status": "available" if has_any_raw_lineup_signal(raw_lineups) else "empty",
        "reason": None if has_any_raw_lineup_signal(raw_lineups) else "lineups_not_published",
    }


# Cette fonction récupère les compositions actuelles depuis le cache ou RapidAPI avec un TTL adapté à leur contenu.
def get_cached_current_flashscore_lineups(
    match_id: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_match_id = decode_flashscore_match_id(match_id)

    if not source_match_id:
        return {
            "source_match_id": None,
            "lineups": [],
            "status": "unavailable",
            "reason": "flashscore_source_match_id_not_found",
        }, {
            "source": FLASHSCORE_SOURCE,
            "from_cache": False,
            "updated_at": None,
            "ttl_minutes": EMPTY_LINEUPS_CACHE_TTL_MINUTES,
        }

    cache_name = build_current_lineups_cache_name(match_id)
    cached_payload = load_cache(cache_name)

    if cached_payload:
        cached_data = cached_payload.get("data", {})
        cached_ttl = resolve_current_lineups_cache_ttl(cached_data)

        if is_cache_fresh(cached_payload, ttl_minutes=cached_ttl):
            return cached_data, build_data_freshness(
                cache_payload=cached_payload,
                from_cache=True,
                ttl_minutes=cached_ttl,
            )

    response_payload = fetch_flashscore_lineups(source_match_id)
    ttl_minutes = resolve_current_lineups_cache_ttl(response_payload)

    if response_payload.get("status") == "error":
        return response_payload, {
            "source": FLASHSCORE_SOURCE,
            "from_cache": False,
            "updated_at": None,
            "ttl_minutes": ttl_minutes,
        }

    saved_payload = save_cache(
        cache_name=cache_name,
        data=response_payload,
        source=FLASHSCORE_SOURCE,
    )

    return saved_payload.get("data", {}), build_data_freshness(
        cache_payload=saved_payload,
        from_cache=False,
        ttl_minutes=ttl_minutes,
    )


# Cette fonction récupère une composition historique officielle avec un cache long car le match est terminé.
def get_cached_historical_flashscore_lineups(
    source_match_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cache_name = build_historical_lineups_cache_name(source_match_id)
    cached_payload = load_cache(cache_name)

    if cached_payload and is_cache_fresh(
        cached_payload,
        ttl_minutes=HISTORICAL_LINEUPS_CACHE_TTL_MINUTES,
    ):
        return cached_payload.get("data", {}), build_data_freshness(
            cache_payload=cached_payload,
            from_cache=True,
            ttl_minutes=HISTORICAL_LINEUPS_CACHE_TTL_MINUTES,
        )

    response_payload = fetch_flashscore_lineups(source_match_id)

    if response_payload.get("status") == "error":
        return response_payload, {
            "source": FLASHSCORE_SOURCE,
            "from_cache": False,
            "updated_at": None,
            "ttl_minutes": HISTORICAL_LINEUPS_CACHE_TTL_MINUTES,
        }

    saved_payload = save_cache(
        cache_name=cache_name,
        data=response_payload,
        source=FLASHSCORE_SOURCE,
    )

    return saved_payload.get("data", {}), build_data_freshness(
        cache_payload=saved_payload,
        from_cache=False,
        ttl_minutes=HISTORICAL_LINEUPS_CACHE_TTL_MINUTES,
    )


# Cette fonction normalise un joueur FlashScore sans confondre sa nationalité avec son club.
def normalize_flashscore_lineup_player(player: Any) -> dict[str, Any]:
    if not isinstance(player, dict):
        return {}

    return {
        "name": player.get("name"),
        "field_name": player.get("fieldName"),
        "number": player.get("number"),
        "player_id": player.get("player_id"),
        "player_url": player.get("player_url"),
        "image_path": player.get("image_path"),
        "country_name": player.get("country_name"),
        "country_logo": player.get("country_image_path"),
        "club_name": player.get("club_name"),
        "club_logo": player.get("club_image_path"),
        "reason": player.get("reason"),
    }


# Cette fonction normalise le bloc domicile ou extérieur d'une composition FlashScore.
def normalize_flashscore_lineup_side(
    lineup_side: dict[str, Any] | None,
    side: str,
) -> dict[str, Any]:
    safe_side = lineup_side if isinstance(lineup_side, dict) else {}
    starting_lineups = [
        normalize_flashscore_lineup_player(player)
        for player in safe_side.get("startingLineups", [])
        if isinstance(player, dict)
    ]
    substitutes = [
        normalize_flashscore_lineup_player(player)
        for player in safe_side.get("substitutes", [])
        if isinstance(player, dict)
    ]
    predicted_lineups = [
        normalize_flashscore_lineup_player(player)
        for player in safe_side.get("predictedLineups", [])
        if isinstance(player, dict)
    ]
    missing_players = [
        normalize_flashscore_lineup_player(player)
        for player in safe_side.get("missingPlayers", [])
        if isinstance(player, dict)
    ]
    unsure_missing_players = [
        normalize_flashscore_lineup_player(player)
        for player in safe_side.get("unsureMissingPlayers", [])
        if isinstance(player, dict)
    ]

    official_formation = safe_side.get("formation")
    predicted_formation = safe_side.get("predictedFormation")
    official_available = bool(starting_lineups or substitutes or official_formation)
    predicted_available = bool(predicted_lineups or predicted_formation)

    return {
        "side": side,
        "status": (
            "official_available"
            if official_available
            else "predicted_available"
            if predicted_available
            else "absences_only"
            if missing_players or unsure_missing_players
            else "unavailable"
        ),
        "composition_origin": (
            "current_official"
            if official_available
            else "current_predicted"
            if predicted_available
            else "none"
        ),
        "average_rating": safe_side.get("averageRating"),
        "formation": official_formation or predicted_formation,
        "official_formation": official_formation,
        "predicted_formation": predicted_formation,
        "official_available": official_available,
        "predicted_available": predicted_available,
        "historical_official_available": False,
        "starting_lineups": starting_lineups,
        "substitutes": substitutes,
        "predicted_lineups": predicted_lineups,
        "missing_players": missing_players,
        "unsure_missing_players": unsure_missing_players,
        "reference_match": None,
    }


# Cette fonction retrouve le bloc domicile ou extérieur dans la réponse FlashScore.
def find_flashscore_lineup_side(
    lineups: list[dict[str, Any]],
    side: str,
) -> dict[str, Any] | None:
    for lineup in lineups:
        if str(lineup.get("side", "")).lower() == side:
            return lineup

    return None


# Cette fonction construit les limites responsables visibles avec les compositions actuelles ou historiques.
def build_lineups_limits() -> list[str]:
    return [
        "Une composition officielle ou probable est affichée uniquement lorsque la source la publie.",
        "Le fallback historique reprend la dernière composition officielle connue et ne prédit pas le prochain onze.",
        "RubyBets n'invente aucun titulaire, remplaçant, absent ou effectif complet.",
        "Aucune cote FlashScore n'est utilisée par RubyBets.",
    ]


# Cette fonction construit un message d'indisponibilité précis selon la cause rencontrée.
def build_lineups_empty_state(payload: dict[str, Any]) -> str:
    reason = payload.get("reason")

    if reason == "flashscore_source_match_id_not_found":
        return "Identifiant FlashScore introuvable pour cette rencontre."

    if reason == "flashscore_request_failed" or payload.get("status") == "error":
        return "La source des compositions est temporairement indisponible."

    return "La composition du match n'est pas encore publiée par la source."


# Cette fonction construit une réponse indisponible homogène lorsque FlashScore n'est pas configuré.
def build_unavailable_lineups_response(
    match_id: int,
    empty_state: str,
) -> dict[str, Any]:
    return {
        "source": FLASHSCORE_SOURCE,
        "source_used": None,
        "status": "unavailable",
        "match_id": match_id,
        "source_match_id": None,
        "lineups": {
            "composition_status": "unavailable",
            "composition_origin": "none",
            "official_available": False,
            "predicted_available": False,
            "historical_fallback_available": False,
            "historical_fallback_complete": False,
            "squad_available": False,
            "home": normalize_flashscore_lineup_side(None, "home"),
            "away": normalize_flashscore_lineup_side(None, "away"),
            "empty_state": empty_state,
            "fallback_label": None,
            "limits": build_lineups_limits(),
        },
        "data_used": {
            "flashscore_lineups": False,
            "official_lineups": False,
            "predicted_lineups": False,
            "historical_official_lineups": False,
            "missing_players": False,
            "squad": False,
            "odds_used": False,
        },
        "data_freshness": {
            "source": FLASHSCORE_SOURCE,
            "from_cache": False,
            "updated_at": None,
            "ttl_minutes": EMPTY_LINEUPS_CACHE_TTL_MINUTES,
        },
        "fallback_available": False,
        "fallback_checked": False,
    }


# Cette fonction construit la réponse normalisée des compositions du match actuel.
def build_current_lineups_response(
    match_id: int,
    payload: dict[str, Any],
    data_freshness: dict[str, Any],
) -> dict[str, Any]:
    lineups = extract_flashscore_lineups_list(payload)
    home_lineup = normalize_flashscore_lineup_side(
        find_flashscore_lineup_side(lineups, "home"),
        "home",
    )
    away_lineup = normalize_flashscore_lineup_side(
        find_flashscore_lineup_side(lineups, "away"),
        "away",
    )

    official_available = home_lineup["official_available"] or away_lineup["official_available"]
    predicted_available = home_lineup["predicted_available"] or away_lineup["predicted_available"]
    missing_players_available = bool(
        home_lineup["missing_players"]
        or home_lineup["unsure_missing_players"]
        or away_lineup["missing_players"]
        or away_lineup["unsure_missing_players"]
    )

    if official_available or predicted_available:
        status = "available"
    elif missing_players_available:
        status = "partial"
    else:
        status = "unavailable"

    composition_status = (
        "official_available"
        if official_available
        else "predicted_available"
        if predicted_available
        else "absences_only"
        if missing_players_available
        else "unavailable"
    )

    return {
        "source": FLASHSCORE_SOURCE,
        "source_used": FLASHSCORE_SOURCE if lineups else None,
        "status": status,
        "match_id": match_id,
        "source_match_id": payload.get("source_match_id"),
        "lineups": {
            "composition_status": composition_status,
            "composition_origin": (
                "current_official"
                if official_available
                else "current_predicted"
                if predicted_available
                else "none"
            ),
            "official_available": official_available,
            "predicted_available": predicted_available,
            "historical_fallback_available": False,
            "historical_fallback_complete": False,
            "squad_available": False,
            "home": home_lineup,
            "away": away_lineup,
            "empty_state": None if status == "available" else build_lineups_empty_state(payload),
            "fallback_label": None,
            "limits": build_lineups_limits(),
        },
        "data_used": {
            "flashscore_lineups": bool(lineups),
            "official_lineups": official_available,
            "predicted_lineups": predicted_available,
            "historical_official_lineups": False,
            "missing_players": missing_players_available,
            "squad": False,
            "odds_used": False,
        },
        "data_freshness": data_freshness,
        "fallback_available": False,
        "fallback_checked": False,
    }


# Cette fonction transforme un identifiant d'historique en identifiant FlashScore court exploitable.
def extract_history_source_match_id(match_id: Any) -> str | None:
    if isinstance(match_id, str) and match_id.startswith("flashscore_"):
        source_match_id = match_id.removeprefix("flashscore_").strip()
        return source_match_id or None

    if isinstance(match_id, int) or (isinstance(match_id, str) and match_id.isdigit()):
        return decode_flashscore_match_id(match_id)

    return None


# Cette fonction prépare les métadonnées du match historique affichées avec la composition de référence.
def build_historical_reference_match(
    recent_match: dict[str, Any],
    source_match_id: str,
) -> dict[str, Any]:
    return {
        "match_id": encode_flashscore_match_id(source_match_id),
        "source_match_id": source_match_id,
        "utc_date": recent_match.get("utc_date"),
        "competition_name": recent_match.get("competition_name"),
        "home_team": recent_match.get("home_team"),
        "away_team": recent_match.get("away_team"),
        "home_score": recent_match.get("home_score"),
        "away_score": recent_match.get("away_score"),
        "data_source": recent_match.get("data_source"),
    }


# Cette fonction cherche la dernière composition officielle connue pour une équipe dans ses matchs récents.
def find_latest_historical_official_lineup(
    team_history: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    recent_matches = team_history.get("recent_matches", [])

    for recent_match in recent_matches[:HISTORICAL_LINEUPS_MATCH_LIMIT]:
        source_match_id = extract_history_source_match_id(recent_match.get("match_id"))

        if not source_match_id:
            continue

        payload, freshness = get_cached_historical_flashscore_lineups(source_match_id)
        lineups = extract_flashscore_lineups_list(payload)
        team_side = "home" if recent_match.get("is_home") else "away"
        normalized_side = normalize_flashscore_lineup_side(
            find_flashscore_lineup_side(lineups, team_side),
            team_side,
        )

        if not normalized_side.get("official_available"):
            continue

        if not normalized_side.get("starting_lineups"):
            continue

        reference_match = build_historical_reference_match(
            recent_match=recent_match,
            source_match_id=source_match_id,
        )
        return normalized_side, reference_match, freshness

    return None, None, None


# Cette fonction fusionne une composition historique avec les absences du match actuel sans reprendre les anciennes absences.
def merge_historical_side_with_current_signals(
    historical_side: dict[str, Any],
    current_side: dict[str, Any],
    target_side: str,
    reference_match: dict[str, Any],
) -> dict[str, Any]:
    merged_side = deepcopy(historical_side)
    merged_side.update(
        {
            "side": target_side,
            "status": "historical_official_available",
            "composition_origin": "historical_official",
            "official_available": False,
            "predicted_available": False,
            "historical_official_available": True,
            "predicted_lineups": [],
            "predicted_formation": None,
            "missing_players": current_side.get("missing_players", []),
            "unsure_missing_players": current_side.get("unsure_missing_players", []),
            "reference_match": reference_match,
        }
    )
    return merged_side


# Cette fonction ajoute les dernières compositions officielles connues quand le match actuel n'en fournit aucune.
async def apply_historical_lineups_fallback(
    match_id: int,
    current_response: dict[str, Any],
) -> dict[str, Any]:
    try:
        history_response = await build_team_history_response(match_id)
    except Exception as error:  # pragma: no cover - garde-fou réseau défensif
        return {
            **current_response,
            "fallback_checked": True,
            "fallback_error": {
                "type": error.__class__.__name__,
                "message": str(error),
            },
        }

    home_side, home_reference, home_freshness = find_latest_historical_official_lineup(
        history_response.get("home_team_history", {})
    )
    away_side, away_reference, away_freshness = find_latest_historical_official_lineup(
        history_response.get("away_team_history", {})
    )

    fallback_home_available = bool(home_side and home_reference)
    fallback_away_available = bool(away_side and away_reference)
    fallback_available = fallback_home_available or fallback_away_available

    if not fallback_available:
        return {
            **current_response,
            "fallback_checked": True,
            "fallback_available": False,
            "fallback": {
                "strategy": "latest_official_lineup_per_team",
                "status": "unavailable",
                "matches_checked_per_team": HISTORICAL_LINEUPS_MATCH_LIMIT,
            },
        }

    current_lineups = current_response.get("lineups", {})
    current_home = current_lineups.get("home", normalize_flashscore_lineup_side(None, "home"))
    current_away = current_lineups.get("away", normalize_flashscore_lineup_side(None, "away"))

    merged_home = (
        merge_historical_side_with_current_signals(
            historical_side=home_side,
            current_side=current_home,
            target_side="home",
            reference_match=home_reference,
        )
        if fallback_home_available and home_side and home_reference
        else current_home
    )
    merged_away = (
        merge_historical_side_with_current_signals(
            historical_side=away_side,
            current_side=current_away,
            target_side="away",
            reference_match=away_reference,
        )
        if fallback_away_available and away_side and away_reference
        else current_away
    )

    fallback_complete = fallback_home_available and fallback_away_available
    missing_players_available = bool(
        merged_home.get("missing_players")
        or merged_home.get("unsure_missing_players")
        or merged_away.get("missing_players")
        or merged_away.get("unsure_missing_players")
    )

    return {
        **current_response,
        "source_used": FLASHSCORE_SOURCE,
        "status": "available" if fallback_complete else "partial",
        "lineups": {
            **current_lineups,
            "composition_status": (
                "historical_official_fallback_available"
                if fallback_complete
                else "historical_official_fallback_partial"
            ),
            "composition_origin": "historical_official",
            "official_available": False,
            "predicted_available": False,
            "historical_fallback_available": True,
            "historical_fallback_complete": fallback_complete,
            "home": merged_home,
            "away": merged_away,
            "empty_state": None,
            "fallback_label": (
                "Dernières compositions officielles connues. "
                "Elles ne constituent pas les compositions probables du prochain match."
            ),
        },
        "data_used": {
            **current_response.get("data_used", {}),
            "historical_official_lineups": True,
            "missing_players": missing_players_available,
        },
        "data_freshness": {
            "current_match": current_response.get("data_freshness", {}),
            "team_history": history_response.get("data_freshness", {}),
            "historical_home_lineup": home_freshness,
            "historical_away_lineup": away_freshness,
        },
        "fallback_available": True,
        "fallback_checked": True,
        "fallback": {
            "strategy": "latest_official_lineup_per_team",
            "status": "complete" if fallback_complete else "partial",
            "matches_checked_per_team": HISTORICAL_LINEUPS_MATCH_LIMIT,
            "home_reference_match": home_reference,
            "away_reference_match": away_reference,
        },
    }


# Cette fonction orchestre la composition actuelle puis le fallback historique si nécessaire.
async def build_match_lineups_response(match_id: int) -> dict[str, Any]:
    if not is_flashscore_lineups_available():
        return build_unavailable_lineups_response(
            match_id=match_id,
            empty_state="FlashScore RapidAPI n'est pas configuré dans cet environnement.",
        )

    payload, data_freshness = get_cached_current_flashscore_lineups(match_id)
    current_response = build_current_lineups_response(
        match_id=match_id,
        payload=payload,
        data_freshness=data_freshness,
    )

    if current_response["lineups"]["composition_status"] in {
        "official_available",
        "predicted_available",
    }:
        return current_response

    return await apply_historical_lineups_fallback(
        match_id=match_id,
        current_response=current_response,
    )


# Schéma de communication du fichier :
# match_lineups_service.py
# ├── utilise rapidapi_flashscore_client.py pour les compositions actuelles et historiques
# ├── utilise team_history_service.py pour identifier les derniers matchs terminés des deux équipes
# ├── utilise cache_service.py avec TTL court pour le vide et TTL long pour l'historique officiel
# ├── fournit build_match_lineups_response() à app/api/matches.py
# └── sera consommé par le frontend via GET /api/matches/{match_id}/lineups
