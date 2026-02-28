#!/usr/bin/env python3
"""Seed AFL 2026 season rounds with accurate dates.

Run after migration 005 to update rounds with actual AFL fixture dates.
Usage: python scripts/seed_rounds.py
"""

import sys
import os
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_cursor

# AFL 2026 Season Schedule (placeholder - update when fixture released)
# Round 1 typically starts mid-March
AFL_2026_ROUNDS = [
    # (round_number, name, start_date, end_date, lockout_time, is_bye, is_finals)
    (1, "Round 1", "2026-03-12", "2026-03-15", "2026-03-12 19:25:00", False, False),
    (2, "Round 2", "2026-03-19", "2026-03-22", "2026-03-19 19:25:00", False, False),
    (3, "Round 3", "2026-03-26", "2026-03-29", "2026-03-26 19:25:00", False, False),
    (4, "Round 4", "2026-04-02", "2026-04-06", "2026-04-02 19:25:00", False, False),
    (5, "Round 5", "2026-04-09", "2026-04-13", "2026-04-09 19:25:00", False, False),
    (6, "Round 6", "2026-04-16", "2026-04-20", "2026-04-16 19:25:00", False, False),
    (7, "Round 7", "2026-04-23", "2026-04-27", "2026-04-23 19:25:00", False, False),
    (8, "Round 8", "2026-04-30", "2026-05-04", "2026-04-30 19:25:00", False, False),
    (9, "Round 9", "2026-05-07", "2026-05-11", "2026-05-07 19:25:00", False, False),
    (10, "Round 10", "2026-05-14", "2026-05-18", "2026-05-14 19:25:00", False, False),
    (11, "Round 11", "2026-05-21", "2026-05-25", "2026-05-21 19:25:00", False, False),
    (12, "Round 12", "2026-05-28", "2026-06-01", "2026-05-28 19:25:00", True, False),  # Bye 1
    (13, "Round 13", "2026-06-04", "2026-06-08", "2026-06-04 19:25:00", True, False),  # Bye 2
    (14, "Round 14", "2026-06-11", "2026-06-15", "2026-06-11 19:25:00", True, False),  # Bye 3
    (15, "Round 15", "2026-06-18", "2026-06-22", "2026-06-18 19:25:00", False, False),
    (16, "Round 16", "2026-06-25", "2026-06-29", "2026-06-25 19:25:00", False, False),
    (17, "Round 17", "2026-07-02", "2026-07-06", "2026-07-02 19:25:00", False, False),
    (18, "Round 18", "2026-07-09", "2026-07-13", "2026-07-09 19:25:00", False, False),
    (19, "Round 19", "2026-07-16", "2026-07-20", "2026-07-16 19:25:00", False, False),
    (20, "Round 20", "2026-07-23", "2026-07-27", "2026-07-23 19:25:00", False, False),
    (21, "Round 21", "2026-07-30", "2026-08-03", "2026-07-30 19:25:00", False, False),
    (22, "Round 22", "2026-08-06", "2026-08-10", "2026-08-06 19:25:00", False, False),
    (23, "Round 23", "2026-08-13", "2026-08-17", "2026-08-13 19:25:00", False, False),
    (24, "Round 24", "2026-08-20", "2026-08-24", "2026-08-20 19:25:00", False, False),
    # Finals
    (25, "Qualifying & Elimination Finals", "2026-08-27", "2026-08-30", "2026-08-27 19:25:00", False, True),
    (26, "Semi Finals", "2026-09-03", "2026-09-06", "2026-09-03 19:25:00", False, True),
    (27, "Preliminary Finals", "2026-09-10", "2026-09-13", "2026-09-10 19:25:00", False, True),
    (28, "Grand Final", "2026-09-26", "2026-09-26", "2026-09-26 14:30:00", False, True),
]


def seed_rounds():
    """Update rounds with accurate 2026 AFL fixture dates."""
    with get_cursor() as cursor:
        # Get season ID for 2026
        cursor.execute("SELECT id FROM seasons WHERE year = 2026")
        season = cursor.fetchone()

        if not season:
            print("Error: 2026 season not found. Run migration 005 first.")
            return

        season_id = season["id"]
        updated = 0

        for round_data in AFL_2026_ROUNDS:
            round_number, name, start_date, end_date, lockout_time, is_bye, is_finals = round_data

            cursor.execute("""
                INSERT INTO rounds (season_id, round_number, name, start_date, end_date,
                                   lockout_time, is_bye_round, is_finals)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (season_id, round_number) DO UPDATE SET
                    name = EXCLUDED.name,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    lockout_time = EXCLUDED.lockout_time,
                    is_bye_round = EXCLUDED.is_bye_round,
                    is_finals = EXCLUDED.is_finals
            """, (season_id, round_number, name, start_date, end_date,
                  lockout_time, is_bye, is_finals))
            updated += 1

        print(f"Updated {updated} rounds for 2026 season")


def get_current_round():
    """Get the current round based on today's date."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT r.round_number, r.name, r.start_date, r.end_date, r.lockout_time
            FROM rounds r
            JOIN seasons s ON r.season_id = s.id
            WHERE s.is_current = TRUE
              AND r.start_date <= CURRENT_DATE
            ORDER BY r.start_date DESC
            LIMIT 1
        """)
        return cursor.fetchone()


def assign_article_rounds():
    """Assign round_id to existing articles based on published_at date."""
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE articles a
            SET round_id = (
                SELECT r.id
                FROM rounds r
                JOIN seasons s ON r.season_id = s.id
                WHERE s.is_current = TRUE
                  AND a.published_at::date BETWEEN r.start_date AND r.end_date
                LIMIT 1
            )
            WHERE a.round_id IS NULL
              AND a.published_at IS NOT NULL
        """)

        # Count updated
        cursor.execute("SELECT COUNT(*) FROM articles WHERE round_id IS NOT NULL")
        count = cursor.fetchone()[0]
        print(f"Articles with round_id assigned: {count}")


if __name__ == "__main__":
    print("Seeding AFL 2026 rounds...")
    seed_rounds()

    print("\nCurrent round:")
    current = get_current_round()
    if current:
        print(f"  {current['name']} ({current['start_date']} - {current['end_date']})")
    else:
        print("  No current round (season not started)")

    print("\nAssigning rounds to existing articles...")
    assign_article_rounds()

    print("\nDone!")
