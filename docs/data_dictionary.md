# Dictionnaire de données — RubyBets

> Rôle du fichier : décrire les principales tables et colonnes utilisées dans le pipeline data / ML de RubyBets afin de rendre les données compréhensibles et traçables.

## 1. Objectif

Ce dictionnaire de données documente les tables créées pour préparer le pipeline Machine Learning de RubyBets.

Il permet de prouver que les données ne sont pas seulement collectées, mais aussi structurées, nettoyées, contrôlées et préparées pour un usage analytique.

## 2. Schéma concerné

| Élément             | Description                                                         |
|---------------------|---------------------------------------------------------------------|
| Base de données     | `rubybets_db`                                                       |
| Schéma principal ML | `ml`                                                                |
| Fichier SQL associé | `database/schema/ml_schema.sql`                                     |
| Usage               | Collecte historique, nettoyage, feature engineering, préparation ML |

## 3. Table `ml.import_batches`

| Colonne         | Rôle                                 | Usage                                                         |
|-----------------|--------------------------------------|---------------------------------------------------------------|
| `id`            | Identifiant unique du batch d'import | Suivre chaque import de fichier                               |
| `source_name`   | Nom de la source de données          | Identifier l’origine du dataset                               |
| `league_code`   | Code de la ligue importée            | Distinguer Premier League, Ligue 1, Bundesliga, Serie A, Liga |
| `season`        | Saison sportive                      | Relier les données à une saison                               |
| `file_path`     | Chemin du fichier CSV importé        | Assurer la traçabilité du fichier brut                        |
| `rows_imported` | Nombre de lignes importées           | Contrôle de volumétrie                                        |
| `imported_at`   | Date d’import                        | Suivi et reproductibilité                                     |

## 4. Table `ml.raw_matches`

| Colonne           | Rôle                                 | Usage                                    |
|-------------------|--------------------------------------|------------------------------------------|
| `id`              | Identifiant unique de la ligne brute | Suivi interne                            |
| `import_batch_id` | Lien vers le batch d'import          | Relier chaque match à son fichier source |
| `league_code`     | Code de la ligue                     | Filtrer par championnat                  |
| `season`          | Saison sportive                      | Contrôler la couverture historique       |
| `match_date`      | Date du match                        | Ordonner les matchs dans le temps        |
| `home_team`       | Équipe à domicile                    | Analyse domicile                         |
| `away_team`       | Équipe extérieure                    | Analyse extérieur                        |
| `home_goals`      | Buts équipe domicile                 | Donnée observée après match              |
| `away_goals`      | Buts équipe extérieure               | Donnée observée après match              |
| `result`          | Résultat brut du match               | Base du label cible                      |
| `raw_payload`     | Données brutes complémentaires       | Conservation des informations sources    |

## 5. Table `ml.clean_matches`

| Colonne        | Rôle                                | Usage                                              |
|----------------|-------------------------------------|----------------------------------------------------|
| `id`           | Identifiant unique du match nettoyé | Référence principale pour le ML                    |
| `raw_match_id` | Lien vers la donnée brute           | Traçabilité raw → clean                            |
| `league_code`  | Code de la ligue                    | Filtre et segmentation par championnat             |
| `season`       | Saison sportive                     | Analyse temporelle                                 |
| `match_date`   | Date normalisée du match            | Calcul chronologique sans fuite de données         |
| `home_team`    | Équipe à domicile normalisée        | Calcul des features domicile                       |
| `away_team`    | Équipe extérieure normalisée        | Calcul des features extérieur                      |
| `home_goals`   | Buts domicile                       | Donnée réelle observée                             |
| `away_goals`   | Buts extérieur                      | Donnée réelle observée                             |
| `result`       | Label cible normalisé               | Valeurs attendues : `HOME_WIN`, `DRAW`, `AWAY_WIN` |

## 6. Table `ml.features`

| Colonne | Rôle | Usage |
|----------------------------------|----------------------------------------------------|------------------------------------------|
| `id`                             | Identifiant unique de la ligne de features         | Suivi interne                            |
| `clean_match_id`                 | Match associé                                      | Relier les variables au match cible      |
| `league_code`                    | Code de la ligue                                   | Filtrer / entraîner par ligue si besoin  |
| `season`                         | Saison sportive                                    | Séparation temporelle train/test         |
| `match_date`                     | Date du match                                      | Respect de l’ordre chronologique         |
| `home_form_points_last_5`        | Points récents de l’équipe domicile sur 5 matchs   | Mesure de forme récente                  |
| `away_form_points_last_5`        | Points récents de l’équipe extérieure sur 5 matchs | Mesure de forme récente                  |
| `home_goals_scored_avg_last_5`   | Moyenne de buts marqués par l’équipe domicile      | Signal offensif                          |
| `away_goals_scored_avg_last_5`   | Moyenne de buts marqués par l’équipe extérieure    | Signal offensif                          |
| `home_goals_conceded_avg_last_5` | Moyenne de buts encaissés par l’équipe domicile    | Signal défensif                          |
| `away_goals_conceded_avg_last_5` | Moyenne de buts encaissés par l’équipe extérieure  | Signal défensif                          |
| `home_advantage`                 | Indicateur d’avantage domicile                     | Variable métier simple                   |
| `target_result`                  | Résultat réel du match                             | Label utilisé pour l’entraînement futur  |

## 7. Table `ml.model_runs`

| Colonne         | Rôle                                     | Usage                                                    |
|-----------------|------------------------------------------|----------------------------------------------------------|
| `id`            | Identifiant unique de l’exécution modèle | Suivre les entraînements futurs                          |
| `model_name`    | Nom du modèle testé                      | Comparer les approches                                   |
| `model_version` | Version du modèle                        | Versionner les expérimentations                          |
| `train_period`  | Période utilisée pour l’entraînement     | Assurer la traçabilité temporelle                        |
| `test_period`   | Période utilisée pour le test            | Éviter l’évaluation aléatoire non maîtrisée              |
| `accuracy`      | Score global du modèle                   | Première métrique de comparaison                         |
| `metrics_json`  | Métriques détaillées                     | Stocker matrice de confusion, scores par classe, limites |
| `created_at`    | Date de l’exécution                      | Suivi des expérimentations                               |

## 8. Règles importantes de qualité

| Règle                                                         | Justification |
|---------------------------------------------------------------|--------------------------------------------------------------|
| Conserver les données brutes dans `ml.raw_matches`            | Permettre la traçabilité de la source                        |
| Nettoyer les données dans `ml.clean_matches`                  | Séparer les données sources des données exploitables         |
| Calculer les features dans `ml.features`                      | Préparer l’entraînement ML sans modifier les matchs nettoyés |
| Respecter l’ordre chronologique                               | Éviter toute fuite de données                                |
| Ne jamais utiliser le résultat du match courant comme feature | Garantir une logique ML correcte                             |
| Accepter des valeurs `NULL` sur les premiers matchs           | Certains matchs n’ont pas encore assez d’historique          |
| Documenter les volumes importés et nettoyés                   | Prouver la qualité dataset en soutenance                     |


Cette organisation permet de relier les données collectées, les traitements de nettoyage, les variables explicatives et les futurs modèles de manière claire et traçable.

<!-- RUBYBETS_ML_1X2_UPDATE_START -->

## Complement dictionnaire - tables ML 1X2

### Table `ml.features`

| Colonne | Type logique | Description |
|---|---|---|
| `id` | Identifiant technique | Identifiant de la ligne de features. |
| `clean_match_id` | Cle de liaison | Identifiant du match nettoye associe. |
| `home_form_points_last_5` | Numerique | Points pris recemment par l'equipe a domicile sur les 5 derniers matchs. |
| `away_form_points_last_5` | Numerique | Points pris recemment par l'equipe exterieure sur les 5 derniers matchs. |
| `home_goals_scored_avg_last_5` | Numerique | Moyenne de buts marques recemment par l'equipe a domicile. |
| `away_goals_scored_avg_last_5` | Numerique | Moyenne de buts marques recemment par l'equipe exterieure. |
| `home_goals_conceded_avg_last_5` | Numerique | Moyenne de buts encaisses recemment par l'equipe a domicile. |
| `away_goals_conceded_avg_last_5` | Numerique | Moyenne de buts encaisses recemment par l'equipe exterieure. |
| `target_result` | Categorie | Resultat reel du match : `HOME_WIN`, `DRAW`, `AWAY_WIN`. |

### Payload attendu par le modele ML

Le modele `LogisticRegression_balanced` attend exactement les 6 features numeriques suivantes :

```text
home_form_points_last_5
away_form_points_last_5
home_goals_scored_avg_last_5
away_goals_scored_avg_last_5
home_goals_conceded_avg_last_5
away_goals_conceded_avg_last_5
```

### Sortie ML experimentale

| Champ | Description |
|---|---|
| `predicted_class` | Classe 1X2 predite par le modele. |
| `probabilities` | Probabilites experimentales pour `HOME_WIN`, `DRAW`, `AWAY_WIN`. |
| `responsible_note` | Rappel indiquant que la baseline ML ne remplace pas le scoring V1 et ne garantit aucun resultat. |

<!-- RUBYBETS_ML_1X2_UPDATE_END -->

