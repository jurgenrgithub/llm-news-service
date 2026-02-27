"""Article ingestion and query endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.database import get_cursor

router = APIRouter()


class ArticleIngest(BaseModel):
    """Request to ingest a full article."""
    url: str
    title: str
    body: str
    source: Optional[str] = None
    published_at: Optional[str] = None


class ArticleIngestResponse(BaseModel):
    """Response from article ingestion."""
    status: str  # "created" | "updated" | "duplicate"
    article_id: Optional[int] = None


@router.post("/ingest", response_model=ArticleIngestResponse)
def ingest_article(request: ArticleIngest):
    """
    Ingest a full article for processing.

    - Deduplicates by URL and content hash
    - Queues for background triage + analysis
    - Returns immediately (processing is async)
    """
    from core.article_processor import ArticleProcessor

    processor = ArticleProcessor()
    result = processor.ingest_article(
        url=request.url,
        title=request.title,
        body=request.body,
        source=request.source,
        published_at=request.published_at,
    )

    if result is None:
        return ArticleIngestResponse(status="duplicate")

    return ArticleIngestResponse(
        status="created",
        article_id=result["id"]
    )


@router.get("/{article_id}")
def get_article(article_id: int):
    """Get article with all extraction events."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
        article = cursor.fetchone()

        if not article:
            raise HTTPException(404, "Article not found")

        cursor.execute(
            """SELECT ae.*, e.canonical_name
               FROM article_entities ae
               LEFT JOIN entities e ON ae.entity_id = e.id
               WHERE ae.article_id = %s""",
            (article_id,)
        )
        entities = cursor.fetchall()

        cursor.execute(
            "SELECT * FROM extraction_events WHERE article_id = %s",
            (article_id,)
        )
        extractions = cursor.fetchall()

    # Convert to serializable format
    article_dict = dict(article)
    for key, value in article_dict.items():
        if hasattr(value, 'isoformat'):
            article_dict[key] = value.isoformat()

    entities_list = []
    for e in entities:
        e_dict = dict(e)
        for key, value in e_dict.items():
            if hasattr(value, 'isoformat'):
                e_dict[key] = value.isoformat()
        entities_list.append(e_dict)

    extractions_list = []
    for ex in extractions:
        ex_dict = dict(ex)
        for key, value in ex_dict.items():
            if hasattr(value, 'isoformat'):
                ex_dict[key] = value.isoformat()
        extractions_list.append(ex_dict)

    return {
        "article": article_dict,
        "entities_mentioned": entities_list,
        "extractions": extractions_list,
    }


@router.get("")
def list_articles(
    status: Optional[str] = Query(None, description="Filter by triage_status"),
    limit: int = Query(20, ge=1, le=100),
):
    """List recent articles."""
    with get_cursor() as cursor:
        if status:
            cursor.execute(
                """SELECT id, url, title, source, published_at, triage_status,
                          analysis_status, scraped_at
                   FROM articles
                   WHERE triage_status = %s
                   ORDER BY scraped_at DESC LIMIT %s""",
                (status, limit)
            )
        else:
            cursor.execute(
                """SELECT id, url, title, source, published_at, triage_status,
                          analysis_status, scraped_at
                   FROM articles
                   ORDER BY scraped_at DESC LIMIT %s""",
                (limit,)
            )
        articles = cursor.fetchall()

    return {
        "articles": [
            {
                "id": a["id"],
                "url": a["url"],
                "title": a["title"],
                "source": a["source"],
                "published_at": a["published_at"].isoformat() if a["published_at"] else None,
                "triage_status": a["triage_status"],
                "analysis_status": a["analysis_status"],
                "scraped_at": a["scraped_at"].isoformat() if a["scraped_at"] else None,
            }
            for a in articles
        ]
    }


@router.post("/process/triage")
def trigger_triage(batch_size: int = Query(50, ge=1, le=200)):
    """Manually trigger triage batch (for testing)."""
    from core.article_processor import ArticleProcessor

    processor = ArticleProcessor()
    count = processor.run_triage_batch(batch_size)
    return {"processed": count}


@router.post("/process/analysis")
def trigger_analysis(batch_size: int = Query(20, ge=1, le=50)):
    """Manually trigger deep analysis batch (for testing)."""
    from core.article_processor import ArticleProcessor
    from core.claude_client import ClaudeClient

    processor = ArticleProcessor(ClaudeClient())
    count = processor.run_analysis_batch(batch_size)
    return {"processed": count}


@router.post("/process/cleanup")
def trigger_cleanup():
    """Manually trigger expired article cleanup."""
    from core.article_processor import ArticleProcessor

    processor = ArticleProcessor()
    count = processor.cleanup_expired()
    return {"deleted": count}
