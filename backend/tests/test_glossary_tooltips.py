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
