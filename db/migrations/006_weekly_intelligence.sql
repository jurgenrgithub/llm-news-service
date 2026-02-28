-- Migration 006: Weekly Intelligence Schema
-- Phase 2: Weekly Snapshots, Rolling Profiles, Weekly Verdicts

-- Weekly Snapshots: Per player-dimension-round summaries
CREATE TABLE IF NOT EXISTS weekly_snapshots (
    id SERIAL PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES entities(id),
    dimension_id INTEGER NOT NULL REFERENCES dimensions(id),
    round_id INTEGER NOT NULL REFERENCES rounds(id),

    -- Human-readable output
    summary TEXT NOT NULL,
    sentiment VARCHAR(20) CHECK (sentiment IN ('positive', 'negative', 'neutral', 'mixed')),
    signal_strength VARCHAR(20) CHECK (signal_strength IN ('strong', 'moderate', 'weak', 'none')),
    fantasy_impact TEXT,

    -- ML-ready features (dual-output)
    ml_features JSONB NOT NULL DEFAULT '{}',
    confidence DECIMAL(4,3) NOT NULL DEFAULT 0.5,

    -- Provenance
    article_count INTEGER NOT NULL DEFAULT 0,
    source_article_ids INTEGER[] NOT NULL DEFAULT '{}',
    model_version VARCHAR(50),
    generated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(entity_id, dimension_id, round_id)
);

-- Rolling Profiles: 3-4 week trend narratives
CREATE TABLE IF NOT EXISTS rolling_profiles (
    id SERIAL PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES entities(id),
    dimension_id INTEGER NOT NULL REFERENCES dimensions(id),

    -- Living narrative
    narrative TEXT NOT NULL,
    trend VARCHAR(20) NOT NULL DEFAULT 'stable'
        CHECK (trend IN ('improving', 'stable', 'declining', 'volatile')),
    trend_confidence DECIMAL(4,3) NOT NULL DEFAULT 0.5,

    -- Window info
    weeks_covered INTEGER NOT NULL DEFAULT 0,
    last_round_id INTEGER REFERENCES rounds(id),

    -- Aggregated ML features
    aggregated_features JSONB NOT NULL DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(entity_id, dimension_id)
);

-- Weekly Verdicts: Final player-round recommendations
CREATE TABLE IF NOT EXISTS weekly_verdicts (
    id SERIAL PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES entities(id),
    round_id INTEGER NOT NULL REFERENCES rounds(id),

    -- Captain recommendation
    captain_rating INTEGER NOT NULL DEFAULT 50 CHECK (captain_rating BETWEEN 0 AND 100),
    captain_reasoning TEXT,

    -- Risk assessment
    risk_level VARCHAR(10) NOT NULL DEFAULT 'medium'
        CHECK (risk_level IN ('low', 'medium', 'high', 'extreme')),
    risk_factors JSONB NOT NULL DEFAULT '[]',

    -- Trade signal
    trade_signal VARCHAR(10) NOT NULL DEFAULT 'hold'
        CHECK (trade_signal IN ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell')),
    trade_reasoning TEXT,

    -- ML features for verdict
    verdict_features JSONB NOT NULL DEFAULT '{}',
    confidence DECIMAL(4,3) NOT NULL DEFAULT 0.5,

    model_version VARCHAR(50),
    generated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(entity_id, round_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_weekly_snapshots_entity_round ON weekly_snapshots(entity_id, round_id);
CREATE INDEX IF NOT EXISTS idx_weekly_snapshots_dimension ON weekly_snapshots(dimension_id);
CREATE INDEX IF NOT EXISTS idx_rolling_profiles_entity ON rolling_profiles(entity_id);
CREATE INDEX IF NOT EXISTS idx_weekly_verdicts_round ON weekly_verdicts(round_id);
CREATE INDEX IF NOT EXISTS idx_weekly_verdicts_captain ON weekly_verdicts(captain_rating DESC);
