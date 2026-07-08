# Rôle du fichier :
# Ce service prépare une lecture contextuelle IA des actualités d'un match
# à partir des articles déjà récupérés par RubyBets.

from typing import Any

from app.core.config import settings
from app.services.huggingface_news_context_client import (
    build_news_classification_input,
    classify_news_text_with_huggingface,
    is_huggingface_available,
)


CONTEXTUAL_READING_CAUTION = (
    "Cette lecture compare uniquement le contexte médiatique disponible. "
    "Elle ne constitue pas une prédiction du résultat sportif."
)
NEWS_AI_MAX_ARTICLES_PER_TEAM_FOR_TEST = 1

# Récupère une valeur texte dans un article sans dépendre strictement de sa forme.
def get_article_text_value(article: dict[str, Any], key: str) -> str:
    value = article.get(key)

    if value is None:
        return ""

    return str(value).strip()


# Transforme la réponse Hugging Face en liste de labels lisibles et triés.
def normalize_huggingface_labels(raw_labels: Any) -> list[dict[str, Any]]:
    normalized_labels: list[dict[str, Any]] = []

    if isinstance(raw_labels, list):
        for item in raw_labels:
            if not isinstance(item, dict):
                continue

            label = item.get("label")
            score = item.get("score")

            if not isinstance(label, str) or score is None:
                continue

            normalized_labels.append(
                {
                    "label": label,
                    "score": round(float(score), 3),
                }
            )

        return sorted(
            normalized_labels,
            key=lambda item: item["score"],
            reverse=True,
        )

    if isinstance(raw_labels, dict):
        labels = raw_labels.get("labels", [])
        scores = raw_labels.get("scores", [])

        if not isinstance(labels, list) or not isinstance(scores, list):
            return []

        for label, score in zip(labels, scores):
            if not isinstance(label, str):
                continue

            normalized_labels.append(
                {
                    "label": label,
                    "score": round(float(score), 3),
                }
            )

    return sorted(
        normalized_labels,
        key=lambda item: item["score"],
        reverse=True,
    )


# Classe un article avec Hugging Face quand le service est disponible.
def classify_article_context_with_ai(article: dict[str, Any]) -> dict[str, Any]:
    title = get_article_text_value(article, "title")
    description = get_article_text_value(article, "description")
    article_url = get_article_text_value(article, "url") or get_article_text_value(article, "link")

    text = build_news_classification_input(title=title, description=description)

    classification = classify_news_text_with_huggingface(text)

    return {
        "title": title,
        "url": article_url,
        "ai_status": classification.get("status", "unknown"),
        "labels": normalize_huggingface_labels(classification.get("labels")),
        "message": classification.get("message", ""),
    }


# Analyse les articles disponibles pour une équipe donnée.
def build_team_ai_context(
    team_name: str,
    articles: list[dict[str, Any]],
    max_articles: int = NEWS_AI_MAX_ARTICLES_PER_TEAM_FOR_TEST,
) -> dict[str, Any]:
    selected_articles = articles[:max_articles]

    if not selected_articles:
        return {
            "team": team_name,
            "status": "insufficient_data",
            "articles_analyzed": 0,
            "ai_labels": [],
            "main_signals": [],
        }

    ai_results = [
        classify_article_context_with_ai(article)
        for article in selected_articles
    ]

    available_results = [
        result
        for result in ai_results
        if result.get("ai_status") == "available"
    ]

    if not available_results:
        fallback_status = ai_results[0].get("ai_status", "disabled") if ai_results else "disabled"

        return {
            "team": team_name,
            "status": fallback_status,
            "articles_analyzed": len(selected_articles),
            "ai_labels": [],
            "main_signals": [],
        }

    label_scores: dict[str, float] = {}

    for result in available_results:
        for label_data in result.get("labels", []):
            label = label_data.get("label")
            score = label_data.get("score", 0)

            if not label:
                continue

            label_scores[label] = max(label_scores.get(label, 0), float(score))

    main_signals = [
        {
            "label": label,
            "score": round(score, 3),
        }
        for label, score in sorted(
            label_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
    ]

    return {
        "team": team_name,
        "status": "available",
        "articles_analyzed": len(selected_articles),
        "ai_labels": ai_results,
        "main_signals": main_signals,
    }


# Produit une lecture comparative prudente entre les deux équipes.
def build_contextual_advantage(
    home_context: dict[str, Any],
    away_context: dict[str, Any],
) -> dict[str, Any]:
    home_count = int(home_context.get("articles_analyzed", 0))
    away_count = int(away_context.get("articles_analyzed", 0))

    if home_context.get("status") != "available" and away_context.get("status") != "available":
        return {
            "team": None,
            "level": "insufficient_data",
            "reasons": [
                "La lecture contextuelle IA n'est pas disponible ou ne dispose pas de données suffisantes."
            ],
            "caution": CONTEXTUAL_READING_CAUTION,
        }

    if abs(home_count - away_count) <= 1:
        return {
            "team": None,
            "level": "neutral",
            "reasons": [
                "Le volume d'articles disponibles est relativement équilibré entre les deux équipes."
            ],
            "caution": CONTEXTUAL_READING_CAUTION,
        }

    advantaged_context = home_context if home_count > away_count else away_context
    disadvantaged_context = away_context if home_count > away_count else home_context

    return {
        "team": advantaged_context.get("team"),
        "level": "low",
        "reasons": [
            f"La couverture médiatique exploitable est plus riche côté {advantaged_context.get('team')}.",
            f"{advantaged_context.get('articles_analyzed', 0)} article(s) analysé(s) contre {disadvantaged_context.get('articles_analyzed', 0)} côté {disadvantaged_context.get('team')}.",
        ],
        "caution": CONTEXTUAL_READING_CAUTION,
    }


# Construit la réponse IA complète pour un match à partir des deux blocs d'articles.
def build_match_news_ai_context(
    home_team_name: str,
    home_articles: list[dict[str, Any]],
    away_team_name: str,
    away_articles: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_huggingface_available():
        return {
            "status": "disabled",
            "source": "huggingface",
            "model": settings.huggingface_model_name,
            "contextual_advantage": {
                "team": None,
                "level": "insufficient_data",
                "reasons": [
                    "Hugging Face est désactivé ou aucun token n'est configuré."
                ],
                "caution": CONTEXTUAL_READING_CAUTION,
            },
            "home_team": {
                "team": home_team_name,
                "status": "disabled",
                "articles_analyzed": 0,
                "main_signals": [],
            },
            "away_team": {
                "team": away_team_name,
                "status": "disabled",
                "articles_analyzed": 0,
                "main_signals": [],
            },
        }

    home_context = build_team_ai_context(home_team_name, home_articles)
    away_context = build_team_ai_context(away_team_name, away_articles)

    return {
        "status": "available",
        "source": "huggingface",
        "model": settings.huggingface_model_name,
        "contextual_advantage": build_contextual_advantage(home_context, away_context),
        "home_team": home_context,
        "away_team": away_context,
    }


# Schéma de communication :
# team_news_context_service.py
#     ↓
# news_context_ai_service.py
#     ↓
# huggingface_news_context_client.py
#     ↓
# backend/app/core/config.py
#     ↓
# future route /api/matches/{match_id}/news-context 