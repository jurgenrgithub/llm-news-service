-- Migration: Deep Article Processing Pipeline
-- Creates articles cache, article_entities triage table, and extends extraction_events

-- Articles cache table (24-hour TTL)
CREATE TABLE IF NOT EXISTS articles (
    id BIGSERIAL PRIMARY KEY,
    url_hash VARCHAR(64) NOT NULL UNIQUE,
    content_hash VARCHAR(64) NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source VARCHAR(100),
    author VARCHAR(200),
    published_at TIMESTAMPTZ,
    triage_status VARCHAR(20) DEFAULT 'pending',
    triage_at TIMESTAMPTZ,
    analysis_status VARCHAR(20) DEFAULT 'pending',
    analysis_at TIMESTAMPTZ,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles(url_hash);
CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_articles_triage ON articles(triage_status) WHERE triage_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_articles_expires ON articles(expires_at);

-- Article entities (triage results - many-to-many)
CREATE TABLE IF NOT EXISTS article_entities (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    entity_id UUID REFERENCES entities(id),
    entity_name VARCHAR(200) NOT NULL,
    entity_type VARCHAR(50),
    mention_count INTEGER DEFAULT 1,
    is_primary_subject BOOLEAN DEFAULT FALSE,
    mention_context VARCHAR(50),
    needs_deep_analysis BOOLEAN DEFAULT FALSE,
    analysis_completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(article_id, entity_name)
);

CREATE INDEX IF NOT EXISTS idx_article_entities_article ON article_entities(article_id);
CREATE INDEX IF NOT EXISTS idx_article_entities_entity ON article_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_article_entities_pending ON article_entities(needs_deep_analysis)
    WHERE needs_deep_analysis = TRUE AND analysis_completed = FALSE;

-- Add columns to extraction_events for article linking
ALTER TABLE extraction_events ADD COLUMN IF NOT EXISTS article_id BIGINT REFERENCES articles(id);
ALTER TABLE extraction_events ADD COLUMN IF NOT EXISTS article_entity_id BIGINT REFERENCES article_entities(id);
ALTER TABLE extraction_events ADD COLUMN IF NOT EXISTS key_quotes JSONB;
ALTER TABLE extraction_events ADD COLUMN IF NOT EXISTS injury_severity VARCHAR(20);
ALTER TABLE extraction_events ADD COLUMN IF NOT EXISTS return_round INTEGER;

CREATE INDEX IF NOT EXISTS idx_events_article ON extraction_events(article_id);
