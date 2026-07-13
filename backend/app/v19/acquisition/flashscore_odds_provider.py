# Rôle du fichier :
# Ce fichier encapsule l'appel RapidAPI FlashScore dédié aux odds d'un match sans calcul métier.

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.rapidapi_flashscore_client import (
    decode_flashscore_match_id,
    get_rapidapi_flashscore_data,
    is_flashscore_error_response,
)


FLASHSCORE_ODDS_ENDPOINT = "/matches/odds"
FLASHSCORE_ODDS_PROVIDER = "flashscore_rapidapi"

FlashScoreOddsClient = Callable[[str, dict[str, Any] | None], Any]


# Récupère le payload odds brut à partir de l'identifiant source FlashScore.
def get_flashscore_match_odds(
    flashscore_match_id: str | None,
    client: FlashScoreOddsClient = get_rapidapi_flashscore_data,
) -> tuple[Any | None, dict[str, Any]]:
    if not flashscore_match_id:
        return None, {
            "provider": FLASHSCORE_ODDS_PROVIDER,
            "status": "missing_match_id",
            "endpoint": FLASHSCORE_ODDS_ENDPOINT,
        }

    try:
        payload = client(
            FLASHSCORE_ODDS_ENDPOINT,
            {"match_id": str(flashscore_match_id)},
        )
    except Exception as exc:
        return None, {
            "provider": FLASHSCORE_ODDS_PROVIDER,
            "status": "error",
            "endpoint": FLASHSCORE_ODDS_ENDPOINT,
            "match_id": str(flashscore_match_id),
            "message": type(exc).__name__,
        }

    if is_flashscore_error_response(payload):
        return None, {
            "provider": FLASHSCORE_ODDS_PROVIDER,
            "status": "error",
            "endpoint": FLASHSCORE_ODDS_ENDPOINT,
            "match_id": str(flashscore_match_id),
            "message": payload.get("message"),
            "status_code": payload.get("status_code"),
        }

    if not isinstance(payload, (dict, list)):
        return None, {
            "provider": FLASHSCORE_ODDS_PROVIDER,
            "status": "unexpected_response",
            "endpoint": FLASHSCORE_ODDS_ENDPOINT,
            "match_id": str(flashscore_match_id),
        }

    return payload, {
        "provider": FLASHSCORE_ODDS_PROVIDER,
        "status": "success",
        "endpoint": FLASHSCORE_ODDS_ENDPOINT,
        "match_id": str(flashscore_match_id),
    }


# Décode un identifiant RubyBets puis récupère les odds du match FlashScore associé.
def get_flashscore_match_odds_for_rubybets(
    rubybets_match_id: int | str | None,
    client: FlashScoreOddsClient = get_rapidapi_flashscore_data,
) -> tuple[Any | None, dict[str, Any]]:
    flashscore_match_id = decode_flashscore_match_id(rubybets_match_id)

    if not flashscore_match_id:
        return None, {
            "provider": FLASHSCORE_ODDS_PROVIDER,
            "status": "not_flashscore_match_id",
            "endpoint": FLASHSCORE_ODDS_ENDPOINT,
            "rubybets_match_id": rubybets_match_id,
        }

    payload, metadata = get_flashscore_match_odds(
        flashscore_match_id=flashscore_match_id,
        client=client,
    )

    return payload, {
        **metadata,
        "rubybets_match_id": rubybets_match_id,
    }


# Schéma de communication :
# rapidapi_flashscore_client.py
#   -> fournit le client HTTP partagé et le décodage des identifiants
# flashscore_odds_provider.py
#   -> récupère uniquement /matches/odds et retourne payload + métadonnées
# flashscore_odds_adapter.py
#   -> normalise ensuite le payload fournisseur
# aucune route, cote ou calcul de gain n'est exposé au frontend
