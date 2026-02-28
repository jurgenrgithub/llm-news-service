"""Two-phase article processing pipeline."""

import hashlib
import json
import re
from typing import List, Optional, Dict

from core.database import get_cursor
from core.claude_client import ClaudeClient
from core.article_indexer import index_article


class ArticleProcessor:
    """Orchestrates article ingestion and processing."""

    def __init__(self, claude_client: ClaudeClient = None):
        self.claude = claude_client
        self._player_patterns = None  # Lazy loaded

    # === INGESTION ===

    def ingest_article(
        self,
        url: str,
        title: str,
        body: str,
        source: str = None,
        published_at: str = None,
    ) -> Optional[Dict]:
        """
        Ingest article into cache. Returns article record or None if duplicate.
        Indexes article immediately for fast entity/keyword lookups.
        """
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        content_hash = hashlib.sha256(body.encode()).hexdigest()

        with get_cursor() as cursor:
            # Check for existing (by URL or content)
            cursor.execute(
                """SELECT id, content_hash FROM articles
                   WHERE url_hash = %s AND expires_at > NOW()""",
                (url_hash,)
            )
            existing = cursor.fetchone()

            if existing:
                # Same URL, check if content changed
                if existing["content_hash"] == content_hash:
                    return None  # Duplicate, skip
                # Content changed - update and re-index
                cursor.execute(
                    """UPDATE articles SET body = %s, content_hash = %s,
                       triage_status = 'pending', analysis_status = 'pending',
                       indexed_at = NULL,
                       scraped_at = NOW(), expires_at = NOW() + INTERVAL '7 days'
                       WHERE id = %s RETURNING *""",
                    (body, content_hash, existing["id"])
                )
                result = cursor.fetchone()
                if result:
                    index_article(result['id'], title, body)
                return result

            # New article
            cursor.execute(
                """INSERT INTO articles
                   (url_hash, content_hash, url, title, body, source, published_at, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW() + INTERVAL '7 days')
                   RETURNING *""",
                (url_hash, content_hash, url, title, body, source, published_at)
            )
            result = cursor.fetchone()

        # Index immediately after insert (outside transaction for isolation)
        if result:
            index_article(result['id'], title, body)

        return result

    # === PHASE 1: TRIAGE ===

    def run_triage_batch(self, batch_size: int = 50) -> int:
        """Process pending articles through triage. Returns count processed."""
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT * FROM articles
                   WHERE triage_status = 'pending'
                   ORDER BY scraped_at LIMIT %s""",
                (batch_size,)
            )
            articles = cursor.fetchall()

        processed = 0
        for article in articles:
            self._triage_article(article)
            processed += 1

        return processed

    def _triage_article(self, article: Dict):
        """
        Phase 1: Fast entity identification.
        - Regex match against known players/teams
        - Detect context (injury keywords, trade keywords)
        - Flag entities needing deep analysis
        """
        text = f"{article['title']} {article['body']}"
        entities_found = []

        # Load player patterns if not cached
        if self._player_patterns is None:
            self._load_player_patterns()

        # Match players
        for pattern, entity_id, canonical_name in self._player_patterns:
            matches = pattern.findall(text)
            if matches:
                context = self._detect_context(text, canonical_name)
                needs_analysis = context in ('injury', 'trade', 'selection', 'return')

                entities_found.append({
                    "entity_id": entity_id,
                    "entity_name": canonical_name,
                    "entity_type": "player",
                    "mention_count": len(matches),
                    "is_primary": canonical_name.lower() in article['title'].lower(),
                    "context": context,
                    "needs_analysis": needs_analysis,
                })

        # Store triage results
        with get_cursor() as cursor:
            for ent in entities_found:
                cursor.execute(
                    """INSERT INTO article_entities
                       (article_id, entity_id, entity_name, entity_type,
                        mention_count, is_primary_subject, mention_context, needs_deep_analysis)
                       VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (article_id, entity_name) DO UPDATE
                       SET mention_count = EXCLUDED.mention_count,
                           needs_deep_analysis = EXCLUDED.needs_deep_analysis""",
                    (article['id'], ent['entity_id'], ent['entity_name'], ent['entity_type'],
                     ent['mention_count'], ent['is_primary'], ent['context'], ent['needs_analysis'])
                )

            # Mark triage complete
            cursor.execute(
                """UPDATE articles SET triage_status = 'completed', triage_at = NOW()
                   WHERE id = %s""",
                (article['id'],)
            )

    def _detect_context(self, text: str, player_name: str) -> str:
        """Detect mention context based on surrounding keywords."""
        text_lower = text.lower()
        player_lower = player_name.lower()

        # Find text around player mention
        idx = text_lower.find(player_lower)
        if idx == -1:
            return "general"

        window = text_lower[max(0, idx-100):idx+100]

        if any(kw in window for kw in ['injur', 'hamstring', 'calf', 'shoulder', 'knee', 'ruled out', 'sidelined', 'miss']):
            return "injury"
        if any(kw in window for kw in ['return', 'back from', 'recovered', 'cleared to play', 'set to return']):
            return "return"
        if any(kw in window for kw in ['trade', 'deal', 'request', 'move to', 'join', 'sign']):
            return "trade"
        if any(kw in window for kw in ['select', 'named', 'omit', 'drop', 'debut', 'axed', 'in for', 'out for']):
            return "selection"
        if any(kw in window for kw in ['form', 'scores', 'points', 'averaging', 'performance', 'disposal']):
            return "form"

        return "general"

    def _load_player_patterns(self):
        """Load regex patterns for all known players."""
        self._player_patterns = []

        with get_cursor() as cursor:
            cursor.execute(
                """SELECT id, canonical_name FROM entities
                   WHERE domain = 'afl' AND entity_type = 'player'"""
            )
            players = cursor.fetchall()

            # Also get aliases
            cursor.execute(
                """SELECT e.id, a.alias FROM entity_aliases a
                   JOIN entities e ON a.entity_id = e.id
                   WHERE e.domain = 'afl' AND e.entity_type = 'player'"""
            )
            aliases = cursor.fetchall()

        seen = set()
        for p in players:
            pattern = re.compile(re.escape(p['canonical_name']), re.IGNORECASE)
            self._player_patterns.append((pattern, str(p['id']), p['canonical_name']))
            seen.add(p['canonical_name'].lower())

        for a in aliases:
            if a['alias'].lower() not in seen:
                pattern = re.compile(r'\b' + re.escape(a['alias']) + r'\b', re.IGNORECASE)
                self._player_patterns.append((pattern, str(a['id']), a['alias']))

    # === PHASE 2: DEEP ANALYSIS ===

    def run_analysis_batch(self, batch_size: int = 20) -> int:
        """Process pending entities through deep LLM analysis."""
        if self.claude is None:
            self.claude = ClaudeClient()

        with get_cursor() as cursor:
            cursor.execute(
                """SELECT ae.*, a.title, a.body, a.url, a.source, a.published_at,
                          e.canonical_name
                   FROM article_entities ae
                   JOIN articles a ON ae.article_id = a.id
                   LEFT JOIN entities e ON ae.entity_id = e.id
                   WHERE ae.needs_deep_analysis = TRUE
                     AND ae.analysis_completed = FALSE
                   ORDER BY a.published_at DESC
                   LIMIT %s""",
                (batch_size,)
            )
            pending = cursor.fetchall()

        processed = 0
        for item in pending:
            self._analyze_entity(item)
            processed += 1

        return processed

    def _analyze_entity(self, item: Dict):
        """
        Phase 2: Deep LLM extraction for one entity in one article.
        """
        player_name = item['canonical_name'] or item['entity_name']

        prompt = f"""Analyze this AFL news article about {player_name}.

ARTICLE:
Title: {item['title']}
Source: {item['source']}
Published: {item['published_at']}

Content:
{item['body'][:4000]}

Extract information about {player_name}:

1. EVENT_TYPE: injury | return | trade | selection | form | contract | other
2. If INJURY:
   - injury_type: hamstring, calf, shoulder, knee, concussion, etc.
   - severity: minor | moderate | severe | season_ending
   - return_estimate: number of weeks, or round number
3. KEY_QUOTES: Direct quotes about {player_name} (max 3)
4. SUMMARY: 2-3 sentence summary of news about {player_name}
5. CONFIDENCE: 0.0-1.0

Respond with ONLY JSON:
{{"event_type": "injury", "injury_type": "hamstring", "severity": "moderate",
  "return_weeks": 3, "return_round": null, "quotes": [{{"text": "...", "speaker": "..."}}],
  "summary": "...", "confidence": 0.9}}
"""

        result = self.claude.query_json(prompt)

        if "error" in result:
            # Mark as completed but don't create event
            self._mark_analysis_complete(item['id'])
            return

        # Skip if player not actually mentioned or low confidence
        event_type = result.get('event_type') or 'other'
        confidence = result.get('confidence') or 0
        if confidence < 0.3:
            self._mark_analysis_complete(item['id'])
            return

        # Create extraction event
        with get_cursor() as cursor:
            cursor.execute(
                """INSERT INTO extraction_events
                   (domain, schema_type, article_hash, headline, source, source_url,
                    extracted_data, entities_mentioned, confidence,
                    article_id, article_entity_id, key_quotes, injury_severity, return_round)
                   VALUES ('afl', %s, %s, %s, %s, %s, %s, %s::uuid[], %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (article_hash) DO NOTHING""",
                (
                    event_type,
                    hashlib.sha256(f"{item['url']}:{player_name}".encode()).hexdigest(),
                    item['title'],
                    item['source'],
                    item['url'],
                    json.dumps(result),
                    [item['entity_id']] if item['entity_id'] else None,
                    result.get('confidence'),
                    item['article_id'],
                    item['id'],
                    json.dumps(result.get('quotes', [])),
                    result.get('severity'),
                    result.get('return_round'),
                )
            )

            self._mark_analysis_complete(item['id'])

    def _mark_analysis_complete(self, article_entity_id: int):
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE article_entities SET analysis_completed = TRUE
                   WHERE id = %s""",
                (article_entity_id,)
            )

    # === CACHE CLEANUP ===

    def cleanup_expired(self) -> int:
        """Remove expired articles and their data."""
        with get_cursor() as cursor:
            cursor.execute(
                """DELETE FROM articles WHERE expires_at < NOW() RETURNING id"""
            )
            deleted = cursor.fetchall()
            return len(deleted)
