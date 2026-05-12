# Monitoring applicatif MVP — RubyBets

Ce document décrit la stratégie de monitoring simple mise en place pour le MVP RubyBets.

Il sert de preuve RNCP pour la compétence C20 : surveiller une application intégrant un service d’IA ou un moteur d’analyse.

---

## 1. Objectif du monitoring

Le monitoring de RubyBets doit permettre de vérifier que l’application reste utilisable, stable et compréhensible pendant la démonstration et la soutenance.

Dans le MVP, le monitoring reste volontairement simple.  
L’objectif n’est pas de mettre en place une infrastructure lourde de production, mais de prouver une démarche professionnelle de surveillance.

Le monitoring porte sur :

- la disponibilité du backend ;
- les routes API principales ;
- la fraîcheur des données ;
- la stabilité du frontend ;
- les résultats des tests backend ;
- la cohérence du moteur de scoring ;
- les cas d’erreur ou de données partielles.

---

## 2. Périmètre surveillé

RubyBets est une application d’aide à la décision football avant-match.

La V1 repose sur :

```
API Football-Data.org
→ backend FastAPI
→ cache JSON local
→ moteur de scoring explicable
→ frontend React
```

Le monitoring MVP ne concerne pas encore un modèle de Machine Learning entraîné, car ce modèle n’existe pas dans la V1.

La surveillance porte donc sur le moteur d’analyse explicable et sur l’application qui l’expose.

---

## 3. Éléments surveillés dans le MVP

| Élément surveillé | Signal de contrôle | Preuve associée |
|---|---|---|
| Backend FastAPI | Route `/health` disponible | `reports/evidence/api_responses/health.json` |
| API compétitions | Réponse `/api/competitions` exploitable | `reports/evidence/api_responses/competitions.json` |
| API matchs | Réponse `/api/matches` exploitable | `reports/evidence/api_responses/matches.json` |
| API prédictions | Réponse `/predictions` avec méthode, confiance, risque, justification | `reports/evidence/api_responses/match_predictions.json` |
| API recommandation | Réponse `/recommendations/multimatch` avec sélection générée | `reports/evidence/api_responses/multimatch_recommendation.json` |
| Tests backend | `pytest` validé | `reports/evidence/build_logs/backend_tests.txt` |
| Build frontend | `npm run build` validé | `reports/evidence/build_logs/frontend_build.txt` |
| Fraîcheur des données | Présence de `data_freshness` dans les réponses | `match_predictions.json`, `matches.json` |
| Encodage des preuves | Absence de mojibake dans les fichiers JSON importants | Vérification Python `contains_mojibake = False` |

---

## 4. Health check backend

La route `/health` sert de point de contrôle minimal.

### Commande de vérification

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### Résultat attendu

```json
{
  "status": "ok"
}
```

### Preuve archivée

```
reports/evidence/api_responses/health.json
```

### Compétences liées

- C5 : API REST disponible ;
- C20 : surveillance applicative.

---

## 5. Vérification des routes métier

Les routes métier principales doivent répondre avec des données exploitables.

Routes déjà vérifiées :

```
GET  /api/competitions
GET  /api/matches
GET  /api/matches/{match_id}/predictions
POST /api/recommendations/multimatch
```

Preuves déjà archivées :

```
reports/evidence/api_responses/competitions.json
reports/evidence/api_responses/matches.json
reports/evidence/api_responses/match_predictions.json
reports/evidence/api_responses/multimatch_recommendation.json
```

Ces fichiers montrent que l’API retourne des données réelles et des résultats du moteur de scoring explicable.

---

## 6. Surveillance de la fraîcheur des données

RubyBets expose une information de fraîcheur des données dans plusieurs réponses API.

Exemples de champs surveillés :

```
source
from_cache
updated_at
ttl_minutes
match_last_updated
data_freshness
```

Cette information permet de vérifier si la donnée vient :

- de l’API externe ;
- du cache backend ;
- d’une source mise à jour récemment ;
- d’une réponse partielle ou ancienne.

La fraîcheur des données est importante car RubyBets travaille sur des matchs avant-match, donc sensibles au temps.

---

## 7. Surveillance du moteur de scoring

Le moteur de scoring V1 doit produire des résultats interprétables.

Les éléments surveillés sont :

- la méthode utilisée ;
- la présence des trois marchés MVP ;
- la présence d’un niveau de confiance ;
- la présence d’un niveau de risque ;
- la présence d’une justification ;
- la présence de limites responsables.

Exemple validé dans la preuve :

```
method: rules_based_scoring_v1
markets: 1X2 / GOALS / BTTS
confidence: low / medium
risk: high / medium
contains_mojibake: False
```

Preuve associée :

```
reports/evidence/api_responses/match_predictions.json
```

---

## 8. Surveillance de la recommandation multi-matchs

La recommandation multi-matchs doit retourner une sélection cohérente selon le niveau de risque demandé.

Éléments surveillés :

- méthode utilisée ;
- nombre de matchs disponibles ;
- nombre de matchs sélectionnés ;
- niveau de risque demandé ;
- présence de recommandations ;
- absence de problème d’encodage.

Exemple validé :

```
method: rules_based_multimatch_selection_v1
available_matches_count: 22
selected_count: 3
risk_level: medium
contains_mojibake: False
```

Preuve associée :

```
reports/evidence/api_responses/multimatch_recommendation.json
```

---

## 9. Tests backend

Les tests backend permettent de vérifier que les routes principales restent stables.

### Commande utilisée

```powershell
cd C:\dev_classe\RNCP\RubyBets\backend
python -m pytest
```

### Résultat validé

```
14 passed in 1.55s
```

### Preuve archivée

```
reports/evidence/build_logs/backend_tests.txt
```

### Compétences liées

- C5 : stabilité des routes API ;
- C9 : exposition du moteur d’analyse ;
- C12 : tests ;
- C18 : validation technique.

---

## 10. Build frontend

Le build frontend permet de vérifier que l’interface React + TypeScript compile correctement.

### Commande utilisée

```powershell
cd C:\dev_classe\RNCP\RubyBets\frontend
npm run build
```

### Résultat validé

```
vite v8.0.10
✓ built in 1.52s
```

### Preuve archivée

```
reports/evidence/build_logs/frontend_build.txt
```

### Compétences liées

- C10 : intégration API dans l’application ;
- C17 : interface ;
- C18 : validation par build.

---

## 11. Gestion des erreurs et cas partiels

RubyBets doit rester utilisable même lorsqu’une donnée est absente ou partielle.

Principe retenu :

```
Un bloc indisponible ne doit pas bloquer tout le parcours utilisateur.
```

Ce principe concerne notamment :

- le détail d’un match ;
- le contexte ;
- l’analyse ;
- les prédictions ;
- les recommandations ;
- la fraîcheur des données.

Cette logique a déjà été renforcée côté frontend avec un chargement plus robuste des blocs de la fiche match.

Cette correction sera documentée dans :

```
docs/incident_log.md
```

---

## 12. Organisation des preuves de monitoring

Les preuves de monitoring sont rangées dans :

```
reports/evidence/
```

Structure actuelle :

```
reports/evidence/
├── api_responses/
├── build_logs/
├── screenshots/
├── monitoring/
└── incident/
```

Les preuves déjà présentes sont :

```
reports/evidence/api_responses/health.json
reports/evidence/api_responses/competitions.json
reports/evidence/api_responses/matches.json
reports/evidence/api_responses/match_predictions.json
reports/evidence/api_responses/multimatch_recommendation.json
reports/evidence/build_logs/backend_tests.txt
reports/evidence/build_logs/frontend_build.txt
```

---

## 13. Limites du monitoring MVP

Le monitoring actuel est adapté à un MVP local et à une soutenance.

Limites assumées :

- pas encore de dashboard Grafana ou Prometheus ;
- pas encore d’alertes automatiques ;
- pas encore de monitoring ML avancé ;
- pas encore de suivi statistique de dérive modèle ;
- pas encore de logs centralisés en production.

Ces limites sont cohérentes avec l’état actuel du projet.

Une solution plus avancée pourra être envisagée après le MVP.

---

## 14. Évolutions possibles

Après le MVP, RubyBets pourra ajouter :

- un fichier de logs applicatifs structuré ;
- un suivi du temps de réponse des routes ;
- un suivi du nombre d’erreurs API ;
- un monitoring de fraîcheur des données ;
- un tableau de bord simple ;
- un suivi des prédictions après résultat réel ;
- un monitoring ML si un modèle entraîné est ajouté.

---

## 15. Compétences RNCP couvertes

| Compétence | Couverture dans RubyBets |
|---|---|
| C5 | API REST surveillée via `/health` et réponses JSON |
| C9 | Routes exposant le scoring vérifiées |
| C10 | Réponses API consommables par le frontend |
| C12 | Tests backend et build frontend conservés |
| C18 | Validation technique reproductible |
| C20 | Monitoring MVP documenté et preuves archivées |
| C21 | Incident technique à documenter dans `incident_log.md` |

---

##

Dans le MVP, RubyBets met en place un monitoring simple mais vérifiable : le backend est contrôlé avec une route `/health`, les principales routes API sont archivées sous forme de réponses JSON, les tests backend et le build frontend sont conservés dans le dossier `reports/evidence/`, et la fraîcheur des données est exposée dans les réponses. Cette approche permet de surveiller l’application sans surcomplexifier le MVP.
