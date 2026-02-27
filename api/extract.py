"""Extraction API endpoint"""

import hashlib
import os
from typing import List, Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.claude_client import ClaudeClient
from core.database import get_cache, set_cache, create_extraction_event
from core.entity_resolver import resolve_entities_from_extraction


router = APIRouter()


class Article(BaseModel):
    """Input article for extraction"""
    headline: str
    source: Optional[str] = None
    url: Optional[str] = None


class ExtractionRequest(BaseModel):
    """Request for extraction"""
    domain: str
    articles: List[Article]


class ExtractedItem(BaseModel):
    """Single extraction result"""
    article_index: int
    schema_detected: str
    entities: List[dict]
    data: dict
    confidence: Optional[float] = None


class ExtractionResponse(BaseModel):
    """Response from extraction"""
    extractions: List[ExtractedItem]
    cached: int
    processed: int


def load_config() -> dict:
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def build_afl_prompt(articles: List[Article]) -> str:
    """Build extraction prompt for AFL domain"""
    headlines = "\n".join(
        f"{i+1}. [{a.source or 'Unknown'}] {a.headline}"
        for i, a in enumerate(articles)
    )

    return f"""Extract structured data from these AFL news headlines.

For EACH headline, detect the news type and extract relevant information:

INJURY schema (for injury/availability news):
- player: player name
- status: AVAILABLE | DOUBTFUL | OUT
- injury_type: hamstring, shoulder, concussion, etc.
- return_estimate: "1 week", "2-3 weeks", "season", etc.

SELECTION schema (for team selection news):
- player: player name
- event: SELECTED | OMITTED | RESTED
- match: opponent if mentioned

TEAM_NEWS schema (for general team news):
- team: team name
- ins: [players in]
- outs: [players out]
- changes: description of changes

FORM schema (for player form news):
- player: player name
- trend: IMPROVING | DECLINING | STEADY
- stats_mentioned: any stats referenced

TRADE schema (for trade news):
- player: player name
- from_team: team trading away
- to_team: team receiving
- status: CONFIRMED | RUMOR | REQUESTED

Headlines:
{headlines}

Respond with ONLY a JSON array (no other text):
[{{"id": 1, "schema": "injury", "player": "...", "status": "OUT", ...}}, ...]

If a headline doesn't match any schema or isn't AFL related, use schema "other" with just a "summary" field.
"""


def build_market_prompt(articles: List[Article]) -> str:
    """Build extraction prompt for Market domain"""
    headlines = "\n".join(
        f"{i+1}. [{a.source or 'Unknown'}] {a.headline}"
        for i, a in enumerate(articles)
    )

    return f"""Score the sentiment of these financial news headlines.

For EACH headline, analyze:
- sentiment_score: 0-100 (0=very negative, 50=neutral, 100=very positive)
- category: macro | equity | crypto | commodity | forex | other
- priority: critical | high | medium | low
- assets_mentioned: list of specific assets/tickers mentioned
- reason: brief explanation

Headlines:
{headlines}

Respond with ONLY a JSON array (no other text):
[{{"id": 1, "sentiment_score": 45, "category": "crypto", "priority": "high", "assets_mentioned": ["BTC"], "reason": "..."}}, ...]
"""


@router.post("", response_model=ExtractionResponse)
def extract(request: ExtractionRequest):
    """
    Extract structured data from news articles.

    Supports domains: afl, market
    """
    config = load_config()
    domain_config = config.get("domains", {}).get(request.domain)

    if not domain_config:
        raise HTTPException(status_code=400, detail=f"Unknown domain: {request.domain}")

    # Build prompt based on domain
    if request.domain == "afl":
        prompt = build_afl_prompt(request.articles)
    elif request.domain == "market":
        prompt = build_market_prompt(request.articles)
    else:
        raise HTTPException(status_code=400, detail=f"Domain not implemented: {request.domain}")

    # Check cache
    cache_key = hashlib.sha256(prompt.encode()).hexdigest()
    cached_response = get_cache(cache_key)

    if cached_response:
        return ExtractionResponse(
            extractions=[ExtractedItem(**e) for e in cached_response],
            cached=len(request.articles),
            processed=0,
        )

    # Call Claude
    claude_config = config.get("claude", {})
    client = ClaudeClient(
        cli_path=claude_config.get("cli_path", "/bin/claude"),
        model=claude_config.get("model", "claude-opus-4-5-20251101"),
        timeout=claude_config.get("timeout", 300),
        max_turns=claude_config.get("max_turns", 1),
    )

    result = client.query_json(prompt)

    if "error" in result:
        raise HTTPException(status_code=500, detail=f"Claude error: {result['error']}")

    # Process results
    extractions = []
    if isinstance(result, list):
        for item in result:
            idx = item.get("id", 1) - 1
            schema = item.pop("schema", "other")
            item.pop("id", None)

            # Resolve entities
            resolved_entities = resolve_entities_from_extraction(item, request.domain)
            entity_ids = [e["id"] for e in resolved_entities]

            extraction = ExtractedItem(
                article_index=idx,
                schema_detected=schema,
                entities=resolved_entities,
                data=item,
                confidence=item.get("confidence"),
            )
            extractions.append(extraction)

            # Store event
            if idx < len(request.articles):
                article = request.articles[idx]
                article_hash = hashlib.sha256(
                    f"{article.headline}:{article.source}".encode()
                ).hexdigest()

                create_extraction_event(
                    domain=request.domain,
                    schema_type=schema,
                    article_hash=article_hash,
                    headline=article.headline,
                    extracted_data=item,
                    source=article.source,
                    source_url=article.url,
                    entities_mentioned=entity_ids if entity_ids else None,
                )

    # Cache response
    cache_ttl = config.get("cache", {}).get("ttl_hours", 1)
    set_cache(cache_key, [e.model_dump() for e in extractions], cache_ttl)

    return ExtractionResponse(
        extractions=extractions,
        cached=0,
        processed=len(request.articles),
    )
