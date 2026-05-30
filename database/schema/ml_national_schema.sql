-- Rôle du fichier :
-- Ce script crée une couche SQL séparée pour les matchs d'équipes nationales.
-- Il permet d'importer, nettoyer et préparer les données Coupe du Monde sans modifier le pipeline ML club existant.

CREATE SCHEMA IF NOT EXISTS ml_national;

-- Table des matchs nationaux bruts récupérés depuis une source externe.
CREATE TABLE IF NOT EXISTS ml_national.raw_matches (
    id BIGSERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,
    source_match_id VARCHAR(100) NOT NULL,
    competition_code VARCHAR(20) NOT NULL,
    competition_name VARCHAR(150),
    season VARCHAR(50),
    match_date_utc TIMESTAMPTZ,
    stage VARCHAR(100),
    group_name VARCHAR(100),
    home_team_name VARCHAR(150),
    away_team_name VARCHAR(150),
    home_score INTEGER,
    away_score INTEGER,
    match_status VARCHAR(50),
    is_neutral_venue BOOLEAN DEFAULT TRUE,
    raw_payload JSONB,
    source_updated_at TIMESTAMPTZ,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ml_national_raw_match_source UNIQUE (source_name, source_match_id)
);

-- Table des matchs nationaux nettoyés et normalisés.
CREATE TABLE IF NOT EXISTS ml_national.clean_matches (
    id BIGSERIAL PRIMARY KEY,
    raw_match_id BIGINT REFERENCES ml_national.raw_matches(id) ON DELETE SET NULL,
    competition_code VARCHAR(20) NOT NULL,
    competition_name VARCHAR(150),
    season VARCHAR(50),
    match_date_utc TIMESTAMPTZ NOT NULL,
    stage VARCHAR(100),
    group_name VARCHAR(100),
    home_team_name VARCHAR(150) NOT NULL,
    away_team_name VARCHAR(150) NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    result_1x2 VARCHAR(20),
    is_neutral_venue BOOLEAN DEFAULT TRUE,
    team_a_is_host BOOLEAN DEFAULT FALSE,
    team_b_is_host BOOLEAN DEFAULT FALSE,
    host_advantage_side VARCHAR(20) DEFAULT 'NONE',
    is_group_stage BOOLEAN DEFAULT FALSE,
    is_knockout_stage BOOLEAN DEFAULT FALSE,
    data_quality_status VARCHAR(50) DEFAULT 'cleaned',
    cleaned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table des features nationales prêtes pour les futures expérimentations ML.
CREATE TABLE IF NOT EXISTS ml_national.features (
    id BIGSERIAL PRIMARY KEY,
    clean_match_id BIGINT NOT NULL REFERENCES ml_national.clean_matches(id) ON DELETE CASCADE,
    feature_version VARCHAR(50) NOT NULL DEFAULT 'national_v1',
    team_type VARCHAR(50) NOT NULL DEFAULT 'national',

    home_form_points_last_5 NUMERIC(6, 3),
    away_form_points_last_5 NUMERIC(6, 3),
    home_form_points_last_10 NUMERIC(6, 3),
    away_form_points_last_10 NUMERIC(6, 3),

    home_goals_scored_avg_last_10 NUMERIC(6, 3),
    away_goals_scored_avg_last_10 NUMERIC(6, 3),
    home_goals_conceded_avg_last_10 NUMERIC(6, 3),
    away_goals_conceded_avg_last_10 NUMERIC(6, 3),

    ranking_gap NUMERIC(8, 3),
    elo_gap NUMERIC(8, 3),

    is_neutral_venue BOOLEAN DEFAULT TRUE,
    team_a_is_host BOOLEAN DEFAULT FALSE,
    team_b_is_host BOOLEAN DEFAULT FALSE,
    host_advantage_side VARCHAR(20) DEFAULT 'NONE',
    is_group_stage BOOLEAN DEFAULT FALSE,
    is_knockout_stage BOOLEAN DEFAULT FALSE,

    target_result VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ml_national_features_match_version UNIQUE (clean_match_id, feature_version)
);

-- Table des classements ou scores de niveau des équipes nationales.
CREATE TABLE IF NOT EXISTS ml_national.team_rankings (
    id BIGSERIAL PRIMARY KEY,
    team_name VARCHAR(150) NOT NULL,
    ranking_source VARCHAR(100) NOT NULL,
    ranking_date DATE NOT NULL,
    rank_position INTEGER,
    rating_value NUMERIC(10, 3),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ml_national_team_ranking UNIQUE (team_name, ranking_source, ranking_date)
);

-- Table des métadonnées de compétitions internationales.
CREATE TABLE IF NOT EXISTS ml_national.competition_metadata (
    id BIGSERIAL PRIMARY KEY,
    competition_code VARCHAR(20) NOT NULL,
    competition_name VARCHAR(150) NOT NULL,
    season VARCHAR(50),
    tournament_type VARCHAR(100),
    host_country VARCHAR(150),
    start_date DATE,
    end_date DATE,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ml_national_competition_metadata UNIQUE (competition_code, season)
);

CREATE INDEX IF NOT EXISTS idx_ml_national_raw_matches_competition
ON ml_national.raw_matches (competition_code);

CREATE INDEX IF NOT EXISTS idx_ml_national_clean_matches_competition_date
ON ml_national.clean_matches (competition_code, match_date_utc);

CREATE INDEX IF NOT EXISTS idx_ml_national_features_clean_match
ON ml_national.features (clean_match_id);

CREATE INDEX IF NOT EXISTS idx_ml_national_team_rankings_team_date
ON ml_national.team_rankings (team_name, ranking_date);

-- Schéma de communication :
-- Football-Data / source externe
--        ↓
-- ml_national.raw_matches
--        ↓
-- ml_national.clean_matches
--        ↓
-- ml_national.features
--        ↓
-- futur candidat ML V17.9 / moteur national RubyBets