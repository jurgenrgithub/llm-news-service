-- LLM News Service: Initial Schema
-- Migration 001

-- Entity registry
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain VARCHAR(50) NOT NULL,           -- 'afl', 'market'
    entity_type VARCHAR(50) NOT NULL,      -- 'player', 'team', 'asset'
    canonical_name VARCHAR(255) NOT NULL,
    external_id VARCHAR(100),              -- AFL player ID, ticker symbol
    attributes JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(domain, entity_type, canonical_name)
);

-- Entity aliases for resolution
CREATE TABLE entity_aliases (
    id SERIAL PRIMARY KEY,
    entity_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    alias VARCHAR(255) NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    source VARCHAR(100),                   -- 'manual', 'llm_learned'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(alias, entity_id)
);
CREATE INDEX idx_aliases_alias ON entity_aliases(LOWER(alias));

-- Extraction events (immutable log)
CREATE TABLE extraction_events (
    id BIGSERIAL PRIMARY KEY,
    domain VARCHAR(50) NOT NULL,
    schema_type VARCHAR(50) NOT NULL,      -- 'injury', 'sentiment', etc.
    article_hash VARCHAR(64) NOT NULL,     -- SHA256 of headline+source
    headline TEXT NOT NULL,
    source VARCHAR(255),
    source_url TEXT,
    published_at TIMESTAMPTZ,
    extracted_data JSONB NOT NULL,         -- The LLM extraction result
    entities_mentioned UUID[],             -- Array of entity IDs
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_events_domain ON extraction_events(domain, created_at DESC);
CREATE INDEX idx_events_entities ON extraction_events USING GIN(entities_mentioned);
CREATE UNIQUE INDEX idx_events_article ON extraction_events(article_hash);

-- Materialized current state (CQRS read model)
CREATE TABLE entity_current_state (
    entity_id UUID PRIMARY KEY REFERENCES entities(id),
    domain VARCHAR(50) NOT NULL,
    state JSONB NOT NULL,                  -- Current computed state
    last_event_id BIGINT,
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Extraction cache (dedup LLM calls)
CREATE TABLE extraction_cache (
    cache_key VARCHAR(64) PRIMARY KEY,     -- SHA256 of prompt
    response JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_cache_expires ON extraction_cache(expires_at);

-- Migration tracking
CREATE TABLE IF NOT EXISTS _migrations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO _migrations (name) VALUES ('001_initial_schema');
