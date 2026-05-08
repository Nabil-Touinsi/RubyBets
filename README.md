# README — État du projet RubyBets

## 1. Présentation générale

RubyBets est une application web de fin d’étude Data & IA conçue comme un outil d’aide à la décision football avant-match.

Le projet ne permet pas de parier directement et ne doit pas être présenté comme un bookmaker. Son objectif est de centraliser des données football réelles, de les analyser et de produire des tendances explicables afin d’aider l’utilisateur à mieux comprendre un match avant son coup d’envoi.

Le projet est aligné avec le référentiel RNCP Développeur IA niveau 6.

Positionnement à retenir :

```
RubyBets ne permet pas de parier.
RubyBets n’est pas un bookmaker.
RubyBets utilise des données réelles, récentes et exploitables.
RubyBets propose une analyse explicable avant-match.
La V1 n’est pas un modèle Machine Learning entraîné.
```

Formulation officielle à utiliser :

```
Première version du moteur d’analyse : scoring explicable basé sur règles métier et données réelles.
```

---

## 2. Cadrage fonctionnel et RNCP

La première phase du projet a consisté à formaliser toute la base documentaire et fonctionnelle de RubyBets.

Les documents produits ou cadrés couvrent notamment :

- le plan fonctionnel global ;
- le cadrage produit ;
- la définition du MVP ;
- les parcours utilisateur ;
- l’arborescence des écrans ;
- le contenu détaillé des écrans ;
- le zoning fonctionnel ;
- la direction UI ;
- la validation des maquettes ;
- le découpage technique ;
- le choix de stack technique ;
- l’architecture globale ;
- le modèle de données ;
- la spécification API ;
- la stratégie data ;
- le cadrage IA et logique prédictive ;
- le plan de développement ;
- la stratégie de tests ;
- la structure du support de soutenance.

Objectif de cette phase : construire un projet défendable comme un vrai produit Data & IA, et non comme une simple démonstration technique.

---

## 3. Choix techniques validés

La stack retenue pour le MVP est la suivante :

```
Frontend : React + TypeScript + Vite
Backend : Python + FastAPI
Source data principale : Football-Data.org
Tests : pytest
CI/CD : GitHub Actions
Versioning : Git + tags GitHub
```

La base PostgreSQL reste prévue dans l’architecture cible. Dans l’état actuel du projet, le dossier `database` existe, mais le fichier `schema.sql` est encore vide.

Le projet fonctionne actuellement principalement avec :

```
API Football-Data.org
+ cache local JSON
+ backend FastAPI
+ frontend React
```

---

## 4. Mise en place du backend

Le backend a été structuré proprement avec une séparation entre routes API, services métier, configuration et tests.

Structure principale :

```
backend/
├── app/
│   ├── api/
│   ├── core/
│   ├── data/cache/
│   └── services/
└── tests/
```

Routes backend disponibles dans le MVP actuel :

```
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

Services backend principaux :

```
cache_service.py
football_data_client.py
match_service.py
analysis_service.py
recommendation_service.py
```

Ces services permettent de séparer la récupération des données, la logique métier, l’analyse, la recommandation et le cache.

---

## 5. Branchement des données réelles

Le projet utilise actuellement Football-Data.org comme source principale de données réelles.

Les données branchées couvrent progressivement :

- les compétitions ;
- les matchs à venir ;
- le détail d’un match ;
- le contexte d’un match ;
- les classements ;
- l’analyse pré-match ;
- les prédictions principales ;
- la recommandation multi-matchs.

Le principe retenu est de ne pas utiliser de données fictives pour les routes métier principales.

---

## 6. Moteur d’analyse actuel

Le moteur actuel de RubyBets n’est pas encore un modèle de Machine Learning entraîné sur un historique de matchs.

Il ne fonctionne donc pas encore selon la logique suivante :

```
Je prends 10 000 anciens matchs
→ j’entraîne un modèle ML
→ le modèle apprend automatiquement des tendances
→ il prédit les futurs matchs
```

À la place, la V1 fonctionne avec une logique explicable :

```
Je récupère des données réelles sur un match
→ je compare les équipes
→ j’applique des règles métier
→ je calcule une tendance
→ j’explique pourquoi cette tendance ressort
```

Le moteur repose actuellement sur deux méthodes :

```
rules_based_scoring_v1
rules_based_multimatch_selection_v1
```

### 6.1 rules_based_scoring_v1

`rules_based_scoring_v1` est la méthode utilisée pour analyser un seul match.

Pour un match donné, RubyBets regarde par exemple :

```
classement de l’équipe domicile
classement de l’équipe extérieure
écart de points
différence de buts
moyenne de buts
forme générale disponible
```

Ensuite, le moteur applique des règles métier simples.

Exemple de logique :

```
Si l’équipe A est mieux classée,
si elle a plus de points,
si sa différence de buts est meilleure,
alors elle possède un avantage contextuel.
```

Le moteur peut alors produire une tendance du type :

```
Tendance favorable à l’équipe domicile
Confiance : moyenne
Risque : moyen
Justification : l’équipe possède un avantage au classement, en points et en différence de buts.
```

Cette sortie n’est pas une certitude. C’est une lecture analytique basée sur des règles métier et des données réelles.

### 6.2 rules_based_multimatch_selection_v1

`rules_based_multimatch_selection_v1` est la méthode utilisée pour générer une sélection recommandée sur plusieurs matchs.

Elle ne prédit pas directement un seul match. Elle sélectionne plusieurs recommandations déjà calculées en fonction du niveau de risque demandé par l’utilisateur.

Exemple :

```
L’utilisateur demande 3 matchs avec un niveau de risque moyen.
```

RubyBets va alors regarder plusieurs matchs disponibles et retenir ceux qui correspondent le mieux aux critères :

```
confiance compatible ;
risque compatible ;
données disponibles ;
recommandation lisible ;
cohérence globale de la sélection.
```

Le résultat est une sélection multi-matchs structurée, sans prise de pari réelle.

---

## 7. Sorties actuelles du moteur

Le moteur actuel produit :

- une tendance 1X2 ;
- une tendance sur le volume de buts ;
- une tendance BTTS ;
- un niveau de confiance ;
- un niveau de risque ;
- une justification lisible ;
- des limites responsables.

Cette logique est cohérente avec une première version explicable et défendable en soutenance.

Phrase à retenir pour l’oral :

```
Dans cette première version, RubyBets intègre un moteur de scoring explicable basé sur des règles métier et des données réelles. Le Machine Learning sera intégré dans une phase ultérieure, après constitution d’un dataset historique propre.
```

---

## 8. Frontend React

Le frontend a été initialisé avec React, TypeScript et Vite.

Plusieurs composants ont été créés ou séparés afin d’éviter un fichier `App.tsx` trop lourd.

Composants principaux :

```
CompetitionsSection.tsx
MatchesSection.tsx
MatchDetailsSection.tsx
MatchContextSection.tsx
MatchAnalysisSection.tsx
MatchPredictionsSection.tsx
MultiMatchRecommendationSection.tsx
GlossarySection.tsx
ResponsibleInfoSection.tsx
StatusPanel.tsx
```

Le frontend consomme les routes backend via :

```
src/services/api.ts
```

Les types TypeScript sont centralisés dans :

```
src/models/rubybets.ts
```

L’objectif est d’avoir une interface branchée sur les vraies réponses API, avec une structure maintenable et cohérente avec les écrans MVP.

---

## 9. Refactorisation et qualité du code

Plusieurs passes de nettoyage ont été réalisées :

- extraction de composants frontend ;
- extraction de services backend ;
- centralisation de constantes ;
- nettoyage des fichiers Python suivis par Git ;
- amélioration du `.gitignore` ;
- structuration des tests backend ;
- ajout de commentaires en haut des fichiers ;
- ajout de commentaires avant les fonctions importantes ;
- ajout de schémas de communication en fin de fichier lorsque nécessaire.

---

## 10. Tests et intégration continue

Une logique de validation professionnelle a été mise en place.

Éléments validés :

```
pytest côté backend
npm run build côté frontend
GitHub Actions
```

État stable connu :

```
Backend tests : OK
Frontend build : OK
GitHub Actions : vert
```

Dernier résultat confirmé côté backend :

```
14 passed
```

---

## 11. Tags GitHub créés

Les versions stables du projet ont été taguées progressivement :

```
rubybets-v0.1
rubybets-v0.2-refactor
rubybets-v0.3-backend-refactor
rubybets-v0.4-backend-tests
rubybets-v0.5-backend-ci
rubybets-v0.6-frontend-ci
rubybets-v0.7-backend-data-cache
```

Dernier tag validé :

```
rubybets-v0.7-backend-data-cache
```

Dernier commit associé :

```
Add reusable cache layer for football data
```

---

## 12. Dernière phase réalisée : cache backend et data_freshness

La dernière grande phase a porté sur la stabilisation du cache backend et de la fraîcheur des données.

Routes vérifiées :

```
GET  /api/competitions                   OK
GET  /api/matches                        OK
GET  /api/matches/{match_id}             OK
GET  /api/matches/{match_id}/context     OK
GET  /api/matches/{match_id}/analysis    OK
GET  /api/matches/{match_id}/predictions OK
POST /api/recommendations/multimatch     OK
```

Comportement vérifié :

```
Premier appel API réel : from_cache = false
Deuxième appel API : from_cache = true
```

Le cache local fonctionne et permet de limiter les appels répétés vers Football-Data.org.

---

## 13. Gestion des fichiers cache

Les fichiers JSON de cache sont générés localement dans :

```
backend/app/data/cache/
```

Exemples de fichiers générés :

```
competitions.json
match_538126.json
matches_pl_scheduled_all_start_dates_all_end_dates.json
standings_pl.json
```

Ces fichiers sont ignorés par Git.

Validation effectuée :

```
git status --short : vide
fichiers JSON du cache visibles uniquement en fichiers ignorés
```

Conclusion : les caches réels ne polluent pas le dépôt Git.

---

## 14. Décision sur data_freshness

Toutes les routes prioritaires exposent une information de fraîcheur des données.

Une différence de structure a été observée entre les routes simples et les routes composées.

Décision retenue :

```
Routes simples → data_freshness direct
Routes combinées → data_freshness composite
```

Routes simples :

```
/api/competitions
/api/matches
/api/matches/{match_id}
```

Elles exposent une fraîcheur directe :

```
source
from_cache
updated_at
ttl_minutes
```

Routes combinées :

```
/api/matches/{match_id}/context
/api/matches/{match_id}/analysis
/api/matches/{match_id}/predictions
/api/recommendations/multimatch
```

Elles exposent une fraîcheur composite, car elles combinent plusieurs données :

```
match_cache
standings_cache
matches_cache
```

Cette différence n’est pas considérée comme un bug. Elle est justifiable techniquement et professionnellement.

---

## 15. Diagnostic encodage

Lors des tests PowerShell, certains accents apparaissaient sous forme cassée :

```
prÃ©dictions
donnÃ©es
Ã©quipes
```

Un test Python direct sur la réponse HTTP a confirmé que le backend renvoie bien du UTF-8 correct.

Résultat du diagnostic :

```text
contains_mojibake = False
```

Conclusion : le problème venait uniquement de l’affichage PowerShell, pas du backend.

Aucune correction côté code n’est nécessaire pour l’encodage.

---

## 16. État actuel du projet

État stable actuel :

```text
Backend stable
Frontend branché
Cache stable
Tests backend OK
Build frontend OK
Git propre au dernier contrôle
Tag v0.7 créé
Données réelles Football-Data.org utilisées
Pas de ML entraîné annoncé
Moteur explicable basé sur règles métier
```

Le socle data backend est maintenant suffisamment stable pour passer à la vérification côté frontend.

---

## 17. Prochaine étape logique

La prochaine micro-phase recommandée est :

```
Vérifier que le frontend consomme correctement les réponses backend actuelles,
notamment data_freshness, confidence, risk, predictions et recommendations.
```

Avant toute nouvelle fonctionnalité IA ou ML, la priorité reste de vérifier que le frontend affiche correctement les données déjà stabilisées côté backend.

---

## 18. Résumé final

RubyBets dispose aujourd’hui d’un socle MVP solide :

- une documentation produit et RNCP structurée ;
- un backend FastAPI fonctionnel ;
- des routes API métier stables ;
- une source réelle Football-Data.org ;
- un cache backend local contrôlé ;
- un moteur de scoring explicable ;
- une recommandation multi-matchs basée sur règles ;
- un frontend React déjà branché ;
- des tests backend validés ;
- une CI GitHub verte ;
- un versioning clair par tags.

La suite du travail doit rester progressive : vérifier l’intégration frontend, corriger les éventuels écarts d’affichage, puis seulement ensuite envisager les améliorations de prédiction ou les futures briques IA.
