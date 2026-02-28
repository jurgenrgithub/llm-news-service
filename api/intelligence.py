"""Intelligence API endpoints for weekly verdicts and snapshots."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from core.database import get_cursor
from core.weekly_processor import WeeklyProcessor

router = APIRouter()


@router.post("/process-round/{round_id}")
def process_round(round_id: int, background_tasks: BackgroundTasks):
    """Trigger weekly processing for a round (runs in background)."""
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM rounds WHERE id = %s", (round_id,))
        if not cursor.fetchone():
            raise HTTPException(404, f"Round {round_id} not found")

    processor = WeeklyProcessor()
    background_tasks.add_task(processor.process_round, round_id)

    return {"status": "processing", "round_id": round_id}


@router.post("/process-round/{round_id}/sync")
def process_round_sync(round_id: int):
    """Trigger weekly processing for a round (synchronous, for testing)."""
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM rounds WHERE id = %s", (round_id,))
        if not cursor.fetchone():
            raise HTTPException(404, f"Round {round_id} not found")

    processor = WeeklyProcessor()
    results = processor.process_round(round_id)

    return {
        "status": "completed",
        "round_id": round_id,
        "results": results
    }


@router.get("/verdicts")
def list_verdicts(
    round_id: Optional[int] = Query(None),
    min_captain_rating: int = Query(0, ge=0, le=100),
    trade_signal: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List weekly verdicts with filtering."""
    with get_cursor() as cursor:
        query = """
            SELECT wv.*, e.canonical_name as entity_name, r.round_number
            FROM weekly_verdicts wv
            JOIN entities e ON wv.entity_id = e.id
            JOIN rounds r ON wv.round_id = r.id
            WHERE wv.captain_rating >= %s
        """
        params = [min_captain_rating]

        if round_id:
            query += " AND wv.round_id = %s"
            params.append(round_id)

        if trade_signal:
            query += " AND wv.trade_signal = %s"
            params.append(trade_signal)

        query += " ORDER BY wv.captain_rating DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        verdicts = cursor.fetchall()

    return {
        "count": len(verdicts),
        "verdicts": [
            {
                "entity_id": v["entity_id"],
                "entity_name": v["entity_name"],
                "round_id": v["round_id"],
                "round_number": v["round_number"],
                "captain_rating": v["captain_rating"],
                "captain_reasoning": v["captain_reasoning"],
                "risk_level": v["risk_level"],
                "risk_factors": v["risk_factors"],
                "trade_signal": v["trade_signal"],
                "trade_reasoning": v["trade_reasoning"],
                "confidence": float(v["confidence"]) if v["confidence"] else None,
            }
            for v in verdicts
        ]
    }


@router.get("/verdicts/{entity_id}")
def get_entity_verdict(entity_id: str, round_id: Optional[int] = None):
    """Get verdict for specific entity."""
    with get_cursor() as cursor:
        if round_id:
            cursor.execute("""
                SELECT wv.*, e.canonical_name as entity_name
                FROM weekly_verdicts wv
                JOIN entities e ON wv.entity_id = e.id
                WHERE wv.entity_id = %s AND wv.round_id = %s
            """, (entity_id, round_id))
        else:
            # Get latest verdict
            cursor.execute("""
                SELECT wv.*, e.canonical_name as entity_name
                FROM weekly_verdicts wv
                JOIN entities e ON wv.entity_id = e.id
                WHERE wv.entity_id = %s
                ORDER BY wv.round_id DESC LIMIT 1
            """, (entity_id,))

        verdict = cursor.fetchone()

    if not verdict:
        raise HTTPException(404, f"No verdict found for entity {entity_id}")

    return {
        "entity_id": verdict["entity_id"],
        "entity_name": verdict["entity_name"],
        "round_id": verdict["round_id"],
        "captain_rating": verdict["captain_rating"],
        "captain_reasoning": verdict["captain_reasoning"],
        "risk_level": verdict["risk_level"],
        "risk_factors": verdict["risk_factors"],
        "trade_signal": verdict["trade_signal"],
        "trade_reasoning": verdict["trade_reasoning"],
        "verdict_features": verdict["verdict_features"],
        "confidence": float(verdict["confidence"]) if verdict["confidence"] else None,
    }


@router.get("/snapshots/{entity_id}")
def get_entity_snapshots(
    entity_id: str,
    round_id: Optional[int] = None,
    dimension_code: Optional[str] = None,
):
    """Get snapshots for an entity."""
    with get_cursor() as cursor:
        query = """
            SELECT ws.*, d.code as dimension_code, d.name as dimension_name
            FROM weekly_snapshots ws
            JOIN dimensions d ON ws.dimension_id = d.id
            WHERE ws.entity_id = %s
        """
        params = [entity_id]

        if round_id:
            query += " AND ws.round_id = %s"
            params.append(round_id)

        if dimension_code:
            query += " AND d.code = %s"
            params.append(dimension_code)

        query += " ORDER BY ws.round_id DESC, d.tier"
        cursor.execute(query, params)
        snapshots = cursor.fetchall()

    return {
        "entity_id": entity_id,
        "count": len(snapshots),
        "snapshots": [
            {
                "dimension_code": s["dimension_code"],
                "dimension_name": s["dimension_name"],
                "round_id": s["round_id"],
                "summary": s["summary"],
                "sentiment": s["sentiment"],
                "signal_strength": s["signal_strength"],
                "fantasy_impact": s["fantasy_impact"],
                "article_count": s["article_count"],
                "confidence": float(s["confidence"]) if s["confidence"] else None,
            }
            for s in snapshots
        ]
    }


@router.get("/profiles/{entity_id}")
def get_entity_profiles(entity_id: str):
    """Get rolling profiles for an entity."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT rp.*, d.code as dimension_code, d.name as dimension_name,
                   e.canonical_name as entity_name
            FROM rolling_profiles rp
            JOIN dimensions d ON rp.dimension_id = d.id
            JOIN entities e ON rp.entity_id = e.id
            WHERE rp.entity_id = %s
            ORDER BY d.tier
        """, (entity_id,))
        profiles = cursor.fetchall()

    if not profiles:
        raise HTTPException(404, f"No profiles found for entity {entity_id}")

    return {
        "entity_id": entity_id,
        "entity_name": profiles[0]["entity_name"] if profiles else None,
        "profiles": [
            {
                "dimension_code": p["dimension_code"],
                "dimension_name": p["dimension_name"],
                "narrative": p["narrative"],
                "trend": p["trend"],
                "trend_confidence": float(p["trend_confidence"]) if p["trend_confidence"] else None,
                "weeks_covered": p["weeks_covered"],
            }
            for p in profiles
        ]
    }


@router.get("/captains")
def get_captain_rankings(
    round_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
):
    """Get captain rankings for a round."""
    with get_cursor() as cursor:
        if round_id:
            cursor.execute("""
                SELECT wv.entity_id, e.canonical_name as name, wv.captain_rating, wv.captain_reasoning,
                       wv.risk_level, wv.confidence
                FROM weekly_verdicts wv
                JOIN entities e ON wv.entity_id = e.id
                WHERE wv.round_id = %s
                ORDER BY wv.captain_rating DESC
                LIMIT %s
            """, (round_id, limit))
        else:
            # Get from current round
            cursor.execute("""
                SELECT wv.entity_id, e.canonical_name as name, wv.captain_rating, wv.captain_reasoning,
                       wv.risk_level, wv.confidence, r.round_number
                FROM weekly_verdicts wv
                JOIN entities e ON wv.entity_id = e.id
                JOIN rounds r ON wv.round_id = r.id
                JOIN seasons s ON r.season_id = s.id
                WHERE s.is_current = TRUE
                ORDER BY r.round_number DESC, wv.captain_rating DESC
                LIMIT %s
            """, (limit,))

        rankings = cursor.fetchall()

    return {
        "count": len(rankings),
        "rankings": [
            {
                "rank": i + 1,
                "entity_id": r["entity_id"],
                "name": r["name"],
                "captain_rating": r["captain_rating"],
                "reasoning": r["captain_reasoning"],
                "risk_level": r["risk_level"],
                "confidence": float(r["confidence"]) if r["confidence"] else None,
            }
            for i, r in enumerate(rankings)
        ]
    }


@router.get("/stats")
def get_intelligence_stats():
    """Get statistics about intelligence data."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM weekly_snapshots) as snapshot_count,
                (SELECT COUNT(*) FROM rolling_profiles) as profile_count,
                (SELECT COUNT(*) FROM weekly_verdicts) as verdict_count,
                (SELECT COUNT(DISTINCT entity_id) FROM weekly_snapshots) as entities_with_snapshots,
                (SELECT COUNT(DISTINCT round_id) FROM weekly_snapshots) as rounds_processed
        """)
        stats = cursor.fetchone()

    return {
        "snapshots": stats["snapshot_count"],
        "profiles": stats["profile_count"],
        "verdicts": stats["verdict_count"],
        "entities_with_snapshots": stats["entities_with_snapshots"],
        "rounds_processed": stats["rounds_processed"],
    }
