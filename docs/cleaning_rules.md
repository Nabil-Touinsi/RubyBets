# Règles de nettoyage des données — RubyBets

> Rôle du fichier : décrire les règles utilisées pour transformer les données historiques brutes en données propres, normalisées et exploitables dans le pipeline data / ML de RubyBets.

## 1. Objectif

Ce document présente les règles de nettoyage appliquées aux datasets historiques de matchs de football utilisés dans RubyBets.

Il permet de prouver que les données ne sont pas seulement collectées, mais aussi contrôlées, nettoyées, normalisées et préparées pour un usage analytique.

## 2. Périmètre concerné

| Élément              | Description                                                        |
|----------------------|--------------------------------------------------------------------|
| Base de données      | `rubybets_db`                                                      |
| Schéma principal ML  | `ml`                                                               |
| Table brute          | `ml.raw_matches`                                                   |
| Table nettoyée       | `ml.clean_matches`                                                 |
| Fichier SQL associé  | `database/schema/ml_schema.sql`                                    |
| Script associé       | `backend/scripts/ml/clean_raw_matches.py`                          |
| Usage                | Nettoyage historique, normalisation, contrôle qualité, préparation ML |

## 3. Données sources utilisées

| Élément              | Rôle                                       | Usage                                                        |
|----------------------|--------------------------------------------|                                                              |
| Fichiers CSV bruts   | Contenir les matchs historiques par ligue  | Source initiale du pipeline data                             |
| `league_code`        | Identifier la compétition                  | Distinguer Premier League, Ligue 1, Bundesliga, Serie A, Ligua
| `season`             | Identifier la saison sportive              | Contrôler la couverture historique                           |
| `match_date`         | Ordonner les matchs dans le temps          | Préparer les calculs chronologiques                          |
| `home_team`          | Identifier l’équipe à domicile             | Construire les signaux domicile                              |
| `away_team`          | Identifier l’équipe extérieure             | Construire les signaux extérieur                             |
| `home_goals`         | Stocker les buts de l’équipe domicile      | Calculer le résultat réel                                    |
| `away_goals`         | Stocker les buts de l’équipe extérieure    | Calculer le résultat réel                                    |
| `result`             | Stocker le résultat brut du match          | Préparer le label cible                                      |

## 4. Chaîne de nettoyage

| Étape | Action                                      | Résultat attendu                                      |
|-------|---------------------------------------------|-------------------------------------------------------|
| 1     | Charger les données depuis `ml.raw_matches` | Récupérer les matchs importés sans modifier la source |
| 2     | Vérifier les champs essentiels              | Identifier les lignes exploitables                    |
| 3     | Supprimer les lignes invalides              | Retirer les entrées corrompues ou incomplètes         |
| 4     | Normaliser les dates                        | Garantir un ordre chronologique fiable                |
| 5     | Normaliser les résultats                    | Obtenir des labels homogènes                          |
| 6     | Insérer dans `ml.clean_matches`             | Produire un dataset propre pour l’analyse             |

## 5. Règles de validation

| Règle                                      | Justification                                       |
|--------------------------------------------|-----------------------------------------------------|
| La date du match doit être exploitable     | Permettre le tri chronologique des matchs           |
| L’équipe à domicile doit être présente     | Identifier correctement le contexte domicile        |
| L’équipe extérieure doit être présente     | Identifier correctement le contexte extérieur       |
| Le score final doit être disponible        | Calculer ou vérifier le résultat du match           |
| Le résultat doit être interprétable        | Créer un label cible fiable                         |
| La ligue et la saison doivent être connues | Contrôler les volumes par compétition et par saison |

## 6. Règles de suppression

| Cas détecté | Action | Justification |
|-----------------------------|-------------------------|-----------------------------------------------------|
| Date absente ou invalide    | Suppression de la ligne | Le match ne peut pas être replacé dans l’historique |
| Équipe domicile absente     | Suppression de la ligne | Le match est inexploitable                          |
| Équipe extérieure absente   | Suppression de la ligne | Le match est inexploitable                          |
| Score final absent          | Suppression de la ligne | Le résultat réel ne peut pas être calculé           |
| Résultat non interprétable  | Suppression de la ligne | Le label cible serait incorrect                     |
| Ligne parasite ou corrompue | Suppression de la ligne | Éviter de fausser les volumes et les statistiques   |

## 7. Règles de normalisation

| Donnée brute    | Donnée normalisée                    | Usage                                  |
|-----------------|--------------------------------------|----------------------------------------|
| `H`             | `HOME_WIN`                           | Victoire de l’équipe à domicile        |
| `D`             | `DRAW`                               | Match nul                              |
| `A`             | `AWAY_WIN`                           | Victoire de l’équipe extérieure        |
| Date CSV        | Date PostgreSQL normalisée           | Tri chronologique fiable               |
| Code ligue brut | `E0`, `F1`, `D1`, `I1`, `SP1`        | Identification stable des championnats |
| Match brut      | Match propre dans `ml.clean_matches` | Exploitation analytique et ML          |

## 8. Contrôles qualité réalisés

| Contrôle | Rôle | Usage |
|---------------------------|-----------------------------------------|-------------------------------|
| Nombre de lignes brutes   | Mesurer le volume importé               | Vérifier la collecte          |
| Nombre de matchs propres  | Mesurer le volume exploitable           | Vérifier le nettoyage         |
| Volume par ligue          | Comparer les championnats               | Détecter les anomalies        |
| Volume par saison         | Contrôler la cohérence historique       | Vérifier la complétude        |
| Répartition des résultats | Observer `HOME_WIN`, `DRAW`, `AWAY_WIN` | Préparer l’analyse ML         |
| Valeurs manquantes        | Identifier les données incomplètes      | Évaluer la qualité du dataset |

## 9. Résultat actuel du nettoyage

| Élément                       | Résultat              |
|-------------------------------|-----------------------|
| Nombre de ligues              | 5                     |
| Période couverte              | 2000/2001 à 2024/2025 |
| Nombre de batches importés    | 125                   |
| Matchs propres Bundesliga     | 7 650                 |
| Matchs propres Premier League | 9 500                 |
| Matchs propres Ligue 1        | 9 103                 |
| Matchs propres Serie A        | 9 204                 |
| Matchs propres La Liga        | 9 500                 |
| Total de matchs propres       | 44 957                |

## 10. Répartition des résultats nettoyés

| Résultat   | Volume |
|------------|--------|
| `HOME_WIN` | 20 556 |
| `DRAW`     | 11 642 |
| `AWAY_WIN` | 12 759 |
| Total      | 44 957 |

## 11. Cas particulier identifié

| Élément                      | Description                             |
|------------------------------|-----------------------------------------|
| Fichier concerné             | `E0_2014_2015.csv`                      |
| Problème observé             | Une ligne parasite dans le fichier brut |
| Volume brut Premier League   | 9 501 lignes                            |
| Volume propre Premier League | 9 500 matchs                            |
| Décision                     | Supprimer la ligne non exploitable      |
| Justification                | Conserver un dataset propre et cohérent |

## 12. Règles liées au feature engineering

| Règle                                                                   | Justification                                       |
|-------------------------------------------------------------------------|-----------------------------------------------------|
| Utiliser uniquement les matchs antérieurs au match courant              | Éviter toute fuite de données                       |
| Ne jamais utiliser le score du match courant comme feature              | Garantir une logique ML correcte                    |
| Conserver le résultat du match courant uniquement comme `target_result` | Préparer l’entraînement futur                       |
| Accepter les valeurs `NULL` sur les premiers matchs                     | Certains matchs n’ont pas encore assez d’historique |
| Ajouter les matchs d’une même date à l’historique après                 | Éviter d’utiliser une information non disponible avant 
  calcul des features                                                       le match 

## 13. Règles importantes de qualité

| Règle                                              | Justification                                        |
|----------------------------------------------------|------------------------------------------------------|
| Conserver les données brutes dans `ml.raw_matches` | Permettre la traçabilité de la source                |
| Nettoyer les données dans `ml.clean_matches`       | Séparer les données sources des données exploitables |
| Documenter les règles de nettoyage                 | Rendre le pipeline défendable en soutenance          |
| Contrôler les volumes après nettoyage              | Prouver la qualité du dataset                        |
| Respecter l’ordre chronologique                    | Préparer un entraînement ML fiable                   |
| Ne pas masquer les données manquantes              | Garder une approche transparente et professionnelle  |

Cette organisation permet de relier les données brutes, les règles de nettoyage, les données propres et les futures features ML de manière claire et traçable.

<!-- RUBYBETS_ML_1X2_UPDATE_START -->

## Complement nettoyage - preparation ML 1X2

La baseline ML utilise uniquement les lignes dont les features rolling sont disponibles.

### Regles appliquees

1. Importer les donnees historiques Football-Data.co.uk dans `ml.raw_matches`.
2. Nettoyer les matchs exploitables dans `ml.clean_matches`.
3. Generer les variables rolling dans `ml.features`.
4. Exclure de l'entrainement les lignes qui possedent au moins une feature ML manquante parmi les 6 variables retenues.
5. Conserver `target_result` comme cible supervisee.
6. Utiliser un split chronologique pour eviter de tester le modele sur un passe deja vu.

### Resultat du nettoyage ML

| Etape | Nombre de lignes |
|---|---:|
| Dataset initial | 44 957 |
| Lignes supprimees pour valeurs manquantes | 337 |
| Dataset entrainable | 44 620 |

### Limite assumee

Les premieres rencontres de certaines equipes ou saisons peuvent manquer de contexte rolling suffisant. Leur exclusion est normale pour cette baseline, car le modele doit recevoir un vecteur de features complet.

<!-- RUBYBETS_ML_1X2_UPDATE_END -->

