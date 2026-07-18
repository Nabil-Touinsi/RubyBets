# Rôle du fichier :
# Ce service télécharge uniquement les articles déjà sélectionnés par RubyBets.
# Il résout les liens Google News, extrait le contenu principal et ne contourne aucun paywall.

from __future__ import annotations

import asyncio
from ipaddress import ip_address
import logging
import re
from typing import Any
import unicodedata
from urllib.parse import unquote, urljoin, urlparse

import httpx
from googlenewsdecoder import new_decoderv1
from trafilatura import extract, html2txt

from app.core.config import settings


LOGGER = logging.getLogger(__name__)
NEWS_ARTICLE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/150.0 Safari/537.36 RubyBetsNewsChatbot/1.0"
)
NEWS_ARTICLE_MAX_RESPONSE_BYTES = 4_000_000
NEWS_ARTICLE_MIN_FULL_TEXT_CHARACTERS = 250
NEWS_ARTICLE_FETCH_CONCURRENCY = 4
NEWS_ARTICLE_MAX_REDIRECTS = 5
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}
GOOGLE_NEWS_HOSTNAMES = {"news.google.com", "news.google.fr"}
GOOGLE_INTERMEDIARY_HOSTNAMES = {
    "consent.google.com",
    "consent.google.fr",
    "www.google.com",
    "google.com",
}
ARTICLE_RELEVANCE_STOPWORDS = {
    "about",
    "against",
    "article",
    "avec",
    "breaking",
    "champions",
    "contre",
    "football",
    "from",
    "highlights",
    "july",
    "league",
    "live",
    "match",
    "news",
    "prediction",
    "score",
    "sport",
    "sports",
    "their",
    "tips",
    "versus",
    "with",
}


# Cette fonction vérifie qu'une URL publique peut être téléchargée sans cible locale évidente.
def is_safe_public_article_url(url: str | None) -> bool:
    parsed_url = urlparse(str(url or "").strip())

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        return False

    hostname = parsed_url.hostname.lower().rstrip(".")

    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".local"):
        return False

    try:
        host_ip = ip_address(hostname)
    except ValueError:
        return True

    return not (
        host_ip.is_private
        or host_ip.is_loopback
        or host_ip.is_link_local
        or host_ip.is_reserved
        or host_ip.is_unspecified
    )


# Cette fonction indique si une URL appartient au relais public Google News.
def is_google_news_article_url(url: str | None) -> bool:
    hostname = (urlparse(str(url or "")).hostname or "").lower().rstrip(".")
    return hostname in GOOGLE_NEWS_HOSTNAMES or hostname.endswith(".news.google.com")


# Cette fonction refuse les pages Google intermédiaires comme sources finales d'un article.
def is_google_intermediary_url(url: str | None) -> bool:
    hostname = (urlparse(str(url or "")).hostname or "").lower().rstrip(".")

    return (
        is_google_news_article_url(url)
        or hostname in GOOGLE_INTERMEDIARY_HOSTNAMES
        or hostname.endswith(".consent.google.com")
        or hostname.endswith(".google.com")
    )


# Cette fonction convertit un lien Google News en URL éditeur sans bloquer la boucle asynchrone.
async def resolve_google_news_publisher_url(
    google_news_url: str,
) -> str | None:
    if not is_google_news_article_url(google_news_url):
        return None

    try:
        decoder_result = await asyncio.to_thread(
            new_decoderv1,
            google_news_url,
        )
    except Exception:  # pragma: no cover - garde-fou face aux erreurs tierces inattendues.
        LOGGER.info(
            "Décodage Google News indisponible: domain=%s",
            urlparse(google_news_url).hostname,
        )
        return None

    if not isinstance(decoder_result, dict):
        return None

    if decoder_result.get("status") is not True:
        return None

    decoded_url = str(decoder_result.get("decoded_url") or "").strip()

    if not is_safe_public_article_url(decoded_url):
        return None

    if is_google_intermediary_url(decoded_url):
        return None

    return decoded_url


# Cette fonction nettoie les espaces du texte extrait tout en conservant les paragraphes.
def clean_article_text(value: str | None) -> str:
    paragraphs = [
        " ".join(paragraph.split())
        for paragraph in str(value or "").splitlines()
        if " ".join(paragraph.split())
    ]
    return "\n\n".join(paragraphs)


# Cette fonction normalise un texte pour contrôler sa correspondance avec l'article demandé.
def normalize_article_relevance_text(value: str | None) -> str:
    normalized_value = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(
        character
        for character in normalized_value
        if not unicodedata.combining(character)
    ).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())


# Cette fonction détecte les pages génériques de consentement, de langues ou d'erreur.
def is_obviously_non_article_text(value: str | None) -> bool:
    normalized_value = normalize_article_relevance_text(value)

    if not normalized_value:
        return True

    language_tokens = {
        "afrikaans",
        "catalan",
        "cestina",
        "dansk",
        "deutsch",
        "english",
        "espanol",
        "francais",
        "italiano",
        "nederlands",
        "polski",
        "portugues",
        "suomi",
        "svenska",
        "turkce",
    }
    content_tokens = set(normalized_value.split())

    if len(language_tokens.intersection(content_tokens)) >= 6:
        return True

    blocking_phrases = (
        "before you continue to google",
        "accept all reject all",
        "page not found",
        "access denied",
        "enable javascript to continue",
        "unsupported browser",
    )
    return any(phrase in normalized_value for phrase in blocking_phrases)


# Cette fonction extrait les mots distinctifs d'une équipe pour comparer un lien éditeur explicite.
def extract_distinctive_team_tokens(value: str | None) -> set[str]:
    generic_tokens = {
        "afc",
        "club",
        "fc",
        "football",
        "fk",
        "sc",
        "team",
    }
    return {
        token
        for token in normalize_article_relevance_text(
            re.sub(r"\([^)]*\)", " ", str(value or ""))
        ).split()
        if len(token) >= 3 and token not in generic_tokens and not token.isdigit()
    }


# Cette fonction contrôle les URL de match explicites sans rejeter les liens éditeurs opaques.
def is_resolved_article_url_coherent(
    article: dict[str, Any],
    resolved_url: str | None,
) -> bool:
    parsed_url = urlparse(str(resolved_url or ""))
    normalized_path = normalize_article_relevance_text(unquote(parsed_url.path))

    if not re.search(r"\b(?:vs|versus)\b", normalized_path):
        return True

    team_values = [
        str(team or "").strip()
        for team in article.get("teams_detected") or []
        if str(team or "").strip()
    ]
    detected_team = str(article.get("team_detected") or "").strip()
    if detected_team and detected_team not in team_values:
        team_values.append(detected_team)

    team_token_sets = [
        extract_distinctive_team_tokens(team_value)
        for team_value in team_values
        if extract_distinctive_team_tokens(team_value)
    ]

    if len(team_token_sets) < 2:
        return True

    path_tokens = set(normalized_path.split())

    for team_tokens in team_token_sets:
        required_matches = 1 if len(team_tokens) == 1 else 2
        if len(team_tokens.intersection(path_tokens)) < required_matches:
            return False

    return True


# Cette fonction vérifie que le contenu extrait parle réellement du titre ou des équipes sélectionnées.
def is_extracted_article_text_relevant(
    article: dict[str, Any],
    extracted_text: str | None,
) -> bool:
    if is_obviously_non_article_text(extracted_text):
        return False

    normalized_content = normalize_article_relevance_text(extracted_text)

    team_values = list(article.get("teams_detected") or [])
    detected_team = article.get("team_detected")
    if detected_team:
        team_values.append(detected_team)

    for team_value in team_values:
        normalized_team = normalize_article_relevance_text(
            re.sub(r"\([^)]*\)", " ", str(team_value or ""))
        )
        team_tokens = [
            token
            for token in normalized_team.split()
            if len(token) >= 4 and token not in {"club", "football"}
        ]

        if normalized_team and normalized_team in normalized_content:
            return True

        if len(team_tokens) >= 2 and sum(
            token in normalized_content.split() for token in set(team_tokens)
        ) >= 2:
            return True

    title_tokens = [
        token
        for token in normalize_article_relevance_text(article.get("title")).split()
        if len(token) >= 4
        and token not in ARTICLE_RELEVANCE_STOPWORDS
        and not token.isdigit()
    ]
    matching_title_tokens = {
        token for token in title_tokens if token in normalized_content.split()
    }

    return len(matching_title_tokens) >= 2


# Cette fonction extrait le texte principal d'une page HTML avec un repli maximisant le rappel.
def extract_main_article_text(html: str, url: str | None = None) -> str:
    extracted_text = extract(
        html,
        url=url,
        output_format="txt",
        include_comments=False,
        include_tables=False,
        favor_recall=True,
        deduplicate=True,
    )
    cleaned_text = clean_article_text(extracted_text)

    if len(cleaned_text) >= NEWS_ARTICLE_MIN_FULL_TEXT_CHARACTERS:
        return cleaned_text

    return clean_article_text(html2txt(html))


# Cette fonction limite un article très long tout en signalant explicitement la troncature technique.
def limit_article_text(text: str, max_characters: int) -> tuple[str, bool]:
    if max_characters <= 0 or len(text) <= max_characters:
        return text, False

    truncated_text = text[:max_characters].rsplit(" ", 1)[0].rstrip()
    return f"{truncated_text}\n\n[Contenu tronqué par la limite technique RubyBets]", True


# Cette fonction construit un repli transparent à partir de l'extrait RSS déjà sélectionné.
def build_rss_fallback_content(
    article: dict[str, Any],
    message: str,
    resolved_url: str | None = None,
    citation_eligible: bool = True,
) -> dict[str, Any]:
    fallback_text = clean_article_text(article.get("description"))
    fallback_resolved_url = str(resolved_url or article.get("url") or "").strip()

    return {
        **article,
        "resolved_url": fallback_resolved_url or article.get("url"),
        "content": fallback_text,
        "content_status": "partial" if fallback_text else "unavailable",
        "content_truncated": False,
        "content_length": len(fallback_text),
        "content_message": message,
        "citation_eligible": citation_eligible,
    }


# Cette fonction suit manuellement les redirections afin de contrôler chaque URL avant téléchargement.
async def fetch_safe_public_response(
    client: httpx.AsyncClient,
    url: str,
) -> httpx.Response:
    current_url = url

    for _ in range(NEWS_ARTICLE_MAX_REDIRECTS + 1):
        if (
            not is_safe_public_article_url(current_url)
            or is_google_intermediary_url(current_url)
        ):
            raise ValueError("Redirection vers une URL publique non exploitable.")

        response = await client.get(current_url, follow_redirects=False)

        if response.status_code not in {301, 302, 303, 307, 308}:
            return response

        location = response.headers.get("location")
        if not location:
            return response

        current_url = urljoin(str(response.url), location)

    raise ValueError("Nombre maximal de redirections dépassé.")


# Cette fonction télécharge puis extrait un article public déjà retenu par le pipeline News.
async def fetch_full_article_content(
    article: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    article_url = str(article.get("url") or "").strip()

    if not is_safe_public_article_url(article_url):
        return build_rss_fallback_content(
            article,
            "URL d'article non exploitable ou non publique.",
        )

    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(settings.news_chatbot_article_timeout_seconds),
        headers={"User-Agent": NEWS_ARTICLE_USER_AGENT},
    )

    resolved_article_url = article_url

    try:
        if is_google_news_article_url(article_url):
            publisher_url = await resolve_google_news_publisher_url(article_url)

            if not publisher_url:
                return build_rss_fallback_content(
                    article,
                    "Le relais Google News n'a pas fourni d'URL éditeur publique exploitable.",
                    citation_eligible=False,
                )

            if not is_resolved_article_url_coherent(article, publisher_url):
                return build_rss_fallback_content(
                    article,
                    "L'URL éditeur décodée semble correspondre à une autre rencontre.",
                    citation_eligible=False,
                )

            resolved_article_url = publisher_url

        response = await fetch_safe_public_response(active_client, resolved_article_url)
        response.raise_for_status()
        resolved_url = str(response.url)

        if (
            not is_safe_public_article_url(resolved_url)
            or is_google_intermediary_url(resolved_url)
        ):
            return build_rss_fallback_content(
                article,
                "La redirection finale reste une page Google intermédiaire non exploitable.",
                resolved_url=resolved_url,
            )

        if len(response.content) > NEWS_ARTICLE_MAX_RESPONSE_BYTES:
            return build_rss_fallback_content(
                article,
                "La page publique dépasse la taille maximale autorisée.",
                resolved_url=resolved_url,
            )

        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and not content_type.startswith("text/"):
            return build_rss_fallback_content(
                article,
                "Le format public de l'article n'est pas du texte HTML exploitable.",
                resolved_url=resolved_url,
            )

        extracted_text = extract_main_article_text(response.text, resolved_url)

        if len(extracted_text) < NEWS_ARTICLE_MIN_FULL_TEXT_CHARACTERS:
            return build_rss_fallback_content(
                article,
                "Le contenu principal public n'a pas pu être extrait intégralement.",
                resolved_url=resolved_url,
            )

        if not is_extracted_article_text_relevant(article, extracted_text):
            return build_rss_fallback_content(
                article,
                "Le contenu extrait ne correspond pas suffisamment à l'article sélectionné.",
                resolved_url=resolved_url,
            )

        limited_text, was_truncated = limit_article_text(
            extracted_text,
            settings.news_chatbot_max_article_characters,
        )

        return {
            **article,
            "resolved_url": resolved_url,
            "content": limited_text,
            "content_status": "partial" if was_truncated else "full",
            "content_truncated": was_truncated,
            "content_length": len(limited_text),
            "content_message": (
                "Contenu principal public extrait."
                if not was_truncated
                else "Contenu principal extrait puis limité par le garde-fou de sécurité RubyBets."
            ),
            "citation_eligible": True,
        }

    except httpx.HTTPStatusError as error:
        LOGGER.info(
            "Article chatbot indisponible: status=%s domain=%s",
            error.response.status_code,
            urlparse(article_url).hostname,
        )
        return build_rss_fallback_content(
            article,
            f"La page publique a retourné le statut HTTP {error.response.status_code}.",
            resolved_url=str(error.response.url or resolved_article_url),
        )

    except (httpx.RequestError, UnicodeError, ValueError):
        LOGGER.info(
            "Article chatbot non récupéré: domain=%s",
            urlparse(article_url).hostname,
        )
        return build_rss_fallback_content(
            article,
            "La page publique est indisponible, trop lente ou illisible.",
            resolved_url=resolved_article_url,
        )

    finally:
        if owns_client:
            await active_client.aclose()


# Cette fonction télécharge plusieurs articles avec une concurrence limitée et un ordre stable.
async def fetch_chatbot_articles_content(
    articles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(NEWS_ARTICLE_FETCH_CONCURRENCY)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.news_chatbot_article_timeout_seconds),
        headers={"User-Agent": NEWS_ARTICLE_USER_AGENT},
    ) as client:

        # Cette fonction interne limite le nombre de pages téléchargées simultanément.
        async def fetch_with_limit(article: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await fetch_full_article_content(article, client=client)

        return await asyncio.gather(
            *(fetch_with_limit(article) for article in articles)
        )


# Schéma de communication :
# match_news_chatbot_service.py
#     ↓ articles déjà sélectionnés par le pipeline News
# news_article_content_service.py
#     ├── décode les relais Google News avec googlenewsdecoder dans un thread
#     ├── n'accepte jamais une page Google intermédiaire comme article final
#     ├── contrôle les URL et redirections publiques
#     ├── rejette les contenus génériques et valide titre / équipes
#     └── extrait le contenu principal avec Trafilatura
#     ↓
# news_chatbot_summarization_service.py -> fragments complets ou extraits RSS -> Groq
