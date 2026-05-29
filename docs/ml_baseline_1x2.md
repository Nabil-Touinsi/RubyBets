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

## Évaluation reproductible du modèle sauvegardé

Un script dédié permet de recharger le modèle ML 1X2 sauvegardé sans relancer l’entraînement complet.

Script concerné :

`backend/scripts/ml/evaluate_saved_1x2_model.py`

Modèle rechargé :

`models/ml/1x2/best_1x2_model.joblib`

Le script relit les données depuis PostgreSQL, applique les 6 features officielles de la baseline 1X2, filtre les saisons de test `2022_2023`, `2023_2024` et `2024_2025`, puis génère une preuve d’évaluation.

Preuve générée :

`reports/evidence/ml_training/28_saved_1x2_model_evaluation.txt`

Résultat constaté :

- Accuracy : `0.4669`
- F1 macro : `0.4266`
- F1 weighted : `0.4525`

Cette étape confirme que la baseline ML expérimentale est reproductible techniquement, tout en restant séparée du scoring explicable V1.

## Métadonnées du modèle sauvegardé

Une fiche de métadonnées accompagne le modèle ML 1X2 sauvegardé afin de tracer clairement son périmètre, ses features, ses scores, ses limites et les preuves associées.

Fichier concerné :

`models/ml/1x2/model_metadata.json`

Cette fiche permet de comprendre rapidement le modèle retenu sans devoir relire tous les logs d’entraînement ou d’évaluation.

## Endpoint de statut enrichi

L’endpoint expérimental suivant permet maintenant de vérifier l’état technique du modèle ML 1X2 sauvegardé :

`GET /api/ml/1x2/status`

Il retourne désormais :

- la disponibilité du modèle sauvegardé ;
- la disponibilité du fichier de métadonnées ;
- le nom du modèle retenu ;
- la cible `1X2` ;
- les classes prédites ;
- les 6 features utilisées ;
- les scores principaux ;
- les preuves associées ;
- le rappel du positionnement expérimental.

Cette route reste strictement technique. Elle sert à contrôler la disponibilité de la baseline ML et à documenter son état, sans intégrer le ML au frontend et sans remplacer le scoring explicable V1.

High-confidence ML signal
- seuil retenu : 0.60
- accuracy : 70.76%
- coverage : 9.2%
- limite : aucun DRAW prédit en forte confiance
- décision : signal expérimental, non intégré au frontend