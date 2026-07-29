# Monitoring applicatif RubyBets

<!-- Rôle du fichier : décrire les contrôles opérationnels réellement disponibles pour surveiller le MVP RubyBets. -->

## 1. Objectif

Le monitoring RubyBets reste volontairement léger et adapté à un MVP local de fin d'étude. Il doit détecter rapidement une indisponibilité du backend, de PostgreSQL ou des artefacts ML, sans ajouter une plateforme de supervision disproportionnée.

Le périmètre surveillé couvre l'application V19 : API FastAPI, base PostgreSQL, artefacts ML, contrats API, tests backend et build frontend.

## 2. Signaux réellement surveillés

| Signal | Contrôle technique | Preuve actuelle | État attendu |
|---|---|---|---|
| Disponibilité du backend | `GET /health` | `backend/app/api/health.py` + test automatisé | HTTP 200 et `status: ok` |
| Disponibilité PostgreSQL | `GET /health/database` | `database_service.check_database_connection()` + deux tests automatisés | `status: ok` ou `unavailable` explicite |
| Intégrité des modèles | `validate_model_artifacts.py` | validation automatique des 7 artefacts dans Backend tests | 7/7 valides, 0 erreur |
| Régressions backend et V19 | `python -m pytest` | GitHub Actions Backend tests #92 | 285 tests passés avant ajout des deux tests de santé DB |
| Compilation frontend | `npm run lint` et `npm run build` | GitHub Actions Frontend build #90 et Application release #1 | lint et build réussis |
| Livraison applicative | workflow `Application release` | Application release #1 | paquet généré et artefact disponible |

## 3. Contrats de santé

### `GET /health`

Ce contrôle vérifie que FastAPI répond. Une réponse différente de HTTP 200 ou de `{ "status": "ok" }` est considérée comme un incident critique de disponibilité backend.

### `GET /health/database`

Ce contrôle vérifie la connexion à `rubybets_db`. La route conserve un contrat lisible :

- `status: ok` : PostgreSQL répond ;
- `status: unavailable` : PostgreSQL ne répond pas, sans masquer l'indisponibilité.

Les deux états sont couverts par des tests de non-régression dans `backend/tests/test_api_contracts.py`.

## 4. Seuils d'alerte MVP

| Niveau | Condition | Action |
|---|---|---|
| Critique | `/health` ne répond pas ou un workflow de validation échoue | bloquer la livraison, consulter les logs du job et corriger avant nouveau tag |
| Élevé | `/health/database` retourne `unavailable` | vérifier PostgreSQL, les variables d'environnement et la chaîne de connexion |
| Élevé | un artefact ML est absent, illisible ou incohérent | bloquer la livraison et régénérer ou restaurer l'artefact concerné |
| Moyen | une route métier retourne un état partiel maîtrisé | conserver le parcours disponible et diagnostiquer la source secondaire |
| Faible | avertissement d'une action GitHub dépréciée sans échec | planifier la mise à niveau sans bloquer le MVP |

## 5. Procédure de contrôle reproductible

```powershell
Set-Location "C:\dev_classe\RNCP\RubyBets"

Set-Location backend
python -m pytest
Set-Location ..

python backend/scripts/ci/validate_model_artifacts.py

Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/health/database
```

Résultats attendus après ce lot :

- 287 tests backend réussis ;
- 7/7 artefacts ML valides ;
- backend `ok` ;
- base `ok` lorsque PostgreSQL est démarré.

## 6. Limites assumées

RubyBets n'est pas encore déployé en production permanente. Il n'y a donc pas de surveillance externe 24 h/24, de tableau de bord Prometheus/Grafana ni d'alerte automatique par courriel. Ces outils seraient disproportionnés pour le MVP actuel.

Le monitoring avancé du modèle — dérive, calibration et comparaison continue entre prédictions et résultats réels — reste une amélioration distincte liée à C11.

## 7. Preuves RNCP mobilisables

- `backend/app/api/health.py` ;
- `backend/tests/test_api_contracts.py` ;
- `.github/workflows/backend-tests.yml` ;
- `.github/workflows/application-release.yml` ;
- `backend/scripts/ci/validate_model_artifacts.py` ;
- commit `6c5890d` ;
- GitHub Actions Backend tests #92, Frontend build #90 et Application release #1.

## 8. Statut

**C20 — preuve suffisante pour le périmètre MVP**, sous réserve d'une exécution verte des 287 tests après ajout des deux contrôles PostgreSQL.

<!-- Schéma de communication : navigateur/tests -> health.py -> database_service.py -> PostgreSQL ; CI -> tests + validation modèles -> artefacts GitHub. -->
