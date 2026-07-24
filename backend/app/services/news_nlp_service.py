# Ce fichier classe et filtre les actualités récupérées en catégories utiles au contexte d'un match.
# La V1 utilise des règles par mots-clés, sans modèle lourd, pour rester stable et démontrable.

from datetime import UTC, date, datetime
import re
from typing import Any
import unicodedata


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
    "match",
    "preview",
    "opponent",
    "qualifying",
    "qualification",
    "champions league",
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
TEAM_COUNTRY_SUFFIX_PATTERN = re.compile(r"\s*\([A-Z0-9]{2,4}\)\s*$", re.IGNORECASE)
MATCH_PAGE_KEYWORDS = [
    " vs ",
    " v ",
    " versus ",
    "live score",
    "box score",
    "match stats",
    "head to head",
    "prediction tips",
]
EXCLUDED_LOW_VALUE_PAGE_KEYWORDS = [
    "box score",
    "boxscore",
    "live score",
    "match stats",
    "head to head",
    "scoring stats",
    "qualifying results",
    "season results",
    "fixtures and results",
    "schedule and results",
    "standings table",
    "accreditation",
    "accreditations",
    "ticket information",
    "ticketing",
]
NEWS_MONTH_NUMBERS = {
    "january": 1,
    "jan": 1,
    "janvier": 1,
    "february": 2,
    "feb": 2,
    "fevrier": 2,
    "march": 3,
    "mar": 3,
    "mars": 3,
    "april": 4,
    "apr": 4,
    "avril": 4,
    "may": 5,
    "mai": 5,
    "june": 6,
    "jun": 6,
    "juin": 6,
    "july": 7,
    "jul": 7,
    "juillet": 7,
    "august": 8,
    "aug": 8,
    "aout": 8,
    "september": 9,
    "sep": 9,
    "septembre": 9,
    "october": 10,
    "oct": 10,
    "octobre": 10,
    "november": 11,
    "nov": 11,
    "novembre": 11,
    "december": 12,
    "dec": 12,
    "decembre": 12,
}


# Cette fonction normalise accents, ponctuation et tirets pour comparer les noms de manière stable.
def normalize_news_text(value: str | None) -> str:
    decomposed_value = unicodedata.normalize("NFKD", str(value or "").lower())
    without_accents = "".join(
        character
        for character in decomposed_value
        if not unicodedata.combining(character)
    )
    alphanumeric_value = re.sub(r"[^a-z0-9]+", " ", without_accents)
    return " ".join(alphanumeric_value.split())


# Cette fonction construit les alias stables d'une équipe à partir du nom brut fournisseur.
def build_team_name_aliases(team_name: str | None) -> list[str]:
    without_country_suffix = TEAM_COUNTRY_SUFFIX_PATTERN.sub("", str(team_name or "")).strip()
    normalized_name = normalize_news_text(without_country_suffix)

    if not normalized_name:
        return []

    aliases = [normalized_name]
    words = normalized_name.split()

    if words and words[0] in {"fc", "afc", "cf", "sc"} and len(words) > 1:
        aliases.append(" ".join(words[1:]))

    return list(dict.fromkeys(aliases))


# Cette fonction construit les alias publics d'une compétition technique.
def build_competition_aliases(competition_name: str | None) -> list[str]:
    normalized_name = normalize_news_text(competition_name)

    if not normalized_name:
        return []

    known_competitions = [
        "champions league",
        "europa league",
        "conference league",
        "premier league",
        "ligue 1",
        "la liga",
        "bundesliga",
        "serie a",
    ]
    aliases = [
        competition
        for competition in known_competitions
        if competition in normalized_name
    ]

    return aliases or [normalized_name]


# Cette fonction regroupe le titre et la description d'un article pour l'analyse simple.
def build_article_text(article: dict[str, Any]) -> str:
    title = normalize_news_text(article.get("title"))
    description = normalize_news_text(article.get("description"))
    return f"{title} {description}".strip()


# Cette fonction vérifie si l'article mentionne une variante fiable de l'équipe concernée.
def article_mentions_team(article: dict[str, Any], team_name: str) -> bool:
    article_text = f" {build_article_text(article)} "
    team_aliases = build_team_name_aliases(team_name)

    return any(f" {alias} " in article_text for alias in team_aliases)


# Cette fonction vérifie si l'article cite directement les deux équipes de l'affiche.
def article_mentions_both_teams(
    article: dict[str, Any],
    team_name: str,
    opponent_team_name: str | None,
) -> bool:
    if not opponent_team_name:
        return False

    return article_mentions_team(article, team_name) and article_mentions_team(
        article,
        opponent_team_name,
    )


# Cette fonction convertit la date ISO du match en date calendrier exploitable pour le classement.
def parse_match_calendar_date(match_utc_date: str | None) -> date | None:
    if not match_utc_date:
        return None

    try:
        parsed_date = datetime.fromisoformat(
            str(match_utc_date).replace("Z", "+00:00")
        )
        return parsed_date.date()
    except ValueError:
        return None


# Cette fonction extrait les dates explicites présentes dans le titre ou la description d'un article.
def extract_article_calendar_dates(article: dict[str, Any]) -> set[date]:
    article_text = build_article_text(article)
    detected_dates: set[date] = set()

    numeric_patterns = [
        (r"\b(20\d{2})\s+([01]?\d)\s+([0-3]?\d)(?:t\d{2})?\b", "ymd"),
        (r"\b([0-3]?\d)\s+([01]?\d)\s+(20\d{2})\b", "dmy"),
    ]

    for pattern, order in numeric_patterns:
        for first_value, second_value, third_value in re.findall(pattern, article_text):
            try:
                if order == "ymd":
                    detected_dates.add(
                        date(int(first_value), int(second_value), int(third_value))
                    )
                else:
                    detected_dates.add(
                        date(int(third_value), int(second_value), int(first_value))
                    )
            except ValueError:
                continue

    month_pattern = "|".join(sorted(NEWS_MONTH_NUMBERS, key=len, reverse=True))
    text_date_patterns = [
        rf"\b({month_pattern})\s+([0-3]?\d)\s+(20\d{{2}})\b",
        rf"\b([0-3]?\d)\s+({month_pattern})\s+(20\d{{2}})\b",
    ]

    for index, pattern in enumerate(text_date_patterns):
        for first_value, second_value, year_value in re.findall(pattern, article_text):
            month_name = first_value if index == 0 else second_value
            day_value = second_value if index == 0 else first_value

            try:
                detected_dates.add(
                    date(
                        int(year_value),
                        NEWS_MONTH_NUMBERS[month_name],
                        int(day_value),
                    )
                )
            except (KeyError, ValueError):
                continue

    return detected_dates


# Cette fonction vérifie si l'article cite explicitement la date du match analysé.
def article_mentions_match_date(
    article: dict[str, Any],
    match_utc_date: str | None,
) -> bool:
    target_date = parse_match_calendar_date(match_utc_date)

    if not target_date:
        return False

    return target_date in extract_article_calendar_dates(article)


# Cette fonction détecte une date explicite différente de celle du match analysé.
def article_mentions_conflicting_match_date(
    article: dict[str, Any],
    match_utc_date: str | None,
) -> bool:
    target_date = parse_match_calendar_date(match_utc_date)
    article_dates = extract_article_calendar_dates(article)

    return bool(target_date and article_dates and target_date not in article_dates)


# Cette fonction repère une page de rencontre qui semble concerner un autre adversaire.
def article_looks_like_fixture_page(article: dict[str, Any]) -> bool:
    normalized_title = f" {normalize_news_text(article.get('title'))} "
    return any(keyword in normalized_title for keyword in MATCH_PAGE_KEYWORDS)


# Cette fonction calcule une priorité produit : affiche actuelle, contexte équipe, autre rencontre.
def build_article_match_priority(
    article: dict[str, Any],
    team_name: str,
    opponent_team_name: str | None = None,
    match_utc_date: str | None = None,
) -> int:
    direct_match = article_mentions_both_teams(
        article,
        team_name,
        opponent_team_name,
    )
    matches_target_date = article_mentions_match_date(article, match_utc_date)
    conflicts_with_target_date = article_mentions_conflicting_match_date(
        article,
        match_utc_date,
    )

    if direct_match and matches_target_date:
        return 600

    if direct_match and not conflicts_with_target_date:
        return 550

    if matches_target_date:
        return 450

    if direct_match and conflicts_with_target_date:
        return 150

    if article_looks_like_fixture_page(article):
        return 200

    return 350



# Cette fonction vérifie si la source ressemble à une page de score générique plutôt qu'à une actualité.
def is_generic_score_source(article: dict[str, Any]) -> bool:
    source_name = normalize_news_text(article.get("source_name"))
    source_url = normalize_news_text(article.get("source_url"))

    return any(
        excluded_source in source_name or excluded_source in source_url
        for excluded_source in EXCLUDED_GENERIC_SOURCES
    )


# Cette fonction exclut les pages de score, résultats ou logistique qui répètent les autres onglets.
def is_low_value_context_page(article: dict[str, Any]) -> bool:
    article_text = build_article_text(article)
    return any(
        normalize_news_text(keyword) in article_text
        for keyword in EXCLUDED_LOW_VALUE_PAGE_KEYWORDS
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


# Cette fonction compte les mots-clés métier présents après normalisation homogène.
def count_matching_keywords(article_text: str, keywords: list[str]) -> int:
    return sum(
        1
        for keyword in keywords
        if normalize_news_text(keyword) in article_text
    )


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

    competition_aliases = build_competition_aliases(competition_name)
    competition_detected = any(
        competition_alias in article_text
        for competition_alias in competition_aliases
    )

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

    if is_low_value_context_page(article):
        return False

    if not is_recent_news_article(article):
        return False

    team_detected = article_mentions_team(article, team_name)

    # Un article uniquement lié à la compétition ne doit pas être attribué à une équipe.
    return team_detected


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
    description_max_length: int | None = 220,
) -> dict[str, Any]:
    category = classify_news_category(article)
    relevance = estimate_news_relevance(article, team_name, competition_name)
    description = article.get("description")

    if description_max_length is not None:
        description = shorten_news_description(description, description_max_length)

    return {
        "title": article.get("title"),
        "description": description,
        "url": article.get("url"),
        "source_name": article.get("source_name"),
        "source_url": article.get("source_url"),
        "published_at": article.get("published_at"),
        "image_url": article.get("image_url"),
        "resolved_url": article.get("resolved_url"),
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
    opponent_team_name: str | None = None,
    match_utc_date: str | None = None,
    max_articles: int = 5,
    description_max_length: int | None = 220,
) -> list[dict[str, Any]]:
    exploitable_articles = [
        article
        for article in articles
        if is_exploitable_team_news_article(article, team_name, competition_name)
    ]
    relevance_order = {"high": 3, "medium": 2, "low": 1}

    sorted_raw_articles = sorted(
        exploitable_articles,
        key=lambda article: (
            build_article_match_priority(
                article,
                team_name=team_name,
                opponent_team_name=opponent_team_name,
                match_utc_date=match_utc_date,
            ),
            relevance_order.get(
                estimate_news_relevance(article, team_name, competition_name),
                0,
            ),
            str(article.get("published_at") or ""),
        ),
        reverse=True,
    )

    return [
        enrich_news_article(
            article,
            team_name,
            competition_name,
            description_max_length=description_max_length,
        )
        for article in sorted_raw_articles[:max_articles]
    ]


# Schéma de communication :
# team_news_context_service.py -> news_nlp_service.py -> articles filtrés et classés pour l'API news-context