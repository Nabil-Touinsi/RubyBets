# Ce fichier récupère des actualités publiques depuis Google News RSS pour alimenter le contexte des équipes.
# Il retourne des articles nettoyés sans inventer de contenu si le flux RSS est vide ou indisponible.

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import quote_plus, urlparse
import re
import xml.etree.ElementTree as ET

import httpx


GOOGLE_NEWS_RSS_SOURCE = "google_news_rss"
GOOGLE_NEWS_RSS_BASE_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_DEFAULT_LANGUAGE = "en-US"
GOOGLE_NEWS_DEFAULT_COUNTRY = "US"
GOOGLE_NEWS_DEFAULT_TIMEOUT_SECONDS = 8.0
GOOGLE_NEWS_DEFAULT_MAX_ARTICLES = 6
GOOGLE_NEWS_USER_AGENT = "Mozilla/5.0 RubyBets/1.0 ContextNews"
GOOGLE_NEWS_MEDIA_NAMESPACE = "http://search.yahoo.com/mrss/"


# Cette fonction conserve uniquement une URL d'image publique en HTTP(S).
def normalize_rss_image_url(value: str | None) -> str | None:
    image_url = unescape(str(value or "")).strip()
    parsed_url = urlparse(image_url)

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        return None

    return image_url


# Cette fonction extrait la première image publique éventuellement incluse dans un fragment HTML RSS.
def extract_rss_image_from_html(value: str | None) -> str | None:
    html_value = unescape(str(value or ""))
    image_match = re.search(
        r"<img[^>]+src=[\"']([^\"']+)[\"']",
        html_value,
        flags=re.IGNORECASE,
    )

    if not image_match:
        return None

    return normalize_rss_image_url(image_match.group(1))


# Cette fonction cherche une miniature RSS dans les balises media, enclosure puis description HTML.
def extract_google_news_image_url(item: ET.Element) -> str | None:
    media_thumbnail = item.find(f"{{{GOOGLE_NEWS_MEDIA_NAMESPACE}}}thumbnail")
    media_content = item.find(f"{{{GOOGLE_NEWS_MEDIA_NAMESPACE}}}content")
    enclosure = item.find("enclosure")

    candidate_urls = [
        media_thumbnail.attrib.get("url") if media_thumbnail is not None else None,
        media_content.attrib.get("url") if media_content is not None else None,
        (
            enclosure.attrib.get("url")
            if enclosure is not None
            and str(enclosure.attrib.get("type") or "").lower().startswith("image/")
            else None
        ),
        extract_rss_image_from_html(item.findtext("description")),
    ]

    for candidate_url in candidate_urls:
        normalized_url = normalize_rss_image_url(candidate_url)
        if normalized_url:
            return normalized_url

    return None


# Cette fonction nettoie un texte RSS en supprimant le HTML et les espaces inutiles.
def clean_rss_text(value: str | None) -> str:
    raw_value = unescape(str(value or ""))
    without_tags = re.sub(r"<[^>]+>", " ", raw_value)
    return " ".join(without_tags.split())


# Cette fonction transforme une date RSS Google News en date ISO lisible par l'API.
def parse_google_news_date(value: str | None) -> str | None:
    if not value:
        return None

    try:
        parsed_date = parsedate_to_datetime(value)

        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=UTC)

        return parsed_date.astimezone(UTC).isoformat()

    except (TypeError, ValueError, IndexError, OverflowError):
        return None


# Cette fonction construit une URL Google News RSS à partir d'une requête équipe.
def build_google_news_rss_url(
    query: str,
    language: str = GOOGLE_NEWS_DEFAULT_LANGUAGE,
    country: str = GOOGLE_NEWS_DEFAULT_COUNTRY,
) -> str:
    clean_query = " ".join(str(query or "").split())
    rss_language = language.split("-")[0] if language else "en"
    ceid = f"{country}:{rss_language}"

    return (
        f"{GOOGLE_NEWS_RSS_BASE_URL}"
        f"?q={quote_plus(clean_query)}"
        f"&hl={quote_plus(language)}"
        f"&gl={quote_plus(country)}"
        f"&ceid={quote_plus(ceid)}"
    )


# Cette fonction extrait une source lisible depuis un item RSS Google News.
def extract_google_news_source(item: ET.Element) -> dict[str, str | None]:
    source_element = item.find("source")

    if source_element is None:
        return {"name": None, "url": None}

    return {
        "name": clean_rss_text(source_element.text),
        "url": source_element.attrib.get("url"),
    }


# Cette fonction transforme un item RSS brut en article normalisé pour RubyBets.
def parse_google_news_item(item: ET.Element) -> dict[str, Any]:
    source = extract_google_news_source(item)
    raw_description = item.findtext("description")

    return {
        "title": clean_rss_text(item.findtext("title")),
        "description": clean_rss_text(raw_description),
        "url": item.findtext("link"),
        "source_name": source.get("name"),
        "source_url": source.get("url"),
        "published_at": parse_google_news_date(item.findtext("pubDate")),
        "image_url": extract_google_news_image_url(item),
    }


# Cette fonction limite les articles aux entrées exploitables par le bloc Contexte.
def keep_exploitable_google_news_articles(
    articles: list[dict[str, Any]],
    max_articles: int = GOOGLE_NEWS_DEFAULT_MAX_ARTICLES,
) -> list[dict[str, Any]]:
    exploitable_articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for article in articles:
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        title_key = title.lower()

        if not title or not url:
            continue

        if url in seen_urls or title_key in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(title_key)
        exploitable_articles.append(article)

        if len(exploitable_articles) >= max_articles:
            break

    return exploitable_articles


# Cette fonction appelle Google News RSS et retourne une réponse maîtrisée même en cas d'erreur réseau.
def fetch_google_news_rss_articles(
    query: str,
    max_articles: int = GOOGLE_NEWS_DEFAULT_MAX_ARTICLES,
    timeout_seconds: float = GOOGLE_NEWS_DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    clean_query = " ".join(str(query or "").split())

    if not clean_query:
        return {
            "source": GOOGLE_NEWS_RSS_SOURCE,
            "status": "unavailable",
            "query": clean_query,
            "articles": [],
            "message": "Requête RSS vide.",
        }

    rss_url = build_google_news_rss_url(clean_query)

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(
                rss_url,
                headers={"User-Agent": GOOGLE_NEWS_USER_AGENT},
            )
            response.raise_for_status()

        root = ET.fromstring(response.text)
        raw_items = root.findall("./channel/item")
        parsed_articles = [parse_google_news_item(item) for item in raw_items]
        articles = keep_exploitable_google_news_articles(parsed_articles, max_articles)

        status = "available" if articles else "empty"

        return {
            "source": GOOGLE_NEWS_RSS_SOURCE,
            "status": status,
            "query": clean_query,
            "fetched_at": datetime.now(UTC).isoformat(),
            "articles": articles,
        }

    except httpx.HTTPStatusError as error:
        return {
            "source": GOOGLE_NEWS_RSS_SOURCE,
            "status": "unavailable",
            "query": clean_query,
            "articles": [],
            "message": f"Google News RSS a retourné une erreur HTTP {error.response.status_code}.",
        }

    except httpx.RequestError as error:
        return {
            "source": GOOGLE_NEWS_RSS_SOURCE,
            "status": "unavailable",
            "query": clean_query,
            "articles": [],
            "message": f"Flux Google News RSS indisponible : {error}.",
        }

    except ET.ParseError:
        return {
            "source": GOOGLE_NEWS_RSS_SOURCE,
            "status": "unavailable",
            "query": clean_query,
            "articles": [],
            "message": "Réponse RSS illisible.",
        }


# Schéma de communication :
# team_news_context_service.py -> google_news_rss_client.py -> Google News RSS public -> articles normalisés