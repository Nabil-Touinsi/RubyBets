# Ce fichier expose le glossaire pédagogique utilisé par le frontend RubyBets.

from fastapi import APIRouter, Query


router = APIRouter(prefix="/api/glossary", tags=["Glossary"])


GLOSSARY_ITEMS = [
    {
        "term": "Analyse pré-match",
        "slug": "prematch-analysis",
        "category": "analysis",
        "definition": (
            "Lecture structurée d'un match avant son coup d'envoi, basée sur les données "
            "réellement disponibles."
        ),
    },
    {
        "term": "1X2",
        "slug": "one-x-two",
        "category": "prediction",
        "definition": (
            "Lecture de tendance sur l'issue possible d'un match : équipe à domicile, "
            "match nul ou équipe à l'extérieur."
        ),
    },
    {
        "term": "BTTS",
        "slug": "btts",
        "category": "prediction",
        "definition": (
            "Abréviation de 'Both Teams To Score'. Elle indique si les deux équipes "
            "présentent une tendance à pouvoir marquer dans le même match."
        ),
    },
    {
        "term": "Over / Under",
        "slug": "over-under",
        "category": "prediction",
        "definition": (
            "Lecture du volume probable de buts par rapport à un seuil donné, par exemple "
            "plus ou moins de 2,5 buts."
        ),
    },
    {
        "term": "Niveau de confiance",
        "slug": "confidence-level",
        "category": "interpretation",
        "definition": (
            "Indicateur qui exprime la solidité relative d'une tendance selon les données "
            "disponibles."
        ),
    },
    {
        "term": "Niveau de risque",
        "slug": "risk-level",
        "category": "interpretation",
        "definition": (
            "Indicateur qui exprime le niveau de prudence à conserver face à une tendance "
            "proposée."
        ),
    },
    {
        "term": "Scoring explicable",
        "slug": "explainable-scoring",
        "category": "method",
        "definition": (
            "Méthode de calcul basée sur des règles lisibles, permettant de comprendre "
            "pourquoi une tendance est proposée."
        ),
    },
    {
        "term": "Données réelles",
        "slug": "real-data",
        "category": "data",
        "definition": (
            "Données issues de sources externes vérifiées, utilisées par RubyBets sans "
            "création de données fictives."
        ),
    },
    {
        "term": "Football-Data.org",
        "slug": "football-data",
        "category": "data-source",
        "definition": (
            "Source principale utilisée par RubyBets pour récupérer les compétitions, "
            "matchs, équipes, classements et informations sportives du MVP."
        ),
    },
    {
        "term": "FlashScore",
        "slug": "flashscore",
        "category": "data-source",
        "definition": (
            "Source secondaire utilisée pour enrichir certaines informations match lorsque "
            "les données sont disponibles."
        ),
    },
    {
        "term": "Fraîcheur des données",
        "slug": "data-freshness",
        "category": "data",
        "definition": (
            "Information indiquant la date de mise à jour ou de génération des données "
            "affichées."
        ),
    },
    {
        "term": "Recommandation multi-matchs",
        "slug": "multimatch-recommendation",
        "category": "recommendation",
        "definition": (
            "Sélection structurée de plusieurs tendances cohérentes avec un niveau de risque "
            "choisi par l'utilisateur."
        ),
    },
    {
        "term": "MVP",
        "slug": "mvp",
        "category": "project",
        "definition": (
            "Minimum Viable Product : première version fonctionnelle du produit, limitée aux "
            "fonctionnalités essentielles."
        ),
    },
]


@router.get("")
async def get_glossary(
    category: str | None = Query(None),
    search: str | None = Query(None),
):
    items = GLOSSARY_ITEMS

    if category:
        items = [
            item
            for item in items
            if item["category"].lower() == category.lower()
        ]

    if search:
        searched_text = search.lower()

        items = [
            item
            for item in items
            if searched_text in item["term"].lower()
            or searched_text in item["definition"].lower()
            or searched_text in item["category"].lower()
        ]

    return {
        "count": len(items),
        "filters": {
            "category": category,
            "search": search,
        },
        "items": items,
    }