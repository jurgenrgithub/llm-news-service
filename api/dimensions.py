"""Dimensions and rounds API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database import get_cursor

router = APIRouter()


@router.get("")
def list_dimensions(
    tier: Optional[int] = Query(None, ge=1, le=5, description="Filter by tier"),
    active_only: bool = Query(True, description="Only show active dimensions"),
):
    """List all dimensions with their metadata."""
    with get_cursor() as cursor:
        if tier:
            cursor.execute(
                """SELECT id, code, name, tier, description, is_active,
                          keyword_mappings, prompt_guidance
                   FROM dimensions
                   WHERE tier = %s AND (is_active = %s OR %s = FALSE)
                   ORDER BY tier, id""",
                (tier, active_only, active_only)
            )
        else:
            cursor.execute(
                """SELECT id, code, name, tier, description, is_active,
                          keyword_mappings, prompt_guidance
                   FROM dimensions
                   WHERE is_active = %s OR %s = FALSE
                   ORDER BY tier, id""",
                (active_only, active_only)
            )
        dimensions = cursor.fetchall()

    return {
        "count": len(dimensions),
        "dimensions": [
            {
                "id": d["id"],
                "code": d["code"],
                "name": d["name"],
                "tier": d["tier"],
                "description": d["description"],
                "is_active": d["is_active"],
                "keyword_mappings": d["keyword_mappings"],
            }
            for d in dimensions
        ]
    }


@router.get("/{dimension_code}")
def get_dimension(dimension_code: str):
    """Get a specific dimension by code."""
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT id, code, name, tier, description, is_active,
                      keyword_mappings, prompt_guidance, bespoke_feature_schema
               FROM dimensions
               WHERE code = %s""",
            (dimension_code,)
        )
        dimension = cursor.fetchone()

    if not dimension:
        raise HTTPException(404, f"Dimension '{dimension_code}' not found")

    return {
        "id": dimension["id"],
        "code": dimension["code"],
        "name": dimension["name"],
        "tier": dimension["tier"],
        "description": dimension["description"],
        "is_active": dimension["is_active"],
        "keyword_mappings": dimension["keyword_mappings"],
        "prompt_guidance": dimension["prompt_guidance"],
        "bespoke_feature_schema": dimension["bespoke_feature_schema"],
    }


@router.get("/{dimension_code}/articles")
def get_dimension_articles(
    dimension_code: str,
    limit: int = Query(20, ge=1, le=100),
):
    """Get articles tagged with this dimension."""
    with get_cursor() as cursor:
        # First get the dimension ID
        cursor.execute(
            "SELECT id FROM dimensions WHERE code = %s",
            (dimension_code,)
        )
        dimension = cursor.fetchone()

        if not dimension:
            raise HTTPException(404, f"Dimension '{dimension_code}' not found")

        # Get articles with this dimension
        cursor.execute(
            """SELECT DISTINCT a.id, a.url, a.title, a.source, a.published_at,
                      t.tag_value, t.match_count, t.is_headline
               FROM articles a
               JOIN article_tags t ON a.id = t.article_id
               WHERE t.dimension_id = %s
               ORDER BY a.published_at DESC
               LIMIT %s""",
            (dimension["id"], limit)
        )
        articles = cursor.fetchall()

    return {
        "dimension": dimension_code,
        "count": len(articles),
        "articles": [
            {
                "id": a["id"],
                "url": a["url"],
                "title": a["title"],
                "source": a["source"],
                "published_at": a["published_at"].isoformat() if a["published_at"] else None,
                "tag_value": a["tag_value"],
                "match_count": a["match_count"],
                "in_headline": a["is_headline"],
            }
            for a in articles
        ]
    }
