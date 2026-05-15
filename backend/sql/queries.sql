-- Rôle du fichier :
-- Ce fichier regroupe les requêtes SQL pour RubyBets.
-- Il permet de démontrer l’extraction, le filtrage, les jointures, les agrégations
-- et le contrôle des données stockées dans la base PostgreSQL du MVP.

-- Requête 1 :
-- Afficher les prochains matchs disponibles avec leur compétition et leurs équipes.
SELECT
    m.id AS match_id,
    m.external_id AS source_match_id,
    c.name AS competition_name,
    home.name AS home_team,
    away.name AS away_team,
    m.utc_date,
    m.status,
    m.data_freshness
FROM matches m
JOIN competitions c ON c.id = m.competition_id
JOIN teams home ON home.id = m.home_team_id
JOIN teams away ON away.id = m.away_team_id
WHERE m.utc_date >= CURRENT_TIMESTAMP
ORDER BY m.utc_date ASC;


-- Requête 2 :
-- Filtrer les matchs par compétition afin de prouver la navigation par ligue.
SELECT
    c.code AS competition_code,
    c.name AS competition_name,
    m.external_id AS source_match_id,
    home.name AS home_team,
    away.name AS away_team,
    m.utc_date,
    m.status
FROM matches m
JOIN competitions c ON c.id = m.competition_id
JOIN teams home ON home.id = m.home_team_id
JOIN teams away ON away.id = m.away_team_id
WHERE c.code = 'PL'
ORDER BY m.utc_date ASC;


-- Requête 3 :
-- Compter le nombre de matchs stockés par compétition.
SELECT
    c.code AS competition_code,
    c.name AS competition_name,
    COUNT(m.id) AS total_matches
FROM competitions c
LEFT JOIN matches m ON m.competition_id = c.id
GROUP BY c.code, c.name
ORDER BY total_matches DESC;


-- Requête 4 :
-- Afficher les prédictions générées pour chaque match.
SELECT
    m.external_id AS source_match_id,
    home.name AS home_team,
    away.name AS away_team,
    p.market_type,
    p.predicted_value,
    p.confidence_level,
    p.risk_level,
    p.score,
    p.engine_version,
    p.generated_at
FROM predictions p
JOIN matches m ON m.id = p.match_id
JOIN teams home ON home.id = m.home_team_id
JOIN teams away ON away.id = m.away_team_id
ORDER BY p.generated_at DESC;


-- Requête 5 :
-- Agréger les prédictions par niveau de risque.
SELECT
    p.risk_level,
    COUNT(p.id) AS total_predictions
FROM predictions p
GROUP BY p.risk_level
ORDER BY total_predictions DESC;


-- Requête 6 :
-- Identifier les matchs stockés qui n’ont pas encore de prédiction.
SELECT
    m.id AS match_id,
    m.external_id AS source_match_id,
    c.code AS competition_code,
    home.name AS home_team,
    away.name AS away_team,
    m.utc_date
FROM matches m
JOIN competitions c ON c.id = m.competition_id
JOIN teams home ON home.id = m.home_team_id
JOIN teams away ON away.id = m.away_team_id
LEFT JOIN predictions p ON p.match_id = m.id
WHERE p.id IS NULL
ORDER BY m.utc_date ASC;


-- Requête 7 :
-- Afficher le détail des recommandations multi-matchs générées.
SELECT
    r.id AS recommendation_id,
    r.risk_profile,
    r.match_count,
    r.generated_at,
    ri.position,
    p.market_type,
    p.predicted_value,
    p.confidence_level,
    p.risk_level,
    home.name AS home_team,
    away.name AS away_team
FROM recommendations r
JOIN recommendation_items ri ON ri.recommendation_id = r.id
JOIN predictions p ON p.id = ri.prediction_id
JOIN matches m ON m.id = p.match_id
JOIN teams home ON home.id = m.home_team_id
JOIN teams away ON away.id = m.away_team_id
ORDER BY r.generated_at DESC, ri.position ASC;


-- Requête 8 :
-- Vérifier les éventuels doublons issus des identifiants externes API.
SELECT
    'competitions' AS table_name,
    external_id,
    COUNT(*) AS duplicate_count
FROM competitions
GROUP BY external_id
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'teams' AS table_name,
    external_id,
    COUNT(*) AS duplicate_count
FROM teams
GROUP BY external_id
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'matches' AS table_name,
    external_id,
    COUNT(*) AS duplicate_count
FROM matches
GROUP BY external_id
HAVING COUNT(*) > 1;


-- Schéma de communication :
-- database/schema/schema.sql
--        ↓
-- rubybets_db PostgreSQL
--        ↓
-- backend/sql/queries.sql
--        ↓
-- preuves RNCP C2 / C4
--        ↓
-- docs + reports/evidence