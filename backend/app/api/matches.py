# Ce fichier expose les routes API des matchs RubyBets pour le MVP.

from fastapi import APIRouter, HTTPException, Query

from app.core.constants import FOOTBALL_DATA_PROVIDER, MVP_COMPETITION_CODES
from app.services.analysis_service import (
    build_context_summary,
    build_predictions,
    build_prematch_analysis,
)
from app.services.football_data_client import get_football_data
from app.services.match_service import (
    clean_params,
    filter_matches_by_team,
    format_match,
    get_match_with_standings,
)


router = APIRouter(prefix="/api/matches", tags=["Matches"])


def ensure_competition_supported(competition_code: str) -> None:
    if competition_code not in MVP_COMPETITION_CODES:
        raise HTTPException(
            status_code=400,
            detail="Competition not supported in RubyBets MVP.",
        )


def ensure_competition_code_found(competition_code: str | None) -> None:
    if not competition_code:
        raise HTTPException(
            status_code=404,
            detail="Competition code not found for this match.",
        )


@router.get("")
async def get_matches(
    competition_code: str = Query("PL"),
    status: str = Query("SCHEDULED"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    team: str | None = Query(None),
):
    competition_code = competition_code.upper()
    ensure_competition_supported(competition_code)

    data = await get_football_data(
        f"/competitions/{competition_code}/matches",
        params=clean_params(
            {
                "status": status,
                "dateFrom": date_from,
                "dateTo": date_to,
            }
        ),
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
    }


@router.get("/{match_id}")
async def get_match_details(match_id: int):
    data = await get_football_data(f"/matches/{match_id}")
    match = data.get("match", data)

    return {
        "source": FOOTBALL_DATA_PROVIDER,
        "match": format_match(match),
        "data_freshness": {
            "last_updated": match.get("lastUpdated"),
            "provider": FOOTBALL_DATA_PROVIDER,
        },
    }


@router.get("/{match_id}/context")
async def get_match_context(match_id: int):
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
            "match_last_updated": match.get("lastUpdated"),
            "provider": FOOTBALL_DATA_PROVIDER,
        },
    }


@router.get("/{match_id}/analysis")
async def get_match_analysis(match_id: int):
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
            "match_last_updated": match.get("lastUpdated"),
            "provider": FOOTBALL_DATA_PROVIDER,
        },
    }


@router.get("/{match_id}/predictions")
async def get_match_predictions(match_id: int):
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
            "match_last_updated": match.get("lastUpdated"),
            "provider": FOOTBALL_DATA_PROVIDER,
        },
    }
