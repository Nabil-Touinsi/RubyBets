# Matrice RNCP RubyBets

<!-- RUBYBETS_ML_1X2_UPDATE_START -->

## Mise a jour RNCP - phase ML experimentale 1X2

Cette section complete la matrice RNCP avec les preuves produites pendant la phase ML experimentale.

| Competence | Preuve RubyBets | Fichiers / dossiers | Statut |
|---|---|---|---|
| C1 | Collecte de donnees historiques football reelles. | `data/ml/raw/`, scripts ML, preuves 01-02 | Realise |
| C2 | Exploitation SQL des tables `ml.raw_matches`, `ml.clean_matches`, `ml.features`. | `database/schema/ml_schema.sql`, requetes executees, preuves ML | Realise partiellement |
| C3 | Nettoyage et preparation des features ML. | `clean_raw_matches.py`, `build_match_features.py`, `docs/cleaning_rules.md` | Realise |
| C5 | Exposition API FastAPI des predictions ML experimentales. | `backend/app/api/ml_predictions.py` | Realise |
| C7 | Comparaison de plusieurs approches ML. | `03_model_comparison.csv`, rapports modeles | Realise |
| C8 | Parametrage et sauvegarde d'un modele ML. | `models/ml/1x2/best_1x2_model.joblib` | Realise |
| C9 | API exposant un service IA experimental. | routes `/api/ml/1x2/*` | Realise |
| C10 | Integration backend du service ML dans l'application. | `ml_1x2_prediction_service.py`, `ml_feature_service.py` | Realise |
| C11 | Suivi experimental des predictions et limites du modele. | preuves 15 a 24, notes responsables | Realise partiellement |
| C12 | Tests automatises du service et des routes ML. | `backend/tests/test_ml_1x2.py`, preuves 23 et 24 | Realise |
| C16 | Coordination technique et versioning de la phase ML. | commits ML + preuves `reports/evidence/ml_training/` | Realise |
| C18 | Validation technique reproductible. | `python -m pytest`, 23 tests backend | Realise |
| C19 | Livraison versionnee des increments ML. | commits GitHub de la phase ML | Realise |
| C20 | Premiere base de surveillance technique de l'API ML. | tests backend globaux + preuves API | Realise partiellement |

### Preuves ML principales

- `01_dataset_summary.txt`
- `03_model_comparison.csv`
- `07_best_model_decision.txt`
- `12_experimental_ml_1x2_api_check.txt`
- `16_experimental_ml_api_from_database_feature_check.txt`
- `19_experimental_ml_api_from_clean_match_check.txt`
- `22_experimental_ml_batch_api_from_clean_matches_check.txt`
- `23_ml_1x2_pytest_batch_from_clean_matches.txt`
- `24_backend_full_pytest_after_batch_ml_api.txt`

### Statut a defendre

La phase ML est realisee comme experimentation backend traçable. Elle reste separee du scoring explicable V1 et non integree au frontend.

<!-- RUBYBETS_ML_1X2_UPDATE_END -->

