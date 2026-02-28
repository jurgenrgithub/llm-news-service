"""Deterministic article tagging at ingest time.

Indexes articles by:
- Players (canonical names + aliases)
- Teams/Clubs (canonical names + aliases)
- Keywords (injury, trade, selection, etc.) with dimension mapping

This runs synchronously at ingest, before any LLM analysis.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from core.database import get_cursor

logger = logging.getLogger(__name__)


# Map keyword tag values to dimension codes
KEYWORD_TO_DIMENSION = {
    "injury": "injury_status",
    "return": "fitness_health",
    "selection": "selection_security",
    "trade": "selection_security",  # Trade affects selection security
    "contract": "role_change",  # Contract affects role security
    "form": "form_trajectory",
}


# Keyword patterns -> normalized tag values
KEYWORD_MAP = {
    # Injury keywords
    "injur": "injury",
    "hamstring": "injury",
    "calf": "injury",
    "shoulder": "injury",
    "knee": "injury",
    "ankle": "injury",
    "concuss": "injury",
    "ruled out": "injury",
    "sidelined": "injury",
    "miss": "injury",
    "setback": "injury",
    # Return keywords
    "return": "return",
    "back from": "return",
    "recovered": "return",
    "cleared to play": "return",
    "set to return": "return",
    "available": "return",
    # Trade keywords
    "trade": "trade",
    "request": "trade",
    "move to": "trade",
    "join": "trade",
    "sign": "trade",
    "departure": "trade",
    "free agent": "trade",
    # Selection keywords
    "select": "selection",
    "named": "selection",
    "omit": "selection",
    "drop": "selection",
    "debut": "selection",
    "axed": "selection",
    "in for": "selection",
    "out for": "selection",
    "recalled": "selection",
    # Contract keywords
    "contract": "contract",
    "re-sign": "contract",
    "deal": "contract",
    "extension": "contract",
    "years": "contract",
    # Form keywords
    "form": "form",
    "scores": "form",
    "points": "form",
    "averaging": "form",
    "performance": "form",
    "disposal": "form",
    "best on ground": "form",
    "bog": "form",
}


class ArticleIndexer:
    """Deterministic article tagging at ingest time."""

    # Singleton pattern for pattern cache
    _instance = None
    _patterns: Optional[List[Tuple[re.Pattern, str, str, str]]] = None
    _dimension_ids: Optional[Dict[str, int]] = None  # code -> id

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_dimensions(self):
        """Load dimension code -> id mapping."""
        self._dimension_ids = {}
        try:
            with get_cursor() as cursor:
                cursor.execute("SELECT id, code FROM dimensions WHERE is_active = TRUE")
                for row in cursor.fetchall():
                    self._dimension_ids[row["code"]] = row["id"]
            logger.info(f"Loaded {len(self._dimension_ids)} dimensions")
        except Exception as e:
            logger.warning(f"Could not load dimensions (table may not exist): {e}")
            self._dimension_ids = {}

    def index_article(self, article_id: int, title: str, body: str) -> Dict:
        """
        Index article immediately on ingest.
        Creates tags for all matched entities + keywords.

        Returns dict with stats about tags created.
        """
        if self._patterns is None:
            self._load_patterns()
        if self._dimension_ids is None:
            self._load_dimensions()

        text = f"{title}\n{body}"
        title_len = len(title)
        tags = []

        # Track unique entity matches (dedupe by entity_id + tag_type)
        entity_matches = defaultdict(lambda: {
            "match_count": 0,
            "is_headline": False,
            "match_text": None,
        })

        # Match entities (players + teams)
        for pattern, entity_id, canonical, entity_type in self._patterns:
            for m in pattern.finditer(text):
                is_headline = m.start() < title_len
                key = (entity_id, entity_type, canonical)

                entity_matches[key]["match_count"] += 1
                if is_headline:
                    entity_matches[key]["is_headline"] = True
                if entity_matches[key]["match_text"] is None:
                    entity_matches[key]["match_text"] = m.group()[:200]

        # Convert entity matches to tags
        for (entity_id, entity_type, canonical), data in entity_matches.items():
            tags.append({
                "tag_type": entity_type,
                "tag_value": canonical,
                "entity_id": entity_id,
                "match_text": data["match_text"],
                "match_count": data["match_count"],
                "is_headline": data["is_headline"],
            })

        # Match keywords (case-insensitive)
        text_lower = text.lower()
        keyword_matches = defaultdict(lambda: {"match_count": 0, "is_headline": False})

        for keyword, tag_value in KEYWORD_MAP.items():
            # Find all occurrences
            idx = 0
            while True:
                idx = text_lower.find(keyword, idx)
                if idx == -1:
                    break
                keyword_matches[tag_value]["match_count"] += 1
                if idx < title_len:
                    keyword_matches[tag_value]["is_headline"] = True
                idx += len(keyword)

        for tag_value, data in keyword_matches.items():
            # Get dimension_id for this keyword
            dimension_code = KEYWORD_TO_DIMENSION.get(tag_value)
            dimension_id = self._dimension_ids.get(dimension_code) if dimension_code else None

            tags.append({
                "tag_type": "keyword",
                "tag_value": tag_value,
                "entity_id": None,
                "dimension_id": dimension_id,
                "match_text": None,
                "match_count": data["match_count"],
                "is_headline": data["is_headline"],
            })

        # Save tags to database
        stats = self._save_tags(article_id, tags)

        logger.info(
            f"Indexed article {article_id}: "
            f"{stats['players']} players, {stats['teams']} teams, {stats['keywords']} keywords"
        )

        return stats

    def _load_patterns(self):
        """Load all entity patterns (players + clubs + aliases)."""
        self._patterns = []

        with get_cursor() as cursor:
            # Get all entities
            cursor.execute("""
                SELECT e.id, e.canonical_name, e.entity_type
                FROM entities e
                WHERE e.domain = 'afl'
            """)
            entities = cursor.fetchall()

            # Get all aliases
            cursor.execute("""
                SELECT e.id, a.alias, e.entity_type, e.canonical_name
                FROM entity_aliases a
                JOIN entities e ON a.entity_id = e.id
                WHERE e.domain = 'afl'
            """)
            aliases = cursor.fetchall()

        seen_patterns = set()

        # Build patterns for canonical names
        for e in entities:
            name = e["canonical_name"]
            if name.lower() not in seen_patterns:
                pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
                self._patterns.append((pattern, str(e["id"]), name, e["entity_type"]))
                seen_patterns.add(name.lower())

        # Build patterns for aliases (map to canonical name for tag_value)
        for a in aliases:
            alias = a["alias"]
            if alias.lower() not in seen_patterns:
                pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
                # Use canonical_name as tag_value for consistency
                self._patterns.append((pattern, str(a["id"]), a["canonical_name"], a["entity_type"]))
                seen_patterns.add(alias.lower())

        logger.info(f"Loaded {len(self._patterns)} entity patterns for indexing")

    def _save_tags(self, article_id: int, tags: List[Dict]) -> Dict:
        """Bulk insert tags for an article."""
        stats = {"players": 0, "teams": 0, "keywords": 0, "total": 0}

        if not tags:
            return stats

        with get_cursor() as cursor:
            for tag in tags:
                try:
                    cursor.execute(
                        """INSERT INTO article_tags
                           (article_id, tag_type, tag_value, entity_id, dimension_id, match_text, match_count, is_headline)
                           VALUES (%s, %s, %s, %s::uuid, %s, %s, %s, %s)
                           ON CONFLICT (article_id, tag_type, tag_value) DO UPDATE
                           SET match_count = EXCLUDED.match_count,
                               is_headline = EXCLUDED.is_headline,
                               dimension_id = COALESCE(EXCLUDED.dimension_id, article_tags.dimension_id)""",
                        (
                            article_id,
                            tag["tag_type"],
                            tag["tag_value"],
                            tag["entity_id"],
                            tag.get("dimension_id"),
                            tag["match_text"],
                            tag["match_count"],
                            tag["is_headline"],
                        )
                    )
                    stats["total"] += 1

                    if tag["tag_type"] == "player":
                        stats["players"] += 1
                    elif tag["tag_type"] == "team":
                        stats["teams"] += 1
                    elif tag["tag_type"] == "keyword":
                        stats["keywords"] += 1

                except Exception as e:
                    logger.warning(f"Failed to insert tag: {e}")

            # Mark article as indexed
            cursor.execute(
                "UPDATE articles SET indexed_at = NOW() WHERE id = %s",
                (article_id,)
            )

        return stats

    def reindex_all(self, batch_size: int = 100) -> Dict:
        """Re-index all unindexed articles."""
        total_stats = {"articles": 0, "players": 0, "teams": 0, "keywords": 0}

        while True:
            with get_cursor() as cursor:
                cursor.execute(
                    """SELECT id, title, body FROM articles
                       WHERE indexed_at IS NULL
                       ORDER BY scraped_at DESC
                       LIMIT %s""",
                    (batch_size,)
                )
                articles = cursor.fetchall()

            if not articles:
                break

            for article in articles:
                stats = self.index_article(article["id"], article["title"], article["body"])
                total_stats["articles"] += 1
                total_stats["players"] += stats.get("players", 0)
                total_stats["teams"] += stats.get("teams", 0)
                total_stats["keywords"] += stats.get("keywords", 0)

        return total_stats

    def clear_cache(self):
        """Clear pattern and dimension cache (call after entity/dimension changes)."""
        self._patterns = None
        self._dimension_ids = None


# Convenience function
def index_article(article_id: int, title: str, body: str) -> Dict:
    """Index a single article."""
    indexer = ArticleIndexer()
    return indexer.index_article(article_id, title, body)


def reindex_all_articles(batch_size: int = 100) -> Dict:
    """Re-index all unindexed articles."""
    indexer = ArticleIndexer()
    return indexer.reindex_all(batch_size)
