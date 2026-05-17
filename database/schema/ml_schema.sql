-- Rôle du fichier :
-- Ce fichier crée la zone Machine Learning de RubyBets.
-- Elle sert à stocker les datasets historiques, les matchs nettoyés,
-- les features avant-match et les résultats d'entraînement du modèle.

CREATE SCHEMA IF NOT EXISTS ml;

CREATE TABLE IF NOT EXISTS ml.import_batches (
    id BIGSERIAL PRIMARY KEY,
    league_code VARCHAR(20) NOT NULL,
    season VARCHAR(20) NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    source_url TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    row_count INTEGER DEFAULT 0,
    status VARCHAR(30) DEFAULT 'imported',
    notes TEXT,

    CONSTRAINT chk_import_batches_status
        CHECK (status IN ('imported', 'cleaned', 'failed'))
);

CREATE TABLE IF NOT EXISTS ml.raw_matches (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,
    raw_date VARCHAR(50),
    raw_home_team VARCHAR(150),
    raw_away_team VARCHAR(150),
    raw_home_goals INTEGER,
    raw_away_goals INTEGER,
    raw_result VARCHAR(10),
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_raw_matches_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES ml.import_batches(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ml.clean_matches (
    id BIGSERIAL PRIMARY KEY,
    raw_match_id BIGINT NOT NULL,
    match_date DATE NOT NULL,
    league_code VARCHAR(20) NOT NULL,
    season VARCHAR(20) NOT NULL,
    home_team VARCHAR(150) NOT NULL,
    away_team VARCHAR(150) NOT NULL,
    home_goals INTEGER NOT NULL,
    away_goals INTEGER NOT NULL,
    result VARCHAR(20) NOT NULL,
    is_valid BOOLEAN DEFAULT TRUE,
    cleaned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_clean_matches_raw_match
        FOREIGN KEY (raw_match_id)
        REFERENCES ml.raw_matches(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_clean_matches_result
        CHECK (result IN ('HOME_WIN', 'DRAW', 'AWAY_WIN'))
);

CREATE TABLE IF NOT EXISTS ml.features (
    id BIGSERIAL PRIMARY KEY,
    clean_match_id BIGINT NOT NULL,

    home_form_points_last_5 NUMERIC(5,2),
    away_form_points_last_5 NUMERIC(5,2),

    home_goals_scored_avg_last_5 NUMERIC(5,2),
    away_goals_scored_avg_last_5 NUMERIC(5,2),

    home_goals_conceded_avg_last_5 NUMERIC(5,2),
    away_goals_conceded_avg_last_5 NUMERIC(5,2),

    home_advantage INTEGER DEFAULT 1,
    target_result VARCHAR(20) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_features_clean_match
        FOREIGN KEY (clean_match_id)
        REFERENCES ml.clean_matches(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_features_target_result
        CHECK (target_result IN ('HOME_WIN', 'DRAW', 'AWAY_WIN'))
);

CREATE TABLE IF NOT EXISTS ml.model_runs (
    id BIGSERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    target VARCHAR(50) NOT NULL,
    dataset_version VARCHAR(100),
    training_rows INTEGER NOT NULL,
    test_rows INTEGER NOT NULL,
    accuracy NUMERIC(6,4),
    f1_score NUMERIC(6,4),
    precision_score NUMERIC(6,4),
    recall_score NUMERIC(6,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_raw_matches_import_batch
    ON ml.raw_matches(import_batch_id);

CREATE INDEX IF NOT EXISTS idx_clean_matches_date
    ON ml.clean_matches(match_date);

CREATE INDEX IF NOT EXISTS idx_clean_matches_league_season
    ON ml.clean_matches(league_code, season);

CREATE INDEX IF NOT EXISTS idx_features_clean_match
    ON ml.features(clean_match_id);

CREATE INDEX IF NOT EXISTS idx_model_runs_target
    ON ml.model_runs(target);

-- Schéma de communication :
-- CSV Football-Data.co.uk
--        ↓
-- ml.import_batches
--        ↓
-- ml.raw_matches
--        ↓
-- ml.clean_matches
--        ↓
-- ml.features
--        ↓
-- ml.model_runs