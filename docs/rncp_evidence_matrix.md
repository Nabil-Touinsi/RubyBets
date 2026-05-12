# Matrice RNCP / preuves — RubyBets

Ce document relie les compétences RNCP C1 à C21 aux preuves techniques déjà réalisées ou à produire dans le dépôt RubyBets.

Il sert de fichier de pilotage pour la soutenance : chaque compétence doit être associée à une preuve localisable dans le code, la documentation, les tests, les captures, les logs ou l’historique Git.

---

## 1. Positionnement du projet

RubyBets est une application web de fin d’étude Data & IA.

L’application aide l’utilisateur à analyser des matchs de football avant leur coup d’envoi. Elle centralise des données réelles, produit une analyse pré-match, affiche des prédictions explicables et propose une recommandation multi-matchs selon un niveau de risque.

RubyBets ne permet pas de parier directement.  
RubyBets n’est pas un bookmaker.  
RubyBets ne promet aucun résultat sportif.

La V1 repose sur une première version du moteur d’analyse :

> Scoring explicable basé sur des règles métier et des données réelles.

Le Machine Learning entraîné est prévu après le MVP, lorsque le projet disposera d’un dataset historique propre.

---

## 2. État réel du projet au moment de cette matrice

| Bloc | État actuel | Preuve déjà disponible ou à archiver |
|---|---|---|
| Cadrage produit | Réalisé | Documents 01 à 09 : cadrage, MVP, parcours, écrans, zoning, direction UI, maquettes |
| Backend FastAPI | Réalisé | Routes API disponibles dans `backend/app/api/` |
| Source data réelle | Réalisé | Football-Data.org utilisée comme source principale |
| Cache backend | Réalisé | `backend/app/services/cache_service.py` + `.gitignore` adapté |
| Routes métier | Réalisé | `/health`, `/api/competitions`, `/api/matches`, `/context`, `/analysis`, `/predictions`, `/recommendations/multimatch`, `/glossary`, `/responsible-info` |
| Tests backend | Réalisé | `pytest` validé avec 14 tests passés |
| CI GitHub Actions | Réalisé / à documenter | Workflows backend et frontend présents dans `.github/workflows/` |
| Frontend React | Réalisé | React + TypeScript + Vite |
| API front centralisée | Réalisé | `frontend/src/services/api.ts` |
| Modèles TypeScript | Réalisé | `frontend/src/models/rubybets.ts` |
| Composants frontend | Réalisé | Composants extraits dans `frontend/src/components/` |
| Recommandation multi-matchs | Réalisé | Bloc UI amélioré et branché |
| Bloc Prédictions | Réalisé | `MatchPredictionsSection.tsx` amélioré + `App.css` |
| Build frontend | Réalisé | `npm run build OK` — Vite v8.0.10 — `✓ built in 1.52s` |
| Documentation GitHub preuves | En cours | Création de `docs/rncp_evidence_matrix.md` |
| Dossier evidence | À produire | `reports/evidence/` |
| SQL / requêtes | À produire | `backend/sql/queries.sql` |
| Scoring documenté | À produire | `docs/scoring_engine.md` |
| Monitoring / incident | À produire | `docs/application_monitoring.md`, `docs/incident_log.md` |

---

## 3. Matrice compétences / preuves

| Compétence | Attendu RNCP | Ce qui est déjà fait dans RubyBets | Preuve localisable | Statut actuel |
|---|---|---|---|---|
| C1 | Automatiser l’extraction de données | Le backend récupère des données football réelles depuis Football-Data.org via des services dédiés. Le cache backend limite les appels répétés et stabilise les réponses. | `backend/app/services/football_data_client.py`, `backend/app/services/cache_service.py`, réponses API à archiver dans `reports/evidence/api_responses/` | Réalisé / preuve à archiver |
| C2 | Développer des requêtes SQL d’extraction | Le modèle cible est documenté, mais le fichier SQL de preuve n’est pas encore produit. | `backend/sql/queries.sql` à créer | À produire |
| C3 | Agréger, nettoyer et homogénéiser les données | Les données API sont adaptées côté backend pour alimenter les routes compétitions, matchs, détails, contexte, analyse et prédictions. Les métadonnées de fraîcheur sont exposées. | `backend/app/services/match_service.py`, `cache_service.py`, `docs/specs_data.md` à créer | À formaliser |
| C4 | Créer une base de données dans le respect RGPD | Le dossier `database` existe. Le modèle de données est documenté dans les livrables, mais `schema.sql` est encore vide. Le MVP ne collecte pas de données personnelles utilisateur. | `database/schema/schema.sql`, `docs/database_model.md`, `docs/rgpd_notes.md` à créer | À produire |
| C5 | Développer une API REST | API FastAPI fonctionnelle avec routes MVP : health, compétitions, matchs, détail match, contexte, analyse, prédictions, recommandation multi-matchs, glossaire, infos responsables. | `backend/app/api/`, Swagger `/docs`, `backend/tests/test_api.py`, captures JSON à archiver | Réalisé / à documenter |
| C6 | Organiser une veille technique et réglementaire | La veille est cadrée dans les documents RNCP, notamment sur API football, IA explicable, usage responsable et limites non-bookmaker. | `24_Veille_benchmark_IA_RubyBets.docx`, futur `docs/veille_benchmark_ia.md` | À formaliser dans le repo |
| C7 | Identifier des services IA existants | Le benchmark est cadré : scoring explicable retenu en V1, ML supervisé reporté après constitution d’un dataset historique propre, API prédictive externe écartée. | `24_Veille_benchmark_IA_RubyBets.docx`, futur `docs/veille_benchmark_ia.md` | À formaliser dans le repo |
| C8 | Paramétrer un service IA | Le moteur de scoring V1 existe côté services backend : règles métier, confiance, risque, recommandations. Il doit maintenant être documenté proprement. | `backend/app/services/analysis_service.py`, `backend/app/services/recommendation_service.py`, futur `docs/scoring_engine.md` | Réalisé / à formaliser |
| C9 | Développer une API exposant un service IA | Les routes `/analysis`, `/predictions` et `/recommendations/multimatch` exposent le moteur de scoring explicable via API. | `backend/app/api/matches.py`, `backend/app/api/recommendations.py`, `backend/tests/test_api.py` | Réalisé / à documenter |
| C10 | Intégrer l’API IA dans une application | Le frontend React consomme les endpoints backend via `api.ts`. Les blocs analyse, prédictions et recommandation utilisent les données API. | `frontend/src/services/api.ts`, `frontend/src/App.tsx`, `frontend/src/components/` | Réalisé |
| C11 | Monitorer un modèle IA | En V1, il ne s’agit pas d’un modèle ML entraîné. Le monitoring doit porter sur le moteur de scoring : fraîcheur des données, erreurs API, cohérence des sorties, nombre de recommandations. | `docs/application_monitoring.md`, `reports/evidence/monitoring/` à créer | À produire |
| C12 | Programmer les tests automatisés du modèle / données | Les tests backend existent et valident les routes principales. Le build frontend valide aussi l’intégration TypeScript. Des tests plus ciblés scoring/cas partiels peuvent être ajoutés. | `backend/tests/test_api.py`, `npm run build`, futur `reports/evidence/build_logs/` | Réalisé partiellement / à compléter |
| C13 | Créer une chaîne de livraison continue | Des workflows GitHub Actions existent pour le backend et le frontend. Il faut archiver les preuves d’exécution et documenter la logique CI/CD. | `.github/workflows/`, futur `docs/ci_cd.md`, `reports/evidence/ci_results/` | Réalisé / à documenter |
| C14 | Analyser le besoin d’application IA | Le besoin, la cible, le périmètre MVP, les cas d’usage et les limites sont documentés dans les fichiers produit. | `01_Cadrage_produit_RubyBets.docx`, `02_Definition_MVP_RubyBets.docx`, `03_Parcours_utilisateur_MVP_RubyBets.docx` | Réalisé |
| C15 | Concevoir le cadre technique | Stack, architecture, modèle de données cible, API et stratégie data sont documentés. | `10_Decoupage_technique_MVP_RubyBets_MAJ_RNCP.docx`, `11_Choix_stack_technique_RubyBets_MAJ_RNCP.docx`, `12_Architecture_globale_RubyBets.docx`, `13_Modele_de_donnees_RubyBets_MAJ_RNCP.docx`, `14_Specification_API_MVP_RubyBets_MAJ_RNCP.docx` | Réalisé / à consolider dans `docs/` |
| C16 | Coordonner la réalisation technique | Le projet est suivi par phases, commits, tags et documents de pilotage. Plusieurs versions stables ont été taguées jusqu’à `rubybets-v0.7-backend-data-cache`. | Historique Git, tags GitHub, `17_Plan_de_developpement_MVP_RubyBets_MAJ_RNCP.docx` | À formaliser dans le repo |
| C17 | Développer les composants techniques et interfaces | Les composants React du MVP sont développés : compétitions, matchs, détails, contexte, analyse, prédictions, recommandation, glossaire, infos responsables. Le bloc Prédictions a été professionnalisé. | `frontend/src/components/`, `frontend/src/App.tsx`, `frontend/src/App.css`, `frontend/src/models/rubybets.ts` | Réalisé |
| C18 | Automatiser les tests à l’intégration continue | Le backend est testé avec `pytest`, le frontend compile avec `npm run build`, et les workflows GitHub Actions sont présents. | `.github/workflows/`, `backend/tests/`, log `npm run build`, futur `reports/evidence/build_logs/` | Réalisé / preuve à archiver |
| C19 | Créer un processus de livraison continue | Les tags de version existent et le build est reproductible. La procédure de livraison doit être documentée dans le README ou un fichier dédié. | Tags GitHub `rubybets-v0.x`, `README.md`, futur `docs/release_process.md` | À formaliser |
| C20 | Surveiller une application IA | Le endpoint `/health` existe. Il faut documenter les métriques MVP : disponibilité API, erreurs, fraîcheur des données, build, tests. | `backend/app/api/health.py`, futur `docs/application_monitoring.md`, futur `reports/evidence/monitoring/` | À produire |
| C21 | Résoudre un incident technique | Un incident crédible a déjà été identifié : fragilité de la fiche match si un appel API secondaire échoue. La correction avec `Promise.allSettled` doit être documentée comme incident. | `frontend/src/App.tsx`, futur `docs/incident_log.md`, futur `reports/evidence/incident/` | À produire |

---

## 4. Dernières preuves ajoutées

| Date | Élément réalisé | Fichiers concernés | Preuve | Impact RNCP |
|---|---|---|---|---|
| 11/05/2026 | Amélioration du bloc Prédictions avant-match | `frontend/src/components/MatchPredictionsSection.tsx`, `frontend/src/App.css` | Affichage en cartes des 3 marchés MVP : 1X2, buts, BTTS, avec confiance, risque, justification et rappel responsable. Build frontend validé : `npm run build OK`. | C10, C17, C18 |
| Mai 2026 | Stabilisation cache backend | `backend/app/services/cache_service.py`, `.gitignore` | Cache JSON local fonctionnel, fichiers de cache ignorés par Git, données réelles stabilisées. | C1, C3, C5 |
| Mai 2026 | Tests backend validés | `backend/tests/test_api.py` | `pytest` validé avec 14 tests passés. | C5, C9, C12, C18 |
| Mai 2026 | Frontend branché au backend | `frontend/src/services/api.ts`, `frontend/src/models/rubybets.ts`, `frontend/src/App.tsx` | Appels API centralisés, types TypeScript structurés, composants branchés. | C10, C17 |
| Mai 2026 | Recommandation multi-matchs améliorée | `frontend/src/components/MultiMatchRecommendationSection.tsx`, `frontend/src/App.css` | UI plus professionnelle pour la sélection multi-matchs, affichage du risque, score, justification et cadre responsable. | C10, C17 |
| Mai 2026 | Robustesse du parcours match | `frontend/src/App.tsx` | Chargement indépendant des blocs avec gestion des cas partiels. À documenter dans `incident_log.md`. | C20, C21 |
| Avril / mai 2026 | Versioning progressif | GitHub tags `rubybets-v0.1` à `rubybets-v0.7-backend-data-cache` | Historique clair des versions stables. | C16, C19 |

---

## 5. Priorités immédiates à partir de cette matrice

| Priorité | Action | Fichier à créer ou compléter | Objectif RNCP |
|---|---|---|---|
| P1 | Documenter le moteur de scoring V1 | `docs/scoring_engine.md` | C7, C8, C9, C10, C11 |
| P1 | Ajouter les requêtes SQL de preuve | `backend/sql/queries.sql` | C2, C4 |
| P1 | Documenter la stratégie data réelle | `docs/specs_data.md` | C1, C2, C3 |
| P2 | Créer le dossier de preuves | `reports/evidence/` | Toutes compétences |
| P2 | Archiver les réponses API | `reports/evidence/api_responses/` | C1, C5, C9, C10 |
| P2 | Archiver les logs de build et tests | `reports/evidence/build_logs/` | C12, C18, C19 |
| P2 | Documenter le monitoring MVP | `docs/application_monitoring.md` | C20 |
| P2 | Documenter l’incident technique | `docs/incident_log.md` | C21 |
| P3 | Corriger les détails CSS mineurs | `frontend/src/App.css` | C17 |

---

## 6. Règle de suivi

À chaque nouvelle avancée du projet :

1. mettre à jour cette matrice ;
2. indiquer la compétence RNCP renforcée ;
3. indiquer le fichier modifié ;
4. ajouter une preuve reproductible ;
5. archiver si possible une capture ou un log dans `reports/evidence/`.

Une compétence ne doit pas seulement être racontée en soutenance : elle doit être visible, vérifiable et localisable dans le dépôt.