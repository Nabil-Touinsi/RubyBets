# Ce fichier classe et filtre les actualités récupérées en catégories utiles au contexte d'un match.
# La V1 utilise des règles par mots-clés, sans modèle lourd, pour rester stable et démontrable.

from datetime import UTC, datetime
from typing import Any


NEWS_CATEGORY_LABELS = {
    "injury_absence": "Blessure / absence",
    "lineup_squad": "Composition / sélection",
    "recent_form": "Forme récente",
    "coach_tactics": "Entraîneur / tactique",
    "competition_context": "Contexte de compétition",
    "other": "Autre",
}

NEWS_CATEGORY_KEYWORDS = {
    "injury_absence": [
        "injury",
        "injured",
        "doubtful",
        "absence",
        "absent",
        "suspended",
        "suspension",
        "fitness",
        "forfait",
        "blessure",
        "blessé",
        "suspendu",
    ],
    "lineup_squad": [
        "squad",
        "lineup",
        "starting xi",
        "selection",
        "roster",
        "team news",
        "probable",
        "called up",
        "composition",
        "sélection",
        "groupe",
        "onze",
    ],
    "recent_form": [
        "form",
        "recent results",
        "momentum",
        "winning streak",
        "unbeaten",
        "defeat",
        "victory",
        "dynamique",
        "série",
        "résultats",
    ],
    "coach_tactics": [
        "coach",
        "manager",
        "tactics",
        "tactical",
        "press conference",
        "system",
        "formation",
        "entraîneur",
        "tactique",
        "conférence",
    ],
    "competition_context": [
        "fixture",
        "tournament",
        "qualification",
        "group stage",
        "world cup",
        "champions league",
        "league",
        "competition",
        "calendrier",
        "compétition",
    ],
}

RELEVANCE_KEYWORDS = [
    "injury",
    "injured",
    "squad",
    "lineup",
    "starting xi",
    "team news",
    "coach",
    "manager",
    "press conference",
    "tactics",
    "form",
    "fixture",
    "competition",
    "selection",
    "absent",
    "suspended",
    "blessure",
    "composition",
    "sélection",
    "entraîneur",
]

EXCLUDED_GENERIC_SOURCES = [
    "flashscore",
    "sofascore",
    "livescore",
    "aiscore",
    "besoccer",
]

MAX_NEWS_AGE_DAYS = 60


# Cette fonction normalise un texte pour faciliter les comparaisons par mots-clés.
def normalize_news_text(value: str | None) -> str:
    return " ".join(str(value or "").lower().split())


# Cette fonction regroupe le titre et la description d'un article pour l'analyse simple.
def build_article_text(article: dict[str, Any]) -> str:
    title = normalize_news_text(article.get("title"))
    description = normalize_news_text(article.get("description"))
    return f"{title} {description}".strip()


# Cette fonction vérifie si l'article mentionne directement l'équipe concernée.
def article_mentions_team(article: dict[str, Any], team_name: str) -> bool:
    article_text = build_article_text(article)
    normalized_team = normalize_news_text(team_name)

    if not normalized_team:
        return False

    return normalized_team in article_text


# Cette fonction vérifie si la source ressemble à une page de score générique plutôt qu'à une actualité.
def is_generic_score_source(article: dict[str, Any]) -> bool:
    source_name = normalize_news_text(article.get("source_name"))
    source_url = normalize_news_text(article.get("source_url"))

    return any(
        excluded_source in source_name or excluded_source in source_url
        for excluded_source in EXCLUDED_GENERIC_SOURCES
    )


# Cette fonction vérifie si l'article est récent selon sa date de publication.
def is_recent_news_article(article: dict[str, Any]) -> bool:
    published_at = article.get("published_at")

    if not published_at:
        return False

    try:
        parsed_date = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))

        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=UTC)

        age_days = (datetime.now(UTC) - parsed_date.astimezone(UTC)).days
        return 0 <= age_days <= MAX_NEWS_AGE_DAYS

    except ValueError:
        return False


# Cette fonction compte les mots-clés métier présents dans un article.
def count_matching_keywords(article_text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in article_text)


# Cette fonction attribue une catégorie simple à une actualité.
def classify_news_category(article: dict[str, Any]) -> str:
    article_text = build_article_text(article)
    best_category = "other"
    best_score = 0

    for category, keywords in NEWS_CATEGORY_KEYWORDS.items():
        score = count_matching_keywords(article_text, keywords)

        if score > best_score:
            best_category = category
            best_score = score

    return best_category


# Cette fonction estime une pertinence simple sans promettre une fiabilité sportive.
def estimate_news_relevance(
    article: dict[str, Any],
    team_name: str,
    competition_name: str | None = None,
) -> str:
    article_text = build_article_text(article)
    team_detected = article_mentions_team(article, team_name)
    keyword_score = count_matching_keywords(article_text, RELEVANCE_KEYWORDS)

    competition_detected = False
    if competition_name:
        competition_detected = normalize_news_text(competition_name) in article_text

    score = keyword_score

    if team_detected:
        score += 2

    if competition_detected:
        score += 1

    if score >= 4:
        return "high"

    if score >= 2:
        return "medium"

    return "low"


# Cette fonction vérifie si une actualité est réellement exploitable pour l'équipe demandée.
def is_exploitable_team_news_article(
    article: dict[str, Any],
    team_name: str,
    competition_name: str | None = None,
) -> bool:
    if not article.get("title") or not article.get("url"):
        return False

    if is_generic_score_source(article):
        return False

    if not is_recent_news_article(article):
        return False

    team_detected = article_mentions_team(article, team_name)
    relevance = estimate_news_relevance(article, team_name, competition_name)

    return team_detected or relevance in {"medium", "high"}


# Cette fonction réduit une description trop longue pour l'affichage frontend.
def shorten_news_description(description: str | None, max_length: int = 220) -> str:
    clean_description = " ".join(str(description or "").split())

    if len(clean_description) <= max_length:
        return clean_description

    return f"{clean_description[:max_length].rstrip()}..."


# Cette fonction enrichit un article brut avec catégorie, pertinence et équipe détectée.
def enrich_news_article(
    article: dict[str, Any],
    team_name: str,
    competition_name: str | None = None,
) -> dict[str, Any]:
    category = classify_news_category(article)
    relevance = estimate_news_relevance(article, team_name, competition_name)

    return {
        "title": article.get("title"),
        "description": shorten_news_description(article.get("description")),
        "url": article.get("url"),
        "source_name": article.get("source_name"),
        "source_url": article.get("source_url"),
        "published_at": article.get("published_at"),
        "category": category,
        "category_label": NEWS_CATEGORY_LABELS.get(category, "Autre"),
        "relevance": relevance,
        "team_detected": team_name,
    }


# Cette fonction filtre les articles faibles puis retourne une liste classée pour une équipe.
def filter_and_enrich_team_news_articles(
    articles: list[dict[str, Any]],
    team_name: str,
    competition_name: str | None = None,
    max_articles: int = 5,
) -> list[dict[str, Any]]:
    exploitable_articles = [
        article
        for article in articles
        if is_exploitable_team_news_article(article, team_name, competition_name)
    ]

    enriched_articles = [
        enrich_news_article(article, team_name, competition_name)
        for article in exploitable_articles
    ]

    relevance_order = {"high": 3, "medium": 2, "low": 1}

    sorted_articles = sorted(
        enriched_articles,
        key=lambda item: relevance_order.get(str(item.get("relevance")), 0),
        reverse=True,
    )

    return sorted_articles[:max_articles]


# Schéma de communication :
# team_news_context_service.py -> news_nlp_service.py -> articles filtrés et classés pour l'API news-context