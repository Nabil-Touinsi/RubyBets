# Rôle du fichier :
# Ce fichier orchestre les actualités contextuelles d'un match RubyBets.
# Il récupère plusieurs flux RSS par équipe, filtre les articles,
# prépare une réponse API responsable et ajoute une lecture IA optionnelle.

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import re
from typing import Any

from app.services.google_news_rss_client import (
    GOOGLE_NEWS_RSS_SOURCE,
    fetch_google_news_rss_articles,
)
from app.core.config import settings
from app.services.news_context_ai_service import build_match_news_ai_context
from app.services.news_article_content_service import fetch_news_context_article_previews
from app.services.news_nlp_service import (
    filter_and_enrich_team_news_articles,
    normalize_news_text,
    shorten_news_description,
)


TEAM_NEWS_CONTEXT_MAX_ARTICLES_PER_TEAM = 5
MATCH_NEWS_CONTEXT_MAX_ARTICLES = 5
TEAM_NEWS_CONTEXT_MAX_RAW_ARTICLES = 12
TEAM_COUNTRY_SUFFIX_PATTERN = re.compile(r"\s*\([A-Z0-9]{2,4}\)\s*$", re.IGNORECASE)
TEAM_NAME_SEPARATOR_PATTERN = re.compile(r"[-‐‑‒–—]+")
_MATCH_NEWS_SELECTION_CACHE: dict[int, dict[str, Any]] = {}


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


# Cette fonction récupère la date UTC du match depuis un payload brut ou déjà formaté.
def extract_match_utc_date_from_match(match: dict[str, Any]) -> str | None:
    return match.get("utc_date") or match.get("utcDate")


# Cette fonction retire les suffixes fournisseur comme « (ARM) » sans modifier le nom affiché dans l'API.
def normalize_team_name_for_news(team_name: str | None) -> str:
    cleaned_name = TEAM_COUNTRY_SUFFIX_PATTERN.sub("", str(team_name or "")).strip()
    return " ".join(cleaned_name.split())


# Cette fonction construit une signature stable du match pour sécuriser le cache partagé avec Ruby.
def build_match_news_selection_signature(match: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(extract_team_name_from_match(match, "home") or ""),
        str(extract_team_name_from_match(match, "away") or ""),
        str(extract_competition_name_from_match(match) or ""),
        str(extract_match_utc_date_from_match(match) or ""),
    )


# Cette fonction mémorise la sélection éditoriale afin que Ruby ne relance pas les flux RSS.
def store_match_news_selected_articles(
    match_id: int,
    match: dict[str, Any],
    articles: list[dict[str, Any]],
) -> None:
    _MATCH_NEWS_SELECTION_CACHE[match_id] = {
        "signature": build_match_news_selection_signature(match),
        "expires_at": datetime.now(UTC)
        + timedelta(minutes=settings.news_chatbot_cache_ttl_minutes),
        "articles": [dict(article) for article in articles],
    }


# Cette fonction retourne la sélection déjà chargée par l'onglet Contexte lorsqu'elle reste fraîche.
def get_cached_match_news_selected_articles(
    match_id: int,
    match: dict[str, Any],
) -> list[dict[str, Any]] | None:
    cache_entry = _MATCH_NEWS_SELECTION_CACHE.get(match_id)

    if not cache_entry:
        return None

    if (
        cache_entry.get("signature") != build_match_news_selection_signature(match)
        or not isinstance(cache_entry.get("expires_at"), datetime)
        or cache_entry["expires_at"] <= datetime.now(UTC)
    ):
        _MATCH_NEWS_SELECTION_CACHE.pop(match_id, None)
        return None

    return [dict(article) for article in cache_entry.get("articles") or []]


# Cette fonction efface la sélection partagée, notamment pour isoler les tests du chatbot.
def clear_match_news_selection_cache() -> None:
    _MATCH_NEWS_SELECTION_CACHE.clear()


# Cette fonction produit les variantes utiles d'un nom d'équipe pour couvrir tirets et espaces.
def build_team_name_variants(team_name: str | None) -> list[str]:
    canonical_name = normalize_team_name_for_news(team_name)

    if not canonical_name:
        return []

    variants = [canonical_name]
    spaced_name = " ".join(TEAM_NAME_SEPARATOR_PATTERN.sub(" ", canonical_name).split())

    if spaced_name and spaced_name.lower() != canonical_name.lower():
        variants.append(spaced_name)

    return variants


# Cette fonction réduit les libellés fournisseur techniques à un nom de compétition recherché par les médias.
def simplify_competition_name_for_news(competition_name: str | None) -> str | None:
    normalized_name = " ".join(str(competition_name or "").lower().split())

    if not normalized_name:
        return None

    known_competitions = [
        ("champions league", "Champions League"),
        ("europa league", "Europa League"),
        ("conference league", "Conference League"),
        ("premier league", "Premier League"),
        ("ligue 1", "Ligue 1"),
        ("la liga", "La Liga"),
        ("bundesliga", "Bundesliga"),
        ("serie a", "Serie A"),
    ]

    for marker, public_name in known_competitions:
        if marker in normalized_name:
            return public_name

    technical_markers = [
        "round",
        "qualification",
        "quarter-final",
        "semi-final",
        "journée",
        "fs_",
        "world championship -",
        "friendly international",
    ]

    if any(marker in normalized_name for marker in technical_markers):
        return None

    return " ".join(str(competition_name or "").split())


# Cette fonction supprime les doublons textuels tout en conservant l'ordre de priorité des requêtes.
def deduplicate_queries(queries: list[str]) -> list[str]:
    seen_queries: set[str] = set()
    deduplicated_queries: list[str] = []

    for query in queries:
        query_key = " ".join(str(query or "").lower().split())

        if not query_key or query_key in seen_queries:
            continue

        seen_queries.add(query_key)
        deduplicated_queries.append(query)

    return deduplicated_queries


# Cette fonction construit plusieurs requêtes RSS naturelles pour une équipe de club.
def build_team_news_queries(
    team_name: str,
    competition_name: str | None = None,
) -> list[str]:
    team_variants = build_team_name_variants(team_name)

    if not team_variants:
        return []

    primary_name = team_variants[0]
    queries = [
        f'"{primary_name}" news',
        f'"{primary_name}" football',
        f'"{primary_name}" injury lineup squad',
    ]

    for variant in team_variants[1:]:
        queries.append(f'"{variant}" news')

    competition_query_name = simplify_competition_name_for_news(competition_name)
    if competition_query_name:
        queries.append(f'"{primary_name}" "{competition_query_name}"')

    return deduplicate_queries(queries)


# Cette fonction construit une requête complémentaire directement liée à l'affiche du match.
def build_match_news_query(
    home_team_name: str | None,
    away_team_name: str | None,
) -> str | None:
    clean_home_name = normalize_team_name_for_news(home_team_name)
    clean_away_name = normalize_team_name_for_news(away_team_name)

    if not clean_home_name or not clean_away_name:
        return None

    return f'"{clean_home_name}" "{clean_away_name}"'


# Cette fonction construit une signature de titre indépendante de l'URL et du nom de l'éditeur.
def build_article_deduplication_key(article: dict[str, Any]) -> str:
    normalized_title = normalize_news_text(article.get("title"))
    normalized_source = normalize_news_text(article.get("source_name"))

    if normalized_source and normalized_title.endswith(f" {normalized_source}"):
        normalized_title = normalized_title[: -(len(normalized_source) + 1)].strip()

    return normalized_title or str(article.get("url") or "").lower().strip()


# Cette fonction supprime les doublons et les reprises éditoriales dans les articles RSS bruts.
def deduplicate_raw_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_keys: set[str] = set()
    deduplicated_articles: list[dict[str, Any]] = []

    for article in articles:
        article_key = build_article_deduplication_key(article)

        if not article_key or article_key in seen_keys:
            continue

        seen_keys.add(article_key)
        deduplicated_articles.append(article)

    return deduplicated_articles


# Cette fonction fusionne les articles des deux équipes pour produire une liste courte au niveau du match.
def merge_team_articles_for_match_context(
    home_articles: list[dict[str, Any]],
    away_articles: list[dict[str, Any]],
    max_articles: int = MATCH_NEWS_CONTEXT_MAX_ARTICLES,
) -> list[dict[str, Any]]:
    merged_articles: list[dict[str, Any]] = []
    article_indexes_by_key: dict[str, int] = {}
    max_team_length = max(len(home_articles), len(away_articles), 0)

    for article_index in range(max_team_length):
        for team_articles in (home_articles, away_articles):
            if article_index >= len(team_articles):
                continue

            article = dict(team_articles[article_index])
            article_key = build_article_deduplication_key(article)
            detected_team = str(article.get("team_detected") or "").strip()

            if article_key in article_indexes_by_key:
                existing_index = article_indexes_by_key[article_key]
                existing_article = dict(merged_articles[existing_index])
                teams_detected = list(existing_article.get("teams_detected") or [])

                if detected_team and detected_team not in teams_detected:
                    teams_detected.append(detected_team)

                existing_article["teams_detected"] = teams_detected
                merged_articles[existing_index] = existing_article
                continue

            if not article_key:
                continue

            article["teams_detected"] = [detected_team] if detected_team else []
            article_indexes_by_key[article_key] = len(merged_articles)
            merged_articles.append(article)

            if len(merged_articles) >= max_articles:
                return merged_articles

    return merged_articles


# Cette fonction remplace dans les blocs équipe les articles enrichis au niveau global du match.
def apply_enriched_articles_to_team_blocks(
    response: dict[str, Any],
    enriched_articles: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched_by_key = {
        build_article_deduplication_key(article): article
        for article in enriched_articles
        if build_article_deduplication_key(article)
    }

    updated_response = dict(response)

    for block_name in ("home_team", "away_team"):
        team_block = dict(updated_response.get(block_name) or {})
        team_articles = []

        for article in team_block.get("articles") or []:
            article_key = build_article_deduplication_key(article)
            team_articles.append(enriched_by_key.get(article_key, article))

        team_block["articles"] = team_articles
        team_block["articles_count"] = len(team_articles)
        updated_response[block_name] = team_block

    updated_response["articles"] = enriched_articles
    updated_response["articles_count"] = len(enriched_articles)
    return updated_response


# Cette fonction collecte les requêtes RSS en parallèle et réutilise les réponses communes aux deux équipes.
def collect_articles_from_queries(
    queries: list[str],
    response_cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    collected_articles: list[dict[str, Any]] = []
    unavailable_messages: list[str] = []
    shared_cache = response_cache if response_cache is not None else {}
    unique_queries = deduplicate_queries(queries)
    missing_queries = [query for query in unique_queries if query not in shared_cache]

    # Cette fonction interne garde le téléchargement synchrone isolé dans un worker dédié.
    def fetch_query(query: str) -> tuple[str, dict[str, Any]]:
        return (
            query,
            fetch_google_news_rss_articles(
                query=query,
                max_articles=TEAM_NEWS_CONTEXT_MAX_RAW_ARTICLES,
            ),
        )

    if missing_queries:
        worker_count = min(4, len(missing_queries))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for query, rss_response in executor.map(fetch_query, missing_queries):
                shared_cache[query] = rss_response

    for query in unique_queries:
        rss_response = shared_cache.get(query, {})

        if rss_response.get("status") == "unavailable":
            message = rss_response.get("message")
            if message:
                unavailable_messages.append(str(message))
            continue

        collected_articles.extend(rss_response.get("articles", []))

    return deduplicate_raw_articles(collected_articles), unavailable_messages


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


# Cette fonction réaligne le statut d'un bloc équipe avec sa liste finale d'articles.
def normalize_team_news_block_status(team_block: dict[str, Any]) -> dict[str, Any]:
    articles = list(team_block.get("articles", []))

    if articles:
        return {
            **team_block,
            "status": "available",
            "articles_count": len(articles),
            "articles": articles,
            "message": None,
        }

    if team_block.get("status") == "unavailable":
        return {
            **team_block,
            "articles_count": 0,
            "articles": [],
        }

    return {
        **team_block,
        "status": "empty",
        "articles_count": 0,
        "articles": [],
        "message": team_block.get("message")
        or "Aucune actualité récente exploitable pour cette équipe.",
    }


# Cette fonction récupère et prépare les actualités d'une équipe avec plusieurs requêtes RSS.
def build_team_news_block(
    team_name: str | None,
    competition_name: str | None = None,
    match_query: str | None = None,
    opponent_team_name: str | None = None,
    match_utc_date: str | None = None,
    max_articles: int = TEAM_NEWS_CONTEXT_MAX_ARTICLES_PER_TEAM,
    description_max_length: int | None = 220,
    rss_response_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not team_name:
        return build_empty_team_news_block(team_name=None)

    queries = build_team_news_queries(team_name, competition_name)

    if match_query:
        queries.append(match_query)

    raw_articles, unavailable_messages = collect_articles_from_queries(
        queries,
        response_cache=rss_response_cache,
    )

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
        opponent_team_name=opponent_team_name,
        match_utc_date=match_utc_date,
        max_articles=max_articles,
        description_max_length=description_max_length,
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
    description_max_length: int | None = 220,
) -> dict[str, Any]:
    home_team_name = extract_team_name_from_match(match, "home")
    away_team_name = extract_team_name_from_match(match, "away")
    competition_name = extract_competition_name_from_match(match)
    match_utc_date = extract_match_utc_date_from_match(match)
    match_query = build_match_news_query(home_team_name, away_team_name)
    rss_response_cache: dict[str, dict[str, Any]] = {}

    home_block = build_team_news_block(
        team_name=home_team_name,
        competition_name=competition_name,
        match_query=match_query,
        opponent_team_name=away_team_name,
        match_utc_date=match_utc_date,
        description_max_length=description_max_length,
        rss_response_cache=rss_response_cache,
    )
    away_block = build_team_news_block(
        team_name=away_team_name,
        competition_name=competition_name,
        match_query=match_query,
        opponent_team_name=home_team_name,
        match_utc_date=match_utc_date,
        description_max_length=description_max_length,
        rss_response_cache=rss_response_cache,
    )

    # Les articles communs à l'affiche restent visibles dans les deux colonnes équipe.
    # Une déduplication globale est appliquée par le service du chatbot Groq avant analyse.
    home_block = normalize_team_news_block_status(home_block)
    away_block = normalize_team_news_block_status(away_block)

    status = build_news_context_status(home_block, away_block)
    merged_articles = merge_team_articles_for_match_context(
        home_block.get("articles", []),
        away_block.get("articles", []),
    )

    ai_context = build_match_news_ai_context(
        home_team_name=home_team_name or "Équipe domicile",
        home_articles=home_block.get("articles", []),
        away_team_name=away_team_name or "Équipe extérieure",
        away_articles=away_block.get("articles", []),
    )

    return {
        "status": status,
        "source": GOOGLE_NEWS_RSS_SOURCE,
        "ai_context": ai_context,
        "match_id": match_id,
        "competition": competition_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "home_team": home_block,
        "away_team": away_block,
        "articles_count": len(merged_articles),
        "articles": merged_articles,
        "empty_state": build_news_context_empty_state(status),
        "limits": build_team_news_context_limits(),
    }


# Cette fonction limite uniquement la copie publique des extraits sans altérer le corpus partagé avec Ruby.
def truncate_news_context_response_descriptions(
    response: dict[str, Any],
    max_length: int = 220,
) -> dict[str, Any]:
    updated_response = dict(response)

    # Cette fonction interne crée une copie courte d'un article pour l'interface.
    def truncate_article(article: dict[str, Any]) -> dict[str, Any]:
        return {
            **article,
            "description": shorten_news_description(
                article.get("description"),
                max_length=max_length,
            ),
        }

    updated_response["articles"] = [
        truncate_article(article)
        for article in updated_response.get("articles") or []
    ]

    for block_name in ("home_team", "away_team"):
        team_block = dict(updated_response.get(block_name) or {})
        team_block["articles"] = [
            truncate_article(article)
            for article in team_block.get("articles") or []
        ]
        updated_response[block_name] = team_block

    return updated_response


# Cette fonction exécute le pipeline RSS hors de la boucle FastAPI puis enrichit seulement les articles retenus.
async def build_enriched_match_news_context_response(
    match_id: int,
    match: dict[str, Any],
) -> dict[str, Any]:
    base_response = await asyncio.to_thread(
        build_match_news_context_response,
        match_id,
        match,
        None,
    )
    selected_articles = list(base_response.get("articles") or [])
    enriched_articles = await fetch_news_context_article_previews(selected_articles)
    store_match_news_selected_articles(match_id, match, enriched_articles)
    enriched_response = apply_enriched_articles_to_team_blocks(
        base_response,
        enriched_articles,
    )
    return truncate_news_context_response_descriptions(enriched_response)


# Schéma de communication :
# matches.py -> team_news_context_service.py
# ├── utilise google_news_rss_client.py pour récupérer plusieurs flux publics par équipe
# ├── utilise news_nlp_service.py pour filtrer et classer les articles
# ├── utilise news_article_content_service.py pour résoudre les éditeurs et récupérer les images
# ├── utilise news_context_ai_service.py pour préparer la lecture contextuelle IA optionnelle
# └── renvoie une réponse news-context à l'API puis au frontend