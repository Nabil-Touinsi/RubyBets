# Rôle du fichier :
# Ce client appelle Hugging Face pour classer des textes d'actualités
# sans bloquer RubyBets si le service externe est indisponible.

from typing import Any

import httpx

from app.core.config import settings


DEFAULT_NEWS_LABELS = [
    "blessure ou absence",
    "composition ou sélection",
    "forme récente",
    "entraîneur ou tactique",
    "contexte de compétition",
    "article général",
]


# Vérifie si Hugging Face peut être appelé selon la configuration locale.
def is_huggingface_available() -> bool:
    return bool(settings.huggingface_enabled and settings.huggingface_api_token)


# Construit le texte envoyé au modèle à partir d'un titre et d'une description.
def build_news_classification_input(title: str, description: str | None = None) -> str:
    clean_title = title.strip()
    clean_description = (description or "").strip()

    if clean_description:
        return f"{clean_title}. {clean_description}"

    return clean_title


# Appelle Hugging Face pour classer un texte avec des labels candidats.
def classify_news_text_with_huggingface(
    text: str,
    candidate_labels: list[str] | None = None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    labels = candidate_labels or DEFAULT_NEWS_LABELS

    if not is_huggingface_available():
        return {
            "status": "disabled",
            "source": "huggingface",
            "model": settings.huggingface_model_name,
            "labels": [],
            "message": "Hugging Face est désactivé ou aucun token n'est configuré.",
        }

    if not text.strip():
        return {
            "status": "empty_input",
            "source": "huggingface",
            "model": settings.huggingface_model_name,
            "labels": [],
            "message": "Aucun texte exploitable à classifier.",
        }

    payload = {
        "inputs": text.strip(),
        "parameters": {
            "candidate_labels": labels,
            "multi_label": True,
        },
    }

    try:
        response = httpx.post(
            settings.get_huggingface_model_url(),
            headers=settings.get_huggingface_headers(),
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        return {
            "status": "available",
            "source": "huggingface",
            "model": settings.huggingface_model_name,
            "labels": data,
            "message": "Classification Hugging Face disponible.",
        }

    except httpx.HTTPStatusError as error:
        return {
            "status": "error",
            "source": "huggingface",
            "model": settings.huggingface_model_name,
            "labels": [],
            "message": f"Erreur HTTP Hugging Face : {error.response.status_code}",
        }

    except httpx.RequestError:
        return {
            "status": "error",
            "source": "huggingface",
            "model": settings.huggingface_model_name,
            "labels": [],
            "message": "Hugging Face est indisponible ou trop lent.",
        }


# Schéma de communication :
# backend/.env
#     ↓
# backend/app/core/config.py
#     ↓
# huggingface_news_context_client.py
#     ↓
# futur service de lecture contextuelle IA
#     ↓
# route /api/matches/{match_id}/news-context