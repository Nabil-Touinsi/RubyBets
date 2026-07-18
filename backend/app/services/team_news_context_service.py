# Rôle du fichier :
# Ce fichier orchestre les actualités contextuelles d'un match RubyBets.
# Il récupère plusieurs flux RSS par équipe, filtre les articles,
# prépare une réponse API responsable et ajoute une lecture IA optionnelle.

from datetime import UTC, datetime
import re
from typing import Any

from app.services.google_news_rss_client import (
    GOOGLE_NEWS_RSS_SOURCE,
    fetch_google_news_rss_articles,
)
from app.services.news_context_ai_service import build_match_news_ai_context
from app.services.news_nlp_service import (
    filter_and_enrich_team_news_articles,
    normalize_news_text,
)


TEAM_NEWS_CONTEXT_MAX_ARTICLES_PER_TEAM = 5
TEAM_NEWS_CONTEXT_MAX_RAW_ARTICLES = 12
TEAM_COUNTRY_SUFFIX_PATTERN = re.compile(r"\s*\([A-Z0-9]{2,4}\)\s*$", re.IGNORECASE)
TEAM_NAME_SEPARATOR_PATTERN = re.compile(r"[-‐‑‒–—]+")


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
) -> dict[str, Any]:
    home_team_name = extract_team_name_from_match(match, "home")
    away_team_name = extract_team_name_from_match(match, "away")
    competition_name = extract_competition_name_from_match(match)
    match_utc_date = extract_match_utc_date_from_match(match)
    match_query = build_match_news_query(home_team_name, away_team_name)

    home_block = build_team_news_block(
        team_name=home_team_name,
        competition_name=competition_name,
        match_query=match_query,
        opponent_team_name=away_team_name,
        match_utc_date=match_utc_date,
    )
    away_block = build_team_news_block(
        team_name=away_team_name,
        competition_name=competition_name,
        match_query=match_query,
        opponent_team_name=home_team_name,
        match_utc_date=match_utc_date,
    )

    # Les articles communs à l'affiche restent visibles dans les deux colonnes équipe.
    # Une déduplication globale est appliquée par le service du chatbot Groq avant analyse.
    home_block = normalize_team_news_block_status(home_block)
    away_block = normalize_team_news_block_status(away_block)

    status = build_news_context_status(home_block, away_block)

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
        "empty_state": build_news_context_empty_state(status),
        "limits": build_team_news_context_limits(),
    }


# Schéma de communication :
# matches.py -> team_news_context_service.py
# ├── utilise google_news_rss_client.py pour récupérer plusieurs flux publics par équipe
# ├── utilise news_nlp_service.py pour filtrer et classer les articles
# ├── utilise news_context_ai_service.py pour préparer la lecture contextuelle IA optionnelle
# └── renvoie une réponse news-context à l'API puis au frontend