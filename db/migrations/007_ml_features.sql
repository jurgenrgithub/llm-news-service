-- Migration 007: ML Features Table
-- Flattened ML-ready features extracted from weekly intelligence
-- For export to FantasyEdge ML pipeline

CREATE TABLE ml_weekly_features (
    id SERIAL PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES entities(id),
    round_id INTEGER NOT NULL REFERENCES rounds(id),

    -- Flattened dimension features (8 dimensions x 3 metrics each)
    -- Injury Status
    injury_mentioned BOOLEAN DEFAULT FALSE,
    injury_sentiment DECIMAL(4,3),      -- 0 to 1
    injury_signal DECIMAL(4,3),         -- 0 to 1 (strength)

    -- Fitness & Health
    fitness_mentioned BOOLEAN DEFAULT FALSE,
    fitness_sentiment DECIMAL(4,3),
    fitness_signal DECIMAL(4,3),

    -- Selection Security
    selection_mentioned BOOLEAN DEFAULT FALSE,
    selection_sentiment DECIMAL(4,3),
    selection_signal DECIMAL(4,3),

    -- Role Change
    role_mentioned BOOLEAN DEFAULT FALSE,
    role_sentiment DECIMAL(4,3),
    role_signal DECIMAL(4,3),

    -- Form Trajectory
    form_mentioned BOOLEAN DEFAULT FALSE,
    form_sentiment DECIMAL(4,3),
    form_signal DECIMAL(4,3),

    -- Captaincy Potential
    captaincy_mentioned BOOLEAN DEFAULT FALSE,
    captaincy_sentiment DECIMAL(4,3),
    captaincy_signal DECIMAL(4,3),

    -- Load Management
    load_mentioned BOOLEAN DEFAULT FALSE,
    load_sentiment DECIMAL(4,3),
    load_signal DECIMAL(4,3),

    -- Coaching Sentiment
    coaching_mentioned BOOLEAN DEFAULT FALSE,
    coaching_sentiment DECIMAL(4,3),
    coaching_signal DECIMAL(4,3),

    -- Aggregated verdict features (from weekly_verdicts)
    captain_rating INTEGER,             -- 0-100
    risk_level VARCHAR(10),             -- low/medium/high/extreme
    trade_signal VARCHAR(15),           -- strong_buy/buy/hold/sell/strong_sell

    -- ML-ready verdict scores
    injury_risk_score DECIMAL(4,3),     -- 0 to 1
    form_score DECIMAL(4,3),            -- 0 to 1
    selection_certainty DECIMAL(4,3),   -- 0 to 1
    upside_potential DECIMAL(4,3),      -- 0 to 1
    floor_safety DECIMAL(4,3),          -- 0 to 1

    -- Overall aggregates
    total_article_count INTEGER DEFAULT 0,
    overall_sentiment DECIMAL(4,3),     -- weighted avg across dimensions
    overall_signal_strength DECIMAL(4,3),
    confidence DECIMAL(4,3),

    generated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(entity_id, round_id)
);

-- Indexes for fast queries
CREATE INDEX idx_ml_features_round ON ml_weekly_features(round_id);
CREATE INDEX idx_ml_features_entity ON ml_weekly_features(entity_id);

-- Materialized view for flat feature export (joins with entity/round info)
CREATE MATERIALIZED VIEW ml_feature_export AS
SELECT
    e.canonical_name as player_name,
    e.external_id as player_external_id,
    r.round_number,
    s.year as season,
    mf.*
FROM ml_weekly_features mf
JOIN entities e ON mf.entity_id = e.id
JOIN rounds r ON mf.round_id = r.id
JOIN seasons s ON r.season_id = s.id
ORDER BY s.year, r.round_number, e.canonical_name;

-- Create index on materialized view
CREATE UNIQUE INDEX idx_ml_feature_export_pk ON ml_feature_export(id);
