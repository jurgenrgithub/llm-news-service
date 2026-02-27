"""Database connection and operations"""

import os
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor
import yaml


def load_db_config() -> dict:
    """Load database config from config.yaml"""
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("database", {})


def get_connection():
    """Get database connection"""
    db_config = load_db_config()
    return psycopg2.connect(
        host=db_config.get("host", "localhost"),
        port=db_config.get("port", 5432),
        dbname=db_config.get("name", "llm_news"),
        user=db_config.get("user", "llm_news"),
        password=db_config.get("password", ""),
    )


@contextmanager
def get_cursor():
    """Context manager for database cursor"""
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


# Entity operations

def get_entity_by_id(entity_id: str) -> Optional[Dict[str, Any]]:
    """Get entity by UUID"""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM entities WHERE id = %s",
            (entity_id,)
        )
        return cursor.fetchone()


def get_entity_by_name(domain: str, entity_type: str, name: str) -> Optional[Dict[str, Any]]:
    """Get entity by canonical name"""
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT * FROM entities
               WHERE domain = %s AND entity_type = %s AND canonical_name = %s""",
            (domain, entity_type, name)
        )
        return cursor.fetchone()


def search_entities(query: str, domain: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Search entities by name or alias"""
    with get_cursor() as cursor:
        # Search by canonical name
        sql = """
            SELECT e.*, 'canonical' as match_type
            FROM entities e
            WHERE LOWER(e.canonical_name) LIKE LOWER(%s)
        """
        params = [f"%{query}%"]

        if domain:
            sql += " AND e.domain = %s"
            params.append(domain)

        sql += """
            UNION
            SELECT e.*, 'alias' as match_type
            FROM entities e
            JOIN entity_aliases a ON e.id = a.entity_id
            WHERE LOWER(a.alias) LIKE LOWER(%s)
        """
        params.append(f"%{query}%")

        if domain:
            sql += " AND e.domain = %s"
            params.append(domain)

        sql += f" LIMIT {limit}"

        cursor.execute(sql, params)
        return list(cursor.fetchall())


def create_entity(
    domain: str,
    entity_type: str,
    canonical_name: str,
    external_id: Optional[str] = None,
    attributes: Optional[dict] = None,
) -> Dict[str, Any]:
    """Create a new entity"""
    import json
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO entities (domain, entity_type, canonical_name, external_id, attributes)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING *""",
            (domain, entity_type, canonical_name, external_id, json.dumps(attributes or {}))
        )
        return cursor.fetchone()


def add_entity_alias(entity_id: str, alias: str, source: str = "manual", confidence: float = 1.0):
    """Add an alias to an entity"""
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO entity_aliases (entity_id, alias, source, confidence)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (alias, entity_id) DO NOTHING""",
            (entity_id, alias, source, confidence)
        )


# Event operations

def create_extraction_event(
    domain: str,
    schema_type: str,
    article_hash: str,
    headline: str,
    extracted_data: dict,
    source: Optional[str] = None,
    source_url: Optional[str] = None,
    entities_mentioned: Optional[List[str]] = None,
    confidence: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Create extraction event (idempotent by article_hash)"""
    import json
    with get_cursor() as cursor:
        try:
            cursor.execute(
                """INSERT INTO extraction_events
                   (domain, schema_type, article_hash, headline, source, source_url,
                    extracted_data, entities_mentioned, confidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s::uuid[], %s)
                   RETURNING *""",
                (domain, schema_type, article_hash, headline, source, source_url,
                 json.dumps(extracted_data), entities_mentioned, confidence)
            )
            return cursor.fetchone()
        except psycopg2.errors.UniqueViolation:
            # Already exists
            return None


def get_entity_events(entity_id: str, limit: int = 20, days: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get extraction events mentioning an entity"""
    with get_cursor() as cursor:
        if days:
            cursor.execute(
                """SELECT * FROM extraction_events
                   WHERE %s = ANY(entities_mentioned)
                   AND created_at >= NOW() - INTERVAL '%s days'
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (entity_id, days, limit)
            )
        else:
            cursor.execute(
                """SELECT * FROM extraction_events
                   WHERE %s = ANY(entities_mentioned)
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (entity_id, limit)
            )
        return list(cursor.fetchall())


# State operations

def get_entity_state(entity_id: str) -> Optional[Dict[str, Any]]:
    """Get current state for an entity"""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM entity_current_state WHERE entity_id = %s",
            (entity_id,)
        )
        return cursor.fetchone()


def update_entity_state(entity_id: str, domain: str, state: dict, last_event_id: int):
    """Update current state for an entity"""
    import json
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO entity_current_state (entity_id, domain, state, last_event_id, computed_at)
               VALUES (%s, %s, %s, %s, NOW())
               ON CONFLICT (entity_id) DO UPDATE
               SET state = EXCLUDED.state,
                   last_event_id = EXCLUDED.last_event_id,
                   computed_at = NOW()""",
            (entity_id, domain, json.dumps(state), last_event_id)
        )


# Cache operations

def get_cache(cache_key: str) -> Optional[dict]:
    """Get cached extraction response"""
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT response FROM extraction_cache
               WHERE cache_key = %s AND expires_at > NOW()""",
            (cache_key,)
        )
        row = cursor.fetchone()
        return row["response"] if row else None


def set_cache(cache_key: str, response: dict, ttl_hours: int = 1):
    """Cache extraction response"""
    import json
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO extraction_cache (cache_key, response, expires_at)
               VALUES (%s, %s, NOW() + INTERVAL '%s hours')
               ON CONFLICT (cache_key) DO UPDATE
               SET response = EXCLUDED.response,
                   expires_at = EXCLUDED.expires_at""",
            (cache_key, json.dumps(response), ttl_hours)
        )
