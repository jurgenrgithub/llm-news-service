"""ML feature export API endpoints."""

import csv
import io
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import PlainTextResponse

from core.database import get_cursor
from core.ml_feature_generator import MLFeatureGenerator

router = APIRouter()


@router.post("/generate/{round_id}")
def generate_ml_features(round_id: int):
    """Generate ML features from weekly intelligence for a round."""
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM rounds WHERE id = %s", (round_id,))
        if not cursor.fetchone():
            raise HTTPException(404, f"Round {round_id} not found")

    generator = MLFeatureGenerator()
    results = generator.generate_for_round(round_id)
    return {"status": "completed", "round_id": round_id, **results}


@router.get("/features")
def get_ml_features(
    round_id: Optional[int] = Query(None),
    season: Optional[int] = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    """Export ML features for FantasyEdge integration."""
    with get_cursor() as cursor:
        query = """
            SELECT
                e.canonical_name as player_name,
                e.external_id as player_external_id,
                r.round_number,
                s.year as season,
                mf.injury_mentioned, mf.injury_sentiment, mf.injury_signal,
                mf.fitness_mentioned, mf.fitness_sentiment, mf.fitness_signal,
                mf.selection_mentioned, mf.selection_sentiment, mf.selection_signal,
                mf.role_mentioned, mf.role_sentiment, mf.role_signal,
                mf.form_mentioned, mf.form_sentiment, mf.form_signal,
                mf.captaincy_mentioned, mf.captaincy_sentiment, mf.captaincy_signal,
                mf.load_mentioned, mf.load_sentiment, mf.load_signal,
                mf.coaching_mentioned, mf.coaching_sentiment, mf.coaching_signal,
                mf.captain_rating, mf.risk_level, mf.trade_signal,
                mf.injury_risk_score, mf.form_score, mf.selection_certainty,
                mf.upside_potential, mf.floor_safety,
                mf.total_article_count, mf.overall_sentiment,
                mf.overall_signal_strength, mf.confidence
            FROM ml_weekly_features mf
            JOIN entities e ON mf.entity_id = e.id
            JOIN rounds r ON mf.round_id = r.id
            JOIN seasons s ON r.season_id = s.id
            WHERE 1=1
        """
        params = []

        if round_id:
            query += " AND mf.round_id = %s"
            params.append(round_id)

        if season:
            query += " AND s.year = %s"
            params.append(season)

        query += " ORDER BY s.year, r.round_number, e.canonical_name"
        cursor.execute(query, params)
        rows = cursor.fetchall()

    if format == "csv":
        # Return CSV for easy pandas loading
        output = io.StringIO()
        if rows:
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        return PlainTextResponse(
            content=output.getvalue(),
            media_type="text/csv"
        )

    # Convert to list of dicts with proper types
    features = []
    for row in rows:
        features.append({
            "player_name": row["player_name"],
            "player_external_id": row["player_external_id"],
            "round": row["round_number"],
            "season": row["season"],
            # Dimension features (24 columns: 8 dims x 3 metrics)
            "injury_mentioned": row["injury_mentioned"],
            "injury_sentiment": float(row["injury_sentiment"]) if row["injury_sentiment"] else None,
            "injury_signal": float(row["injury_signal"]) if row["injury_signal"] else None,
            "fitness_mentioned": row["fitness_mentioned"],
            "fitness_sentiment": float(row["fitness_sentiment"]) if row["fitness_sentiment"] else None,
            "fitness_signal": float(row["fitness_signal"]) if row["fitness_signal"] else None,
            "selection_mentioned": row["selection_mentioned"],
            "selection_sentiment": float(row["selection_sentiment"]) if row["selection_sentiment"] else None,
            "selection_signal": float(row["selection_signal"]) if row["selection_signal"] else None,
            "role_mentioned": row["role_mentioned"],
            "role_sentiment": float(row["role_sentiment"]) if row["role_sentiment"] else None,
            "role_signal": float(row["role_signal"]) if row["role_signal"] else None,
            "form_mentioned": row["form_mentioned"],
            "form_sentiment": float(row["form_sentiment"]) if row["form_sentiment"] else None,
            "form_signal": float(row["form_signal"]) if row["form_signal"] else None,
            "captaincy_mentioned": row["captaincy_mentioned"],
            "captaincy_sentiment": float(row["captaincy_sentiment"]) if row["captaincy_sentiment"] else None,
            "captaincy_signal": float(row["captaincy_signal"]) if row["captaincy_signal"] else None,
            "load_mentioned": row["load_mentioned"],
            "load_sentiment": float(row["load_sentiment"]) if row["load_sentiment"] else None,
            "load_signal": float(row["load_signal"]) if row["load_signal"] else None,
            "coaching_mentioned": row["coaching_mentioned"],
            "coaching_sentiment": float(row["coaching_sentiment"]) if row["coaching_sentiment"] else None,
            "coaching_signal": float(row["coaching_signal"]) if row["coaching_signal"] else None,
            # Verdict aggregates
            "captain_rating": row["captain_rating"],
            "risk_level": row["risk_level"],
            "trade_signal": row["trade_signal"],
            # ML-ready scores
            "injury_risk_score": float(row["injury_risk_score"]) if row["injury_risk_score"] else None,
            "form_score": float(row["form_score"]) if row["form_score"] else None,
            "selection_certainty": float(row["selection_certainty"]) if row["selection_certainty"] else None,
            "upside_potential": float(row["upside_potential"]) if row["upside_potential"] else None,
            "floor_safety": float(row["floor_safety"]) if row["floor_safety"] else None,
            # Aggregates
            "total_article_count": row["total_article_count"],
            "overall_sentiment": float(row["overall_sentiment"]) if row["overall_sentiment"] else None,
            "overall_signal_strength": float(row["overall_signal_strength"]) if row["overall_signal_strength"] else None,
            "confidence": float(row["confidence"]) if row["confidence"] else None,
        })

    return {
        "count": len(features),
        "features": features
    }


@router.get("/features/{player_name}")
def get_player_features(player_name: str, limit: int = Query(10, ge=1, le=50)):
    """Get ML features history for a specific player."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT
                e.canonical_name as player_name,
                r.round_number, s.year as season,
                mf.captain_rating, mf.risk_level, mf.trade_signal,
                mf.injury_risk_score, mf.form_score, mf.selection_certainty,
                mf.upside_potential, mf.floor_safety,
                mf.overall_sentiment, mf.confidence
            FROM ml_weekly_features mf
            JOIN entities e ON mf.entity_id = e.id
            JOIN rounds r ON mf.round_id = r.id
            JOIN seasons s ON r.season_id = s.id
            WHERE LOWER(e.canonical_name) LIKE LOWER(%s)
            ORDER BY s.year DESC, r.round_number DESC
            LIMIT %s
        """, (f"%{player_name}%", limit))
        rows = cursor.fetchall()

    if not rows:
        raise HTTPException(404, f"No features found for player matching '{player_name}'")

    return {
        "player": rows[0]["player_name"] if rows else player_name,
        "count": len(rows),
        "history": [
            {
                "round": r["round_number"],
                "season": r["season"],
                "captain_rating": r["captain_rating"],
                "risk_level": r["risk_level"],
                "trade_signal": r["trade_signal"],
                "injury_risk_score": float(r["injury_risk_score"]) if r["injury_risk_score"] else None,
                "form_score": float(r["form_score"]) if r["form_score"] else None,
                "selection_certainty": float(r["selection_certainty"]) if r["selection_certainty"] else None,
                "upside_potential": float(r["upside_potential"]) if r["upside_potential"] else None,
                "floor_safety": float(r["floor_safety"]) if r["floor_safety"] else None,
                "overall_sentiment": float(r["overall_sentiment"]) if r["overall_sentiment"] else None,
                "confidence": float(r["confidence"]) if r["confidence"] else None,
            }
            for r in rows
        ]
    }


@router.get("/stats")
def get_ml_stats():
    """Get statistics about ML feature data."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM ml_weekly_features) as feature_rows,
                (SELECT COUNT(DISTINCT entity_id) FROM ml_weekly_features) as players_with_features,
                (SELECT COUNT(DISTINCT round_id) FROM ml_weekly_features) as rounds_with_features,
                (SELECT AVG(captain_rating) FROM ml_weekly_features) as avg_captain_rating,
                (SELECT AVG(overall_sentiment) FROM ml_weekly_features) as avg_sentiment
        """)
        stats = cursor.fetchone()

    return {
        "feature_rows": stats["feature_rows"],
        "players_with_features": stats["players_with_features"],
        "rounds_with_features": stats["rounds_with_features"],
        "avg_captain_rating": float(stats["avg_captain_rating"]) if stats["avg_captain_rating"] else None,
        "avg_sentiment": float(stats["avg_sentiment"]) if stats["avg_sentiment"] else None,
    }
