# Ce fichier vérifie la normalisation des noms et le filtrage du pipeline News RubyBets.
# Il protège le cas des clubs FlashScore avec suffixe pays, tirets et variantes éditoriales.

from datetime import UTC, datetime
import xml.etree.ElementTree as ET

from app.services.google_news_rss_client import parse_google_news_item
from app.services.news_article_content_service import extract_article_preview_image_url
from app.services.news_nlp_service import (
    article_mentions_match_date,
    article_mentions_team,
    build_article_match_priority,
    filter_and_enrich_team_news_articles,
    is_exploitable_team_news_article,
)
from app.services.team_news_context_service import (
    build_match_news_context_response,
    build_match_news_query,
    build_team_news_queries,
    deduplicate_raw_articles,
    normalize_team_name_for_news,
    simplify_competition_name_for_news,
)


# Cette fonction fabrique un article RSS récent pour les tests sans appel réseau.
def build_recent_article(
    title: str,
    source_name: str = "Test Sports",
) -> dict[str, str | None]:
    return {
        "title": title,
        "description": "Contexte avant-match et informations récentes.",
        "url": f"https://example.com/{abs(hash(title))}",
        "source_name": source_name,
        "source_url": "https://example.com",
        "published_at": datetime.now(UTC).isoformat(),
    }


# Cette fonction vérifie que le suffixe pays FlashScore ne pollue plus les requêtes News.
def test_news_query_removes_flashscore_country_suffix() -> None:
    assert normalize_team_name_for_news("Ararat-Armenia (ARM)") == "Ararat-Armenia"
    assert normalize_team_name_for_news("Shamrock Rovers (IRL)") == "Shamrock Rovers"
    assert build_match_news_query(
        "Ararat-Armenia (ARM)",
        "Shamrock Rovers (IRL)",
    ) == '"Ararat-Armenia" "Shamrock Rovers"'


# Cette fonction vérifie que les variantes avec et sans tiret sont réellement interrogées.
def test_team_queries_cover_hyphen_and_space_variants() -> None:
    queries = build_team_news_queries(
        "Ararat-Armenia (ARM)",
        "Champions League - Qualification - Quarter-finals",
    )

    assert '"Ararat-Armenia" news' in queries
    assert '"Ararat Armenia" news' in queries
    assert '"Ararat-Armenia" "Champions League"' in queries
    assert all("(ARM)" not in query for query in queries)
    assert all("national football team" not in query for query in queries)


# Cette fonction vérifie que le libellé technique fournisseur est réduit au nom public de la compétition.
def test_competition_name_is_simplified_for_news() -> None:
    assert simplify_competition_name_for_news(
        "Champions League - Qualification - Quarter-finals"
    ) == "Champions League"


# Cette fonction vérifie la détection éditoriale de FC, des tirets et des suffixes pays.
def test_article_mentions_normalized_team_variants() -> None:
    article = build_recent_article(
        "Shamrock Rovers vs. FC Ararat-Armenia - Live Score - July 28, 2026"
    )

    assert article_mentions_team(article, "Ararat-Armenia (ARM)") is True
    assert article_mentions_team(article, "Shamrock Rovers (IRL)") is True


# Cette fonction vérifie qu'une actualité éditoriale récente est conservée et qu'une page de score est rejetée.
def test_filter_keeps_recent_editorial_news_and_rejects_score_page() -> None:
    recent_article = build_recent_article(
        "Ararat Armenia squad update before Shamrock Rovers tie"
    )
    score_page = build_recent_article(
        "Ararat Armenia vs Shamrock Rovers Box Score - July 21, 2026"
    )

    articles = filter_and_enrich_team_news_articles(
        articles=[score_page, recent_article],
        team_name="Ararat-Armenia (ARM)",
        competition_name="Champions League - Qualification - Quarter-finals",
    )

    assert len(articles) == 1
    assert articles[0]["title"] == recent_article["title"]
    assert articles[0]["relevance"] in {"medium", "high"}


# Cette fonction vérifie que deux URL Google différentes ne dupliquent pas le même titre.
def test_raw_articles_are_deduplicated_by_normalized_title() -> None:
    first_article = {
        **build_recent_article(
            "Champions League: Ararat-Armenia’s opponent determined - NEWS.am Sport",
            source_name="NEWS.am Sport",
        ),
        "url": "https://news.google.com/article-1",
    }
    duplicate_article = {
        **first_article,
        "url": "https://news.google.com/article-2",
    }

    deduplicated_articles = deduplicate_raw_articles(
        [first_article, duplicate_article]
    )

    assert deduplicated_articles == [first_article]


# Cette fonction vérifie que les reprises du même article par plusieurs éditeurs sont regroupées.
def test_syndicated_articles_are_deduplicated_without_publisher_suffix() -> None:
    base_title = (
        "World Cup star Lopes returns to Champions League action "
        "captaining Shamrock Rovers to win"
    )
    articles = [
        {
            **build_recent_article(
                f"{base_title} - ABC News",
                source_name="ABC News",
            ),
            "url": "https://news.google.com/abc",
        },
        {
            **build_recent_article(
                f"{base_title} - Toronto Star",
                source_name="Toronto Star",
            ),
            "url": "https://news.google.com/toronto",
        },
    ]

    deduplicated_articles = deduplicate_raw_articles(articles)

    assert deduplicated_articles == [articles[0]]


# Cette fonction vérifie qu'une actualité générique de compétition n'est pas attribuée à une équipe absente.
def test_competition_only_article_is_rejected_for_team() -> None:
    article = build_recent_article(
        "Champions League qualifying: Fixtures, results, dates, how it works"
    )

    assert is_exploitable_team_news_article(
        article,
        team_name="Shamrock Rovers (IRL)",
        competition_name="Champions League - Qualification - Quarter-finals",
    ) is False


# Cette fonction vérifie qu'une page de score citant les deux équipes est exclue du contexte éditorial.
def test_score_page_mentioning_both_teams_is_rejected() -> None:
    article = build_recent_article(
        "Ararat-Armenia vs Shamrock Rovers Box Score - July 21, 2026"
    )

    assert is_exploitable_team_news_article(
        article,
        team_name="Ararat-Armenia (ARM)",
        competition_name="Champions League - Qualification - Quarter-finals",
    ) is False
    assert is_exploitable_team_news_article(
        article,
        team_name="Shamrock Rovers (IRL)",
        competition_name="Champions League - Qualification - Quarter-finals",
    ) is False


# Cette fonction vérifie qu'une actualité éditoriale liée directement aux deux équipes reste exploitable.
def test_editorial_match_news_mentioning_both_teams_is_kept() -> None:
    article = build_recent_article(
        "Ararat-Armenia prepares for Shamrock Rovers after coach press conference"
    )

    assert is_exploitable_team_news_article(
        article,
        team_name="Ararat-Armenia (ARM)",
        competition_name="Champions League - Qualification - Quarter-finals",
    ) is True


# Cette fonction vérifie que les formats de date média usuels correspondent à la date du match.
def test_match_date_detection_supports_common_media_formats() -> None:
    match_utc_date = "2026-07-21T16:00:00Z"
    titles = [
        "Ararat Armenia vs Shamrock Rovers - July 21, 2026",
        "FC Ararat-Armenia - Shamrock Rovers 21.07.2026",
        "Ararat Armenia vs Shamrock Rovers (2026-07-21T16:00:00.000Z)",
        "Ararat-Armenia contre Shamrock Rovers - 21 juillet 2026",
    ]

    assert all(
        article_mentions_match_date(build_recent_article(title), match_utc_date)
        for title in titles
    )


# Cette fonction vérifie que l'affiche actuelle passe avant les nouvelles générales et les anciens adversaires.
def test_current_match_articles_are_ranked_before_team_context() -> None:
    current_match = build_recent_article(
        "Ararat-Armenia vs Shamrock Rovers preview - July 21, 2026"
    )
    current_match_without_date = build_recent_article(
        "Ararat-Armenia vs Shamrock Rovers - beIN SPORTS"
    )
    team_context = build_recent_article(
        "Ararat-Armenia prepares for the next Champions League round"
    )
    previous_opponent = build_recent_article(
        "Riga vs Ararat-Armenia: coach reaction after qualifier"
    )

    articles = filter_and_enrich_team_news_articles(
        articles=[previous_opponent, team_context, current_match_without_date, current_match],
        team_name="Ararat-Armenia (ARM)",
        opponent_team_name="Shamrock Rovers (IRL)",
        competition_name="Champions League - Qualification - Quarter-finals",
        match_utc_date="2026-07-21T16:00:00Z",
    )

    assert [article["title"] for article in articles] == [
        current_match["title"],
        current_match_without_date["title"],
        team_context["title"],
        previous_opponent["title"],
    ]


# Cette fonction vérifie qu'une page du match retour datée différemment est fortement rétrogradée.
def test_return_leg_with_conflicting_date_is_demoted() -> None:
    return_leg = build_recent_article(
        "Shamrock Rovers vs FC Ararat-Armenia - Live Score - July 28, 2026"
    )
    team_context = build_recent_article(
        "Shamrock Rovers travel with the squad to Armenia"
    )

    assert build_article_match_priority(
        return_leg,
        team_name="Shamrock Rovers (IRL)",
        opponent_team_name="Ararat-Armenia (ARM)",
        match_utc_date="2026-07-21T16:00:00Z",
    ) < build_article_match_priority(
        team_context,
        team_name="Shamrock Rovers (IRL)",
        opponent_team_name="Ararat-Armenia (ARM)",
        match_utc_date="2026-07-21T16:00:00Z",
    )


# Cette fonction vérifie qu'une page contre un autre adversaire reste derrière une actualité générale utile.
def test_other_opponent_fixture_is_demoted_below_team_news() -> None:
    other_fixture = build_recent_article(
        "Shamrock Rovers vs Floriana - Live Score and Match Stats"
    )
    team_news = build_recent_article(
        "Shamrock Rovers squad update before Champions League trip"
    )

    assert build_article_match_priority(
        other_fixture,
        team_name="Shamrock Rovers (IRL)",
        opponent_team_name="Ararat-Armenia (ARM)",
        match_utc_date="2026-07-21T16:00:00Z",
    ) < build_article_match_priority(
        team_news,
        team_name="Shamrock Rovers (IRL)",
        opponent_team_name="Ararat-Armenia (ARM)",
        match_utc_date="2026-07-21T16:00:00Z",
    )


# Cette fonction vérifie qu'un article commun au match reste visible pour les deux équipes.
def test_shared_match_articles_remain_visible_in_both_team_blocks(monkeypatch) -> None:
    shared_articles = [
        build_recent_article(
            f"Ararat-Armenia vs Shamrock Rovers - source {index} - July 21, 2026"
        )
        for index in range(1, 6)
    ]

    # Ce faux service retourne le même corpus pour les deux équipes du match.
    def fake_build_team_news_block(**kwargs):
        return {
            "name": kwargs["team_name"],
            "query": '"Ararat-Armenia" "Shamrock Rovers"',
            "queries": ['"Ararat-Armenia" "Shamrock Rovers"'],
            "status": "available",
            "articles_count": len(shared_articles),
            "articles": [dict(article) for article in shared_articles],
            "message": None,
        }

    monkeypatch.setattr(
        "app.services.team_news_context_service.build_team_news_block",
        fake_build_team_news_block,
    )
    monkeypatch.setattr(
        "app.services.team_news_context_service.build_match_news_ai_context",
        lambda **kwargs: {"status": "disabled"},
    )

    response = build_match_news_context_response(
        match_id=1832763682060712,
        match={
            "utc_date": "2026-07-21T16:00:00Z",
            "competition": {"name": "Champions League - Qualification"},
            "home_team": {"name": "Ararat-Armenia (ARM)"},
            "away_team": {"name": "Shamrock Rovers (IRL)"},
        },
    )

    assert response["home_team"]["articles_count"] == 5
    assert response["away_team"]["articles_count"] == 5
    assert response["home_team"]["status"] == "available"
    assert response["away_team"]["status"] == "available"
    assert response["status"] == "available"
    assert response["articles_count"] == 5


# Cette fonction vérifie que l'image éventuellement incluse dans le HTML RSS est conservée.
def test_google_news_item_extracts_rss_image() -> None:
    item = ET.fromstring(
        """
        <item>
          <title>Dinamo Zagreb squad update</title>
          <description><![CDATA[<img src="https://cdn.example.com/news.jpg" />Article preview]]></description>
          <link>https://news.google.com/articles/example</link>
          <pubDate>Fri, 24 Jul 2026 10:00:00 GMT</pubDate>
          <source url="https://example.com">Example Sports</source>
        </item>
        """
    )

    article = parse_google_news_item(item)

    assert article["image_url"] == "https://cdn.example.com/news.jpg"


# Cette fonction vérifie l'extraction d'une image Open Graph depuis une page éditeur.
def test_article_preview_extracts_open_graph_image() -> None:
    html = """
    <html><head>
      <meta property="og:image" content="/media/match-preview.webp" />
    </head><body>Article</body></html>
    """

    assert extract_article_preview_image_url(
        html,
        "https://publisher.example.com/news/story",
    ) == "https://publisher.example.com/media/match-preview.webp"


# Cette fonction vérifie qu'un bloc disponible sans article est normalisé en état vide.
def test_empty_team_block_cannot_remain_available(monkeypatch) -> None:
    call_count = 0

    # Ce faux service simule un bloc incohérent sans article pour la seconde équipe.
    def fake_build_team_news_block(**kwargs):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return {
                "name": kwargs["team_name"],
                "query": '"Ararat-Armenia" news',
                "queries": ['"Ararat-Armenia" news'],
                "status": "available",
                "articles_count": 1,
                "articles": [build_recent_article("Ararat-Armenia squad update")],
                "message": None,
            }

        return {
            "name": kwargs["team_name"],
            "query": '"Shamrock Rovers" news',
            "queries": ['"Shamrock Rovers" news'],
            "status": "available",
            "articles_count": 0,
            "articles": [],
            "message": None,
        }

    monkeypatch.setattr(
        "app.services.team_news_context_service.build_team_news_block",
        fake_build_team_news_block,
    )
    monkeypatch.setattr(
        "app.services.team_news_context_service.build_match_news_ai_context",
        lambda **kwargs: {"status": "disabled"},
    )

    response = build_match_news_context_response(
        match_id=1832763682060712,
        match={
            "utc_date": "2026-07-21T16:00:00Z",
            "competition": {"name": "Champions League - Qualification"},
            "home_team": {"name": "Ararat-Armenia (ARM)"},
            "away_team": {"name": "Shamrock Rovers (IRL)"},
        },
    )

    assert response["away_team"]["status"] == "empty"
    assert response["away_team"]["articles_count"] == 0
    assert response["away_team"]["message"]
    assert response["status"] == "partial"


# Schéma de communication :
# test_news_context_pipeline.py -> team_news_context_service.py + news_nlp_service.py -> pipeline News validé
