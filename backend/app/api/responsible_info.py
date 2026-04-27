# Ce fichier expose les messages responsables et limites d'utilisation de RubyBets.

from fastapi import APIRouter


router = APIRouter(prefix="/api/responsible-info", tags=["Responsible information"])


RESPONSIBLE_INFO_ITEMS = [
    {
        "type": "positioning",
        "priority": "high",
        "title": "RubyBets est une aide à la décision",
        "content": (
            "RubyBets aide à analyser des matchs de football avant leur coup d'envoi. "
            "L'application ne permet pas de parier et ne remplace pas le jugement de l'utilisateur."
        ),
        "display_zone": "responsible_info_page",
        "is_active": True,
    },
    {
        "type": "limitation",
        "priority": "high",
        "title": "Aucune garantie de résultat",
        "content": (
            "Les analyses, prédictions et recommandations affichées sont des tendances "
            "calculées à partir de données disponibles. Elles ne garantissent jamais le résultat final d'un match."
        ),
        "display_zone": "responsible_info_page",
        "is_active": True,
    },
    {
        "type": "data",
        "priority": "high",
        "title": "Données réelles mais parfois incomplètes",
        "content": (
            "RubyBets utilise des données réelles issues de sources externes. Certaines informations "
            "peuvent être absentes, incomplètes ou mises à jour avec un délai."
        ),
        "display_zone": "responsible_info_page",
        "is_active": True,
    },
    {
        "type": "scope",
        "priority": "medium",
        "title": "Analyse avant-match uniquement",
        "content": (
            "La version MVP de RubyBets se concentre uniquement sur l'analyse avant-match. "
            "L'application ne réalise pas d'analyse en direct pendant les rencontres."
        ),
        "display_zone": "responsible_info_page",
        "is_active": True,
    },
    {
        "type": "method",
        "priority": "medium",
        "title": "Moteur explicable V1",
        "content": (
            "Le moteur actuel repose sur un scoring explicable basé sur des règles métier "
            "et des données réelles. Il ne s'agit pas encore d'un modèle de machine learning entraîné."
        ),
        "display_zone": "responsible_info_page",
        "is_active": True,
    },
    {
        "type": "responsible_use",
        "priority": "high",
        "title": "Usage responsable",
        "content": (
            "Les informations proposées doivent être utilisées comme un support d'analyse. "
            "Elles ne doivent pas être interprétées comme une incitation au pari."
        ),
        "display_zone": "responsible_info_page",
        "is_active": True,
    },
]


@router.get("")
async def get_responsible_info():
    active_items = [
        item
        for item in RESPONSIBLE_INFO_ITEMS
        if item["is_active"]
    ]

    return {
        "count": len(active_items),
        "items": active_items,
        "summary": {
            "product_positioning": "Application d'aide à la décision football avant-match.",
            "real_betting_enabled": False,
            "live_analysis_enabled": False,
            "uses_real_data": True,
            "guarantees_result": False,
        },
    }