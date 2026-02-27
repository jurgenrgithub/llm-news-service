"""Entity API endpoints"""

from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.database import (
    get_entity_by_id,
    search_entities,
    get_entity_state,
    get_entity_events,
    create_entity,
    add_entity_alias,
)


router = APIRouter()


class EntityResponse(BaseModel):
    """Entity details"""
    id: str
    domain: str
    entity_type: str
    canonical_name: str
    external_id: Optional[str]
    attributes: dict


class EntityStateResponse(BaseModel):
    """Entity with current state"""
    entity: EntityResponse
    current_state: Optional[dict]


class EntitySearchResult(BaseModel):
    """Search result"""
    id: str
    name: str
    type: str
    domain: str
    match_type: str


class CreateEntityRequest(BaseModel):
    """Request to create an entity"""
    domain: str
    entity_type: str
    canonical_name: str
    external_id: Optional[str] = None
    attributes: Optional[dict] = None
    aliases: Optional[List[str]] = None


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, description="Search query"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    """Search entities by name or alias"""
    results = search_entities(q, domain=domain, limit=limit)

    return {
        "query": q,
        "results": [
            EntitySearchResult(
                id=str(r["id"]),
                name=r["canonical_name"],
                type=r["entity_type"],
                domain=r["domain"],
                match_type=r.get("match_type", "canonical"),
            )
            for r in results
        ],
    }


@router.get("/{entity_id}")
def get_entity(entity_id: str) -> EntityResponse:
    """Get entity by ID"""
    entity = get_entity_by_id(entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return EntityResponse(
        id=str(entity["id"]),
        domain=entity["domain"],
        entity_type=entity["entity_type"],
        canonical_name=entity["canonical_name"],
        external_id=entity["external_id"],
        attributes=entity["attributes"] or {},
    )


@router.get("/{entity_id}/status")
def get_status(entity_id: str) -> EntityStateResponse:
    """Get entity with current state"""
    entity = get_entity_by_id(entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    state = get_entity_state(entity_id)

    return EntityStateResponse(
        entity=EntityResponse(
            id=str(entity["id"]),
            domain=entity["domain"],
            entity_type=entity["entity_type"],
            canonical_name=entity["canonical_name"],
            external_id=entity["external_id"],
            attributes=entity["attributes"] or {},
        ),
        current_state=state["state"] if state else None,
    )


@router.get("/{entity_id}/news")
def get_news(
    entity_id: str,
    days: Optional[int] = Query(None, ge=1, le=365, description="Filter to last N days"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Get recent news/extractions for an entity"""
    entity = get_entity_by_id(entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    events = get_entity_events(entity_id, limit=limit, days=days)

    return {
        "entity": EntityResponse(
            id=str(entity["id"]),
            domain=entity["domain"],
            entity_type=entity["entity_type"],
            canonical_name=entity["canonical_name"],
            external_id=entity["external_id"],
            attributes=entity["attributes"] or {},
        ),
        "extractions": [
            {
                "id": e["id"],
                "headline": e["headline"],
                "schema": e["schema_type"],
                "data": e["extracted_data"],
                "source": e["source"],
                "extracted_at": e["created_at"].isoformat() if e["created_at"] else None,
            }
            for e in events
        ],
    }


@router.post("")
def create(request: CreateEntityRequest) -> EntityResponse:
    """Create a new entity"""
    entity = create_entity(
        domain=request.domain,
        entity_type=request.entity_type,
        canonical_name=request.canonical_name,
        external_id=request.external_id,
        attributes=request.attributes,
    )

    # Add aliases if provided
    if request.aliases:
        for alias in request.aliases:
            add_entity_alias(str(entity["id"]), alias, source="manual")

    return EntityResponse(
        id=str(entity["id"]),
        domain=entity["domain"],
        entity_type=entity["entity_type"],
        canonical_name=entity["canonical_name"],
        external_id=entity["external_id"],
        attributes=entity["attributes"] or {},
    )
