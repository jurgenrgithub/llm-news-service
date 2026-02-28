-- Migration 005: Dimensions & Rounds Framework
-- Fantasy AFL Intelligence Platform - Phase 1
-- Adds: seasons, rounds, dimensions tables + extends article_tags

BEGIN;

-- ============================================
-- SEASONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS seasons (
    id SERIAL PRIMARY KEY,
    year INTEGER UNIQUE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure only one current season
CREATE UNIQUE INDEX IF NOT EXISTS idx_seasons_current
ON seasons (is_current) WHERE is_current = TRUE;

-- ============================================
-- ROUNDS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS rounds (
    id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    name VARCHAR(50),  -- "Round 1", "Finals Week 1", etc.
    start_date DATE,
    end_date DATE,
    lockout_time TIMESTAMPTZ,  -- When teams lock for fantasy
    is_finals BOOLEAN DEFAULT FALSE,
    is_bye_round BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(season_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_rounds_season ON rounds(season_id);
CREATE INDEX IF NOT EXISTS idx_rounds_dates ON rounds(start_date, end_date);

-- ============================================
-- DIMENSIONS TABLE
-- ============================================
-- 8 analytical dimensions (Tier 1-2) for fantasy intelligence
CREATE TABLE IF NOT EXISTS dimensions (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 5),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    prompt_guidance TEXT,  -- Instructions for LLM extraction
    keyword_mappings TEXT[],  -- Keywords that map to this dimension
    bespoke_feature_schema JSONB,  -- ML feature structure
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dimensions_tier ON dimensions(tier);
CREATE INDEX IF NOT EXISTS idx_dimensions_active ON dimensions(is_active) WHERE is_active = TRUE;

-- ============================================
-- SEED 8 CORE DIMENSIONS (Tier 1-2)
-- ============================================
INSERT INTO dimensions (code, name, tier, description, keyword_mappings, prompt_guidance) VALUES
-- Tier 1: Critical (biggest fantasy impact)
('injury_status', 'Injury Status', 1,
 'Current injury state, severity, and recovery timeline',
 ARRAY['injury', 'injured', 'hamstring', 'calf', 'shoulder', 'knee', 'ankle', 'concussion', 'ruled out', 'sidelined', 'miss', 'setback'],
 'Extract: injury type, body part, severity (minor/moderate/severe/season-ending), expected return (weeks or round), official club statement vs speculation'),

('fitness_health', 'Fitness & Health', 1,
 'General fitness, managed workloads, playing through issues',
 ARRAY['fitness', 'fatigue', 'soreness', 'managed', 'limited', 'training', 'rested'],
 'Extract: fitness level (full/limited/modified), any load management, training status, whether playing at 100%'),

('selection_security', 'Selection Security', 1,
 'Likelihood of being selected to play',
 ARRAY['selected', 'named', 'omitted', 'dropped', 'axed', 'recalled', 'debut', 'in for', 'out for', 'emergency'],
 'Extract: selection status (locked/likely/uncertain/unlikely/out), competition for spot, VFL/reserves status'),

('role_change', 'Role Change', 1,
 'Position or role changes affecting fantasy output',
 ARRAY['role', 'position', 'move', 'forward', 'midfield', 'defence', 'ruck', 'tag', 'tagging'],
 'Extract: current role, any role changes, position shifts, tagging assignments, TOG expectations'),

-- Tier 2: Important (significant fantasy relevance)
('form_trajectory', 'Form Trajectory', 2,
 'Recent performance trend and scoring patterns',
 ARRAY['form', 'scores', 'points', 'averaging', 'performance', 'disposal', 'best on ground', 'bog', 'struggling'],
 'Extract: form direction (hot/improving/stable/declining/cold), recent scores vs season average, standout stats'),

('captaincy_potential', 'Captaincy Potential', 2,
 'Suitability for fantasy captain selection',
 ARRAY['captain', 'premium', 'must-have', 'ceiling', 'floor', 'consistent'],
 'Extract: captaincy rating (1-10), ceiling potential, floor risk, consistency assessment'),

('load_management', 'Load Management', 2,
 'Minutes, rotations, and workload concerns',
 ARRAY['managed', 'rested', 'minutes', 'TOG', 'time on ground', 'rotations', 'quarter'],
 'Extract: expected TOG%, any planned rest, rotation patterns, game-time concerns'),

('coaching_sentiment', 'Coaching Sentiment', 2,
 'Coach comments and club messaging about player',
 ARRAY['coach', 'said', 'according to', 'club', 'statement', 'media'],
 'Extract: coach tone (positive/neutral/negative), key quotes, club confidence level')

ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    tier = EXCLUDED.tier,
    description = EXCLUDED.description,
    keyword_mappings = EXCLUDED.keyword_mappings,
    prompt_guidance = EXCLUDED.prompt_guidance;

-- ============================================
-- EXTEND ARTICLE_TAGS WITH DIMENSION_ID
-- ============================================
ALTER TABLE article_tags
ADD COLUMN IF NOT EXISTS dimension_id INTEGER REFERENCES dimensions(id);

CREATE INDEX IF NOT EXISTS idx_article_tags_dimension ON article_tags(dimension_id);

-- ============================================
-- ADD ROUND_ID TO ARTICLES
-- ============================================
ALTER TABLE articles
ADD COLUMN IF NOT EXISTS round_id INTEGER REFERENCES rounds(id);

CREATE INDEX IF NOT EXISTS idx_articles_round ON articles(round_id);

-- ============================================
-- SEED 2026 SEASON
-- ============================================
INSERT INTO seasons (year, is_current) VALUES (2026, TRUE)
ON CONFLICT (year) DO UPDATE SET is_current = TRUE;

-- AFL 2026 rounds (dates TBD - using placeholder dates)
-- Round 1 typically mid-March
INSERT INTO rounds (season_id, round_number, name, start_date, end_date, lockout_time)
SELECT
    s.id,
    r.round_number,
    CASE
        WHEN r.round_number <= 24 THEN 'Round ' || r.round_number
        ELSE 'Finals Week ' || (r.round_number - 24)
    END,
    '2026-03-13'::date + ((r.round_number - 1) * 7),
    '2026-03-15'::date + ((r.round_number - 1) * 7),
    ('2026-03-13'::date + ((r.round_number - 1) * 7) + TIME '19:00')::timestamptz
FROM seasons s
CROSS JOIN generate_series(1, 27) AS r(round_number)
WHERE s.year = 2026
ON CONFLICT (season_id, round_number) DO NOTHING;

-- ============================================
-- MIGRATE EXISTING KEYWORD TAGS TO DIMENSIONS
-- ============================================
-- Map existing keyword tags to their corresponding dimensions
UPDATE article_tags SET dimension_id = (
    SELECT d.id FROM dimensions d WHERE d.code = 'injury_status'
) WHERE tag_type = 'keyword' AND tag_value = 'injury' AND dimension_id IS NULL;

UPDATE article_tags SET dimension_id = (
    SELECT d.id FROM dimensions d WHERE d.code = 'fitness_health'
) WHERE tag_type = 'keyword' AND tag_value = 'return' AND dimension_id IS NULL;

UPDATE article_tags SET dimension_id = (
    SELECT d.id FROM dimensions d WHERE d.code = 'selection_security'
) WHERE tag_type = 'keyword' AND tag_value = 'selection' AND dimension_id IS NULL;

UPDATE article_tags SET dimension_id = (
    SELECT d.id FROM dimensions d WHERE d.code = 'form_trajectory'
) WHERE tag_type = 'keyword' AND tag_value = 'form' AND dimension_id IS NULL;

-- Trade spans multiple dimensions, default to selection_security
UPDATE article_tags SET dimension_id = (
    SELECT d.id FROM dimensions d WHERE d.code = 'selection_security'
) WHERE tag_type = 'keyword' AND tag_value = 'trade' AND dimension_id IS NULL;

UPDATE article_tags SET dimension_id = (
    SELECT d.id FROM dimensions d WHERE d.code = 'role_change'
) WHERE tag_type = 'keyword' AND tag_value = 'contract' AND dimension_id IS NULL;

-- ============================================
-- HELPER FUNCTION: Get current round
-- ============================================
CREATE OR REPLACE FUNCTION get_current_round()
RETURNS INTEGER AS $$
DECLARE
    current_round_id INTEGER;
BEGIN
    SELECT r.id INTO current_round_id
    FROM rounds r
    JOIN seasons s ON r.season_id = s.id
    WHERE s.is_current = TRUE
      AND r.start_date <= CURRENT_DATE
      AND r.end_date >= CURRENT_DATE;

    -- If no exact match, get the most recent round
    IF current_round_id IS NULL THEN
        SELECT r.id INTO current_round_id
        FROM rounds r
        JOIN seasons s ON r.season_id = s.id
        WHERE s.is_current = TRUE
          AND r.start_date <= CURRENT_DATE
        ORDER BY r.start_date DESC
        LIMIT 1;
    END IF;

    RETURN current_round_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- VIEW: Articles by round with dimension tags
-- ============================================
CREATE OR REPLACE VIEW v_articles_by_round AS
SELECT
    a.id AS article_id,
    a.title,
    a.url,
    a.source,
    a.published_at,
    r.round_number,
    r.name AS round_name,
    s.year AS season_year,
    COALESCE(
        json_agg(DISTINCT jsonb_build_object(
            'tag_type', t.tag_type,
            'tag_value', t.tag_value,
            'dimension', d.code,
            'is_headline', t.is_headline
        )) FILTER (WHERE t.id IS NOT NULL),
        '[]'
    ) AS tags
FROM articles a
LEFT JOIN rounds r ON a.round_id = r.id
LEFT JOIN seasons s ON r.season_id = s.id
LEFT JOIN article_tags t ON a.id = t.article_id
LEFT JOIN dimensions d ON t.dimension_id = d.id
GROUP BY a.id, a.title, a.url, a.source, a.published_at, r.round_number, r.name, s.year;

COMMIT;
