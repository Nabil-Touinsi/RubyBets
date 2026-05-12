# Stratégie data — RubyBets

Ce document décrit l’état réel de la chaîne data du MVP RubyBets.

Il sert de preuve RNCP pour expliquer comment les données football sont récupérées, stabilisées, exposées par l’API et utilisées par le moteur de scoring explicable.

---

## 1. Positionnement data du MVP

RubyBets est une application web d’aide à la décision football avant-match.

Le MVP utilise des données réelles issues d’une API football externe.  
Il ne repose pas sur des données fictives pour les routes métier principales.

Dans l’état actuel du projet, RubyBets fonctionne avec :

```txt
API Football-Data.org
+ backend FastAPI
+ cache JSON local
+ moteur de scoring explicable
+ frontend React
```

La base de données relationnelle n’est pas encore active dans le MVP actuel.

Le dossier `database/` existe, mais le fichier `schema.sql` reste à produire ou à compléter dans une phase ultérieure.

---

## 2. État réel actuel

| Élément | Statut actuel | Commentaire |
|---|---|---|
| Source API football | Réalisé | Football-Data.org est utilisée comme source principale du MVP |
| Backend FastAPI | Réalisé | Les routes exposent les compétitions, matchs, analyses, prédictions et recommandations |
| Cache local JSON | Réalisé | Le cache stabilise les appels API et limite les requêtes externes répétées |
| Data freshness | Réalisé | Les routes exposent des informations de fraîcheur des données |
| Base SQL active | Non réalisée | Aucune base relationnelle n’est encore branchée au MVP |
| `database/schema.sql` | À produire | Le schéma doit être ajouté lorsque la couche SQL sera consolidée |
| `backend/sql/queries.sql` | À produire plus tard | À créer uniquement après définition d’un vrai schéma exploitable |
| Dataset historique ML | Non réalisé | Prévu après MVP pour un futur entraînement Machine Learning |

---

## 3. Source de données principale

La source principale actuelle est Football-Data.org.

Elle est utilisée pour récupérer des données football réelles, notamment :

- les compétitions ;
- les matchs à venir ;
- les détails d’un match ;
- les équipes ;
- certains éléments de contexte selon disponibilité ;
- les informations nécessaires au scoring explicable.

Cette source permet de construire un MVP crédible sans inventer de données.

---

## 4. Rôle du cache backend

Le cache backend sert à stabiliser les données récupérées depuis l’API externe.

Il permet de :

- réduire les appels répétés à Football-Data.org ;
- éviter de dépendre uniquement de la disponibilité instantanée de l’API externe ;
- accélérer les tests locaux ;
- conserver temporairement des réponses JSON exploitables ;
- afficher une information de fraîcheur des données.

Le cache est stocké localement dans :

```txt
backend/app/data/cache/
```

Les fichiers de cache sont ignorés par Git afin d’éviter de versionner des données générées localement.

---

## 5. Données utilisées dans le MVP

Les données utilisées dans RubyBets sont organisées en plusieurs niveaux.

| Niveau | Description | Exemple |
|---|---|---|
| Données sources | Données reçues depuis Football-Data.org | compétitions, matchs, équipes, dates |
| Données préparées | Données restructurées pour l’API RubyBets | objets JSON propres, champs homogènes, statuts lisibles |
| Données analytiques | Lecture produite par RubyBets | contexte, résumé, facteurs clés |
| Données de scoring | Résultats calculés par règles métier | 1X2, buts, BTTS, confiance, risque |
| Données responsables | Contenus pédagogiques et limites | glossaire, messages responsables |

---

## 6. Routes API concernées

Les données sont exposées au frontend via les routes FastAPI suivantes :

```txt
GET  /health
GET  /api/competitions
GET  /api/matches
GET  /api/matches/{match_id}
GET  /api/matches/{match_id}/context
GET  /api/matches/{match_id}/analysis
GET  /api/matches/{match_id}/predictions
POST /api/recommendations/multimatch
GET  /api/glossary
GET  /api/responsible-info
GET  /api/data-sources
```

Ces routes permettent au frontend React de consommer les données du MVP sans accéder directement à l’API externe.

---

## 7. Fraîcheur des données

RubyBets expose une information de fraîcheur des données afin de rendre le fonctionnement plus transparent.

Deux formats existent actuellement :

### Routes simples

Les routes simples exposent une fraîcheur directe :

```txt
source
from_cache
updated_at
ttl_minutes
```

Exemples de routes simples :

```txt
/api/competitions
/api/matches
/api/matches/{match_id}
```

### Routes composées

Les routes composées peuvent exposer une fraîcheur composite, car elles combinent plusieurs sources ou plusieurs traitements.

Exemples de routes composées :

```txt
/api/matches/{match_id}/context
/api/matches/{match_id}/analysis
/api/matches/{match_id}/predictions
/api/recommendations/multimatch
```

Cette différence est normale : une analyse ou une prédiction peut dépendre à la fois du match, du classement, du cache et de données complémentaires.

---

## 8. Gestion des données manquantes

Le MVP doit gérer les données manquantes sans bloquer toute l’application.

Principe retenu :

```txt
Une donnée indisponible ne doit pas faire planter tout le parcours utilisateur.
```

Le frontend et le backend doivent pouvoir afficher :

- un bloc disponible ;
- un bloc partiel ;
- un message d’indisponibilité ;
- une justification prudente ;
- un rappel des limites.

Cette logique est cohérente avec le positionnement responsable du projet.

---

## 9. Absence actuelle de base relationnelle

Dans l’état actuel du MVP, RubyBets n’utilise pas encore une base de données relationnelle active.

Cela signifie que :

- les données ne sont pas encore persistées dans PostgreSQL ;
- les prédictions ne sont pas encore stockées durablement en base ;
- les recommandations ne sont pas encore historisées en SQL ;
- les requêtes SQL de preuve ne sont pas encore exécutables ;
- le fichier `backend/sql/queries.sql` doit être produit plus tard, après création du schéma réel.

Cette décision évite de produire une preuve SQL artificielle qui ne correspondrait pas à l’état réel du projet.

---

## 10. Base SQL cible

Une base relationnelle reste prévue dans l’architecture cible.

Elle pourra servir à stocker :

- les compétitions ;
- les équipes ;
- les matchs ;
- les contextes de match ;
- les analyses pré-match ;
- les prédictions ;
- les recommandations multi-matchs ;
- les informations de fraîcheur ;
- les logs utiles au monitoring.

Cette consolidation permettra de renforcer les compétences RNCP C2 et C4.

---

## 11. Compétences RNCP liées à la data

| Compétence | Couverture actuelle |
|---|---|
| C1 | Réalisé / à documenter : récupération de données réelles depuis Football-Data.org |
| C2 | À produire plus tard : requêtes SQL après création du schéma réel |
| C3 | Réalisé partiellement / à formaliser : préparation, homogénéisation, cache, gestion des données manquantes |
| C4 | À produire plus tard : base relationnelle, schéma SQL et note RGPD |
| C5 | Réalisé / à documenter : API REST FastAPI exposant les données au frontend |

---

## 12. Preuves déjà disponibles

| Preuve | Emplacement |
|---|---|
| Client API football | `backend/app/services/football_data_client.py` |
| Cache backend | `backend/app/services/cache_service.py` |
| Services matchs | `backend/app/services/match_service.py` |
| Routes API | `backend/app/api/` |
| Tests backend | `backend/tests/test_api.py` |
| Types frontend | `frontend/src/models/rubybets.ts` |
| Appels API frontend | `frontend/src/services/api.ts` |
| Fichiers cache ignorés par Git | `.gitignore` |
| Build frontend validé | `npm run build OK` |
| Tests backend validés | `pytest` avec 14 tests passés |

---

## 13. Preuves à produire ensuite

| Priorité | Preuve à produire | Emplacement cible |
|---|---|---|
| P1 | Réponses API JSON représentatives | `reports/evidence/api_responses/` |
| P1 | Logs de build et tests | `reports/evidence/build_logs/` |
| P1 | Captures Swagger / OpenAPI | `reports/evidence/screenshots/` |
| P2 | Schéma SQL réel | `database/schema/schema.sql` |
| P2 | Requêtes SQL exécutables | `backend/sql/queries.sql` |
| P2 | Note RGPD MVP | `docs/rgpd_notes.md` |
| P2 | Documentation du monitoring data | `docs/application_monitoring.md` |

---

## 14. Règles de qualité data

RubyBets doit respecter les règles suivantes :

1. ne pas inventer de données pour masquer une absence de source ;
2. conserver une distinction entre données sources, données préparées et données calculées ;
3. exposer une information de fraîcheur lorsque c’est possible ;
4. gérer les données manquantes avec des messages clairs ;
5. éviter toute promesse de résultat sportif ;
6. protéger les clés API dans `.env` et ne jamais les versionner ;
7. documenter toute limite liée à la source externe.

---

## 15. Limites assumées

Le MVP actuel présente les limites suivantes :

- source principale unique ;
- dépendance aux quotas et à la disponibilité de Football-Data.org ;
- absence de base relationnelle active ;
- absence de dataset historique complet ;
- absence de modèle ML entraîné ;
- certaines statistiques peuvent être indisponibles selon les matchs ;
- le cache local ne remplace pas une base de données durable.

Ces limites sont acceptées pour le MVP, mais elles doivent être clairement expliquées en soutenance.

---

## 

Dans la V1, RubyBets utilise une chaîne data courte et maîtrisée : les données football sont récupérées depuis une API réelle, stabilisées par un cache backend, exposées par FastAPI, puis utilisées par un moteur de scoring explicable. La base SQL et le dataset historique ML sont prévus comme étapes de consolidation après le MVP, afin de renforcer la persistance, les requêtes d’analyse et l’entraînement futur d’un modèle.
