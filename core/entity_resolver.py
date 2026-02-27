"""Entity resolution - link extracted names to entity UUIDs"""

from typing import List, Dict, Optional
from core.database import search_entities


def resolve_entity(name: str, domain: str, entity_type: str = None) -> Optional[Dict]:
    """
    Resolve entity name to UUID.

    Strategy:
    1. Exact match on canonical_name
    2. Exact match on alias
    3. Fuzzy match (Levenshtein) if close enough
    """
    if not name:
        return None

    # Search by name (searches canonical + aliases)
    results = search_entities(name.strip(), domain=domain, limit=5)

    if not results:
        return None

    # Exact match (case-insensitive)
    for r in results:
        if r["canonical_name"].lower() == name.lower():
            return r

    # Alias exact match
    for r in results:
        if r.get("match_type") == "alias":
            return r

    # Fuzzy match using Levenshtein
    try:
        from Levenshtein import ratio
        best_match = None
        best_score = 0.0
        for r in results:
            score = ratio(name.lower(), r["canonical_name"].lower())
            if score > best_score and score >= 0.8:  # 80% threshold
                best_score = score
                best_match = r
        return best_match
    except ImportError:
        # Levenshtein not available, skip fuzzy matching
        return None


def resolve_entities_from_extraction(
    extracted_data: dict,
    domain: str,
) -> List[Dict]:
    """
    Extract entity names from LLM result and resolve to UUIDs.

    AFL fields: player, team, ins, outs, from_team, to_team
    Market fields: assets_mentioned
    """
    resolved = []
    seen_ids = set()

    # Single-value entity fields
    entity_fields = ["player", "team", "from_team", "to_team"]

    for field in entity_fields:
        name = extracted_data.get(field)
        if name and isinstance(name, str):
            entity = resolve_entity(name, domain)
            if entity and str(entity["id"]) not in seen_ids:
                resolved.append({
                    "id": str(entity["id"]),
                    "name": entity["canonical_name"],
                    "type": entity["entity_type"],
                    "resolved": True,
                })
                seen_ids.add(str(entity["id"]))

    # List fields (ins, outs, assets_mentioned)
    list_fields = ["ins", "outs", "assets_mentioned"]

    for field in list_fields:
        names = extracted_data.get(field, [])
        if isinstance(names, list):
            for name in names:
                if name and isinstance(name, str):
                    entity = resolve_entity(name, domain)
                    if entity and str(entity["id"]) not in seen_ids:
                        resolved.append({
                            "id": str(entity["id"]),
                            "name": entity["canonical_name"],
                            "type": entity["entity_type"],
                            "resolved": True,
                        })
                        seen_ids.add(str(entity["id"]))

    return resolved
