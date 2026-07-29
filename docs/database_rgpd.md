# Base PostgreSQL et périmètre RGPD du MVP RubyBets

## Rôle du document

Ce document formalise la preuve C4 de RubyBets : une base PostgreSQL structurée, reliée au backend FastAPI et utilisée sans collecte de données personnelles dans le périmètre actuel du MVP.

## 1. Base active et modèle relationnel

RubyBets utilise PostgreSQL via la variable `DATABASE_URL`, conservée dans `backend/.env` et exclue du dépôt Git.

Le schéma métier principal est défini dans :

- `database/schema/schema.sql` ;
- `backend/app/services/database_service.py` ;
- `backend/app/services/persistence_service.py` ;
- `backend/sql/queries.sql`.

Le modèle principal contient les tables :

- `competitions` ;
- `teams` ;
- `matches` ;
- `predictions` ;
- `recommendations` ;
- `recommendation_items` ;
- `archived_predictions`.

Les clés primaires, clés étrangères, contraintes `UNIQUE`, contraintes `CHECK` et index assurent la cohérence des relations entre les données football, les prédictions et les recommandations.

## 2. Chaîne technique réelle

```text
Football-Data.org / pipelines historiques
                    ↓
normalisation et persistance backend
                    ↓
PostgreSQL rubybets_db
                    ↓
routes FastAPI et contrôles /health/database
                    ↓
frontend React et preuves techniques
```

La connexion est centralisée dans `database_service.py`. La route `/health/database` vérifie la disponibilité de PostgreSQL sans exposer la chaîne de connexion.

## 3. Périmètre des données du MVP

Le MVP stocke uniquement :

- des données football issues de sources documentées ;
- des données préparées et des features analytiques ;
- des prédictions et recommandations calculées ;
- des métadonnées techniques de fraîcheur et de version.

Le MVP ne contient actuellement :

- aucun compte utilisateur ;
- aucune donnée de paiement ;
- aucun historique de pari réel ;
- aucune adresse, date de naissance, adresse électronique ou numéro de téléphone ;
- aucune donnée d’authentification utilisateur.

Les noms d’équipes, de compétitions et les informations sportives ne sont pas traités comme des données personnelles d’utilisateur.

## 4. Mesures de confidentialité et de sécurité

- Les secrets de connexion restent dans `.env`, exclu par `.gitignore`.
- Aucun mot de passe ni URL complète de base n’est écrit dans les rapports de preuve.
- Les routes publiques du MVP n’exposent aucune opération sensible sur des comptes.
- Les logs doivent rester techniques et ne pas contenir de secret.
- Toute future fonction de compte utilisateur imposera une nouvelle analyse du modèle, des durées de conservation, des droits d’accès et de suppression, ainsi que des mesures de sécurité adaptées.

Cette section décrit le périmètre actuel du MVP ; elle ne prétend pas couvrir une future version avec comptes ou paiements.

## 5. Preuve reproductible

Commande à exécuter depuis la racine du dépôt :

```powershell
python backend/scripts/ci/validate_database_schema.py
```

Le script interroge en lecture seule les métadonnées PostgreSQL et vérifie :

- la connexion à la base active ;
- la présence des tables métier principales ;
- les relations par clés étrangères ;
- les contraintes et index ;
- l’absence de tables ou colonnes usuelles de données personnelles dans le MVP ;
- l’exclusion de `.env` par Git.

Rapport produit :

```text
reports/evidence/database/database_schema_validation.json
```

Le rapport ne contient ni mot de passe, ni URL de connexion, ni secret.

## 6. Preuves associées à C4

| Type de preuve | Emplacement |
|---|---|
| Schéma physique PostgreSQL | `database/schema/schema.sql` |
| Schémas analytiques | `database/schema/ml_schema.sql`, `database/schema/ml_national_schema.sql` |
| Connexion backend | `backend/app/services/database_service.py` |
| Persistance métier | `backend/app/services/persistence_service.py` |
| Requêtes SQL | `backend/sql/queries.sql`, `backend/sql/ml_queries.sql` |
| Santé de la base | `GET /health/database` |
| Validation automatique | `backend/scripts/ci/validate_database_schema.py` |
| Rapport réel | `reports/evidence/database/database_schema_validation.json` |

## 7. Statut C4

La compétence C4 peut être présentée comme **preuve suffisante** lorsque le rapport de validation retourne `PASSED` sur la base PostgreSQL active et que les fichiers de preuve sont versionnés.

La matrice Word 22 et la documentation de soutenance devront alors être actualisées pour retirer l’ancien statut « à produire / reporté ».
