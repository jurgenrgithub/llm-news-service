-- Migration 004: Article Tags for deterministic indexing
-- Enables fast entity/keyword lookups without scanning article bodies

BEGIN;

-- Article tags table - denormalized for fast queries
CREATE TABLE IF NOT EXISTS article_tags (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    tag_type VARCHAR(20) NOT NULL,           -- 'player', 'team', 'keyword'
    tag_value VARCHAR(100) NOT NULL,         -- canonical name or keyword
    entity_id UUID REFERENCES entities(id),  -- NULL for keywords
    match_text VARCHAR(200),                 -- actual text that matched
    match_count INTEGER DEFAULT 1,           -- times matched in article
    is_headline BOOLEAN DEFAULT FALSE,       -- matched in title
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate tags
    UNIQUE(article_id, tag_type, tag_value)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_article_tags_entity ON article_tags(entity_id) WHERE entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_article_tags_type_value ON article_tags(tag_type, tag_value);
CREATE INDEX IF NOT EXISTS idx_article_tags_article ON article_tags(article_id);
CREATE INDEX IF NOT EXISTS idx_article_tags_headline ON article_tags(article_id) WHERE is_headline = TRUE;

-- Add indexed_at column to articles table for tracking
ALTER TABLE articles ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_articles_not_indexed ON articles(id) WHERE indexed_at IS NULL;

COMMIT;
