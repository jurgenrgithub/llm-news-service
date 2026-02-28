"""Rounds and seasons API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database import get_cursor

router = APIRouter()


@router.get("/seasons")
def list_seasons():
    """List all seasons."""
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT id, year, is_current, created_at
               FROM seasons
               ORDER BY year DESC"""
        )
        seasons = cursor.fetchall()

    return {
        "count": len(seasons),
        "seasons": [
            {
                "id": s["id"],
                "year": s["year"],
                "is_current": s["is_current"],
            }
            for s in seasons
        ]
    }


@router.get("/current")
def get_current_round():
    """Get the current round based on today's date."""
    with get_cursor() as cursor:
        # Try to find round matching current date
        cursor.execute(
            """SELECT r.id, r.round_number, r.name, r.start_date, r.end_date,
                      r.lockout_time, r.is_finals, r.is_bye_round,
                      s.year AS season_year
               FROM rounds r
               JOIN seasons s ON r.season_id = s.id
               WHERE s.is_current = TRUE
                 AND r.start_date <= CURRENT_DATE
                 AND r.end_date >= CURRENT_DATE
               LIMIT 1"""
        )
        round_data = cursor.fetchone()

        # If no exact match, get most recent past round
        if not round_data:
            cursor.execute(
                """SELECT r.id, r.round_number, r.name, r.start_date, r.end_date,
                          r.lockout_time, r.is_finals, r.is_bye_round,
                          s.year AS season_year
                   FROM rounds r
                   JOIN seasons s ON r.season_id = s.id
                   WHERE s.is_current = TRUE
                     AND r.start_date <= CURRENT_DATE
                   ORDER BY r.start_date DESC
                   LIMIT 1"""
            )
            round_data = cursor.fetchone()

    if not round_data:
        return {"current_round": None, "message": "No current round found"}

    return {
        "current_round": {
            "id": round_data["id"],
            "round_number": round_data["round_number"],
            "name": round_data["name"],
            "season_year": round_data["season_year"],
            "start_date": round_data["start_date"].isoformat() if round_data["start_date"] else None,
            "end_date": round_data["end_date"].isoformat() if round_data["end_date"] else None,
            "lockout_time": round_data["lockout_time"].isoformat() if round_data["lockout_time"] else None,
            "is_finals": round_data["is_finals"],
            "is_bye_round": round_data["is_bye_round"],
        }
    }


@router.get("")
def list_rounds(
    season_year: Optional[int] = Query(None, description="Filter by season year"),
    include_finals: bool = Query(True, description="Include finals rounds"),
):
    """List all rounds for a season."""
    with get_cursor() as cursor:
        if season_year:
            cursor.execute(
                """SELECT r.id, r.round_number, r.name, r.start_date, r.end_date,
                          r.lockout_time, r.is_finals, r.is_bye_round,
                          s.year AS season_year
                   FROM rounds r
                   JOIN seasons s ON r.season_id = s.id
                   WHERE s.year = %s AND (r.is_finals = FALSE OR %s = TRUE)
                   ORDER BY r.round_number""",
                (season_year, include_finals)
            )
        else:
            cursor.execute(
                """SELECT r.id, r.round_number, r.name, r.start_date, r.end_date,
                          r.lockout_time, r.is_finals, r.is_bye_round,
                          s.year AS season_year
                   FROM rounds r
                   JOIN seasons s ON r.season_id = s.id
                   WHERE s.is_current = TRUE AND (r.is_finals = FALSE OR %s = TRUE)
                   ORDER BY r.round_number""",
                (include_finals,)
            )
        rounds = cursor.fetchall()

    return {
        "count": len(rounds),
        "rounds": [
            {
                "id": r["id"],
                "round_number": r["round_number"],
                "name": r["name"],
                "season_year": r["season_year"],
                "start_date": r["start_date"].isoformat() if r["start_date"] else None,
                "end_date": r["end_date"].isoformat() if r["end_date"] else None,
                "lockout_time": r["lockout_time"].isoformat() if r["lockout_time"] else None,
                "is_finals": r["is_finals"],
                "is_bye_round": r["is_bye_round"],
            }
            for r in rounds
        ]
    }


@router.get("/{round_id}")
def get_round(round_id: int):
    """Get a specific round by ID."""
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT r.id, r.round_number, r.name, r.start_date, r.end_date,
                      r.lockout_time, r.is_finals, r.is_bye_round,
                      s.year AS season_year
               FROM rounds r
               JOIN seasons s ON r.season_id = s.id
               WHERE r.id = %s""",
            (round_id,)
        )
        round_data = cursor.fetchone()

    if not round_data:
        raise HTTPException(404, f"Round {round_id} not found")

    return {
        "id": round_data["id"],
        "round_number": round_data["round_number"],
        "name": round_data["name"],
        "season_year": round_data["season_year"],
        "start_date": round_data["start_date"].isoformat() if round_data["start_date"] else None,
        "end_date": round_data["end_date"].isoformat() if round_data["end_date"] else None,
        "lockout_time": round_data["lockout_time"].isoformat() if round_data["lockout_time"] else None,
        "is_finals": round_data["is_finals"],
        "is_bye_round": round_data["is_bye_round"],
    }


@router.get("/{round_id}/articles")
def get_round_articles(
    round_id: int,
    limit: int = Query(50, ge=1, le=200),
):
    """Get all articles for a specific round."""
    with get_cursor() as cursor:
        # Verify round exists
        cursor.execute("SELECT id, name FROM rounds WHERE id = %s", (round_id,))
        round_data = cursor.fetchone()

        if not round_data:
            raise HTTPException(404, f"Round {round_id} not found")

        # Get articles for this round
        cursor.execute(
            """SELECT a.id, a.url, a.title, a.source, a.published_at,
                      a.triage_status, a.analysis_status
               FROM articles a
               WHERE a.round_id = %s
               ORDER BY a.published_at DESC
               LIMIT %s""",
            (round_id, limit)
        )
        articles = cursor.fetchall()

    return {
        "round_id": round_id,
        "round_name": round_data["name"],
        "count": len(articles),
        "articles": [
            {
                "id": a["id"],
                "url": a["url"],
                "title": a["title"],
                "source": a["source"],
                "published_at": a["published_at"].isoformat() if a["published_at"] else None,
                "triage_status": a["triage_status"],
                "analysis_status": a["analysis_status"],
            }
            for a in articles
        ]
    }


@router.post("/{round_id}/assign-articles")
def assign_articles_to_round(round_id: int):
    """Assign articles to a round based on their published_at date."""
    with get_cursor() as cursor:
        # Verify round exists and get date range
        cursor.execute(
            "SELECT id, start_date, end_date FROM rounds WHERE id = %s",
            (round_id,)
        )
        round_data = cursor.fetchone()

        if not round_data:
            raise HTTPException(404, f"Round {round_id} not found")

        # Assign articles within date range
        cursor.execute(
            """UPDATE articles
               SET round_id = %s
               WHERE round_id IS NULL
                 AND published_at IS NOT NULL
                 AND published_at::date BETWEEN %s AND %s
               RETURNING id""",
            (round_id, round_data["start_date"], round_data["end_date"])
        )
        assigned = cursor.fetchall()

    return {
        "round_id": round_id,
        "articles_assigned": len(assigned),
        "article_ids": [a["id"] for a in assigned],
    }
