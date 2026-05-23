# Baseline ML 1X2 RubyBets

<!-- RUBYBETS_ML_1X2_UPDATE_START -->

## Baseline ML 1X2 experimentale

Ce document synthetise l'etat actuel de la baseline ML 1X2 RubyBets.

### Objectif

Entrainer et exposer une premiere baseline Machine Learning capable de produire une prediction experimentale du resultat 1X2 d'un match de football :

- `HOME_WIN`
- `DRAW`
- `AWAY_WIN`

### Dataset

| Element | Valeur |
|---|---:|
| Dataset initial | 44 957 lignes |
| Lignes supprimees | 337 |
| Dataset entrainable | 44 620 lignes |
| Train | 2000_2001 a 2021_2022 |
| Test | 2022_2023 a 2024_2025 |

### Modeles compares

- `DummyClassifier_most_frequent`
- `LogisticRegression_balanced`
- `RandomForest_balanced`
- `XGBoost_classifier`

### Modele retenu

Le modele retenu est `LogisticRegression_balanced`, car il offre le meilleur compromis entre performance globale, lisibilite, capacite a predire les trois classes et facilite d'integration backend.

### Artefact sauvegarde

```text
models/ml/1x2/best_1x2_model.joblib
```

### Services backend

| Fichier | Role |
|---|---|
| `backend/app/services/ml_1x2_prediction_service.py` | Charge le modele et produit une prediction 1X2. |
| `backend/app/services/ml_feature_service.py` | Recupere les features ML depuis PostgreSQL. |
| `backend/app/api/ml_predictions.py` | Expose les routes API experimentales ML. |
| `backend/tests/test_ml_1x2.py` | Teste les services et routes ML avec monkeypatch pour eviter une dependance CI a PostgreSQL. |

### Routes API

```text
POST /api/ml/1x2/predict
POST /api/ml/1x2/predict/from-feature/{feature_id}
POST /api/ml/1x2/predict/from-clean-match/{clean_match_id}
POST /api/ml/1x2/predict/batch/from-clean-matches
```

### Validation finale actuelle

| Validation | Resultat |
|---|---|
| Tests ML dedies | 9 passed |
| Tests backend globaux | 23 passed |
| Derniere preuve globale | `reports/evidence/ml_training/24_backend_full_pytest_after_batch_ml_api.txt` |

### Limites

Cette baseline reste experimentale. Elle ne remplace pas le scoring explicable V1, ne garantit aucun resultat sportif et n'est pas integree au frontend pour le moment.

<!-- RUBYBETS_ML_1X2_UPDATE_END -->

