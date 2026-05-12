# Moteur de scoring explicable — RubyBets

Ce document décrit le fonctionnement du moteur d’analyse V1 de RubyBets.

Il sert de preuve RNCP pour expliquer comment l’application produit des tendances avant-match à partir de données réelles, sans présenter la V1 comme un modèle de Machine Learning entraîné.

---

## 1. Positionnement du moteur V1

La V1 de RubyBets repose sur une première version du moteur d’analyse :

> Scoring explicable basé sur des règles métier et des données réelles.

Le moteur ne doit pas être présenté comme un modèle de Machine Learning entraîné.

RubyBets ne dit pas :

> Le modèle a appris automatiquement à partir de milliers de matchs historiques.

RubyBets dit :

> Le moteur compare des signaux football disponibles avant-match, applique des règles métier simples, puis produit une tendance accompagnée d’un niveau de confiance, d’un niveau de risque et d’une justification.

Le Machine Learning est prévu après le MVP, lorsque le projet disposera d’un dataset historique propre, structuré et labellisé.

---

## 2. Objectif du scoring

Le scoring sert à transformer des données football réelles en lecture analytique exploitable par l’utilisateur.

Il permet de produire :

- une tendance 1X2 ;
- une tendance sur le volume de buts ;
- une tendance BTTS ;
- un niveau de confiance ;
- un niveau de risque ;
- une justification lisible ;
- des limites responsables.

Ces sorties ne sont pas des certitudes. Elles servent uniquement à structurer l’analyse avant-match.

---

## 3. Données utilisées

Le moteur utilise les données disponibles via le backend RubyBets.

Exemples de données exploitées selon disponibilité :

- compétition ;
- équipes domicile et extérieur ;
- date du match ;
- statut du match ;
- classement ;
- points ;
- différence de buts ;
- moyenne de buts ;
- forme générale disponible ;
- fraîcheur des données ;
- disponibilité ou indisponibilité de certains blocs.

La qualité du scoring dépend donc directement de la disponibilité et de la fraîcheur des données.

---

## 4. Marchés couverts dans le MVP

Le MVP couvre uniquement les marchés principaux suivants.

| Marché | Rôle dans RubyBets |
|---|---|
| 1X2 | Identifier une tendance domicile, nul ou extérieur |
| Volume de buts | Estimer une tendance offensive ou prudente |
| BTTS | Estimer si les deux équipes peuvent marquer |
| Confiance | Indiquer la solidité relative du signal |
| Risque | Indiquer le niveau de prudence à conserver |
| Justification | Expliquer pourquoi la tendance est proposée |

Les marchés avancés comme buteurs, corners ou cartons sont exclus du MVP.

---

## 5. Principe général du calcul

Le moteur applique une logique simple :

1. récupérer les données disponibles sur le match ;
2. comparer les signaux entre les deux équipes ;
3. appliquer des règles métier ;
4. produire une tendance ;
5. associer un niveau de confiance ;
6. associer un niveau de risque ;
7. générer une justification compréhensible.

Exemple de logique métier :

```txt
Si une équipe est mieux classée,
si elle possède plus de points,
si sa différence de buts est meilleure,
alors elle obtient un avantage contextuel dans l’analyse.
```

Cette logique reste volontairement explicable pour être défendable dans le cadre du projet RNCP.

---

## 6. Niveaux de confiance

Le niveau de confiance indique la solidité relative du signal.

| Niveau | Interprétation |
|---|---|
| Faible | Les données sont limitées, contradictoires ou insuffisantes |
| Moyen | Plusieurs signaux vont dans le même sens, mais une incertitude reste présente |
| Élevé | Les signaux disponibles sont cohérents et renforcent fortement la tendance |

La confiance ne doit jamais être comprise comme une garantie de résultat.

---

## 7. Niveaux de risque

Le niveau de risque indique le degré de prudence à conserver.

| Niveau | Interprétation |
|---|---|
| Faible | Lecture relativement stable selon les données disponibles |
| Moyen | Lecture exploitable mais avec incertitude réelle |
| Élevé | Signaux fragiles, contradictoires ou données trop partielles |

Le risque est affiché pour éviter une lecture trop affirmative des prédictions.

---

## 8. Sorties API attendues

Le moteur expose ses résultats via les routes backend.

Routes principales concernées :

```txt
GET /api/matches/{match_id}/analysis
GET /api/matches/{match_id}/predictions
POST /api/recommendations/multimatch
```

Les sorties doivent contenir au minimum :

- le marché analysé ;
- le libellé de la tendance ;
- le niveau de confiance ;
- le niveau de risque ;
- la justification ;
- les limites ou messages responsables ;
- la fraîcheur des données lorsque disponible.

---

## 9. Intégration frontend

Les résultats du scoring sont affichés dans l’interface React.

Fichiers concernés :

```txt
frontend/src/components/MatchPredictionsSection.tsx
frontend/src/components/MultiMatchRecommendationSection.tsx
frontend/src/services/api.ts
frontend/src/models/rubybets.ts
```

Le bloc Prédictions affiche désormais les trois marchés MVP sous forme de cartes :

- 1X2 ;
- buts ;
- BTTS.

Chaque carte affiche :

- la recommandation analytique ;
- la confiance ;
- le risque ;
- la justification ;
- un rappel responsable.

---

## 10. Limites assumées

Le moteur V1 présente plusieurs limites assumées :

- il ne s’agit pas d’un modèle ML entraîné ;
- il ne garantit aucun résultat sportif ;
- il dépend de la disponibilité des données réelles ;
- il peut produire des résultats prudents si les données sont partielles ;
- il ne couvre pas les marchés avancés ;
- il ne remplace pas une analyse humaine complète ;
- il ne permet aucune prise de pari réelle.

Ces limites sont importantes pour maintenir un positionnement responsable.

---

## 11. Preuves associées

| Preuve | Emplacement |
|---|---|
| Services backend d’analyse | `backend/app/services/analysis_service.py` |
| Services backend de recommandation | `backend/app/services/recommendation_service.py` |
| Routes API concernées | `backend/app/api/matches.py`, `backend/app/api/recommendations.py` |
| Tests backend | `backend/tests/test_api.py` |
| Intégration frontend | `frontend/src/services/api.ts` |
| Interface prédictions | `frontend/src/components/MatchPredictionsSection.tsx` |
| Interface recommandation | `frontend/src/components/MultiMatchRecommendationSection.tsx` |
| Styles frontend | `frontend/src/App.css` |
| Preuves à archiver | `reports/evidence/api_responses/`, `reports/evidence/screenshots/`, `reports/evidence/build_logs/` |

---

## 12. Validation actuelle

Dernière validation connue :

```txt
npm run build OK
Vite v8.0.10
✓ built in 1.52s
```

Le bloc Prédictions a été amélioré côté interface avec :

- cartes 1X2 / buts / BTTS ;
- confiance ;
- risque ;
- justification ;
- message responsable.

---

Pour le MVP, RubyBets utilise une première version du moteur d’analyse basée sur un scoring explicable. Ce moteur combine des règles métier et des données réelles pour produire des tendances avant-match, un niveau de confiance, un niveau de risque et une justification lisible. Il ne s’agit pas encore d’un modèle de Machine Learning entraîné ; cette évolution viendra après la constitution d’un dataset historique propre.
