# Rôle du fichier :
# Ces tests valident le backend du chatbot RubyBets sous quota Groq gratuit.
# Aucun test n'appelle réellement Internet, Google News ou l'API Groq.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from pydantic import ValidationError

from app.api import news_chatbot as news_chatbot_api
from app.core.config import settings
from app.schemas.news_chatbot import NewsChatbotMode, NewsChatbotRequest
from app.services.groq_chatbot_client import (
    GroqChatbotError,
    adapt_groq_completion_tokens,
    build_groq_response_format,
    clear_groq_rate_limit_state,
    parse_groq_json_content,
    request_groq_chatbot_completion,
)
from app.services.match_news_chatbot_service import (
    build_local_news_chatbot_fallback_answer,
    build_match_news_chatbot_response,
    build_news_chatbot_messages,
    clean_local_news_chatbot_candidate,
    clear_news_chatbot_cache,
    is_news_chatbot_outcome_question,
    merge_team_articles_for_chatbot,
    sanitize_uncited_news_chatbot_factual_claims,
    select_news_chatbot_articles_for_question,
    validate_news_chatbot_source_ids,
)
from app.services.news_article_content_service import (
    extract_main_article_text,
    fetch_chatbot_articles_content,
    fetch_full_article_content,
    is_extracted_article_text_relevant,
    is_google_intermediary_url,
    is_obviously_non_article_text,
    is_resolved_article_url_coherent,
    is_safe_public_article_url,
    limit_article_text,
    resolve_google_news_publisher_url,
)
from app.services.news_chatbot_summarization_service import (
    build_fast_question_article_digests,
    build_fast_summary_article_digests,
    clear_news_chatbot_article_digest_cache,
    normalize_chatbot_text,
    split_article_content_into_chunks,
    summarize_news_chatbot_article,
)


FAKE_MATCH = {
    "utc_date": "2026-07-21T16:00:00Z",
    "competition": {"name": "Champions League - Qualification"},
    "home_team": {"name": "Ararat-Armenia (ARM)"},
    "away_team": {"name": "Shamrock Rovers (IRL)"},
}


# Cette fonction construit un article chatbot contrôlé pour les tests unitaires.
def build_chatbot_article(
    article_id: str,
    title: str,
    url: str,
    team: str,
    content_status: str = "full",
    content: str | None = None,
) -> dict:
    article_content = content or (f"Contenu public détaillé pour {title}. " * 20).strip()
    return {
        "article_id": article_id,
        "title": title,
        "description": f"Description complète de {title}",
        "url": url,
        "resolved_url": url,
        "source_name": "Test Media",
        "published_at": "2026-07-18T10:00:00+00:00",
        "team_detected": team,
        "teams_detected": [team],
        "content": article_content,
        "content_status": content_status,
        "content_truncated": content_status == "partial",
        "content_length": len(article_content),
    }


# Cette fonction construit un digest d'article contrôlé pour isoler la synthèse finale.
def build_article_digest(article: dict, chunks: int = 1) -> dict:
    return {
        "article_id": article["article_id"],
        "title": article["title"],
        "source_name": article["source_name"],
        "published_at": article["published_at"],
        "content_status": article["content_status"],
        "citation_eligible": article.get("citation_eligible") is not False,
        "summary": f"Résumé complet de {article['title']}.",
        "key_facts": [f"Fait confirmé dans {article['title']}."],
        "limitations": [],
        "source_ids": [article["article_id"]],
        "chunks_analyzed": chunks,
        "chunks_expected": chunks,
        "complete_analysis": True,
    }


# Cette fonction construit une application FastAPI minimale pour isoler la route chatbot.
def build_news_chatbot_test_client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(news_chatbot_api.router)
    return TestClient(test_app)


# Cette fonction vérifie que le mode question impose un texte utilisateur exploitable.
def test_news_chatbot_request_requires_question_in_question_mode() -> None:
    with pytest.raises(ValidationError):
        NewsChatbotRequest(mode=NewsChatbotMode.QUESTION)

    request = NewsChatbotRequest(
        mode=NewsChatbotMode.QUESTION,
        question="  Quelles absences sont mentionnées ?  ",
    )

    assert request.question == "Quelles absences sont mentionnées ?"


# Cette fonction vérifie que la fusion alterne les équipes et supprime les doublons globaux.
def test_merge_team_articles_for_chatbot_is_balanced_and_deduplicated() -> None:
    shared_home = build_chatbot_article(
        "TEMP-1",
        "Ararat-Armenia vs Shamrock Rovers preview - Test Media",
        "https://example.com/shared-home",
        "Ararat-Armenia (ARM)",
    )
    shared_away = {
        **shared_home,
        "url": "https://example.com/shared-away",
        "resolved_url": "https://example.com/shared-away",
        "team_detected": "Shamrock Rovers (IRL)",
    }
    home_only = build_chatbot_article(
        "TEMP-2",
        "Ararat-Armenia squad update",
        "https://example.com/home",
        "Ararat-Armenia (ARM)",
    )
    away_only = build_chatbot_article(
        "TEMP-3",
        "Shamrock Rovers injury update",
        "https://example.com/away",
        "Shamrock Rovers (IRL)",
    )

    merged = merge_team_articles_for_chatbot(
        [shared_home, home_only],
        [shared_away, away_only],
        max_articles=12,
    )

    assert [article["article_id"] for article in merged] == [
        "NEWS-01",
        "NEWS-02",
        "NEWS-03",
    ]
    assert merged[0]["teams_detected"] == [
        "Ararat-Armenia (ARM)",
        "Shamrock Rovers (IRL)",
    ]
    assert merged[1]["title"] == home_only["title"]
    assert merged[2]["title"] == away_only["title"]


# Cette fonction vérifie que les URL locales ou privées sont refusées avant téléchargement.
def test_article_url_security_rejects_local_targets() -> None:
    assert is_safe_public_article_url("https://example.com/article") is True
    assert is_safe_public_article_url("http://localhost:8000/private") is False
    assert is_safe_public_article_url("http://127.0.0.1/private") is False
    assert is_safe_public_article_url("file:///tmp/article.html") is False


# Cette fonction vérifie que Trafilatura extrait le texte principal et ignore la navigation.
def test_extract_main_article_text_keeps_article_body() -> None:
    html = """
    <html><body>
      <nav>Menu accueil abonnement contact</nav>
      <article>
        <h1>Actualité du match</h1>
        <p>Ararat-Armenia prépare son prochain match européen avec un groupe presque complet.</p>
        <p>Shamrock Rovers a annoncé plusieurs choix de composition avant le déplacement.</p>
        <p>Les entraîneurs ont également évoqué la récupération et la charge du calendrier.</p>
        <p>Cette quatrième phrase apporte assez de matière pour valider l'extraction principale.</p>
      </article>
      <footer>Mentions légales et cookies</footer>
    </body></html>
    """

    extracted = extract_main_article_text(html, "https://example.com/article")

    assert "Ararat-Armenia prépare" in extracted
    assert "Shamrock Rovers" in extracted
    assert "Menu accueil abonnement" not in extracted


# Cette fonction vérifie que la limite technique est explicite et jamais silencieuse.
def test_limit_article_text_marks_truncation() -> None:
    limited_text, truncated = limit_article_text("mot " * 100, max_characters=80)

    assert truncated is True
    assert "Contenu tronqué" in limited_text


# Cette fonction vérifie que les pages de consentement Google ne sont jamais des articles finaux.
def test_google_consent_url_is_rejected_as_article_source() -> None:
    assert is_google_intermediary_url("https://consent.google.com/m?continue=x") is True
    assert is_google_intermediary_url("https://news.google.com/rss/articles/example") is True
    assert is_google_intermediary_url("https://publisher.example/article") is False


# Cette fonction vérifie qu'un décodage valide retourne uniquement l'URL éditeur publique.
def test_resolve_google_news_publisher_url_returns_editor_url(monkeypatch) -> None:
    google_url = "https://news.google.com/rss/articles/encoded-id?oc=5"
    publisher_url = "https://publisher.example/sport/article-1"

    # Ce faux décodeur évite tout appel réel à Google News.
    def fake_decoder(source_url: str) -> dict:
        assert source_url == google_url
        return {"status": True, "decoded_url": publisher_url}

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        fake_decoder,
    )

    resolved_url = asyncio.run(resolve_google_news_publisher_url(google_url))

    assert resolved_url == publisher_url


# Cette fonction vérifie que toutes les réponses de décodage invalides sont rejetées.
@pytest.mark.parametrize(
    "decoder_result",
    [
        {"status": False, "message": "decode failed"},
        {"status": True},
        {"status": True, "decoded_url": ""},
        {
            "status": True,
            "decoded_url": "https://news.google.com/rss/articles/encoded-id",
        },
        {
            "status": True,
            "decoded_url": "https://consent.google.com/m?continue=x",
        },
        {"status": True, "decoded_url": "https://www.google.com/article"},
        {"status": True, "decoded_url": "ftp://publisher.example/article"},
        {"status": True, "decoded_url": "http://127.0.0.1/private"},
        "invalid-result",
    ],
)
def test_resolve_google_news_publisher_url_rejects_invalid_results(
    monkeypatch,
    decoder_result,
) -> None:
    # Ce faux décodeur renvoie chaque variante invalide sans accès réseau.
    def fake_decoder(_source_url: str):
        return decoder_result

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        fake_decoder,
    )

    resolved_url = asyncio.run(
        resolve_google_news_publisher_url(
            "https://news.google.com/rss/articles/encoded-id?oc=5"
        )
    )

    assert resolved_url is None


# Cette fonction vérifie qu'une erreur interne de la bibliothèque reste isolée.
def test_resolve_google_news_publisher_url_isolates_decoder_exception(monkeypatch) -> None:
    # Ce faux décodeur simule une panne locale de la dépendance.
    def failing_decoder(_source_url: str) -> dict:
        raise RuntimeError("decoder unavailable")

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        failing_decoder,
    )

    resolved_url = asyncio.run(
        resolve_google_news_publisher_url(
            "https://news.google.com/rss/articles/encoded-id?oc=5"
        )
    )

    assert resolved_url is None


# Cette fonction vérifie que le décodeur synchrone s'exécute dans un thread dédié.
def test_resolve_google_news_publisher_url_uses_asyncio_to_thread(monkeypatch) -> None:
    calls: list[tuple[object, tuple, dict]] = []
    publisher_url = "https://publisher.example/article"

    # Cette coroutine remplace asyncio.to_thread et enregistre la fonction déportée.
    async def fake_to_thread(function, *args, **kwargs):
        calls.append((function, args, kwargs))
        return {"status": True, "decoded_url": publisher_url}

    monkeypatch.setattr(
        "app.services.news_article_content_service.asyncio.to_thread",
        fake_to_thread,
    )

    resolved_url = asyncio.run(
        resolve_google_news_publisher_url(
            "https://news.google.com/rss/articles/encoded-id?oc=5"
        )
    )

    assert resolved_url == publisher_url
    assert len(calls) == 1
    assert calls[0][1] == (
        "https://news.google.com/rss/articles/encoded-id?oc=5",
    )
    assert calls[0][2] == {}


# Cette fonction vérifie qu'une URL hors Google News n'active jamais le décodeur.
def test_resolve_google_news_publisher_url_ignores_non_google_url(monkeypatch) -> None:
    decoder_called = False

    # Ce faux décodeur échoue si le garde-fou de domaine n'est pas respecté.
    def fake_decoder(_source_url: str) -> dict:
        nonlocal decoder_called
        decoder_called = True
        return {"status": True, "decoded_url": "https://publisher.example/article"}

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        fake_decoder,
    )

    resolved_url = asyncio.run(
        resolve_google_news_publisher_url("https://publisher.example/article")
    )

    assert resolved_url is None
    assert decoder_called is False


# Cette fonction vérifie qu'un contenu Google générique ne passe pas le contrôle de pertinence.
def test_article_relevance_rejects_google_language_selector() -> None:
    article = {
        "title": "Ararat-Armenia vs Shamrock Rovers preview",
        "team_detected": "Ararat-Armenia (ARM)",
        "teams_detected": ["Ararat-Armenia (ARM)", "Shamrock Rovers (IRL)"],
    }
    consent_text = (
        "English United States Deutsch Español Français Italiano العربية "
        "All languages Afrikaans català Čeština Dansk"
    )
    relevant_text = (
        "Ararat-Armenia prépare la réception de Shamrock Rovers. "
        "Les deux équipes ont confirmé leur déplacement européen."
    )

    assert is_extracted_article_text_relevant(article, consent_text) is False
    assert is_extracted_article_text_relevant(article, relevant_text) is True


# Cette fonction vérifie qu'un slug de match explicite correspond bien aux deux équipes détectées.
def test_resolved_article_url_coherence_rejects_mismatched_matchup_slug() -> None:
    article = {
        "title": "Ararat Armenia vs Shamrock Rovers - FotMob",
        "team_detected": "Ararat-Armenia (ARM)",
        "teams_detected": [
            "Ararat-Armenia (ARM)",
            "Shamrock Rovers (IRL)",
        ],
    }

    assert is_resolved_article_url_coherent(
        article,
        "https://publisher.example/ararat-armenia-vs-shamrock-rovers",
    ) is True
    assert is_resolved_article_url_coherent(
        article,
        "https://www.fotmob.com/sw/matches/fk-vardar-skopje-vs-ararat-armeniariga-fc/qklb7ndv",
    ) is False
    assert is_resolved_article_url_coherent(
        article,
        "https://publisher.example/articles/123456",
    ) is True


# Cette fonction vérifie qu'une URL de rencontre incohérente reste un fallback non citable.
def test_fetch_full_article_content_rejects_mismatched_matchup_url(
    monkeypatch,
) -> None:
    google_url = "https://news.google.com/rss/articles/AU_yqL-mismatch?oc=5"
    publisher_url = (
        "https://www.fotmob.com/sw/matches/"
        "fk-vardar-skopje-vs-ararat-armeniariga-fc/qklb7ndv"
    )

    # Ce faux décodeur reproduit l'URL incohérente observée en validation réelle.
    def fake_decoder(_source_url: str) -> dict:
        return {"status": True, "decoded_url": publisher_url}

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        fake_decoder,
    )

    # Ce transport échoue si le garde-fou laisse partir une requête réseau inutile.
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Téléchargement inattendu: {request.url}")

    # Cette coroutine exécute le rejet avec un client HTTP entièrement simulé.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-02",
                    "title": "Ararat Armenia vs Shamrock Rovers - FotMob",
                    "description": "Ararat Armenia vs Shamrock Rovers FotMob",
                    "url": google_url,
                    "team_detected": "Ararat-Armenia (ARM)",
                    "teams_detected": [
                        "Ararat-Armenia (ARM)",
                        "Shamrock Rovers (IRL)",
                    ],
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["content_status"] == "partial"
    assert result["citation_eligible"] is False
    assert result["resolved_url"] == google_url
    assert "autre rencontre" in result["content_message"]


# Cette fonction vérifie que Google News est décodé avant le téléchargement de l'éditeur.
def test_fetch_full_article_content_decodes_google_news_before_extraction(
    monkeypatch,
) -> None:
    google_url = "https://news.google.com/rss/articles/AU_yqL-test?oc=5"
    publisher_url = "https://publisher.example/sport/ararat-shamrock"
    article_html = (
        "<html><body><article><h1>Ararat-Armenia squad update</h1><p>"
        + (
            "Ararat-Armenia prépare le match contre Shamrock Rovers "
            "avec un groupe presque complet. "
        ) * 20
        + "</p></article></body></html>"
    )

    # Ce faux décodeur retourne l'URL éditeur sans appel réel à Google News.
    def fake_decoder(source_url: str) -> dict:
        assert source_url == google_url
        return {"status": True, "decoded_url": publisher_url}

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        fake_decoder,
    )

    # Ce transport autorise uniquement le téléchargement de la page éditeur.
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == publisher_url
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=article_html,
            request=request,
        )

    # Cette coroutine exécute le flux complet sans accès réseau réel.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-01",
                    "title": "Ararat-Armenia squad update",
                    "description": "Extrait RSS",
                    "url": google_url,
                    "team_detected": "Ararat-Armenia (ARM)",
                    "teams_detected": ["Ararat-Armenia (ARM)"],
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["content_status"] == "full"
    assert result["resolved_url"] == publisher_url
    assert "Shamrock Rovers" in result["content"]


# Cette fonction vérifie qu'un échec de décodage Google reste partiel et sans appel réseau.
def test_fetch_full_article_content_falls_back_when_google_decode_fails(
    monkeypatch,
) -> None:
    # Ce faux décodeur simule une URL Google News non résolue.
    def fake_decoder(_source_url: str) -> dict:
        return {"status": False, "message": "decode failed"}

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        fake_decoder,
    )

    # Ce transport échoue si le service tente de télécharger la page Google intermédiaire.
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Aucun appel réseau attendu : {request.url}")

    # Cette coroutine vérifie le repli RSS sans accès réseau réel.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-01",
                    "title": "Ararat-Armenia preview",
                    "description": "Extrait RSS disponible.",
                    "url": "https://news.google.com/rss/articles/AU_yqL-test?oc=5",
                    "team_detected": "Ararat-Armenia (ARM)",
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["content_status"] == "partial"
    assert result["resolved_url"].startswith("https://news.google.com/")
    assert result["content"] == "Extrait RSS disponible."
    assert "URL éditeur" in result["content_message"]


# Cette fonction vérifie qu'une exception du décodeur n'interrompt pas le traitement de l'article.
def test_fetch_full_article_content_isolates_decoder_exception(monkeypatch) -> None:
    # Ce faux décodeur simule une panne inattendue de la bibliothèque.
    def failing_decoder(_source_url: str) -> dict:
        raise RuntimeError("decoder unavailable")

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        failing_decoder,
    )

    # Ce transport ne doit jamais être appelé après l'échec du décodage.
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Aucun appel réseau attendu : {request.url}")

    # Cette coroutine vérifie que le fallback RSS reste disponible.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-02",
                    "title": "Shamrock Rovers preview",
                    "description": "Extrait RSS conservé.",
                    "url": "https://news.google.com/rss/articles/decoder-error?oc=5",
                    "team_detected": "Shamrock Rovers (IRL)",
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["article_id"] == "NEWS-02"
    assert result["content_status"] == "partial"
    assert result["content"] == "Extrait RSS conservé."


# Cette fonction vérifie qu'une page HTML publique produit un contenu complet exploitable.
def test_fetch_full_article_content_uses_public_html() -> None:
    html = "<html><body><article><p>" + ("Ararat-Armenia prépare son groupe pour le match. " * 30) + "</p></article></body></html>"

    # Ce transport simule une page éditeur publique sans accès réseau.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=html,
            request=request,
        )

    # Cette coroutine exécute le service avec un transport HTTP simulé.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-01",
                    "title": "Ararat-Armenia group update",
                    "description": "Extrait RSS",
                    "url": "https://example.com/article",
                    "team_detected": "Ararat-Armenia (ARM)",
                    "teams_detected": ["Ararat-Armenia (ARM)"],
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["content_status"] == "full"
    assert "Ararat-Armenia prépare" in result["content"]
    assert result["resolved_url"] == "https://example.com/article"


# Cette fonction vérifie qu'un contenu extrait trop court reste un fallback RSS partiel.
def test_fetch_full_article_content_rejects_short_extraction() -> None:
    short_html = (
        "<html><body><article><p>"
        "Ararat-Armenia prépare le match."
        "</p></article></body></html>"
    )

    # Ce transport simule un article public dont le contenu principal est insuffisant.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=short_html,
            request=request,
        )

    # Cette coroutine exécute l'extraction courte sans accès réseau réel.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-03",
                    "title": "Ararat-Armenia match preview",
                    "description": "Extrait RSS de secours.",
                    "url": "https://publisher.example/short-article",
                    "team_detected": "Ararat-Armenia (ARM)",
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["content_status"] == "partial"
    assert result["content"] == "Extrait RSS de secours."
    assert "extrait intégralement" in result["content_message"]


# Cette fonction vérifie qu'un sélecteur de langues long n'est jamais déclaré comme article complet.
def test_fetch_full_article_content_rejects_language_selector_page() -> None:
    language_selector = (
        "English Deutsch Español Français Italiano Afrikaans català Čeština Dansk "
        "Nederlands Polski Português Suomi Svenska Türkçe "
    ) * 12
    html = f"<html><body><main>{language_selector}</main></body></html>"

    # Ce transport simule une page de langues renvoyée à la place d'un article.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=html,
            request=request,
        )

    # Cette coroutine vérifie que le contenu générique est rejeté.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-04",
                    "title": "Ararat-Armenia vs Shamrock Rovers preview",
                    "description": "Extrait RSS fiable.",
                    "url": "https://publisher.example/language-selector",
                    "team_detected": "Ararat-Armenia (ARM)",
                    "teams_detected": [
                        "Ararat-Armenia (ARM)",
                        "Shamrock Rovers (IRL)",
                    ],
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert is_obviously_non_article_text(language_selector) is True
    assert result["content_status"] == "partial"
    assert result["content"] == "Extrait RSS fiable."
    assert "ne correspond pas suffisamment" in result["content_message"]


# Cette fonction vérifie qu'une redirection vers Google Consent est rejetée avant téléchargement final.
def test_fetch_full_article_content_rejects_google_consent_redirect() -> None:
    requested_urls: list[str] = []

    # Ce transport simule une redirection éditeur vers une page de consentement Google.
    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://consent.google.com/m?continue=x"},
            request=request,
        )

    # Cette coroutine vérifie le garde-fou de redirection sans accès réseau réel.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-05",
                    "title": "Ararat-Armenia update",
                    "description": "Extrait RSS conservé.",
                    "url": "https://publisher.example/redirect",
                    "team_detected": "Ararat-Armenia (ARM)",
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert requested_urls == ["https://publisher.example/redirect"]
    assert result["content_status"] == "partial"
    assert result["content"] == "Extrait RSS conservé."


# Cette fonction vérifie qu'une page bloquée utilise seulement l'extrait RSS et signale le statut partiel.
def test_fetch_full_article_content_falls_back_to_rss_description() -> None:
    # Ce transport simule une page publique refusée par l'éditeur.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    # Cette coroutine exécute le repli RSS avec un transport HTTP simulé.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-01",
                    "title": "Article bloqué",
                    "description": "Extrait RSS disponible pour le chatbot.",
                    "url": "https://example.com/article",
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["content_status"] == "partial"
    assert result["content"] == "Extrait RSS disponible pour le chatbot."
    assert "HTTP 403" in result["content_message"]


# Cette fonction vérifie qu'un éditeur décodé reste visible même si sa page refuse l'extraction.
def test_fetch_full_article_content_preserves_decoded_publisher_url_on_http_error(
    monkeypatch,
) -> None:
    google_url = "https://news.google.com/rss/articles/publisher-blocked?oc=5"
    publisher_url = "https://publisher.example/blocked-article"

    # Ce faux décodeur simule une résolution correcte vers l'éditeur.
    def fake_decoder(_source_url: str) -> dict:
        return {"status": True, "decoded_url": publisher_url}

    monkeypatch.setattr(
        "app.services.news_article_content_service.new_decoderv1",
        fake_decoder,
    )

    # Ce transport simule un refus HTTP de la page éditeur résolue.
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == publisher_url
        return httpx.Response(403, request=request)

    # Cette coroutine contrôle le fallback RSS et la conservation de l'URL éditeur.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full_article_content(
                {
                    "article_id": "NEWS-06",
                    "title": "Ararat-Armenia opponent confirmed",
                    "description": "Extrait RSS conservé.",
                    "url": google_url,
                },
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["content_status"] == "partial"
    assert result["resolved_url"] == publisher_url
    assert result["content"] == "Extrait RSS conservé."
    assert "HTTP 403" in result["content_message"]


# Cette fonction vérifie que les articles gardent leur ordre et leurs identifiants malgré les durées variables.
def test_fetch_chatbot_articles_content_preserves_order_and_ids(monkeypatch) -> None:
    articles = [
        {"article_id": "NEWS-01", "url": "https://example.com/slow"},
        {"article_id": "NEWS-02", "url": "https://example.com/fallback"},
        {"article_id": "NEWS-03", "url": "https://example.com/fast"},
    ]

    # Ce faux téléchargement simule des durées différentes et un article partiel isolé.
    async def fake_fetch_full_article_content(article, client=None):
        delay = {"NEWS-01": 0.02, "NEWS-02": 0.01, "NEWS-03": 0.0}[
            article["article_id"]
        ]
        await asyncio.sleep(delay)
        return {
            **article,
            "content_status": (
                "partial" if article["article_id"] == "NEWS-02" else "full"
            ),
        }

    monkeypatch.setattr(
        "app.services.news_article_content_service.fetch_full_article_content",
        fake_fetch_full_article_content,
    )

    results = asyncio.run(fetch_chatbot_articles_content(articles))

    assert [article["article_id"] for article in results] == [
        "NEWS-01",
        "NEWS-02",
        "NEWS-03",
    ]
    assert results[1]["content_status"] == "partial"
    assert results[2]["content_status"] == "full"


# Cette fonction vérifie que le découpage conserve l'intégralité sémantique du contenu source.
def test_split_article_content_into_chunks_preserves_all_text() -> None:
    source_text = "\n\n".join(
        [
            "Premier paragraphe avec les informations de composition.",
            "Deuxième paragraphe " + ("très détaillé " * 120),
            "Troisième paragraphe avec la date exacte du match.",
        ]
    )

    chunks = split_article_content_into_chunks(source_text, max_characters=1000)

    assert len(chunks) >= 2
    assert normalize_chatbot_text(" ".join(chunks)) == normalize_chatbot_text(source_text)
    assert all(len(chunk) <= 1000 for chunk in chunks)


# Cette fonction vérifie que tous les fragments d'un article sont analysés puis réutilisés depuis le cache.
def test_summarize_article_analyzes_all_chunks_and_reuses_cache(monkeypatch) -> None:
    clear_news_chatbot_article_digest_cache()
    article = build_chatbot_article(
        "NEWS-01",
        "Article très détaillé",
        "https://example.com/long",
        "Ararat-Armenia (ARM)",
        content=" ".join(f"Information-{index}" for index in range(700)),
    )
    groq_calls = 0

    # Ce faux client résume chaque fragment sans utiliser la clé Groq réelle.
    async def fake_groq_completion(messages, **kwargs):
        nonlocal groq_calls
        groq_calls += 1
        assert len(messages) == 1
        assert "CONTENU DU FRAGMENT" in messages[0]["content"]
        return {
            "summary": f"Résumé du fragment {groq_calls}.",
            "key_facts": [f"Fait {groq_calls}."],
            "limitations": [],
            "source_ids": ["NEWS-01"],
        }

    monkeypatch.setattr(
        "app.services.news_chatbot_summarization_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    first_digest, first_cached = asyncio.run(summarize_news_chatbot_article(article))
    first_call_count = groq_calls
    second_digest, second_cached = asyncio.run(summarize_news_chatbot_article(article))

    assert first_digest is not None
    assert first_digest["complete_analysis"] is True
    assert first_digest["chunks_analyzed"] == first_digest["chunks_expected"]
    assert first_digest["chunks_analyzed"] >= 2
    assert first_cached is False
    assert second_cached is True
    assert second_digest == first_digest
    assert groq_calls == first_call_count


# Cette fonction vérifie qu'un fragment Groq défaillant devient une limite partielle sans perdre l'article entier.
def test_summarize_article_keeps_partial_digest_when_one_chunk_fails(monkeypatch) -> None:
    clear_news_chatbot_article_digest_cache()
    article = build_chatbot_article(
        "NEWS-01",
        "Article partiellement analysable",
        "https://example.com/partial-digest",
        "Ararat-Armenia (ARM)",
        content=" ".join(f"Information-{index}" for index in range(900)),
    )
    groq_calls = 0

    # Ce faux client échoue sur un seul fragment puis laisse les autres analyses continuer.
    async def fake_groq_completion(messages, **kwargs):
        nonlocal groq_calls
        groq_calls += 1

        if groq_calls == 2:
            raise GroqChatbotError(
                code="GROQ_REQUEST_REJECTED",
                public_message="Fragment refusé.",
                status_code=502,
            )

        return {
            "summary": f"Résumé du fragment {groq_calls}.",
            "key_facts": [f"Fait {groq_calls}."],
            "limitations": [],
            "source_ids": ["NEWS-01"],
        }

    monkeypatch.setattr(
        "app.services.news_chatbot_summarization_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    digest, from_cache = asyncio.run(summarize_news_chatbot_article(article))

    assert digest is not None
    assert from_cache is False
    assert digest["complete_analysis"] is False
    assert digest["chunks_failed"] == 1
    assert digest["chunks_analyzed"] == digest["chunks_expected"] - 1
    assert digest["source_ids"] == ["NEWS-01"]
    assert any("1 fragment" in limitation for limitation in digest["limitations"])


# Cette fonction vérifie que les faits importants non cités sont retirés sans supprimer les titres.
def test_uncited_factual_claim_guard_removes_unsupported_score() -> None:
    answer = (
        "**Forme récente**\n\n"
        "- Ararat-Armenia a perdu 5-0 contre Riga FC.\n\n"
        "- Shamrock Rovers a remporté son match retour [NEWS-01].\n\n"
        "**Limites**\n\n"
        "Les conditions météo ne sont pas précisées."
    )

    sanitized_answer, removed_count = sanitize_uncited_news_chatbot_factual_claims(
        answer,
        FAKE_MATCH,
    )

    assert removed_count == 1
    assert "5-0" not in sanitized_answer
    assert "Shamrock Rovers" in sanitized_answer
    assert "[NEWS-01]" in sanitized_answer
    assert "**Forme récente**" in sanitized_answer


# Cette fonction vérifie que seuls les identifiants réellement présents peuvent être cités.
def test_validate_news_chatbot_source_ids_rejects_invented_sources() -> None:
    articles = [
        build_chatbot_article(
            "NEWS-01",
            "Article un",
            "https://example.com/one",
            "Ararat-Armenia (ARM)",
        )
    ]

    validated = validate_news_chatbot_source_ids(
        ["NEWS-01", "NEWS-99", "NEWS-01"],
        articles,
    )

    assert validated == ["NEWS-01"]


# Cette fonction vérifie la synthèse, les citations et le cache sans appel Groq réel.
def test_match_news_chatbot_response_builds_cited_summary_and_reuses_cache(
    monkeypatch,
) -> None:
    clear_news_chatbot_cache()
    articles = [
        build_chatbot_article(
            "NEWS-01",
            "Ararat-Armenia squad update",
            "https://example.com/one",
            "Ararat-Armenia (ARM)",
        ),
        build_chatbot_article(
            "NEWS-02",
            "Shamrock Rovers travel update",
            "https://example.com/two",
            "Shamrock Rovers (IRL)",
            content_status="partial",
        ),
    ]
    groq_calls = 0

    # Ce faux préparateur évite tout RSS et tout téléchargement pendant le test.
    async def fake_get_prepared_articles(match_id, match):
        return articles, "fingerprint-test", False

    # Ce faux analyseur échoue si l'ancien chemin Groq par fragments est encore utilisé.
    async def fake_summarize_articles(selected_articles):
        raise AssertionError("Le résumé rapide ne doit plus analyser les fragments avec Groq.")

    # Ce faux client reproduit une réponse JSON Groq avec citations contrôlées.
    async def fake_groq_completion(messages, **kwargs):
        nonlocal groq_calls
        groq_calls += 1
        assert len(messages) == 1
        assert "SOURCE_ID: NEWS-01" in messages[0]["content"]
        assert "DIGESTS DES ARTICLES ANALYSÉS" in messages[0]["content"]
        assert kwargs["max_completion_tokens"] == 900
        return {
            "answer": "Les deux équipes préparent le match avec prudence [NEWS-01] [NEWS-02].",
            "source_ids": ["NEWS-01", "NEWS-02"],
            "insufficient_data": False,
            "limitations": ["Un article est partiel."],
        }

    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.get_prepared_news_chatbot_articles",
        fake_get_prepared_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.summarize_news_chatbot_articles",
        fake_summarize_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    first_response = asyncio.run(
        build_match_news_chatbot_response(
            match_id=123,
            match=FAKE_MATCH,
            mode=NewsChatbotMode.SUMMARY,
            match_source="flashscore_rapidapi",
        )
    )
    second_response = asyncio.run(
        build_match_news_chatbot_response(
            match_id=123,
            match=FAKE_MATCH,
            mode=NewsChatbotMode.SUMMARY,
            match_source="flashscore_rapidapi",
        )
    )

    assert first_response["status"] == "partial"
    assert first_response["source_articles_count"] == 2
    assert first_response["analyzed_articles_count"] == 2
    assert first_response["analyzed_chunks_count"] == 2
    assert [source["article_id"] for source in first_response["sources"]] == [
        "NEWS-01",
        "NEWS-02",
    ]
    assert second_response["cached"] is True
    assert groq_calls == 1


# Cette fonction vérifie que la réponse finale retire les faits non cités et les sources non éligibles.
def test_match_news_chatbot_response_filters_unsupported_claims_and_sources(
    monkeypatch,
) -> None:
    clear_news_chatbot_cache()
    articles = [
        build_chatbot_article(
            "NEWS-01",
            "Shamrock Rovers qualification update",
            "https://example.com/one",
            "Shamrock Rovers (IRL)",
        ),
        {
            **build_chatbot_article(
                "NEWS-02",
                "Ararat Armenia vs Shamrock Rovers - FotMob",
                "https://news.google.com/rss/articles/mismatch",
                "Ararat-Armenia (ARM)",
                content_status="partial",
            ),
            "citation_eligible": False,
        },
    ]

    # Ce faux préparateur fournit les deux statuts sans appel externe.
    async def fake_get_prepared_articles(match_id, match):
        return articles, "fingerprint-quality-guard", False

    # Ce faux analyseur conserve le statut de citation de chaque source.
    async def fake_summarize_articles(selected_articles):
        return [build_article_digest(article) for article in selected_articles], 0

    # Ce faux client injecte un score non cité et une citation explicitement non éligible.
    async def fake_groq_completion(messages, **kwargs):
        return {
            "answer": (
                "**Contexte**\n\n"
                "Ararat-Armenia a perdu 5-0 contre Riga FC.\n\n"
                "Shamrock Rovers a validé sa qualification [NEWS-01].\n\n"
                "Quatre absences sont annoncées [NEWS-02]."
            ),
            "source_ids": ["NEWS-01", "NEWS-02"],
            "insufficient_data": False,
            "limitations": [],
        }

    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.get_prepared_news_chatbot_articles",
        fake_get_prepared_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.summarize_news_chatbot_articles",
        fake_summarize_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    response = asyncio.run(
        build_match_news_chatbot_response(
            match_id=789,
            match=FAKE_MATCH,
            mode=NewsChatbotMode.SUMMARY,
        )
    )

    assert response["status"] == "partial"
    assert response["insufficient_data"] is True
    assert "5-0" not in response["answer"]
    assert "NEWS-02" not in response["answer"]
    assert [source["article_id"] for source in response["sources"]] == ["NEWS-01"]
    assert any(
        "sans citation" in limitation.lower()
        for limitation in response["limitations"]
    )
    assert any(
        "non éligibles" in limitation.lower()
        for limitation in response["limitations"]
    )


# Cette fonction vérifie que les questions sur le vainqueur sont reconnues sans dépendre des accents.
def test_news_chatbot_outcome_question_detection_is_conversational() -> None:
    assert is_news_chatbot_outcome_question("Selon toi Ruby, qui va gagner ce match ?") is True
    assert is_news_chatbot_outcome_question("Quelle équipe est favorite ?") is True
    assert is_news_chatbot_outcome_question("Quelles absences sont confirmées ?") is False


# Cette fonction vérifie que les libellés techniques sont retirés des extraits de secours.
def test_clean_local_news_chatbot_candidate_removes_metadata_labels() -> None:
    assert clean_local_news_chatbot_candidate(
        "Compétition: Ligue des champions UEFA."
    ) == "Ligue des champions UEFA."
    assert clean_local_news_chatbot_candidate(
        "Teams: Ararat-Armenia and Shamrock Rovers."
    ) == "Ararat-Armenia and Shamrock Rovers."


# Cette fonction vérifie que le repli d'une question prédictive reste naturel, prudent et sourcé.
def test_local_question_fallback_avoids_robotic_metadata_for_winner_question() -> None:
    articles = [
        build_chatbot_article(
            "NEWS-03",
            "Contexte du match",
            "https://example.com/context",
            "Ararat-Armenia (ARM)",
        ),
        build_chatbot_article(
            "NEWS-05",
            "Préparation des équipes",
            "https://example.com/preparation",
            "Shamrock Rovers (IRL)",
        ),
    ]
    digests = [
        {
            **build_article_digest(articles[0]),
            "summary": "Compétition: Ligue des champions UEFA, match aller.",
            "key_facts": ["Match: Ararat-Armenia vs Shamrock Rovers."],
        },
        {
            **build_article_digest(articles[1]),
            "summary": "Teams: Ararat-Armenia and Shamrock Rovers.",
            "key_facts": ["Date: 21 juillet 2026."],
        },
    ]

    answer, source_ids, limitations = build_local_news_chatbot_fallback_answer(
        mode=NewsChatbotMode.QUESTION,
        question="Selon toi Ruby, qui va gagner ce match ?",
        article_digests=digests,
    )

    assert "ne permettent pas de désigner un vainqueur fiable" in answer
    assert "Le résultat reste donc ouvert" in answer
    assert "Compétition:" not in answer
    assert "Match:" not in answer
    assert "Teams:" not in answer
    assert source_ids == ["NEWS-03", "NEWS-05"]
    assert "[NEWS-03]" in answer
    assert "[NEWS-05]" in answer
    assert limitations


# Cette fonction vérifie que la question classe localement les sources et en retient au plus cinq.
def test_question_article_selection_limits_and_prioritizes_relevant_sources() -> None:
    articles = [
        build_chatbot_article(
            f"NEWS-{index:02d}",
            f"Actualité générale {index}",
            f"https://example.com/article-{index}",
            "Ararat-Armenia (ARM)",
        )
        for index in range(1, 8)
    ]
    articles[-1]["title"] = "Deux absences confirmées avant le match"
    articles[-1]["description"] = "Deux absences sont signalées dans le groupe."

    selected_articles = select_news_chatbot_articles_for_question(
        articles,
        "Quelles absences sont confirmées ?",
    )

    assert len(selected_articles) == 5
    assert selected_articles[0]["article_id"] == "NEWS-07"


# Cette fonction vérifie que le mode question utilise des digests locaux puis un seul appel Groq final.
def test_question_mode_skips_chunk_summarization_and_calls_groq_once(
    monkeypatch,
) -> None:
    clear_news_chatbot_cache()
    articles = [
        build_chatbot_article(
            f"NEWS-{index:02d}",
            f"Préparation du match {index}",
            f"https://example.com/preparation-{index}",
            (
                "Ararat-Armenia (ARM)"
                if index % 2
                else "Shamrock Rovers (IRL)"
            ),
        )
        for index in range(1, 8)
    ]
    groq_calls = 0

    # Ce faux préparateur fournit sept articles déjà extraits sans accès réseau.
    async def fake_get_prepared_articles(match_id, match):
        return articles, "fingerprint-fast-question", False

    # Ce faux analyseur échoue si le chemin lent par fragments est appelé en mode question.
    async def forbidden_summarize_articles(selected_articles):
        raise AssertionError("Le mode question ne doit pas résumer les fragments avec Groq.")

    # Ce faux client vérifie que seul le prompt final de cinq sources est envoyé.
    async def fake_groq_completion(messages, **kwargs):
        nonlocal groq_calls
        groq_calls += 1
        prompt = messages[0]["content"]
        assert prompt.count("SOURCE_ID: NEWS-") == 5
        assert kwargs["max_completion_tokens"] == 500
        return {
            "answer": (
                "Ararat-Armenia semble disposer d'une préparation plus stable "
                "selon les éléments publiés [NEWS-01]."
            )
        }

    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.get_prepared_news_chatbot_articles",
        fake_get_prepared_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.summarize_news_chatbot_articles",
        forbidden_summarize_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    response = asyncio.run(
        build_match_news_chatbot_response(
            match_id=458,
            match=FAKE_MATCH,
            mode=NewsChatbotMode.QUESTION,
            question="Quelle équipe semble la mieux préparée ?",
        )
    )

    assert groq_calls == 1
    assert response["status"] == "available"
    assert response["source_articles_count"] == 7
    assert response["analyzed_articles_count"] == 5
    assert response["analyzed_chunks_count"] == 5
    assert [source["article_id"] for source in response["sources"]] == [
        "NEWS-01"
    ]


# Cette fonction vérifie que les digests rapides restent citables sans appel fournisseur.
def test_fast_question_digests_preserve_source_metadata() -> None:
    article = build_chatbot_article(
        "NEWS-04",
        "Point effectif avant le match",
        "https://example.com/squad",
        "Ararat-Armenia (ARM)",
        content="Deux joueurs sont indisponibles pour la rencontre.",
    )

    digests = build_fast_question_article_digests([article])

    assert len(digests) == 1
    assert digests[0]["source_ids"] == ["NEWS-04"]
    assert digests[0]["fast_local_digest"] is True
    assert digests[0]["complete_analysis"] is True
    assert "indisponibles" in digests[0]["summary"]


# Cette fonction vérifie que le résumé rapide conserve toutes les sources sans appel fournisseur intermédiaire.
def test_fast_summary_digests_preserve_all_sources_and_limit_content() -> None:
    articles = [
        build_chatbot_article(
            f"NEWS-{index:02d}",
            f"Actualité du match {index}",
            f"https://example.com/summary-{index}",
            "Ararat-Armenia (ARM)",
            content=("Information détaillée sur la préparation. " * 100),
        )
        for index in range(1, 13)
    ]

    digests = build_fast_summary_article_digests(articles)

    assert len(digests) == 12
    assert [digest["article_id"] for digest in digests] == [
        f"NEWS-{index:02d}" for index in range(1, 13)
    ]
    assert all(digest["fast_local_digest"] is True for digest in digests)
    assert all(len(digest["summary"]) <= 1103 for digest in digests)


# Cette fonction vérifie que le mode résumé utilise douze digests locaux puis un seul appel Groq final.
def test_summary_mode_skips_chunk_summarization_and_calls_groq_once(
    monkeypatch,
) -> None:
    clear_news_chatbot_cache()
    articles = [
        build_chatbot_article(
            f"NEWS-{index:02d}",
            f"Contexte du match {index}",
            f"https://example.com/context-{index}",
            (
                "Ararat-Armenia (ARM)"
                if index % 2
                else "Shamrock Rovers (IRL)"
            ),
        )
        for index in range(1, 13)
    ]
    groq_calls = 0

    # Ce faux préparateur fournit douze articles déjà extraits sans accès réseau.
    async def fake_get_prepared_articles(match_id, match):
        return articles, "fingerprint-fast-summary", False

    # Ce faux analyseur interdit l'ancien traitement Groq de chaque fragment.
    async def forbidden_summarize_articles(selected_articles):
        raise AssertionError("Le résumé ne doit plus résumer les fragments avec Groq.")

    # Ce faux client vérifie qu'un seul prompt final contient les douze sources.
    async def fake_groq_completion(messages, **kwargs):
        nonlocal groq_calls
        groq_calls += 1
        prompt = messages[0]["content"]
        assert prompt.count("SOURCE_ID: NEWS-") == 12
        assert kwargs["max_completion_tokens"] == 900
        return {
            "answer": (
                "Les deux équipes préparent la rencontre avec des informations "
                "encore partielles [NEWS-01] [NEWS-02]."
            )
        }

    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.get_prepared_news_chatbot_articles",
        fake_get_prepared_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.summarize_news_chatbot_articles",
        forbidden_summarize_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    response = asyncio.run(
        build_match_news_chatbot_response(
            match_id=459,
            match=FAKE_MATCH,
            mode=NewsChatbotMode.SUMMARY,
        )
    )

    assert groq_calls == 1
    assert response["source_articles_count"] == 12
    assert response["analyzed_articles_count"] == 12
    assert response["analyzed_chunks_count"] == 12
    assert [source["article_id"] for source in response["sources"]] == [
        "NEWS-01",
        "NEWS-02",
    ]


# Cette fonction vérifie que le prompt question impose un style direct sans champs techniques.
def test_news_chatbot_question_prompt_requests_natural_answer() -> None:
    article = build_chatbot_article(
        "NEWS-01",
        "Article fiable",
        "https://example.com/one",
        "Ararat-Armenia (ARM)",
    )
    messages = build_news_chatbot_messages(
        match=FAKE_MATCH,
        mode=NewsChatbotMode.QUESTION,
        question="Qui va gagner ?",
        article_digests=[build_article_digest(article)],
    )
    prompt = messages[0]["content"]

    assert "deux ou trois phrases naturelles et conversationnelles" in prompt
    assert "Compétition:" in prompt
    assert "n'affiche jamais" in prompt
    assert "actualités seules" in prompt
    assert "garantir un vainqueur" in prompt


# Cette fonction vérifie qu'une citation invalide déclenche un repli local réellement sourcé.
def test_match_news_chatbot_response_recovers_missing_citations_from_digests(
    monkeypatch,
) -> None:
    clear_news_chatbot_cache()
    articles = [
        build_chatbot_article(
            "NEWS-01",
            "Article fiable",
            "https://example.com/one",
            "Ararat-Armenia (ARM)",
        )
    ]

    # Ce faux préparateur fournit un article complet sans requête externe.
    async def fake_get_prepared_articles(match_id, match):
        return articles, "fingerprint-missing-source", False

    # Ce faux analyseur fournit un digest complet de l'article.
    async def fake_summarize_articles(selected_articles):
        return [build_article_digest(articles[0])], 0

    # Ce faux client tente volontairement de citer une source absente.
    async def fake_groq_completion(messages, **kwargs):
        return {
            "answer": "Une information est annoncée [NEWS-99].",
            "source_ids": ["NEWS-99"],
            "insufficient_data": False,
            "limitations": [],
        }

    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.get_prepared_news_chatbot_articles",
        fake_get_prepared_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.summarize_news_chatbot_articles",
        fake_summarize_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    response = asyncio.run(
        build_match_news_chatbot_response(
            match_id=456,
            match=FAKE_MATCH,
            mode=NewsChatbotMode.QUESTION,
            question="Quelles informations sont confirmées ?",
        )
    )

    assert response["status"] == "partial"
    assert response["insufficient_data"] is True
    assert [source["article_id"] for source in response["sources"]] == ["NEWS-01"]
    assert "[NEWS-01]" in response["answer"]
    assert any(
        "reconstruite" in limitation.lower()
        for limitation in response["limitations"]
    )
    assert "NEWS-99" not in response["answer"]


# Cette fonction vérifie qu'une panne de génération finale conserve une synthèse locale citée.
def test_match_news_chatbot_response_uses_local_fallback_when_final_generation_fails(
    monkeypatch,
) -> None:
    clear_news_chatbot_cache()
    articles = [
        build_chatbot_article(
            "NEWS-01",
            "Préparation du match",
            "https://example.com/preparation",
            "Ararat-Armenia (ARM)",
        )
    ]

    # Ce faux préparateur fournit un article déjà téléchargé.
    async def fake_get_prepared_articles(match_id, match):
        return articles, "fingerprint-final-failure", False

    # Ce faux analyseur fournit un digest exploitable avant la génération finale.
    async def fake_summarize_articles(selected_articles):
        return [build_article_digest(articles[0])], 0

    # Ce faux client reproduit un refus Groq sur la dernière étape.
    async def fake_groq_completion(messages, **kwargs):
        raise GroqChatbotError(
            code="GROQ_REQUEST_REJECTED",
            public_message="Refus fournisseur.",
            status_code=502,
        )

    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.get_prepared_news_chatbot_articles",
        fake_get_prepared_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.summarize_news_chatbot_articles",
        fake_summarize_articles,
    )
    monkeypatch.setattr(
        "app.services.match_news_chatbot_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    response = asyncio.run(
        build_match_news_chatbot_response(
            match_id=457,
            match=FAKE_MATCH,
            mode=NewsChatbotMode.SUMMARY,
        )
    )

    assert response["status"] == "partial"
    assert response["insufficient_data"] is True
    assert "[NEWS-01]" in response["answer"]
    assert [source["article_id"] for source in response["sources"]] == ["NEWS-01"]


# Cette fonction vérifie qu'un article entièrement refusé par Groq conserve un extrait local non mis en cache.
def test_summarize_article_builds_local_digest_when_all_chunks_fail(monkeypatch) -> None:
    clear_news_chatbot_article_digest_cache()
    article = build_chatbot_article(
        "NEWS-01",
        "Article avec extrait local",
        "https://example.com/local-digest",
        "Ararat-Armenia (ARM)",
        content="Le groupe prépare le match à domicile avec prudence.",
    )

    # Ce faux client refuse chaque fragment afin d'activer le repli extractif.
    async def fake_groq_completion(messages, **kwargs):
        raise GroqChatbotError(
            code="GROQ_REQUEST_REJECTED",
            public_message="Refus fournisseur.",
            status_code=502,
        )

    monkeypatch.setattr(
        "app.services.news_chatbot_summarization_service.request_groq_chatbot_completion",
        fake_groq_completion,
    )

    digest, from_cache = asyncio.run(summarize_news_chatbot_article(article))

    assert from_cache is False
    assert digest is not None
    assert digest["article_id"] == "NEWS-01"
    assert digest["complete_analysis"] is False
    assert digest["source_ids"] == ["NEWS-01"]
    assert digest["summary"]


# Cette fonction vérifie le décodage JSON et le rejet d'une réponse Groq non structurée.
def test_parse_groq_json_content_accepts_json_and_rejects_plain_text() -> None:
    parsed = parse_groq_json_content(
        '{"answer":"Résumé","source_ids":["NEWS-01"],"insufficient_data":false,"limitations":[]}'
    )

    assert parsed["answer"] == "Résumé"

    with pytest.raises(GroqChatbotError) as error_info:
        parse_groq_json_content("Réponse libre non JSON")

    assert error_info.value.code == "GROQ_INVALID_RESPONSE"


# Cette fonction vérifie la construction du contrat JSON Schema strict envoyé à Groq.
def test_build_groq_response_format_uses_strict_json_schema() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    response_format = build_groq_response_format("rubybets_test", schema)

    assert response_format == {
        "type": "json_schema",
        "json_schema": {
            "name": "rubybets_test",
            "strict": True,
            "schema": schema,
        },
    }


# Cette fonction vérifie le modèle GPT-OSS, le JSON et le respect de Retry-After après une limite 429.
def test_groq_client_uses_gpt_oss_and_retries_after_429(monkeypatch) -> None:
    clear_groq_rate_limit_state()
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "groq_max_retries", 1)
    requests: list[dict] = []
    sleeps: list[float] = []

    # Ce transport renvoie d'abord une limite puis une réponse JSON valide.
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode("utf-8")))
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "2"},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"answer":"OK","source_ids":[],"insufficient_data":false,"limitations":[]}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
            request=request,
        )

    # Cette fonction remplace l'attente réelle pour garder le test instantané.
    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    # Cette coroutine exécute le client avec le transport HTTP simulé.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await request_groq_chatbot_completion(
                [{"role": "user", "content": "Réponds en JSON."}],
                max_completion_tokens=64,
                response_schema={
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "string"}},
                        "insufficient_data": {"type": "boolean"},
                        "limitations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "answer",
                        "source_ids",
                        "insufficient_data",
                        "limitations",
                    ],
                    "additionalProperties": False,
                },
                response_schema_name="rubybets_test_response",
                client=client,
                sleep_func=fake_sleep,
            )

    result = asyncio.run(execute_test())

    assert result["answer"] == "OK"
    assert len(requests) == 2
    assert requests[0]["model"] == "openai/gpt-oss-120b"
    assert "include_reasoning" not in requests[0]
    assert requests[0]["reasoning_format"] == "hidden"
    assert requests[0]["temperature"] == 0.2
    assert "top_p" not in requests[0]
    assert requests[0]["tool_choice"] == "none"
    assert requests[0]["parallel_tool_calls"] is False
    assert requests[0]["response_format"]["type"] == "json_schema"
    assert requests[0]["response_format"]["json_schema"]["strict"] is True
    assert (
        requests[0]["response_format"]["json_schema"]["name"]
        == "rubybets_test_response"
    )
    assert 2.0 in sleeps


# Cette fonction vérifie que le mode texte final n'envoie aucun format JSON au fournisseur.
def test_groq_client_text_mode_returns_plain_answer_without_response_format(monkeypatch) -> None:
    clear_groq_rate_limit_state()
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_max_retries", 0)
    requests: list[dict] = []

    # Ce transport conserve le payload puis renvoie un texte cité simple.
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Information vérifiée [NEWS-01]."}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8},
            },
            request=request,
        )

    # Cette coroutine exécute l'appel texte avec un transport local simulé.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await request_groq_chatbot_completion(
                [{"role": "user", "content": "Réponds avec une citation."}],
                max_completion_tokens=64,
                response_format_mode="text",
                structured_retry_limit=0,
                client=client,
            )

    result = asyncio.run(execute_test())

    assert result["answer"] == "Information vérifiée [NEWS-01]."
    assert "response_format" not in requests[0]
    assert requests[0]["tool_choice"] == "none"


# Cette fonction vérifie qu'un long prompt structuré reçoit immédiatement un budget de sortie suffisant.
def test_adapt_groq_completion_tokens_increases_long_structured_requests() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    assert adapt_groq_completion_tokens(
        messages=[{"role": "user", "content": "x" * 6000}],
        completion_tokens=420,
        response_schema=schema,
    ) == 1024
    assert adapt_groq_completion_tokens(
        messages=[{"role": "user", "content": "court"}],
        completion_tokens=420,
        response_schema=schema,
    ) == 420


# Cette fonction vérifie qu'une génération JSON tronquée est retentée une fois avec un budget supérieur.
def test_groq_client_retries_json_validate_failed_with_more_tokens(monkeypatch) -> None:
    clear_groq_rate_limit_state()
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "groq_max_retries", 1)
    requests: list[dict] = []

    # Ce transport simule une sortie JSON incomplète puis une réponse structurée valide.
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode("utf-8")))

        if len(requests) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Failed to generate JSON.",
                        "type": "invalid_request_error",
                        "code": "json_validate_failed",
                    }
                },
                request=request,
            )

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"answer":"OK","source_ids":[],"insufficient_data":false,"limitations":[]}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
            request=request,
        )

    # Cette fonction remplace toute attente réelle dans ce scénario de reprise immédiate.
    async def fake_sleep(_seconds: float) -> None:
        return None

    # Cette coroutine exécute le client avec un transport Groq entièrement simulé.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await request_groq_chatbot_completion(
                [{"role": "user", "content": "Réponds avec le contrat demandé."}],
                max_completion_tokens=420,
                response_schema={
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "string"}},
                        "insufficient_data": {"type": "boolean"},
                        "limitations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "answer",
                        "source_ids",
                        "insufficient_data",
                        "limitations",
                    ],
                    "additionalProperties": False,
                },
                response_schema_name="rubybets_retry_test",
                client=client,
                sleep_func=fake_sleep,
            )

    result = asyncio.run(execute_test())

    assert result["answer"] == "OK"
    assert len(requests) == 2
    assert requests[0]["max_completion_tokens"] == 420
    assert requests[1]["max_completion_tokens"] == 1024
    assert requests[1]["reasoning_format"] == "hidden"
    assert requests[1]["temperature"] == 0.0
    assert requests[1]["tool_choice"] == "none"
    assert requests[1]["parallel_tool_calls"] is False


# Cette fonction vérifie qu’une tentative de tool use hallucinée est neutralisée puis retentée.
def test_groq_client_retries_tool_use_failed_without_tools(monkeypatch) -> None:
    clear_groq_rate_limit_state()
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "groq_max_retries", 1)
    requests: list[dict] = []

    # Ce transport simule un appel d’outil invalide puis une réponse structurée correcte.
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode("utf-8")))

        if len(requests) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Failed to call a tool.",
                        "type": "invalid_request_error",
                        "code": "tool_use_failed",
                    }
                },
                request=request,
            )

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"answer":"OK","source_ids":[],"insufficient_data":false,"limitations":[]}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
            request=request,
        )

    # Cette fonction évite toute attente réelle pendant la reprise simulée.
    async def fake_sleep(_seconds: float) -> None:
        return None

    # Cette coroutine vérifie la neutralisation explicite des outils sur les deux tentatives.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await request_groq_chatbot_completion(
                [{"role": "user", "content": "Retourne le contrat demandé."}],
                max_completion_tokens=420,
                response_schema={
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "string"}},
                        "insufficient_data": {"type": "boolean"},
                        "limitations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "answer",
                        "source_ids",
                        "insufficient_data",
                        "limitations",
                    ],
                    "additionalProperties": False,
                },
                response_schema_name="rubybets_tool_retry_test",
                client=client,
                sleep_func=fake_sleep,
            )

    result = asyncio.run(execute_test())

    assert result["answer"] == "OK"
    assert len(requests) == 2
    assert requests[0]["tool_choice"] == "none"
    assert requests[0]["parallel_tool_calls"] is False
    assert requests[1]["tool_choice"] == "none"
    assert requests[1]["parallel_tool_calls"] is False
    assert requests[1]["temperature"] == 0.0
    assert requests[1]["max_completion_tokens"] == 1024


# Cette fonction vérifie le repli JSON simple après deux échecs structurés successifs.
def test_groq_client_falls_back_to_json_object_after_structured_failures(monkeypatch) -> None:
    clear_groq_rate_limit_state()
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "groq_max_retries", 2)
    requests: list[dict] = []

    # Ce transport reproduit tool_use_failed, json_validate_failed puis une réponse JSON valide.
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode("utf-8")))

        if len(requests) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Failed to call a tool.",
                        "type": "invalid_request_error",
                        "code": "tool_use_failed",
                    }
                },
                request=request,
            )

        if len(requests) == 2:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Failed to generate JSON.",
                        "type": "invalid_request_error",
                        "code": "json_validate_failed",
                    }
                },
                request=request,
            )

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"answer":"OK","source_ids":[],"insufficient_data":false,"limitations":[]}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
            request=request,
        )

    # Cette fonction évite toute attente réelle pendant les reprises simulées.
    async def fake_sleep(_seconds: float) -> None:
        return None

    # Cette coroutine exécute le scénario complet avec un transport HTTP local.
    async def execute_test() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await request_groq_chatbot_completion(
                [{"role": "user", "content": "Retourne uniquement un objet JSON valide."}],
                max_completion_tokens=420,
                response_schema={
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "string"}},
                        "insufficient_data": {"type": "boolean"},
                        "limitations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "answer",
                        "source_ids",
                        "insufficient_data",
                        "limitations",
                    ],
                    "additionalProperties": False,
                },
                response_schema_name="rubybets_fallback_test",
                client=client,
                sleep_func=fake_sleep,
            )

    result = asyncio.run(execute_test())

    assert result["answer"] == "OK"
    assert len(requests) == 3
    assert requests[0]["response_format"]["type"] == "json_schema"
    assert requests[1]["response_format"]["type"] == "json_schema"
    assert requests[2]["response_format"] == {"type": "json_object"}
    assert requests[0]["max_completion_tokens"] == 420
    assert requests[1]["max_completion_tokens"] == 1024
    assert requests[2]["max_completion_tokens"] == 2048
    assert requests[2]["tool_choice"] == "none"
    assert requests[2]["parallel_tool_calls"] is False


# Cette fonction vérifie le contrat public de la route avec un service entièrement simulé.
def test_news_chatbot_api_returns_typed_response(monkeypatch) -> None:
    # Ce faux chargeur fournit le match sans appeler FlashScore ou Football-Data.
    async def fake_load_match(match_id: int):
        assert match_id == 123
        return FAKE_MATCH, "flashscore_rapidapi"

    # Ce faux service fournit une réponse publique déjà validée.
    async def fake_build_response(**kwargs):
        assert kwargs["mode"] is NewsChatbotMode.SUMMARY
        return {
            "status": "available",
            "match_id": 123,
            "mode": "summary",
            "answer": "Résumé sourcé [NEWS-01].",
            "sources": [
                {
                    "article_id": "NEWS-01",
                    "title": "Article fiable",
                    "url": "https://example.com/one",
                    "source_name": "Test Media",
                    "published_at": "2026-07-18T10:00:00+00:00",
                    "content_status": "full",
                }
            ],
            "source_articles_count": 1,
            "full_content_articles_count": 1,
            "partial_content_articles_count": 0,
            "unavailable_articles_count": 0,
            "analyzed_articles_count": 1,
            "analyzed_chunks_count": 3,
            "insufficient_data": False,
            "cached": False,
            "generated_at": datetime.now(UTC),
            "model": "openai/gpt-oss-120b",
            "match_source": "flashscore_rapidapi",
            "responsible_note": "Aucune garantie de résultat.",
            "limitations": [],
        }

    monkeypatch.setattr(news_chatbot_api, "load_match_for_news_chatbot", fake_load_match)
    monkeypatch.setattr(
        news_chatbot_api,
        "build_match_news_chatbot_response",
        fake_build_response,
    )

    response = build_news_chatbot_test_client().post(
        "/api/matches/123/news-chat",
        json={"mode": "summary"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "openai/gpt-oss-120b"
    assert payload["analyzed_chunks_count"] == 3
    assert payload["sources"][0]["article_id"] == "NEWS-01"
    assert "api_key" not in response.text.lower()


# Cette fonction vérifie qu'une limite Groq est renvoyée avec un code public maîtrisé.
def test_news_chatbot_api_maps_groq_rate_limit(monkeypatch) -> None:
    # Ce faux chargeur évite les fournisseurs football pendant le test.
    async def fake_load_match(match_id: int):
        return FAKE_MATCH, "flashscore_rapidapi"

    # Ce faux service reproduit une limite fournisseur Groq.
    async def fake_build_response(**kwargs):
        raise GroqChatbotError(
            code="GROQ_RATE_LIMITED",
            public_message="Le chatbot est temporairement limité.",
            status_code=429,
        )

    monkeypatch.setattr(news_chatbot_api, "load_match_for_news_chatbot", fake_load_match)
    monkeypatch.setattr(
        news_chatbot_api,
        "build_match_news_chatbot_response",
        fake_build_response,
    )

    response = build_news_chatbot_test_client().post(
        "/api/matches/123/news-chat",
        json={"mode": "summary"},
    )

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "GROQ_RATE_LIMITED"


# Cette fonction vérifie que le prompt ne confond pas fuseaux horaires ou alias de stade avec une contradiction.
def test_news_chatbot_prompt_normalizes_timezones_and_place_aliases() -> None:
    article = build_chatbot_article(
        "NEWS-01",
        "Ararat-Armenia vs Shamrock Rovers preview",
        "https://example.com/preview",
        "Ararat-Armenia (ARM)",
    )
    messages = build_news_chatbot_messages(
        match=FAKE_MATCH,
        mode=NewsChatbotMode.SUMMARY,
        question=None,
        article_digests=[build_article_digest(article)],
    )

    prompt = messages[0]["content"].lower()

    assert "conversion de fuseau horaire" in prompt
    assert "normalisation de l'heure locale/utc" in prompt
    assert "alias d'un même lieu" in prompt
    assert "formulations différentes à vérifier" in prompt


# Schéma de communication :
# test_news_chatbot_backend.py
#     ↓
# schémas + extraction + découpage intégral + cache + client Groq + route FastAPI
#     ↓
# aucun appel réel Internet / Groq pendant les tests
