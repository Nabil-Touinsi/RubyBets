# Ce fichier orchestre les actualités contextuelles d'un match RubyBets.
# Il récupère plusieurs flux RSS par équipe, filtre les articles et prépare une réponse API responsable.

from datetime import UTC, datetime
from typing import Any

from app.services.google_news_rss_client import (
    GOOGLE_NEWS_RSS_SOURCE,
    fetch_google_news_rss_articles,
)
from app.services.news_nlp_service import filter_and_enrich_team_news_articles


TEAM_NEWS_CONTEXT_MAX_ARTICLES_PER_TEAM = 5
TEAM_NEWS_CONTEXT_MAX_RAW_ARTICLES = 12


# Cette fonction extrait une valeur imbriquée dans un dictionnaire sans casser si une clé manque.
def get_nested_value(payload: dict[str, Any], keys: list[str]) -> Any:
    current_value: Any = payload

    for key in keys:
        if not isinstance(current_value, dict):
            return None

        current_value = current_value.get(key)

    return current_value


# Cette fonction récupère le nom d'une équipe depuis un match brut ou déjà formaté.
def extract_team_name_from_match(match: dict[str, Any], side: str) -> str | None:
    formatted_key = f"{side}_team"
    raw_key = f"{side}Team"

    return (
        get_nested_value(match, [formatted_key, "name"])
        or get_nested_value(match, [raw_key, "name"])
    )


# Cette fonction récupère le nom de compétition depuis un match brut ou déjà formaté.
def extract_competition_name_from_match(match: dict[str, Any]) -> str | None:
    return get_nested_value(match, ["competition", "name"])


# Cette fonction vérifie si le nom de compétition est trop technique pour une requête Google News.
def is_generic_or_technical_competition_name(competition_name: str | None) -> bool:
    normalized_name = " ".join(str(competition_name or "").lower().split())

    if not normalized_name:
        return True

    technical_markers = [
        "round",
        "journée",
        "fs_",
        "world championship -",
        "friendly international",
    ]

    return any(marker in normalized_name for marker in technical_markers)


# Cette fonction construit plusieurs requêtes RSS naturelles pour une équipe.
def build_team_news_queries(
    team_name: str,
    competition_name: str | None = None,
) -> list[str]:
    queries = [
        f'"{team_name}" football news',
        f'"{team_name}" national football team news',
        f'"{team_name}" football injury lineup squad',
    ]

    if competition_name and not is_generic_or_technical_competition_name(competition_name):
        queries.append(f'"{team_name}" football "{competition_name}"')

    return queries


# Cette fonction construit une requête complémentaire liée à l'affiche du match.
def build_match_news_query(
    home_team_name: str | None,
    away_team_name: str | None,
) -> str | None:
    if not home_team_name or not away_team_name:
        return None

    return f'"{home_team_name}" "{away_team_name}" football news'


# Cette fonction supprime les doublons dans une liste d'articles RSS bruts.
def deduplicate_raw_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_keys: set[str] = set()
    deduplicated_articles: list[dict[str, Any]] = []

    for article in articles:
        article_key = str(article.get("url") or article.get("title") or "").lower()

        if not article_key or article_key in seen_keys:
            continue

        seen_keys.add(article_key)
        deduplicated_articles.append(article)

    return deduplicated_articles


# Cette fonction collecte les articles bruts depuis plusieurs requêtes RSS.
def collect_articles_from_queries(queries: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    collected_articles: list[dict[str, Any]] = []
    unavailable_messages: list[str] = []

    for query in queries:
        rss_response = fetch_google_news_rss_articles(
            query=query,
            max_articles=TEAM_NEWS_CONTEXT_MAX_RAW_ARTICLES,
        )

        if rss_response.get("status") == "unavailable":
            message = rss_response.get("message")
            if message:
                unavailable_messages.append(str(message))
            continue

        collected_articles.extend(rss_response.get("articles", []))

    return deduplicate_raw_articles(collected_articles), unavailable_messages


# Cette fonction supprime les doublons entre les deux équipes en privilégiant le premier bloc traité.
def deduplicate_articles_between_teams(
    home_articles: list[dict[str, Any]],
    away_articles: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen_keys: set[str] = set()
    cleaned_home_articles: list[dict[str, Any]] = []
    cleaned_away_articles: list[dict[str, Any]] = []

    for article in home_articles:
        article_key = str(article.get("url") or article.get("title") or "").lower()

        if article_key and article_key not in seen_keys:
            seen_keys.add(article_key)
            cleaned_home_articles.append(article)

    for article in away_articles:
        article_key = str(article.get("url") or article.get("title") or "").lower()

        if article_key and article_key not in seen_keys:
            seen_keys.add(article_key)
            cleaned_away_articles.append(article)

    return cleaned_home_articles, cleaned_away_articles


# Cette fonction construit les messages responsables affichés avec les actualités.
def build_team_news_context_limits() -> list[str]:
    return [
        "Actualités publiques issues de flux RSS.",
        "Les articles sont fournis à titre contextuel et peuvent être incomplets.",
        "RubyBets ne garantit pas l’exhaustivité des informations.",
        "Ces actualités ne constituent pas une prédiction sportive.",
        "Aucune cote FlashScore n’est utilisée par RubyBets.",
    ]


# Cette fonction construit un bloc vide homogène pour une équipe.
def build_empty_team_news_block(
    team_name: str | None,
    queries: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": team_name,
        "query": queries[0] if queries else None,
        "queries": queries or [],
        "status": "empty",
        "articles_count": 0,
        "articles": [],
        "message": "Aucune actualité récente exploitable pour cette équipe.",
    }


# Cette fonction récupère et prépare les actualités d'une équipe avec plusieurs requêtes RSS.
def build_team_news_block(
    team_name: str | None,
    competition_name: str | None = None,
    match_query: str | None = None,
) -> dict[str, Any]:
    if not team_name:
        return build_empty_team_news_block(team_name=None)

    queries = build_team_news_queries(team_name, competition_name)

    if match_query:
        queries.append(match_query)

    raw_articles, unavailable_messages = collect_articles_from_queries(queries)

    if not raw_articles and unavailable_messages:
        return {
            "name": team_name,
            "query": queries[0],
            "queries": queries,
            "status": "unavailable",
            "articles_count": 0,
            "articles": [],
            "message": unavailable_messages[0] or "Flux RSS indisponible.",
        }

    enriched_articles = filter_and_enrich_team_news_articles(
        articles=raw_articles,
        team_name=team_name,
        competition_name=competition_name,
        max_articles=TEAM_NEWS_CONTEXT_MAX_ARTICLES_PER_TEAM,
    )

    if not enriched_articles:
        return build_empty_team_news_block(team_name=team_name, queries=queries)

    return {
        "name": team_name,
        "query": queries[0],
        "queries": queries,
        "status": "available",
        "articles_count": len(enriched_articles),
        "articles": enriched_articles,
        "message": None,
    }


# Cette fonction détermine le statut global selon les blocs domicile et extérieur.
def build_news_context_status(
    home_block: dict[str, Any],
    away_block: dict[str, Any],
) -> str:
    statuses = {home_block.get("status"), away_block.get("status")}

    if "available" in statuses:
        return "available" if statuses == {"available"} else "partial"

    if "unavailable" in statuses:
        return "unavailable"

    return "empty"


# Cette fonction prépare l'empty state global pour le frontend.
def build_news_context_empty_state(status: str) -> str | None:
    if status == "available":
        return None

    if status == "partial":
        return "Actualités disponibles partiellement pour ce match."

    if status == "unavailable":
        return "Le flux d’actualités est temporairement indisponible."

    return (
        "Aucune actualité récente exploitable. RubyBets n’a pas trouvé "
        "d’actualité suffisamment pertinente pour ce match dans les flux consultés."
    )


# Cette fonction construit la réponse complète news-context à partir d'un match.
def build_match_news_context_response(
    match_id: int,
    match: dict[str, Any],
) -> dict[str, Any]:
    home_team_name = extract_team_name_from_match(match, "home")
    away_team_name = extract_team_name_from_match(match, "away")
    competition_name = extract_competition_name_from_match(match)
    match_query = build_match_news_query(home_team_name, away_team_name)

    home_block = build_team_news_block(
        team_name=home_team_name,
        competition_name=competition_name,
        match_query=match_query,
    )
    away_block = build_team_news_block(
        team_name=away_team_name,
        competition_name=competition_name,
        match_query=match_query,
    )

    home_articles, away_articles = deduplicate_articles_between_teams(
        home_articles=home_block.get("articles", []),
        away_articles=away_block.get("articles", []),
    )

    home_block = {
        **home_block,
        "articles": home_articles,
        "articles_count": len(home_articles),
        "status": "available" if home_articles else home_block.get("status"),
    }
    away_block = {
        **away_block,
        "articles": away_articles,
        "articles_count": len(away_articles),
        "status": "available" if away_articles else away_block.get("status"),
    }

    status = build_news_context_status(home_block, away_block)

    return {
        "status": status,
        "source": GOOGLE_NEWS_RSS_SOURCE,
        "match_id": match_id,
        "competition": competition_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "home_team": home_block,
        "away_team": away_block,
        "empty_state": build_news_context_empty_state(status),
        "limits": build_team_news_context_limits(),
    }


# Schéma de communication :
# matches.py -> team_news_context_service.py
# ├── utilise google_news_rss_client.py pour récupérer plusieurs flux publics par équipe
# ├── utilise news_nlp_service.py pour filtrer et classer les articles
# └── renvoie une réponse news-context à l'API puis au frontend