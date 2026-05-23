# Monitoring applicatif RubyBets

<!-- RUBYBETS_ML_1X2_UPDATE_START -->

## Mise a jour monitoring - API ML experimentale

Le monitoring de la phase ML reste volontairement simple et adapte au niveau MVP. Il vise a verifier que l'API experimentale repond, que le modele est charge correctement et que les tests backend continuent de passer.

### Signaux surveilles

| Signal | Preuve actuelle | Statut |
|---|---|---|
| Chargement du modele ML | `08_model_reload_check.txt`, `09_backend_ml_service_check.txt` | Realise |
| Service ML backend | `10_backend_ml_service_pytest.txt` | Realise |
| API ML manuelle | `12_experimental_ml_1x2_api_check.txt` | Realise |
| API ML depuis PostgreSQL | preuves 16, 19, 22 | Realise |
| Tests ML dedies | preuve 23 : `9 passed` | Realise |
| Tests backend globaux | preuve 24 : `23 passed` | Realise |

### Points de vigilance

- La baseline ML peut produire une prediction incorrecte par rapport au resultat reel.
- Une erreur de chargement du fichier `best_1x2_model.joblib` doit etre consideree comme critique pour les routes `/api/ml/1x2/*`.
- Les routes ML ne sont pas integrees au frontend et ne bloquent pas le MVP V1.
- La surveillance avancee de derive modele, calibration et performance en production reste post-MVP.

### Action de controle avant soutenance

```powershell
cd C:\dev_classe\RNCP\RubyBets\backend
python -m pytest
```

Resultat attendu apres la phase batch ML :

```text
23 passed
```

<!-- RUBYBETS_ML_1X2_UPDATE_END -->

