# Rôle du fichier :
# Cette route expose les archives de prédictions RubyBets au frontend.
# Elle permet de consulter les prédictions sauvegardées et leur verdict.

from typing import Any

from fastapi import APIRouter, Query

from app.services.archives_service import (
    get_archived_predictions,
    reconcile_pending_archives,
)


router = APIRouter(
    prefix="/api/archives",
    tags=["Archives"],
)


# Cette route retourne les prédictions archivées avec filtres et pagination.
@router.get("/predictions")
def read_archived_predictions(
    market_type: str | None = Query(default=None),
    verdict: str | None = Query(default=None),
    match_status: str | None = Query(default=None),
    competition_name: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return get_archived_predictions(
        market_type=market_type,
        verdict=verdict,
        match_status=match_status,
        competition_name=competition_name,
        search=search,
        limit=limit,
        offset=offset,
    )


# Cette route actualise un lot limité d'archives dont le match a déjà commencé.
@router.post("/reconcile")
async def reconcile_archived_predictions(
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    return await reconcile_pending_archives(limit=limit)


# Schéma de communication :
# frontend ArchivesScreen.tsx
#     ↓
# GET /api/archives/predictions?competition_name=...
# POST /api/archives/reconcile
#     ↓
# archives_service.py
#     ↓
# database_service.py
#     ↓
# PostgreSQL archived_predictions