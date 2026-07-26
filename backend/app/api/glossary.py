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
        "term": "Double chance",
        "slug": "double-chance",
        "category": "prediction",
        "definition": (
            "Lecture qui regroupe deux issues possibles parmi les trois du 1X2 : domicile ou nul, "
            "extérieur ou nul, ou victoire de l'une des deux équipes."
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
            "Source utilisée par RubyBets pour récupérer certaines compétitions, rencontres, "
            "équipes et informations sportives."
        ),
    },
    {
        "term": "FlashScore",
        "slug": "flashscore",
        "category": "data-source",
        "definition": (
            "Source secondaire utilisée pour enrichir certaines informations de match lorsque "
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
    {
        "term": "Buts attendus (xG)",
        "slug": "expected-goals-xg",
        "category": "advanced-stat",
        "definition": (
            "Estimation de la qualité des occasions créées. Plus une occasion paraît favorable, "
            "plus sa valeur xG est élevée."
        ),
    },
    {
        "term": "Buts attendus cadrés (xGOT)",
        "slug": "expected-goals-on-target-xgot",
        "category": "advanced-stat",
        "definition": (
            "Estimation de la dangerosité des tirs cadrés en tenant compte de la qualité et du "
            "placement du tir après la frappe."
        ),
    },
    {
        "term": "Passes décisives attendues (xA)",
        "slug": "expected-assists-xa",
        "category": "advanced-stat",
        "definition": (
            "Estimation de la qualité des passes qui créent une occasion susceptible de devenir "
            "un but."
        ),
    },
    {
        "term": "Possession",
        "slug": "ball-possession",
        "category": "match-stat",
        "definition": (
            "Part du temps pendant laquelle une équipe contrôle le ballon au cours d'une rencontre."
        ),
    },
    {
        "term": "Tirs",
        "slug": "total-shots",
        "category": "match-stat",
        "definition": (
            "Ensemble des tentatives effectuées vers le but, qu'elles soient cadrées, non cadrées "
            "ou contrées."
        ),
    },
    {
        "term": "Tirs cadrés",
        "slug": "shots-on-target",
        "category": "match-stat",
        "definition": (
            "Tirs dirigés vers le cadre et qui auraient pu entrer sans l'intervention du gardien "
            "ou d'un défenseur."
        ),
    },
    {
        "term": "Précision des tirs",
        "slug": "shot-accuracy",
        "category": "match-stat",
        "definition": (
            "Part des tirs tentés qui terminent cadrés. Cet indicateur complète le simple volume "
            "de tirs."
        ),
    },
    {
        "term": "Conversion des tirs",
        "slug": "shot-conversion",
        "category": "match-stat",
        "definition": (
            "Part des tirs transformés en buts. Elle décrit l'efficacité de finition sur les "
            "occasions tentées."
        ),
    },
    {
        "term": "Grandes occasions",
        "slug": "big-chances",
        "category": "match-stat",
        "definition": (
            "Occasions considérées comme particulièrement favorables pour marquer. Leur définition "
            "précise peut varier selon la source."
        ),
    },
    {
        "term": "Précision des passes",
        "slug": "pass-accuracy",
        "category": "match-stat",
        "definition": (
            "Part des passes réussies parmi toutes les passes tentées par une équipe."
        ),
    },
    {
        "term": "Passes dans le dernier tiers",
        "slug": "final-third-passes",
        "category": "match-stat",
        "definition": (
            "Passes réalisées dans la zone offensive la plus proche du but adverse. Elles donnent "
            "un repère sur la capacité à progresser vers une zone dangereuse."
        ),
    },
    {
        "term": "Duels gagnés",
        "slug": "duels-won",
        "category": "match-stat",
        "definition": (
            "Situations de confrontation directe remportées par une équipe pour conserver ou "
            "récupérer le ballon."
        ),
    },
    {
        "term": "Buts marqués",
        "slug": "goals-scored",
        "category": "match-stat",
        "definition": (
            "Nombre de buts inscrits par une équipe sur la période ou l'échantillon affiché."
        ),
    },
    {
        "term": "Buts encaissés",
        "slug": "goals-conceded",
        "category": "match-stat",
        "definition": (
            "Nombre de buts concédés par une équipe sur la période ou l'échantillon affiché."
        ),
    },
    {
        "term": "Forme récente",
        "slug": "recent-form",
        "category": "form",
        "definition": (
            "Lecture des résultats et performances les plus récents d'une équipe avant le match."
        ),
    },
    {
        "term": "Indice de forme",
        "slug": "form-index",
        "category": "form",
        "definition": (
            "Repère synthétique construit à partir des résultats récents pour faciliter la "
            "comparaison de dynamique entre deux équipes."
        ),
    },
    {
        "term": "Série de résultats",
        "slug": "result-streak",
        "category": "form",
        "definition": (
            "Enchaînement récent de victoires, matchs nuls ou défaites d'une équipe."
        ),
    },
    {
        "term": "Face à face",
        "slug": "head-to-head",
        "category": "context",
        "definition": (
            "Historique des confrontations directes disponibles entre les deux équipes."
        ),
    },
    {
        "term": "Avantage domicile",
        "slug": "home-advantage",
        "category": "context",
        "definition": (
            "Effet possible du fait de jouer dans son stade et son environnement habituel. Il "
            "constitue un contexte, jamais une garantie."
        ),
    },
    {
        "term": "Classement",
        "slug": "standings",
        "category": "context",
        "definition": (
            "Position d'une équipe dans sa compétition selon les résultats enregistrés au moment "
            "de la mise à jour."
        ),
    },
    {
        "term": "Composition probable",
        "slug": "probable-lineup",
        "category": "lineup",
        "definition": (
            "Estimation des joueurs susceptibles de débuter le match. Elle peut évoluer jusqu'à "
            "la publication officielle."
        ),
    },
    {
        "term": "Composition officielle",
        "slug": "official-lineup",
        "category": "lineup",
        "definition": (
            "Liste des titulaires et remplaçants publiée officiellement avant le coup d'envoi."
        ),
    },
    {
        "term": "Absence ou indisponibilité",
        "slug": "player-absence",
        "category": "lineup",
        "definition": (
            "Situation d'un joueur annoncé absent, blessé, suspendu ou indisponible selon les "
            "informations fournies par la source."
        ),
    },
    {
        "term": "Joueur incertain",
        "slug": "doubtful-player",
        "category": "lineup",
        "definition": (
            "Joueur dont la participation n'est pas confirmée au moment de la consultation."
        ),
    },
    {
        "term": "Données partielles",
        "slug": "partial-data",
        "category": "data",
        "definition": (
            "État indiquant que certaines informations sont disponibles mais que d'autres manquent "
            "encore pour compléter la lecture."
        ),
    },
    {
        "term": "Qualité des informations",
        "slug": "information-quality",
        "category": "data",
        "definition": (
            "Repère sur la couverture, la fraîcheur et la complétude des informations utilisées. "
            "Il ne mesure pas la certitude du résultat sportif."
        ),
    },
    {
        "term": 'Score de forme',
        "slug": 'form-score',
        "category": 'form',
        "definition": ('Repère qui résume les points obtenus par une équipe sur les matchs récents pris en compte.'),
    },
    {
        "term": 'Points obtenus / maximum',
        "slug": 'points-earned-maximum',
        "category": 'form',
        "definition": ("Comparaison entre les points réellement gagnés et le nombre maximal de points qu'une équipe pouvait obtenir sur la période étudiée."),
    },
    {
        "term": 'Différence de buts',
        "slug": 'goal-difference',
        "category": 'form',
        "definition": ('Écart entre les buts marqués et les buts encaissés sur la période affichée.'),
    },
    {
        "term": 'Total récent',
        "slug": 'recent-total',
        "category": 'form',
        "definition": ('Valeur cumulée uniquement sur les matchs récents utilisés dans la comparaison.'),
    },
    {
        "term": 'Production offensive',
        "slug": 'offensive-production',
        "category": 'match-reading',
        "definition": ("Repère synthétique sur la capacité récente d'une équipe à créer et convertir des situations offensives."),
    },
    {
        "term": 'Volume offensif',
        "slug": 'offensive-volume',
        "category": 'match-reading',
        "definition": ("Quantité d'actions offensives observées, notamment à travers le nombre de tirs tentés."),
    },
    {
        "term": 'Contrôle du ballon',
        "slug": 'ball-control',
        "category": 'match-reading',
        "definition": ("Repère sur la capacité d'une équipe à conserver le ballon et à organiser ses séquences de jeu."),
    },
    {
        "term": 'Solidité défensive',
        "slug": 'defensive-solidity',
        "category": 'match-reading',
        "definition": ("Repère sur la capacité d'une équipe à limiter les buts et les occasions concédées."),
    },
    {
        "term": 'Couverture des données',
        "slug": 'data-coverage',
        "category": 'data',
        "definition": ("Nombre de matchs pour lesquels la statistique affichée est réellement disponible dans l'échantillon analysé."),
    },
    {
        "term": 'Données disponibles',
        "slug": 'available-data',
        "category": 'data',
        "definition": ("État indiquant que les informations nécessaires à cette partie de l'analyse ont été trouvées."),
    },
    {
        "term": 'Comparaison des signaux',
        "slug": 'signal-comparison',
        "category": 'match-reading',
        "definition": ('Mise en parallèle de plusieurs indicateurs observés pour les deux équipes, sans produire de certitude sur le résultat.'),
    },
    {
        "term": 'Résumé analytique',
        "slug": 'analytical-summary',
        "category": 'match-reading',
        "definition": ("Vue courte qui regroupe les principaux indicateurs disponibles avant d'entrer dans le détail."),
    },
    {
        "term": 'Signaux récents',
        "slug": 'recent-signals',
        "category": 'match-reading',
        "definition": ('Tendances observées à partir des derniers matchs terminés réellement disponibles.'),
    },
    {
        "term": 'Analyse offensive',
        "slug": 'offensive-analysis',
        "category": 'match-reading',
        "definition": ("Lecture des indicateurs liés à la création d'occasions, aux tirs et à l'efficacité devant le but."),
    },
    {
        "term": 'Production et efficacité',
        "slug": 'production-efficiency',
        "category": 'match-reading',
        "definition": ("Comparaison entre le volume d'actions offensives créé et la capacité à les transformer en situations dangereuses ou en buts."),
    },
    {
        "term": 'Analyse défensive',
        "slug": 'defensive-analysis',
        "category": 'match-reading',
        "definition": ('Lecture des indicateurs liés aux occasions concédées, aux interventions défensives et à la protection du but.'),
    },
    {
        "term": 'Résistance et pression subie',
        "slug": 'resistance-pressure',
        "category": 'match-reading',
        "definition": ('Lecture de la manière dont une équipe supporte les attaques adverses et limite leurs conséquences.'),
    },
    {
        "term": 'Contrôle du match',
        "slug": 'match-control',
        "category": 'match-reading',
        "definition": ("Lecture de la maîtrise du ballon, des passes, des duels et de l'occupation du terrain."),
    },
    {
        "term": 'Possession, passes et duels',
        "slug": 'possession-passes-duels',
        "category": 'match-reading',
        "definition": ("Ensemble d'indicateurs utilisés pour observer la maîtrise du ballon, la circulation et les confrontations directes."),
    },
    {
        "term": 'Indicateur',
        "slug": 'indicator',
        "category": 'method',
        "definition": ("Mesure utilisée pour décrire un aspect précis de la performance d'une équipe."),
    },
    {
        "term": 'Moyenne par match',
        "slug": 'average-per-match',
        "category": 'method',
        "definition": ("Valeur moyenne calculée sur les matchs pour lesquels l'information est disponible."),
    },
    {
        "term": 'Moyenne disponible',
        "slug": 'available-average',
        "category": 'method',
        "definition": ('Moyenne calculée uniquement à partir des rencontres contenant réellement cette donnée.'),
    },
    {
        "term": 'Réussites / tentatives',
        "slug": 'successes-attempts',
        "category": 'method',
        "definition": ("Rapport entre le nombre d'actions réussies et le nombre total d'actions tentées."),
    },
    {
        "term": 'Buts / tirs',
        "slug": 'goals-shots-ratio',
        "category": 'method',
        "definition": ('Rapport entre les buts marqués et le nombre total de tirs tentés.'),
    },
    {
        "term": 'Tirs cadrés / tirs',
        "slug": 'shots-on-target-shots-ratio',
        "category": 'method',
        "definition": ("Rapport entre les tirs cadrés et l'ensemble des tirs tentés."),
    },
    {
        "term": 'Buts attendus subis (xG subi)',
        "slug": 'expected-goals-against',
        "category": 'advanced-stat',
        "definition": ('Estimation de la qualité des occasions concédées par une équipe à ses adversaires.'),
    },
    {
        "term": 'Buts attendus cadrés subis (xGOT subi)',
        "slug": 'expected-goals-on-target-against',
        "category": 'advanced-stat',
        "definition": ('Estimation de la dangerosité des tirs cadrés concédés après la frappe.'),
    },
    {
        "term": 'Tirs concédés',
        "slug": 'shots-conceded',
        "category": 'match-stat',
        "definition": ("Nombre de tirs tentés par les adversaires contre l'équipe observée."),
    },
    {
        "term": 'Tirs cadrés concédés',
        "slug": 'shots-on-target-conceded',
        "category": 'match-stat',
        "definition": ("Nombre de tirs adverses dirigés vers le cadre contre l'équipe observée."),
    },
    {
        "term": 'Arrêts du gardien',
        "slug": 'goalkeeper-saves',
        "category": 'match-stat',
        "definition": ('Interventions du gardien qui empêchent un tir cadré adverse de devenir un but.'),
    },
    {
        "term": 'Dégagements',
        "slug": 'clearances',
        "category": 'match-stat',
        "definition": ("Actions défensives qui éloignent le ballon d'une zone dangereuse."),
    },
    {
        "term": 'Interceptions',
        "slug": 'interceptions',
        "category": 'match-stat',
        "definition": ('Actions par lesquelles un joueur coupe une passe adverse et récupère ou détourne le ballon.'),
    },
    {
        "term": 'Erreurs menant à un tir',
        "slug": 'errors-leading-to-shot',
        "category": 'match-stat',
        "definition": ("Erreurs directement suivies d'une tentative de tir de l'adversaire."),
    },
    {
        "term": 'Erreurs menant à un but',
        "slug": 'errors-leading-to-goal',
        "category": 'match-stat',
        "definition": ("Erreurs directement suivies d'un but de l'adversaire."),
    },
    {
        "term": 'Touches dans la surface adverse',
        "slug": 'touches-opposition-box',
        "category": 'match-stat',
        "definition": ('Nombre de contrôles ou contacts avec le ballon effectués dans la surface de réparation adverse.'),
    },
    {
        "term": 'Précision des passes longues',
        "slug": 'long-pass-accuracy',
        "category": 'match-stat',
        "definition": ('Part des passes longues réussies parmi toutes les passes longues tentées.'),
    },
    {
        "term": 'Réussite des tacles',
        "slug": 'tackle-success',
        "category": 'match-stat',
        "definition": ('Part des tacles réussis parmi les tentatives de tacle enregistrées.'),
    },
    {
        "term": 'Corners',
        "slug": 'corner-kicks',
        "category": 'match-stat',
        "definition": ('Coups de pied de coin obtenus par une équipe après une déviation adverse derrière la ligne de but.'),
    },
    {
        "term": 'Comparaison sur données disponibles',
        "slug": 'comparison-available-data',
        "category": 'data',
        "definition": ('Comparaison limitée aux statistiques réellement présentes pour les deux équipes.'),
    },
    {
        "term": 'Qualité des données',
        "slug": 'data-quality',
        "category": 'data',
        "definition": ("Repère sur la complétude, la cohérence et la fraîcheur des données utilisées dans l'analyse."),
    },
    {
        "term": "Couverture de l'analyse",
        "slug": 'analysis-coverage',
        "category": 'data',
        "definition": ("Part de l'échantillon récent pour laquelle les statistiques nécessaires à l'analyse ont pu être récupérées."),
    },

]


# Cette route retourne les définitions filtrées par catégorie ou par texte recherché.
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


# Schéma de communication du fichier :
# app/main.py
#   └── app/api/glossary.py
#         ├── expose GET /api/glossary
#         ├── fournit les notions utilisées par ResourcesScreen.tsx
#         └── est vérifié par tests/test_glossary_enrichment.py
