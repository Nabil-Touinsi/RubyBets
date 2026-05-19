-- Role du fichier : requetes SQL de preuve pour controler le pipeline data ML de RubyBets.
-- Objectif : prouver C2 avec des requetes utiles sur le schema ML.

-- 1) Controle des batches importes par ligue
SELECT
    league_code,
    COUNT(*) AS total_batches,
    SUM(row_count) AS total_raw_rows
FROM ml.import_batches
GROUP BY league_code
ORDER BY league_code;

-- 2) Controle des lignes brutes par ligue
SELECT
    ib.league_code,
    COUNT(rm.id) AS total_raw_matches
FROM ml.import_batches ib
JOIN ml.raw_matches rm ON rm.import_batch_id = ib.id
GROUP BY ib.league_code
ORDER BY ib.league_code;

-- 3) Controle des matchs nettoyes par ligue
SELECT
    league_code,
    COUNT(*) AS total_clean_matches
FROM ml.clean_matches
WHERE is_valid = true
GROUP BY league_code
ORDER BY league_code;

-- 4) Repartition globale des resultats
SELECT
    result,
    COUNT(*) AS total_matches
FROM ml.clean_matches
WHERE is_valid = true
GROUP BY result
ORDER BY total_matches DESC;

-- 5) Controle des features generees
SELECT
    COUNT(*) AS total_features,
    COUNT(target_result) AS total_targets,
    COUNT(*) - COUNT(home_form_points_last_5) AS home_form_nulls,
    COUNT(*) - COUNT(away_form_points_last_5) AS away_form_nulls,
    COUNT(*) - COUNT(home_goals_scored_avg_last_5) AS home_scored_nulls,
    COUNT(*) - COUNT(away_goals_scored_avg_last_5) AS away_scored_nulls,
    COUNT(*) - COUNT(home_goals_conceded_avg_last_5) AS home_conceded_nulls,
    COUNT(*) - COUNT(away_goals_conceded_avg_last_5) AS away_conceded_nulls
FROM ml.features;

-- 6) Controle des plages de forme recente
SELECT
    MIN(home_form_points_last_5) AS home_form_min,
    MAX(home_form_points_last_5) AS home_form_max,
    MIN(away_form_points_last_5) AS away_form_min,
    MAX(away_form_points_last_5) AS away_form_max
FROM ml.features
WHERE home_form_points_last_5 IS NOT NULL
  AND away_form_points_last_5 IS NOT NULL;

-- 7) Jointure entre matchs nettoyes et features
SELECT
    cm.league_code,
    cm.season,
    cm.match_date,
    cm.home_team,
    cm.away_team,
    f.home_form_points_last_5,
    f.away_form_points_last_5,
    f.target_result
FROM ml.clean_matches cm
JOIN ml.features f ON f.clean_match_id = cm.id
WHERE cm.is_valid = true
ORDER BY cm.match_date
LIMIT 20;

-- 8) Controle des executions de modeles
SELECT
    COUNT(*) AS total_model_runs
FROM ml.model_runs;