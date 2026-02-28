"""Weekly intelligence processor for fantasy AFL insights."""

import json
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

from core.database import get_cursor
from core.claude_client import ClaudeClient


@dataclass
class ArticleContext:
    """Article data for processing."""
    id: int
    title: str
    body: str
    source: str
    published_at: datetime
    dimension_tags: List[str]


class WeeklyProcessor:
    """Generates weekly snapshots, rolling profiles, and verdicts."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.claude = ClaudeClient(model=model, max_turns=1)

    def process_round(self, round_id: int, entity_ids: Optional[List[int]] = None) -> Dict:
        """Process all players for a round."""
        with get_cursor() as cursor:
            # Get entities to process
            if entity_ids:
                cursor.execute(
                    "SELECT id, canonical_name as name FROM entities WHERE id = ANY(%s) AND entity_type = 'player'",
                    (entity_ids,)
                )
            else:
                cursor.execute(
                    "SELECT id, canonical_name as name FROM entities WHERE entity_type = 'player'"
                )
            entities = cursor.fetchall()

            # Get active dimensions
            cursor.execute("SELECT id, code, prompt_guidance FROM dimensions WHERE is_active = TRUE")
            dimensions = cursor.fetchall()

        results = {"snapshots": 0, "profiles": 0, "verdicts": 0, "errors": []}

        for entity in entities:
            entity_dict = {"id": entity["id"], "name": entity["name"]}

            # Stage 1: Generate snapshots per dimension
            for dimension in dimensions:
                dim_dict = {
                    "id": dimension["id"],
                    "code": dimension["code"],
                    "prompt_guidance": dimension["prompt_guidance"]
                }
                try:
                    if self._generate_snapshot(entity_dict, dim_dict, round_id):
                        results["snapshots"] += 1
                except Exception as e:
                    results["errors"].append(f"Snapshot {entity['name']}/{dimension['code']}: {e}")

            # Stage 2: Update rolling profile per dimension
            for dimension in dimensions:
                dim_dict = {
                    "id": dimension["id"],
                    "code": dimension["code"],
                    "prompt_guidance": dimension["prompt_guidance"]
                }
                try:
                    if self._update_rolling_profile(entity_dict, dim_dict, round_id):
                        results["profiles"] += 1
                except Exception as e:
                    results["errors"].append(f"Profile {entity['name']}/{dimension['code']}: {e}")

            # Stage 3: Generate weekly verdict
            try:
                if self._generate_verdict(entity_dict, round_id):
                    results["verdicts"] += 1
            except Exception as e:
                results["errors"].append(f"Verdict {entity['name']}: {e}")

        return results

    def _get_articles_for_entity_dimension(
        self, entity_id, dimension_id: int, round_id: int
    ) -> List[ArticleContext]:
        """Get articles tagged with entity AND dimension for this round."""
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT a.id, a.title, a.body, a.source, a.published_at
                FROM articles a
                JOIN article_tags t_entity ON a.id = t_entity.article_id
                JOIN article_tags t_dim ON a.id = t_dim.article_id
                WHERE t_entity.tag_type = 'player' AND t_entity.entity_id = %s
                  AND t_dim.dimension_id = %s
                  AND a.round_id = %s
                ORDER BY a.published_at DESC
            """, (entity_id, dimension_id, round_id))
            rows = cursor.fetchall()

        return [
            ArticleContext(
                id=r["id"],
                title=r["title"],
                body=r["body"] or "",
                source=r["source"],
                published_at=r["published_at"],
                dimension_tags=[]
            ) for r in rows
        ]

    def _generate_snapshot(
        self, entity: Dict, dimension: Dict, round_id: int
    ) -> bool:
        """Generate weekly snapshot for entity-dimension-round."""
        articles = self._get_articles_for_entity_dimension(
            entity["id"], dimension["id"], round_id
        )

        if not articles:
            return False  # No relevant articles

        # Build article context
        article_text = "\n\n---\n\n".join([
            f"**{a.title}** ({a.source})\n{a.body[:2000]}"
            for a in articles[:5]  # Limit to 5 articles
        ])

        prompt = f"""Analyze these AFL news articles about {entity["name"]} regarding {dimension["code"].replace("_", " ")}.

{dimension.get("prompt_guidance") or ""}

ARTICLES:
{article_text}

Respond with ONLY valid JSON:
{{
    "summary": "2-3 sentence summary of what the news says about this dimension",
    "sentiment": "positive|negative|neutral|mixed",
    "signal_strength": "strong|moderate|weak|none",
    "fantasy_impact": "One sentence on fantasy relevance",
    "ml_features": {{
        "mentioned": true,
        "sentiment_score": 0.0 to 1.0,
        "signal_score": 0.0 to 1.0,
        "recency_days": average days since articles,
        "source_quality": 0.0 to 1.0
    }},
    "confidence": 0.0 to 1.0
}}"""

        result = self.claude.query_json(prompt)

        if "error" in result:
            print(f"Snapshot generation failed for {entity['name']}/{dimension['code']}: {result['error']}")
            return False

        # Store snapshot
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO weekly_snapshots
                (entity_id, dimension_id, round_id, summary, sentiment, signal_strength,
                 fantasy_impact, ml_features, confidence, article_count, source_article_ids)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id, dimension_id, round_id) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    sentiment = EXCLUDED.sentiment,
                    signal_strength = EXCLUDED.signal_strength,
                    fantasy_impact = EXCLUDED.fantasy_impact,
                    ml_features = EXCLUDED.ml_features,
                    confidence = EXCLUDED.confidence,
                    article_count = EXCLUDED.article_count,
                    source_article_ids = EXCLUDED.source_article_ids,
                    generated_at = NOW()
            """, (
                entity["id"], dimension["id"], round_id,
                result.get("summary", ""),
                result.get("sentiment", "neutral"),
                result.get("signal_strength", "none"),
                result.get("fantasy_impact", ""),
                json.dumps(result.get("ml_features", {})),
                result.get("confidence", 0.5),
                len(articles),
                [a.id for a in articles]
            ))

        return True

    def _update_rolling_profile(
        self, entity: Dict, dimension: Dict, round_id: int
    ) -> bool:
        """Update rolling profile with recent snapshots."""
        with get_cursor() as cursor:
            # Get last 4 weeks of snapshots
            cursor.execute("""
                SELECT ws.summary, ws.sentiment, ws.signal_strength, ws.ml_features,
                       r.round_number
                FROM weekly_snapshots ws
                JOIN rounds r ON ws.round_id = r.id
                WHERE ws.entity_id = %s AND ws.dimension_id = %s
                ORDER BY r.round_number DESC
                LIMIT 4
            """, (entity["id"], dimension["id"]))
            snapshots = cursor.fetchall()

        if not snapshots:
            return False

        # Build context from recent snapshots
        snapshot_context = "\n".join([
            f"Round {s['round_number']}: {s['summary']} (sentiment: {s['sentiment']})"
            for s in snapshots
        ])

        prompt = f"""Based on the last {len(snapshots)} weeks of news about {entity["name"]}
regarding {dimension["code"].replace("_", " ")}:

{snapshot_context}

Respond with ONLY valid JSON:
{{
    "narrative": "2-3 sentence narrative describing the trend over these weeks",
    "trend": "improving|stable|declining|volatile",
    "trend_confidence": 0.0 to 1.0,
    "aggregated_features": {{
        "avg_sentiment": 0.0 to 1.0,
        "trend_direction": -1.0 to 1.0,
        "consistency": 0.0 to 1.0,
        "weeks_positive": count,
        "weeks_negative": count
    }}
}}"""

        result = self.claude.query_json(prompt)

        if "error" in result:
            print(f"Profile update failed for {entity['name']}/{dimension['code']}: {result['error']}")
            return False

        # Upsert profile
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO rolling_profiles
                (entity_id, dimension_id, narrative, trend, trend_confidence,
                 weeks_covered, last_round_id, aggregated_features)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id, dimension_id) DO UPDATE SET
                    narrative = EXCLUDED.narrative,
                    trend = EXCLUDED.trend,
                    trend_confidence = EXCLUDED.trend_confidence,
                    weeks_covered = EXCLUDED.weeks_covered,
                    last_round_id = EXCLUDED.last_round_id,
                    aggregated_features = EXCLUDED.aggregated_features,
                    updated_at = NOW()
            """, (
                entity["id"], dimension["id"],
                result.get("narrative", ""),
                result.get("trend", "stable"),
                result.get("trend_confidence", 0.5),
                len(snapshots), round_id,
                json.dumps(result.get("aggregated_features", {}))
            ))

        return True

    def _generate_verdict(self, entity: Dict, round_id: int) -> bool:
        """Generate weekly verdict combining all dimensions."""
        with get_cursor() as cursor:
            # Get all snapshots for this round
            cursor.execute("""
                SELECT d.code, ws.summary, ws.sentiment, ws.signal_strength, ws.fantasy_impact
                FROM weekly_snapshots ws
                JOIN dimensions d ON ws.dimension_id = d.id
                WHERE ws.entity_id = %s AND ws.round_id = %s
            """, (entity["id"], round_id))
            snapshots = cursor.fetchall()

            # Get rolling profiles
            cursor.execute("""
                SELECT d.code, rp.narrative, rp.trend
                FROM rolling_profiles rp
                JOIN dimensions d ON rp.dimension_id = d.id
                WHERE rp.entity_id = %s
            """, (entity["id"],))
            profiles = cursor.fetchall()

        if not snapshots:
            return False

        # Build context
        snapshot_context = "\n".join([
            f"- {s['code']}: {s['summary']} ({s['sentiment']}, {s['signal_strength']})"
            for s in snapshots
        ])

        profile_context = "\n".join([
            f"- {p['code']}: {p['narrative']} (trend: {p['trend']})"
            for p in profiles
        ]) if profiles else "No historical profiles yet."

        prompt = f"""Generate a fantasy AFL verdict for {entity["name"]} this round.

THIS WEEK'S NEWS:
{snapshot_context}

RECENT TRENDS:
{profile_context}

Respond with ONLY valid JSON:
{{
    "captain_rating": 0-100 (100 = must captain),
    "captain_reasoning": "One sentence why they are/aren't a good captain",
    "risk_level": "low|medium|high|extreme",
    "risk_factors": ["list", "of", "risk", "factors"],
    "trade_signal": "strong_buy|buy|hold|sell|strong_sell",
    "trade_reasoning": "One sentence trade recommendation",
    "verdict_features": {{
        "injury_risk": 0.0 to 1.0,
        "form_score": 0.0 to 1.0,
        "selection_certainty": 0.0 to 1.0,
        "upside_potential": 0.0 to 1.0,
        "floor_safety": 0.0 to 1.0
    }},
    "confidence": 0.0 to 1.0
}}"""

        result = self.claude.query_json(prompt)

        if "error" in result:
            print(f"Verdict generation failed for {entity['name']}: {result['error']}")
            return False

        # Store verdict
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO weekly_verdicts
                (entity_id, round_id, captain_rating, captain_reasoning,
                 risk_level, risk_factors, trade_signal, trade_reasoning,
                 verdict_features, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id, round_id) DO UPDATE SET
                    captain_rating = EXCLUDED.captain_rating,
                    captain_reasoning = EXCLUDED.captain_reasoning,
                    risk_level = EXCLUDED.risk_level,
                    risk_factors = EXCLUDED.risk_factors,
                    trade_signal = EXCLUDED.trade_signal,
                    trade_reasoning = EXCLUDED.trade_reasoning,
                    verdict_features = EXCLUDED.verdict_features,
                    confidence = EXCLUDED.confidence,
                    generated_at = NOW()
            """, (
                entity["id"], round_id,
                result.get("captain_rating", 50),
                result.get("captain_reasoning", ""),
                result.get("risk_level", "medium"),
                json.dumps(result.get("risk_factors", [])),
                result.get("trade_signal", "hold"),
                result.get("trade_reasoning", ""),
                json.dumps(result.get("verdict_features", {})),
                result.get("confidence", 0.5)
            ))

        return True


def process_single_entity(entity_id: int, round_id: int) -> Dict:
    """Process a single entity for a round."""
    processor = WeeklyProcessor()
    return processor.process_round(round_id, entity_ids=[entity_id])
