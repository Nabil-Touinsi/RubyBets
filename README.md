# RubyBets — Application Data & IA d’aide à la décision football

## 1. Présentation du projet

RubyBets est une application web de fin d’étude Data & IA conçue pour aider à analyser des matchs de football avant leur coup d’envoi.

Le projet ne permet pas de parier, n’est pas un bookmaker et ne promet aucun résultat sportif. L’objectif est de centraliser des données football réelles, de produire une lecture claire avant-match et de présenter des recommandations analytiques explicables.

Formulation officielle du MVP :

```
Première version du moteur d’analyse : scoring explicable basé sur règles métier et données réelles.
```

Le Machine Learning entraîné est traité comme une évolution progressive, après constitution et contrôle d’un dataset historique propre.

---

## 2. Objectif pédagogique et conformité RNCP

RubyBets est construit pour répondre aux attentes du référentiel RNCP Développeur IA niveau 6 et aux consignes de coaching ECE / Simplon.

Le dépôt doit prouver :

- la collecte de données réelles ;
- la présence de données brutes dans `data/ml/raw/` ;
- le nettoyage et la normalisation des données ;
- l’existence de requêtes SQL utiles et documentées ;
- la reproductibilité par des commandes claires ;
- la traçabilité par GitHub ;
- la présence de preuves dans `reports/evidence/`.

Principe de soutenance :

```
Donnée collectée → donnée contrôlée → donnée exploitable → compétence prouvée.
```

---

## 3. Stack technique

| Bloc                  | Technologie                  | Rôle                                        |
|-----------------------|------------------------------|---------------------------------------------|
| Frontend              | React + TypeScript + Vite    | Interface utilisateur multi-écrans          |
| Backend               | Python + FastAPI             | API REST, orchestration métier, scoring V1  |
| Base de données       | PostgreSQL                   | Stockage structuré des données MVP et ML    |
| Connecteur PostgreSQL | psycopg                      | Connexion Python vers PostgreSQL            |
| Données historiques   | Football-Data.co.uk          | Datasets CSV historiques pour le pipeline ML|
| Données API MVP       | Football-Data.org            | Matchs, compétitions et données avant-match |
| Tests                 | pytest + npm run build       | Validation backend et frontend              |
| Versioning            | Git + GitHub                 | Traçabilité, commits et preuves             |
-----------------------------------------------------------------------------------------------------
---

## 4. Structure principale du projet

```
RubyBets/
├── .github/workflows/                  # CI backend et frontend
├── backend/                            # API FastAPI et scripts data / ML
│   ├── app/
│   │   ├── api/                        # Routes FastAPI
│   │   ├── core/                       # Configuration
│   │   └── services/                   # Services métier, data, scoring, persistance
│   ├── scripts/ml/                     # Scripts collecte, import, nettoyage, features
│   ├── sql/queries.sql                 # Requêtes SQL de preuve C2
│   ├── tests/                          # Tests backend
│   └── requirements.txt
├── data/ml/raw/                        # CSV historiques bruts par ligue
├── database/schema/                    # Schémas SQL PostgreSQL
│   ├── schema.sql                      # Tables MVP
│   └── ml_schema.sql                   # Tables ML
├── docs/                               # Documentation technique et RNCP
├── frontend/                           # Application React / TypeScript / Vite
├── reports/evidence/                   # Preuves soutenance
└── README.md
```

---

## 5. Positionnement responsable

RubyBets respecte les règles suivantes :

```
Aucun pari réel dans l’application.
Aucune intégration bookmaker.
Aucune promesse de résultat.
Aucune donnée fictive pour masquer une absence de source.
Aucune clé API ou mot de passe versionné dans Git.
```

Les recommandations affichées sont des aides analytiques. Elles doivent toujours être présentées avec prudence, confiance, risque et justification.

---

## 6. Backend FastAPI

### Routes principales

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

### Services principaux

```
backend/app/services/cache_service.py
backend/app/services/database_service.py
backend/app/services/football_data_client.py
backend/app/services/match_service.py
backend/app/services/analysis_service.py
backend/app/services/recommendation_service.py
backend/app/services/persistence_service.py
```

---

## 7. Frontend React

Le frontend est organisé en écrans et composants afin de correspondre aux maquettes MVP.

Écrans principaux :

```
DashboardScreen.tsx
MatchesScreen.tsx
MatchDetailsScreen.tsx
AnalysisScreen.tsx
PredictionsScreen.tsx
RecommendationScreen.tsx
GlossaryScreen.tsx
ResponsibleInfoScreen.tsx
```

Composants principaux :

```
MatchesSection.tsx
MatchDetailsSection.tsx
MatchAnalysisSection.tsx
MatchPredictionsSection.tsx
MultiMatchRecommendationSection.tsx
GlossarySection.tsx
ResponsibleInfoSection.tsx
DataFreshnessBlock.tsx
```

Le frontend consomme le backend via :

```
frontend/src/services/api.ts
```

Les types TypeScript sont centralisés dans :

```
frontend/src/models/rubybets.ts
```

---

## 8. Base de données PostgreSQL

Base locale utilisée :

```
rubybets_db
```

Schéma MVP :

```
database/schema/schema.sql
```

Tables MVP principales :

```
competitions
teams
matches
predictions
recommendations
recommendation_items
```

Schéma ML :

```
database/schema/ml_schema.sql
```

Tables ML principales :

```
ml.import_batches
ml.raw_matches
ml.clean_matches
ml.features
ml.model_runs
```

Commandes de création des schémas :

```powershell
psql -d rubybets_db -f database\schema\schema.sql
psql -d rubybets_db -f database\schema\ml_schema.sql
```

---

## 9. Données historiques ML

Les datasets historiques sont stockés dans :

```
data/ml/raw/
```

Ligues intégrées :

| Ligue | Code source  | Période               |
|----------------|-----|-----------------------|
| Premier League | E0  | 2000/2001 à 2024/2025 |
| Ligue 1        | F1  | 2000/2001 à 2024/2025 |
| Bundesliga     | D1  | 2000/2001 à 2024/2025 |
| Serie A        | I1  | 2000/2001 à 2024/2025 |
| La Liga        | SP1 | 2000/2001 à 2024/2025 |

Volumes contrôlés après nettoyage :

| Ligue | Matchs propres  |
|----------------|--------|
| Bundesliga     | 7 650  |
| Premier League | 9 500  |
| Ligue 1        | 9 103  |
| Serie A        | 9 204  |
| La Liga        | 9 500  |
| Total          | 44 957 |

Répartition globale des résultats :

| Résultat | Nombre |
|----------|--------|
| HOME_WIN | 20 556 |
| DRAW     | 11 642 |
| AWAY_WIN | 12 759 |

---

## 10. Pipeline data / ML

### Scripts disponibles

```
backend/scripts/ml/download_league_datasets.py
backend/scripts/ml/download_premier_league_datasets.py
backend/scripts/ml/import_raw_matches.py
backend/scripts/ml/clean_raw_matches.py
backend/scripts/ml/build_match_features.py
```

### Télécharger les datasets historiques

Télécharger toutes les ligues configurées :

```powershell
python backend\scripts\ml\download_league_datasets.py --start-year 2000 --end-year 2024
```

Télécharger une seule ligue :

```powershell
python backend\scripts\ml\download_league_datasets.py --league ligue_1 --start-year 2024 --end-year 2024
```

### Importer un fichier brut en base

Exemple pour une saison Premier League :

```powershell
python backend\scripts\ml\import_raw_matches.py --csv data\ml\raw\premier_league\E0_2024_2025.csv --season 2024_2025 --league-code E0
```

### Nettoyer un batch importé

```powershell
python backend\scripts\ml\clean_raw_matches.py --source-file E0_2024_2025.csv
```

### Générer les features ML

```powershell
python backend\scripts\ml\build_match_features.py
```

Résultat validé lors de ML :

```
Matchs nettoyés chargés : 44 957
Features insérées dans ml.features : 44 957
Matchs sans historique domicile : 217
Matchs sans historique extérieur : 217
Règle anti-fuite respectée.
```

---

## 11. Features ML actuellement créées

Le fichier suivant génère les premières variables explicatives :

```
backend/scripts/ml/build_match_features.py
```

Features créées :

```
home_form_points_last_5
away_form_points_last_5
home_goals_scored_avg_last_5
away_goals_scored_avg_last_5
home_goals_conceded_avg_last_5
away_goals_conceded_avg_last_5
home_advantage
target_result
```

Règle anti-fuite : les features d’un match sont calculées uniquement avec les matchs joués avant ce match. Le résultat du match courant est conservé uniquement comme cible `target_result`.

---

## 12. Requêtes SQL de preuve C2

Les requêtes SQL sont stockées dans :

```
backend/sql/queries.sql
```

Elles permettent de démontrer :

- la sélection de colonnes utiles ;
- le filtrage métier ;
- les jointures entre tables ;
- les agrégations ;
- le contrôle des doublons ;
- la lecture des prédictions ;
- la lecture des recommandations multi-matchs.

Ce fichier sert de preuve pour C2, à condition d’ajouter aussi une capture ou un export de résultat dans `reports/evidence/`.

---

## 13. Preuves disponibles

Dossier principal :

```
reports/evidence/
```

Preuves API :

```
reports/evidence/api_responses/health.json
reports/evidence/api_responses/competitions.json
reports/evidence/api_responses/matches.json
reports/evidence/api_responses/match_predictions.json
reports/evidence/api_responses/multimatch_recommendation.json
```

Preuves de build et tests :

```
reports/evidence/build_logs/backend_tests.txt
reports/evidence/build_logs/frontend_build.txt
```

Captures déjà produites :

```
reports/evidence/screenshots/01_ui_dashboard.png
reports/evidence/screenshots/02_ui_matches_list.png
reports/evidence/screenshots/03_ui_match_details.png
reports/evidence/screenshots/04_ui_predictions_block.png
reports/evidence/screenshots/05_ui_multimatch_recommendation.png
reports/evidence/screenshots/06_ui_responsible_info.png
reports/evidence/screenshots/07_swagger_endpoints.png
reports/evidence/screenshots/08_project_tree_docs_evidence.png
reports/evidence/screenshots/09_git_status_before_commit.png
reports/evidence/monitoring/07_health_monitoring.png
```

---

## 14. Documentation projet

Documents Markdown disponibles :

```
docs/api_documentation.md
docs/application_monitoring.md
docs/incident_log.md
docs/rncp_evidence_matrix.md
docs/scoring_engine.md
docs/specs_data.md
```

```
docs/data_dictionary.md
docs/cleaning_rules.md
```

```
reports/evidence/data_quality/01_raw_vs_clean_summary.md
reports/evidence/sql/01_queries_execution.png
reports/evidence/sql/02_sql_results_summary.csv
reports/evidence/screenshots/c1_collecte_terminal.png
reports/evidence/screenshots/c2_sql_execution.png
reports/evidence/screenshots/c3_cleaning_before_after.png
```

---

## 15. Installation backend

Depuis le dossier `backend` :

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Créer un fichier `backend/.env` local non versionné :

```
FOOTBALL_DATA_API_KEY=...
FOOTBALL_DATA_BASE_URL=https://api.football-data.org/v4
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/rubybets_db
```

Lancer le backend :

```powershell
python -m uvicorn app.main:app --reload
```

Tester la disponibilité :

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Résultat attendu :

```json
{
  "status": "ok"
}
```

---

## 16. Installation frontend

Depuis le dossier `frontend` :

```powershell
cd frontend
npm install
npm run dev
```

Build de validation :

```powershell
npm run build
```

---

## 17. Tests et validation

Backend :

```powershell
cd backend
python -m pytest
```

Résultat stable déjà obtenu :

```
14 passed
```

Frontend :

```powershell
cd frontend
npm run build
```

Résultat attendu : compilation TypeScript + build Vite sans erreur.

---

<!-- RUBYBETS_ML_1X2_UPDATE_START -->

## Machine Learning experimental - baseline 1X2

RubyBets dispose maintenant d'une baseline Machine Learning experimentale pour le resultat 1X2.

### Etat actuel

- Source ML : donnees historiques Football-Data.co.uk.
- Tables utilisees : `ml.raw_matches`, `ml.clean_matches`, `ml.features`.
- Modele retenu : `LogisticRegression_balanced`.
- Artefact : `models/ml/1x2/best_1x2_model.joblib`.
- API : routes experimentales `/api/ml/1x2/*`.
- Tests : `backend/tests/test_ml_1x2.py`.
- Preuves : `reports/evidence/ml_training/01` a `24`.

### Commandes de validation

```powershell
cd C:\dev_classe\RNCP\RubyBets\backend
python -m pytest tests\test_ml_1x2.py
python -m pytest
```

Resultats attendus apres la phase batch ML :

```text
tests/test_ml_1x2.py -> 9 passed
backend complet -> 23 passed
```

### Cadre responsable

Le ML est experimental. Il ne remplace pas le scoring explicable V1, ne constitue pas une promesse de resultat et n'est pas integre au frontend MVP pour le moment.

<!-- RUBYBETS_ML_1X2_UPDATE_END -->

