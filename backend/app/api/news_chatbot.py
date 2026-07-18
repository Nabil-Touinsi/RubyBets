# Rôle du fichier :
# Cette route expose le chatbot d'actualités d'un match RubyBets.
# Elle récupère le match, appelle le service chatbot et transforme les erreurs Groq en réponses API maîtrisées.

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api import matches as matches_api
from app.core.constants import FOOTBALL_DATA_PROVIDER
from app.schemas.news_chatbot import NewsChatbotRequest, NewsChatbotResponse
from app.services.cache_service import build_cache_name, get_cached_football_data
from app.services.groq_chatbot_client import GroqChatbotError
from app.services.match_news_chatbot_service import build_match_news_chatbot_response
from app.services.rapidapi_flashscore_client import FLASHSCORE_SOURCE


LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matches", tags=["News Chatbot"])


# Cette fonction récupère la fiche match avec FlashScore en priorité et Football-Data en fallback.
async def load_match_for_news_chatbot(
    match_id: int,
) -> tuple[dict[str, Any], str]:
    if matches_api.is_flashscore_available():
        match, metadata, _ = matches_api.get_cached_flashscore_match_detail(match_id)

        if match and metadata.get("status") == "success":
            return match, FLASHSCORE_SOURCE

    data, _ = await get_cached_football_data(
        cache_name=build_cache_name("match", match_id),
        endpoint=f"/matches/{match_id}",
        ttl_minutes=matches_api.MATCH_DETAIL_CACHE_TTL_MINUTES,
    )
    match = data.get("match", data)

    if not isinstance(match, dict) or not match:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MATCH_NOT_FOUND",
                "message": "Match introuvable pour le chatbot d'actualités.",
            },
        )

    return match, FOOTBALL_DATA_PROVIDER


# Cette route génère une synthèse ou répond à une question uniquement depuis les actualités RubyBets.
@router.post(
    "/{match_id}/news-chat",
    response_model=NewsChatbotResponse,
    responses={
        404: {"description": "Match introuvable."},
        429: {"description": "Limite temporaire du fournisseur Groq."},
        502: {"description": "Réponse fournisseur non exploitable."},
        503: {"description": "Chatbot non configuré ou indisponible."},
    },
)
async def chat_about_match_news(
    match_id: int,
    request: NewsChatbotRequest,
) -> NewsChatbotResponse:
    match, match_source = await load_match_for_news_chatbot(match_id)

    try:
        response = await build_match_news_chatbot_response(
            match_id=match_id,
            match=match,
            mode=request.mode,
            question=request.question,
            match_source=match_source,
        )
        return NewsChatbotResponse.model_validate(response)

    except GroqChatbotError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.code,
                "message": error.public_message,
            },
        ) from error

    except HTTPException:
        raise

    except Exception as error:
        LOGGER.exception(
            "Unexpected news chatbot error: match_id=%s error_type=%s",
            match_id,
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NEWS_CHATBOT_UNAVAILABLE",
                "message": "Le chatbot d'actualités est temporairement indisponible.",
            },
        ) from error


# Schéma de communication :
# POST /api/matches/{match_id}/news-chat
#     ↓
# news_chatbot.py -> chargement match FlashScore / Football-Data
#     ↓
# match_news_chatbot_service.py -> extraction articles + Groq
#     ↓
# NewsChatbotResponse vers le frontend futur
