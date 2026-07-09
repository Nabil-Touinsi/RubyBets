-- Ce fichier crée le schéma SQL initial de RubyBets pour stocker les compétitions,
-- équipes, matchs, prédictions, recommandations et archives de prédictions du MVP.

BEGIN;

CREATE TABLE IF NOT EXISTS competitions (
    id SERIAL PRIMARY KEY,
    external_id INTEGER NOT NULL UNIQUE,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    country VARCHAR(100),
    season VARCHAR(20),
    source VARCHAR(100) NOT NULL DEFAULT 'football-data.org',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    external_id INTEGER NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    short_name VARCHAR(100),
    tla VARCHAR(10),
    crest_url TEXT,
    country VARCHAR(100),
    source VARCHAR(100) NOT NULL DEFAULT 'football-data.org',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    external_id INTEGER NOT NULL UNIQUE,
    competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE RESTRICT,
    home_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
    away_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
    utc_date TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL,
    matchday INTEGER,
    stage VARCHAR(100),
    source VARCHAR(100) NOT NULL DEFAULT 'football-data.org',
    data_freshness VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    market_type VARCHAR(20) NOT NULL,
    predicted_value VARCHAR(100) NOT NULL,
    confidence_level VARCHAR(20) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    score NUMERIC(6, 2),
    justification TEXT,
    engine_version VARCHAR(100) NOT NULL DEFAULT 'rules_based_scoring_v1',
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_predictions_market_type CHECK (market_type IN ('1X2', 'GOALS', 'BTTS')),
    CONSTRAINT chk_predictions_confidence CHECK (confidence_level IN ('low', 'medium', 'high')),
    CONSTRAINT chk_predictions_risk CHECK (risk_level IN ('low', 'medium', 'high')),
    CONSTRAINT uq_prediction_match_market UNIQUE (match_id, market_type)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id SERIAL PRIMARY KEY,
    risk_profile VARCHAR(20) NOT NULL,
    match_count INTEGER NOT NULL,
    global_rationale TEXT,
    engine_version VARCHAR(100) NOT NULL DEFAULT 'rules_based_multimatch_selection_v1',
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_recommendations_risk_profile CHECK (risk_profile IN ('low', 'medium', 'high')),
    CONSTRAINT chk_recommendations_match_count CHECK (match_count > 0)
);

CREATE TABLE IF NOT EXISTS recommendation_items (
    id SERIAL PRIMARY KEY,
    recommendation_id INTEGER NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    prediction_id INTEGER NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    selection_reason TEXT,
    CONSTRAINT chk_recommendation_items_position CHECK (position > 0),
    CONSTRAINT uq_recommendation_prediction UNIQUE (recommendation_id, prediction_id)
);

-- Table des archives de prédictions RubyBets.
-- Elle conserve un snapshot des prédictions générées afin de les comparer plus tard au score final.
CREATE TABLE IF NOT EXISTS archived_predictions (
    id SERIAL PRIMARY KEY,

    match_id INTEGER REFERENCES matches(id) ON DELETE SET NULL,
    prediction_id INTEGER REFERENCES predictions(id) ON DELETE SET NULL,

    rubybets_match_id VARCHAR(100) NOT NULL,
    source_match_id VARCHAR(100),

    competition_name VARCHAR(150),
    home_team_name VARCHAR(150) NOT NULL,
    away_team_name VARCHAR(150) NOT NULL,

    home_team_logo_url TEXT,
    away_team_logo_url TEXT,
    home_team_country_code VARCHAR(10),
    away_team_country_code VARCHAR(10),

    match_date TIMESTAMP,
    prediction_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    market_type VARCHAR(50) NOT NULL,
    predicted_value VARCHAR(100) NOT NULL,
    confidence_level VARCHAR(20),
    risk_level VARCHAR(20),
    justification TEXT,
    engine_version VARCHAR(150) NOT NULL,

    final_home_score INTEGER,
    final_away_score INTEGER,
    match_status VARCHAR(50) NOT NULL DEFAULT 'scheduled',

    verdict VARCHAR(30) NOT NULL DEFAULT 'pending',
    checked_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_archived_predictions_confidence
        CHECK (confidence_level IS NULL OR confidence_level IN ('low', 'medium', 'high')),

    CONSTRAINT chk_archived_predictions_risk
        CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high')),

    CONSTRAINT chk_archived_predictions_verdict
        CHECK (verdict IN ('pending', 'correct', 'incorrect', 'not_verifiable'))
);

CREATE INDEX IF NOT EXISTS idx_matches_utc_date ON matches(utc_date);
CREATE INDEX IF NOT EXISTS idx_matches_competition_id ON matches(competition_id);
CREATE INDEX IF NOT EXISTS idx_predictions_match_id ON predictions(match_id);
CREATE INDEX IF NOT EXISTS idx_predictions_risk_level ON predictions(risk_level);
CREATE INDEX IF NOT EXISTS idx_recommendations_generated_at ON recommendations(generated_at);
CREATE INDEX IF NOT EXISTS idx_archived_predictions_rubybets_match_id
ON archived_predictions(rubybets_match_id);

CREATE INDEX IF NOT EXISTS idx_archived_predictions_market_type
ON archived_predictions(market_type);

CREATE INDEX IF NOT EXISTS idx_archived_predictions_verdict
ON archived_predictions(verdict);

CREATE INDEX IF NOT EXISTS idx_archived_predictions_prediction_date
ON archived_predictions(prediction_date);

CREATE INDEX IF NOT EXISTS idx_archived_predictions_match_status
ON archived_predictions(match_status);

CREATE INDEX IF NOT EXISTS idx_archived_predictions_competition_name
ON archived_predictions(competition_name);
COMMIT;

-- Schéma de communication :
-- Football-Data.org / cache backend
--        ↓
-- competitions / teams / matches
--        ↓
-- predictions
--        ↓
-- archived_predictions
--        ↓
-- recommendations / recommendation_items
--        ↓
-- backend FastAPI → frontend React