# Documentation API — RubyBets

Ce document présente les routes API actuellement disponibles dans le MVP RubyBets.

Il sert de preuve RNCP pour montrer que le backend FastAPI expose des données football réelles, des analyses avant-match, des prédictions explicables et une recommandation multi-matchs consommables par le frontend React.

---

## 1. Rôle de l’API dans RubyBets

L’API RubyBets sert d’intermédiaire entre :

```
Football-Data.org
→ backend FastAPI
→ moteur de scoring explicable
→ frontend React
```

Le frontend ne contacte pas directement la source externe.  
Il consomme les réponses préparées par le backend RubyBets.

Cette séparation permet de :

- centraliser les appels vers la source football ;
- stabiliser les données grâce au cache backend ;
- exposer des routes lisibles pour le frontend ;
- gérer les erreurs et les cas partiels ;
- afficher la fraîcheur des données ;
- conserver des preuves API exploitables en soutenance.

---

## 2. Positionnement responsable

RubyBets est une application d’aide à la décision football avant-match.

L’API ne permet pas de parier.  
Elle ne déclenche aucune transaction.  
Elle ne se connecte à aucun bookmaker.  
Elle expose uniquement des données, analyses, tendances et recommandations analytiques.

La V1 repose sur un moteur de scoring explicable basé sur règles métier et données réelles.

---

## 3. Routes API disponibles

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | Vérifier que le backend répond |
| GET | `/api/competitions` | Récupérer les compétitions suivies |
| GET | `/api/matches` | Récupérer les matchs à venir |
| GET | `/api/matches/{match_id}` | Récupérer le détail d’un match |
| GET | `/api/matches/{match_id}/context` | Récupérer le contexte d’un match |
| GET | `/api/matches/{match_id}/analysis` | Récupérer l’analyse pré-match |
| GET | `/api/matches/{match_id}/predictions` | Récupérer les prédictions 1X2, buts et BTTS |
| POST | `/api/recommendations/multimatch` | Générer une recommandation multi-matchs |
| GET | `/api/glossary` | Récupérer le glossaire pédagogique |
| GET | `/api/responsible-info` | Récupérer les informations responsables |
| GET | `/api/data-sources` | Décrire les sources de données utilisées |

---

## 4. Route `/health`

### Méthode

```
GET /health
```

### Rôle

Cette route permet de vérifier rapidement que le backend FastAPI est disponible.

Elle sert aussi de preuve simple pour le monitoring applicatif MVP.

### Exemple de réponse archivée

```json
{
  "status": "ok"
}
```

### Preuve locale

```
reports/evidence/api_responses/health.json
```

### Compétences RNCP renforcées

- C5 : API REST disponible ;
- C20 : surveillance applicative simple via health check.

---

## 5. Route `/api/competitions`

### Méthode

```
GET /api/competitions
```

### Rôle

Cette route retourne les compétitions football suivies dans le MVP.

Elle permet au frontend d’afficher les ligues disponibles et de structurer la navigation utilisateur.

### Exemple de contenu validé

La réponse archivée contient notamment :

```
count: 6
Premier League
UEFA Champions League
Ligue 1
```

### Preuve locale

```
reports/evidence/api_responses/competitions.json
```

### Compétences RNCP renforcées

- C1 : récupération de données réelles ;
- C5 : exposition API REST ;
- C10 : données consommables par le frontend.

---

## 6. Route `/api/matches`

### Méthode

```
GET /api/matches
```

### Rôle

Cette route retourne les matchs à venir selon les filtres disponibles.

Elle constitue le point d’entrée principal du parcours utilisateur : l’utilisateur choisit un match à analyser.

### Exemple de contenu validé

La preuve actuelle montre :

```
source: football-data.org
competition_code: PL
count: 22
status: TIMED
```

### Preuve locale

```
reports/evidence/api_responses/matches.json
```

### Compétences RNCP renforcées

- C1 : collecte de données réelles ;
- C3 : préparation des données pour l’application ;
- C5 : API REST exploitable ;
- C17 : alimentation de l’interface de liste des matchs.

---

## 7. Route `/api/matches/{match_id}`

### Méthode

```
GET /api/matches/{match_id}
```

### Rôle

Cette route retourne les informations détaillées d’un match précis :

- compétition ;
- équipes ;
- date ;
- statut ;
- score si disponible ;
- arbitres si disponibles ;
- fraîcheur des données.

### Usage frontend

Cette route alimente la fiche détail match.

### Preuve à produire

```
reports/evidence/api_responses/match_details.json
```

### Compétences RNCP renforcées

- C5 : API REST ;
- C10 : intégration front/back ;
- C17 : fiche match côté interface.

---

## 8. Route `/api/matches/{match_id}/context`

### Méthode

```
GET /api/matches/{match_id}/context
```

### Rôle

Cette route retourne les éléments de contexte disponibles pour un match.

Elle peut contenir des informations sur :

- classement ;
- dynamique ;
- données disponibles ;
- qualité ou limites de la donnée ;
- fraîcheur.

### Usage frontend

Cette route alimente le bloc contexte match.

### Preuve à produire

```
reports/evidence/api_responses/match_context.json
```

### Compétences RNCP renforcées

- C3 : préparation des données ;
- C5 : exposition API ;
- C10 : intégration dans l’application ;
- C17 : affichage contextualisé.

---

## 9. Route `/api/matches/{match_id}/analysis`

### Méthode

```
GET /api/matches/{match_id}/analysis
```

### Rôle

Cette route retourne une analyse pré-match explicable.

Elle sert à transformer les données disponibles en lecture compréhensible pour l’utilisateur.

### Usage frontend

Cette route alimente le bloc Analyse pré-match.

### Preuve à produire

```
reports/evidence/api_responses/match_analysis.json
```

### Compétences RNCP renforcées

- C8 : logique d’analyse ;
- C9 : API exposant le service d’analyse ;
- C10 : intégration API dans l’application ;
- C11 : interprétation des résultats.

---

## 10. Route `/api/matches/{match_id}/predictions`

### Méthode

```
GET /api/matches/{match_id}/predictions
```

### Rôle

Cette route retourne les prédictions principales du MVP :

- 1X2 ;
- volume de buts ;
- BTTS ;
- confiance ;
- risque ;
- justification ;
- limites ;
- fraîcheur des données.

### Exemple de contenu validé

La preuve actuelle contient :

```
method: rules_based_scoring_v1
market: 1X2
market: GOALS
market: BTTS
confidence: low / medium
risk: high / medium
data_freshness: présent
contains_mojibake: False
```

### Preuve locale

```
reports/evidence/api_responses/match_predictions.json
```

### Compétences RNCP renforcées

- C8 : paramétrage du moteur de scoring ;
- C9 : API exposant le scoring ;
- C10 : intégration API dans le frontend ;
- C11 : interprétation avec confiance, risque et justification ;
- C17 : affichage dans le bloc Prédictions.

---

## 11. Route `/api/recommendations/multimatch`

### Méthode

```
POST /api/recommendations/multimatch
```

### Payload utilisé pour la preuve

```json
{
  "match_count": 3,
  "risk_level": "medium"
}
```

### Rôle

Cette route génère une recommandation multi-matchs selon :

- le nombre de matchs demandé ;
- le niveau de risque choisi ;
- les données disponibles ;
- les prédictions calculées par le moteur de scoring.

### Exemple de contenu validé

La preuve actuelle contient :

```
method: rules_based_multimatch_selection_v1
available_matches_count: 22
selected_count: 3
risk_level: medium
contains_mojibake: False
```

### Preuve locale

```
reports/evidence/api_responses/multimatch_recommendation.json
```

### Compétences RNCP renforcées

- C9 : API exposant le moteur de recommandation ;
- C10 : intégration dans l’application ;
- C11 : interprétation des résultats ;
- C17 : parcours de recommandation MVP.

---

## 12. Route `/api/glossary`

### Méthode

```
GET /api/glossary
```

### Rôle

Cette route retourne les définitions pédagogiques utiles à l’utilisateur.

Elle permet d’expliquer les termes métier comme :

- 1X2 ;
- BTTS ;
- over / under ;
- confiance ;
- risque ;
- scoring ;
- recommandation analytique.

### Preuve à produire

```
reports/evidence/api_responses/glossary.json
```

### Compétences RNCP renforcées

- C14 : compréhension du besoin utilisateur ;
- C17 : interface pédagogique ;
- C6 : usage responsable et explicabilité.

---

## 13. Route `/api/responsible-info`

### Méthode

```
GET /api/responsible-info
```

### Rôle

Cette route retourne les messages responsables affichés dans l’application.

Elle rappelle notamment que :

- RubyBets n’est pas un bookmaker ;
- aucun pari réel n’est possible ;
- les prédictions ne sont pas des certitudes ;
- l’utilisateur doit interpréter les résultats avec prudence.

### Preuve à produire

```
reports/evidence/api_responses/responsible_info.json
```

### Compétences RNCP renforcées

- C6 : usage responsable ;
- C14 : cadrage du besoin ;
- C17 : affichage responsable dans l’interface.

---

## 14. Route `/api/data-sources`

### Méthode

```
GET /api/data-sources
```

### Rôle

Cette route décrit les sources de données utilisées par RubyBets.

Elle contribue à la transparence data du projet.

### Preuve à produire

```
reports/evidence/api_responses/data_sources.json
```

### Compétences RNCP renforcées

- C1 : source de données ;
- C3 : stratégie de préparation ;
- C5 : transparence via API ;
- C20 : suivi de la disponibilité des sources.

---

## 15. Preuves API déjà archivées

| Preuve | Fichier |
|---|---|
| Health check | `reports/evidence/api_responses/health.json` |
| Compétitions | `reports/evidence/api_responses/competitions.json` |
| Matchs | `reports/evidence/api_responses/matches.json` |
| Prédictions match | `reports/evidence/api_responses/match_predictions.json` |
| Recommandation multi-matchs | `reports/evidence/api_responses/multimatch_recommendation.json` |

---

## 16. Preuves API à archiver ensuite

| Preuve | Fichier cible |
|---|---|
| Détail match | `reports/evidence/api_responses/match_details.json` |
| Contexte match | `reports/evidence/api_responses/match_context.json` |
| Analyse pré-match | `reports/evidence/api_responses/match_analysis.json` |
| Glossaire | `reports/evidence/api_responses/glossary.json` |
| Informations responsables | `reports/evidence/api_responses/responsible_info.json` |
| Sources de données | `reports/evidence/api_responses/data_sources.json` |

---

## 17. Commandes utiles

### Lancer le backend

```powershell
cd C:\dev_classe\RNCP\RubyBets\backend
python -m uvicorn app.main:app --reload
```

### Archiver `/health`

```powershell
cd C:\dev_classe\RNCP\RubyBets

Invoke-RestMethod http://127.0.0.1:8000/health |
ConvertTo-Json -Depth 10 |
Set-Content -Encoding UTF8 reports\evidence\api_responses\health.json
```

### Archiver `/api/competitions`

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/competitions |
ConvertTo-Json -Depth 10 |
Set-Content -Encoding UTF8 reports\evidence\api_responses\competitions.json
```

### Archiver `/api/matches`

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/matches |
ConvertTo-Json -Depth 10 |
Set-Content -Encoding UTF8 reports\evidence\api_responses\matches.json
```

---

## 18. Points de vigilance

Les preuves JSON doivent rester propres et lisibles.

Lorsque PowerShell casse l’affichage des accents, il faut générer le fichier avec Python en UTF-8 :

```
json.dumps(data, ensure_ascii=False, indent=2)
```

Un fichier de preuve ne doit pas contenir de clé API, de secret ou de donnée sensible.

---

##

L’API RubyBets expose les données et résultats nécessaires au MVP : compétitions, matchs, analyse, prédictions et recommandation multi-matchs. Les endpoints sont testables via FastAPI, consommés par le frontend React et archivés sous forme de réponses JSON dans le dossier `reports/evidence/`. Cette organisation permet de prouver la disponibilité de l’API, l’intégration front/back et l’exposition du moteur de scoring explicable.
