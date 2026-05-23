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

<!-- RUBYBETS_ML_1X2_UPDATE_END -->

