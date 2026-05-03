# Ce fichier expose les routes API des matchs RubyBets pour le MVP.
# Il applique le cache data sur les listes de matchs et les fiches match pour limiter les appels Football-Data.

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.constants import FOOTBALL_DATA_PROVIDER, MVP_COMPETITION_CODES
from app.services.analysis_service import (
    build_context_summary,
    build_predictions,
    build_prematch_analysis,
)
from app.services.cache_service import build_cache_name, get_cached_football_data
from app.services.match_service import (
    clean_params,
    filter_matches_by_team,
    format_match,
    get_match_with_standings,
)


router = APIRouter(prefix="/api/matches", tags=["Matches"])


MATCHES_CACHE_TTL_MINUTES = 30
MATCH_DETAIL_CACHE_TTL_MINUTES = 30


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


# Cette fonction prépare les métadonnées de fraîcheur visibles dans les réponses liées aux matchs.
def build_match_data_freshness(
    data_freshness: dict[str, Any],
    match_last_updated: str | None = None,
) -> dict[str, Any]:
    return {
        **data_freshness,
        "provider": FOOTBALL_DATA_PROVIDER,
        "last_updated": match_last_updated,
    }


# Cette route retourne les matchs à venir avec cache sur l'appel Football-Data brut.
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
    filtered_matches = filter_matches_by_team(raw_matches, team)
    formatted_matches = [format_match(match) for match in filtered_matches]

    return {
        "source": FOOTBALL_DATA_PROVIDER,
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


# Cette route retourne la fiche détaillée d'un match avec cache sur l'appel Football-Data.
@router.get("/{match_id}")
async def get_match_details(match_id: int) -> dict[str, Any]:
    data, data_freshness = await get_cached_football_data(
        cache_name=build_cache_name("match", match_id),
        endpoint=f"/matches/{match_id}",
        ttl_minutes=MATCH_DETAIL_CACHE_TTL_MINUTES,
    )
    match = data.get("match", data)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
        "match": format_match(match),
        "data_freshness": build_match_data_freshness(
            data_freshness=data_freshness,
            match_last_updated=match.get("lastUpdated"),
        ),
    }


# Cette route retourne le contexte d'un match à partir de la fiche match et du classement mis en cache.
@router.get("/{match_id}/context")
async def get_match_context(match_id: int) -> dict[str, Any]:
    match_data = await get_match_with_standings(match_id)
    match = match_data["match"]
    competition_code = match_data["competition_code"]
    home_standing = match_data["home_standing"]
    away_standing = match_data["away_standing"]

    ensure_competition_code_found(competition_code)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
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


# Cette route retourne l'analyse pré-match basée sur les données match et classement mises en cache.
@router.get("/{match_id}/analysis")
async def get_match_analysis(match_id: int) -> dict[str, Any]:
    match_data = await get_match_with_standings(match_id)
    match = match_data["match"]
    competition_code = match_data["competition_code"]
    home_standing = match_data["home_standing"]
    away_standing = match_data["away_standing"]

    ensure_competition_code_found(competition_code)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
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


# Cette route retourne les prédictions MVP basées sur les données match et classement mises en cache.
@router.get("/{match_id}/predictions")
async def get_match_predictions(match_id: int) -> dict[str, Any]:
    match_data = await get_match_with_standings(match_id)
    match = match_data["match"]
    competition_code = match_data["competition_code"]
    home_standing = match_data["home_standing"]
    away_standing = match_data["away_standing"]

    ensure_competition_code_found(competition_code)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
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
# ├── utilise cache_service.py pour les listes de matchs et les fiches match
# ├── utilise match_service.py pour enrichir contexte, analyse et prédictions avec les classements
# ├── utilise analysis_service.py pour générer les synthèses et prédictions explicables
# └── renvoie les données formatées à app.main puis au frontend
