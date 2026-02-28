#!/usr/bin/env python3
"""Seed AFL clubs and their aliases into the entities table."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_cursor, create_entity, add_entity_alias

# 18 AFL clubs with their common aliases
AFL_CLUBS = [
    {
        "name": "Adelaide",
        "short": "ADE",
        "aliases": ["Crows", "Adelaide Crows", "AFC"],
    },
    {
        "name": "Brisbane Lions",
        "short": "BRI",
        "aliases": ["Lions", "Brisbane", "BL"],
    },
    {
        "name": "Carlton",
        "short": "CAR",
        "aliases": ["Blues", "Carlton Blues", "CFC"],
    },
    {
        "name": "Collingwood",
        "short": "COL",
        "aliases": ["Magpies", "Pies", "Collingwood Magpies"],
    },
    {
        "name": "Essendon",
        "short": "ESS",
        "aliases": ["Bombers", "Dons", "Essendon Bombers", "EFC"],
    },
    {
        "name": "Fremantle",
        "short": "FRE",
        "aliases": ["Dockers", "Freo", "Fremantle Dockers", "FFC"],
    },
    {
        "name": "Geelong",
        "short": "GEE",
        "aliases": ["Cats", "Geelong Cats", "GFC"],
    },
    {
        "name": "Gold Coast",
        "short": "GCS",
        "aliases": ["Suns", "Gold Coast Suns", "GCFC"],
    },
    {
        "name": "GWS Giants",
        "short": "GWS",
        "aliases": ["Giants", "GWS", "Greater Western Sydney"],
    },
    {
        "name": "Hawthorn",
        "short": "HAW",
        "aliases": ["Hawks", "Hawthorn Hawks", "HFC"],
    },
    {
        "name": "Melbourne",
        "short": "MEL",
        "aliases": ["Demons", "Dees", "Melbourne Demons", "MFC"],
    },
    {
        "name": "North Melbourne",
        "short": "NME",
        "aliases": ["Kangaroos", "Roos", "Kangas", "North", "NMFC"],
    },
    {
        "name": "Port Adelaide",
        "short": "POR",
        "aliases": ["Power", "Port", "Port Adelaide Power", "PAFC"],
    },
    {
        "name": "Richmond",
        "short": "RIC",
        "aliases": ["Tigers", "Richmond Tigers", "RFC"],
    },
    {
        "name": "St Kilda",
        "short": "STK",
        "aliases": ["Saints", "St Kilda Saints", "SKFC"],
    },
    {
        "name": "Sydney",
        "short": "SYD",
        "aliases": ["Swans", "Sydney Swans", "SFC"],
    },
    {
        "name": "West Coast",
        "short": "WCE",
        "aliases": ["Eagles", "West Coast Eagles", "WCE"],
    },
    {
        "name": "Western Bulldogs",
        "short": "WBD",
        "aliases": ["Bulldogs", "Dogs", "Doggies", "Footscray"],
    },
]


def seed_clubs():
    """Insert all AFL clubs and their aliases."""
    created = 0
    skipped = 0
    aliases_added = 0

    for club in AFL_CLUBS:
        # Check if club already exists
        with get_cursor() as cursor:
            cursor.execute(
                """SELECT id FROM entities
                   WHERE domain = 'afl' AND entity_type = 'team'
                   AND canonical_name = %s""",
                (club["name"],)
            )
            existing = cursor.fetchone()

        if existing:
            entity_id = str(existing["id"])
            print(f"  [SKIP] {club['name']} already exists")
            skipped += 1
        else:
            # Create new entity
            entity = create_entity(
                domain="afl",
                entity_type="team",
                canonical_name=club["name"],
                attributes={"short": club["short"]},
            )
            entity_id = str(entity["id"])
            print(f"  [NEW] {club['name']} (ID: {entity_id[:8]}...)")
            created += 1

        # Add aliases
        for alias in club["aliases"]:
            try:
                add_entity_alias(entity_id, alias, source="seed")
                aliases_added += 1
            except Exception:
                pass  # Duplicate alias, ignore

    print(f"\nSummary:")
    print(f"  Created: {created} clubs")
    print(f"  Skipped: {skipped} (already exist)")
    print(f"  Aliases added: {aliases_added}")


if __name__ == "__main__":
    print("Seeding AFL clubs...")
    seed_clubs()
    print("\nDone!")
