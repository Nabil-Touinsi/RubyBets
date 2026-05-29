# Documentation API RubyBets

<!-- RUBYBETS_ML_1X2_UPDATE_START -->

## Mise a jour ML experimentale 1X2 - API

Cette section documente les endpoints Machine Learning experimentaux ajoutes apres la constitution du dataset historique et l'entrainement de la baseline 1X2.

### Positionnement

Les routes suivantes exposent une baseline ML experimentale basee sur `LogisticRegression_balanced`. Elles ne remplacent pas le moteur de scoring explicable V1 et ne doivent pas etre presentees comme une garantie de resultat sportif.

### Routes disponibles

| Methode | Endpoint | Role | Statut |
|---|---|---|---|
| POST | `/api/ml/1x2/predict` | Predire un resultat 1X2 a partir de 6 features envoyees manuellement. | Experimental |
| POST | `/api/ml/1x2/predict/from-feature/{feature_id}` | Predire un resultat 1X2 depuis une ligne technique `ml.features`. | Experimental |
| POST | `/api/ml/1x2/predict/from-clean-match/{clean_match_id}` | Predire un resultat 1X2 depuis les features d'un match nettoye. | Experimental |
| POST | `/api/ml/1x2/predict/batch/from-clean-matches` | Predire plusieurs resultats 1X2 depuis plusieurs `clean_match_id`. | Experimental |

### Exemple de payload batch

```json
{
  "clean_match_ids": [10086, 10087, 10088]
}
```

### Exemple de structure de reponse batch

```json
{
  "source": "rubybets_ml_baseline",
  "scope": "experimental",
  "requested_count": 3,
  "returned_count": 3,
  "predictions": [
    {
      "feature_source": {
        "feature_id": 20,
        "clean_match_id": 10086,
        "target_result": "HOME_WIN",
        "features": {}
      },
      "result": {
        "status": "experimental_ml_baseline",
        "model_name": "LogisticRegression_balanced",
        "target": "1X2",
        "predicted_class": "AWAY_WIN",
        "probabilities": {
          "AWAY_WIN": 0.4808,
          "DRAW": 0.3548,
          "HOME_WIN": 0.1644
        }
      }
    }
  ]
}
```

### Gestion des erreurs

| Cas | Code HTTP | Comportement attendu |
|---|---:|---|
| Liste `clean_match_ids` vide | 400 | La requete est refusee car aucune prediction batch n'est possible. |
| `feature_id` ou `clean_match_id` introuvable | 404 | L'API retourne un message explicite. |
| Features incompletes ou modele indisponible | 500 potentiel | A traiter comme erreur technique, sans integration frontend pour le moment. |

### Preuves associees

| Preuve | Fichier |
|---|---|
| API ML depuis features manuelles | `reports/evidence/ml_training/12_experimental_ml_1x2_api_check.txt` |
| Tests API unifiee | `reports/evidence/ml_training/13_unified_ml_1x2_pytest.txt` |
| API ML depuis `feature_id` | `reports/evidence/ml_training/16_experimental_ml_api_from_database_feature_check.txt` |
| API ML depuis `clean_match_id` | `reports/evidence/ml_training/19_experimental_ml_api_from_clean_match_check.txt` |
| API ML batch | `reports/evidence/ml_training/22_experimental_ml_batch_api_from_clean_matches_check.txt` |
| Tests ML batch | `reports/evidence/ml_training/23_ml_1x2_pytest_batch_from_clean_matches.txt` |
| Validation backend globale | `reports/evidence/ml_training/24_backend_full_pytest_after_batch_ml_api.txt` |

## Endpoint de statut ML 1X2 expérimental

### `GET /api/ml/1x2/status`

Cet endpoint permet de vérifier l’état technique de la baseline ML 1X2 expérimentale.

Il retourne notamment :

- la disponibilité du modèle sauvegardé ;
- la disponibilité du fichier de métadonnées ;
- le nom du modèle retenu ;
- la cible `1X2` ;
- les classes prédites ;
- les features attendues ;
- les scores principaux d’évaluation ;
- les preuves associées ;
- le rappel du positionnement expérimental.

Fichiers liés :

- `models/ml/1x2/best_1x2_model.joblib`
- `models/ml/1x2/model_metadata.json`
- `backend/app/api/ml_predictions.py`

Important : cet endpoint reste une route technique de contrôle. Il ne remplace pas le scoring explicable V1 et n’intègre pas encore la baseline ML dans le frontend.

---

## Routes expérimentales ML V17.8

### Positionnement

Les routes V17.8 sont des routes expérimentales destinées à valider progressivement l’intégration technique du sélecteur ML multi-marchés V17.8.

Elles ne remplacent pas le scoring explicable V1 et ne sont pas utilisées par la route officielle :

```text
GET /api/matches/{match_id}/predictions
```

Elles ne modifient pas PostgreSQL, `ml.features`, le frontend ou le moteur de scoring V1.

Leur rôle est uniquement de tester, en isolation, le comportement du module expérimental V17.8 avant toute intégration produit future.

---

### `GET /api/experimental/ml/v17-8/demo`

#### Rôle

Retourne une démonstration contrôlée du service expérimental V17.8 à partir d’un jeu de features préparé manuellement.

Cette route permet de vérifier que le service V17.8 peut produire une recommandation expérimentale ou une abstention, sans utiliser les vrais matchs RubyBets.

#### Type de route

```text
Expérimentale
Demo only
Non utilisée par le frontend
Non reliée à PostgreSQL
Non reliée à ml.features
```

#### Flux technique

```text
features demo contrôlées
→ ml_v17_8_service.py
→ recommandation expérimentale V17.8 ou abstention
```

#### Réponse attendue

La réponse contient notamment :

```text
source
scope
status
message
demo_features_profile
result
```

#### Preuves associées

```text
reports/evidence/ml_training/283_v17_8_demo_api_response.json
reports/evidence/ml_training/284_v17_8_demo_api_tests.txt
```

---

### `GET /api/experimental/ml/v17-8/adapter-demo`

#### Rôle

Retourne une démonstration contrôlée du flux complet :

```text
données match préparées
→ ml_v17_8_feature_adapter.py
→ ml_v17_8_service.py
→ recommandation expérimentale V17.8 ou abstention
```

Cette route rapproche l’expérimentation V17.8 d’une future intégration réelle, tout en restant volontairement déconnectée des vrais matchs RubyBets.

#### Type de route

```text
Expérimentale
Adapter demo only
Non utilisée par le frontend
Non reliée à PostgreSQL
Non reliée à ml.features
Non reliée à la route officielle /predictions
```

#### Flux technique

```text
prepared_match_data
→ ml_v17_8_feature_adapter.py
→ ml_v17_8_service.py
```

#### Réponse attendue

La réponse contient notamment :

```text
source
scope
status
message
demo_features_profile
flow
result
```

Le champ `result` contient le retour de l’adaptateur, avec :

```text
adapter_metadata
result
```

`adapter_metadata` décrit le contexte adapté : match, compétition, features manquantes ou complètes.

`result` contient la recommandation expérimentale V17.8 produite par le service.

#### Preuves associées

```text
reports/evidence/ml_training/286_v17_8_adapter_demo_api_response.json
reports/evidence/ml_training/287_v17_8_adapter_demo_api_tests.txt
```

---

### Limites assumées

Ces routes restent strictement expérimentales.

Elles ne doivent pas être présentées comme une fonctionnalité utilisateur finale. Elles servent à prouver que le backend peut isoler, tester et documenter une logique ML expérimentale sans fragiliser le MVP officiel.

Le scoring explicable V1 reste le socle officiel de RubyBets pour la version actuelle du produit.

---

### Statut de validation

```text
Service V17.8 : validé
Adaptateur V17.8 : validé
Route demo : validée
Route adapter-demo : validée
Tests backend ciblés : 8 passed in 1.77s
```

