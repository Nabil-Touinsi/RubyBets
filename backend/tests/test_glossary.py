# Ce fichier regroupe les tests backend du domaine glossary.
# Les sections sources restent identifiables pour préserver la traçabilité et faciliter la maintenance.


# ============================================================================
# Section issue de : backend/tests/test_glossary_enrichment.py
# ============================================================================

# Ce fichier vérifie l'enrichissement et la stabilité du glossaire public RubyBets.

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.glossary import GLOSSARY_ITEMS, router


app = FastAPI()
app.include_router(router)
client = TestClient(app)


# Ce test vérifie que chaque entrée possède un identifiant unique et les champs publics attendus.
def test_glossary_items_have_unique_public_contract():
    slugs = [item["slug"] for item in GLOSSARY_ITEMS]

    assert len(GLOSSARY_ITEMS) == 81
    assert len(slugs) == len(set(slugs))

    for item in GLOSSARY_ITEMS:
        assert set(item) == {"term", "slug", "category", "definition"}
        assert all(isinstance(item[field], str) and item[field].strip() for field in item)


# Ce test vérifie que les principales notions visibles dans la fiche détail match sont exposées.
def test_glossary_contains_match_detail_concepts():
    response = client.get("/api/glossary")
    payload = response.json()
    terms = {item["term"] for item in payload["items"]}

    expected_terms = {
        "Double chance",
        "Buts attendus (xG)",
        "Buts attendus cadrés (xGOT)",
        "Passes décisives attendues (xA)",
        "Possession",
        "Tirs cadrés",
        "Grandes occasions",
        "Précision des passes",
        "Forme récente",
        "Face à face",
        "Composition probable",
        "Composition officielle",
        "Données partielles",
        "Qualité des informations",
        "Score de forme",
        "Couverture des données",
        "Production offensive",
        "Buts attendus subis (xG subi)",
        "Tirs cadrés concédés",
        "Touches dans la surface adverse",
        "Précision des passes longues",
        "Réussite des tacles",
        "Comparaison sur données disponibles",
    }

    assert response.status_code == 200
    assert payload["count"] == 81
    assert expected_terms.issubset(terms)


# Ce test vérifie que la recherche trouve les acronymes et les termes pédagogiques associés.
def test_glossary_search_finds_advanced_statistics():
    response = client.get("/api/glossary", params={"search": "xGOT"})
    payload = response.json()

    slugs = {item["slug"] for item in payload["items"]}

    assert response.status_code == 200
    assert payload["count"] == 2
    assert slugs == {
        "expected-goals-on-target-xgot",
        "expected-goals-on-target-against",
    }


# Ce test vérifie que le filtre de catégorie conserve les notions de composition cohérentes.
def test_glossary_category_filter_returns_lineup_terms():
    response = client.get("/api/glossary", params={"category": "lineup"})
    payload = response.json()
    slugs = {item["slug"] for item in payload["items"]}

    assert response.status_code == 200
    assert payload["count"] == 4
    assert slugs == {
        "probable-lineup",
        "official-lineup",
        "player-absence",
        "doubtful-player",
    }


# Schéma de communication du fichier :
# tests/test_glossary_enrichment.py
#   └── app/api/glossary.py
#         ├── vérifie le contrat public des entrées
#         ├── vérifie les notions de la fiche détail match
#         └── vérifie la recherche et le filtrage

# ============================================================================
# Section issue de : backend/tests/test_glossary_tooltips.py
# ============================================================================

# Ce fichier vérifie les définitions utilisées par les infobulles de la fiche Détail match.

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.glossary import GLOSSARY_ITEMS, router


app = FastAPI()
app.include_router(router)
client = TestClient(app)


# Ce test vérifie que tous les libellés principaux des tableaux possèdent une définition publique.
def test_match_detail_table_labels_are_defined():
    terms = {item["term"] for item in GLOSSARY_ITEMS}
    expected_terms = {
        "Score de forme",
        "Buts marqués",
        "Buts encaissés",
        "Différence de buts",
        "Production offensive",
        "Volume offensif",
        "Précision des tirs",
        "Contrôle du ballon",
        "Solidité défensive",
        "Buts attendus (xG)",
        "Buts attendus cadrés (xGOT)",
        "Tirs",
        "Tirs cadrés",
        "Conversion des tirs",
        "Grandes occasions",
        "Touches dans la surface adverse",
        "Passes décisives attendues (xA)",
        "Buts attendus subis (xG subi)",
        "Buts attendus cadrés subis (xGOT subi)",
        "Tirs concédés",
        "Tirs cadrés concédés",
        "Arrêts du gardien",
        "Dégagements",
        "Interceptions",
        "Erreurs menant à un tir",
        "Erreurs menant à un but",
        "Possession",
        "Précision des passes",
        "Passes dans le dernier tiers",
        "Précision des passes longues",
        "Réussite des tacles",
        "Duels gagnés",
        "Corners",
    }

    assert expected_terms.issubset(terms)


# Ce test vérifie que les sous-libellés et états de couverture sont également expliqués.
def test_match_detail_secondary_labels_are_defined():
    terms = {item["term"] for item in GLOSSARY_ITEMS}
    expected_terms = {
        "Points obtenus / maximum",
        "Total récent",
        "Moyenne par match",
        "Moyenne disponible",
        "Réussites / tentatives",
        "Buts / tirs",
        "Tirs cadrés / tirs",
        "Couverture des données",
        "Données disponibles",
        "Données partielles",
        "Indicateur",
        "Comparaison des signaux",
        "Comparaison sur données disponibles",
        "Qualité des données",
        "Couverture de l'analyse",
    }

    assert expected_terms.issubset(terms)


# Ce test vérifie qu'une recherche textuelle retrouve une définition utilisée par une infobulle.
def test_glossary_search_returns_tooltip_definition():
    response = client.get("/api/glossary", params={"search": "tirs cadrés concédés"})
    payload = response.json()

    slugs = {item["slug"] for item in payload["items"]}

    assert response.status_code == 200
    assert "shots-on-target-conceded" in slugs


# Schéma de communication du fichier :
# tests/test_glossary_tooltips.py
#   └── app/api/glossary.py
#         ├── vérifie les libellés principaux
#         ├── vérifie les sous-libellés
#         └── vérifie la recherche utilisée par le frontend

# Schéma de communication du fichier :
# backend/tests/test_glossary.py
#   ├── importe les routes, services et contrats du domaine testé
#   ├── utilise les fixtures partagées de backend/tests/conftest.py
#   └── est collecté par pytest dans la suite backend complète
