# Rôle du fichier :
# Cette route expose les archives de prédictions RubyBets au frontend.
# Elle permet de consulter les prédictions sauvegardées et leur verdict.

from typing import Any

from fastapi import APIRouter, Query

from app.services.archives_service import get_archived_predictions


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
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return get_archived_predictions(
        market_type=market_type,
        verdict=verdict,
        match_status=match_status,
        search=search,
        limit=limit,
        offset=offset,
    )


# Schéma de communication :
# frontend ArchivesScreen.tsx
#     ↓
# GET /api/archives/predictions
#     ↓
# archives_service.py
#     ↓
# database_service.py
#     ↓
# PostgreSQL archived_predictions