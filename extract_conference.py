from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

def extract_conference_years(
    database: Path | str = "heart.db",
) -> list[int]:
    """Extract all conference years available in the database.

    Parameters
    ----------
    database
        Path to the SQLite database.

    Returns
    -------
    list[int]
        Conference years sorted from most recent to oldest, including future conferences.
    """
    database = Path(database)

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT year
            FROM conference
            WHERE year IS NOT NULL
            ORDER BY year DESC
            """
        ).fetchall()

    return [int(row[0]) for row in rows]


def extract_conference(
    year: int,
    database: Path | str = "heart.db",
) -> dict[str, Any] | None:
    database = Path(database)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row

        conference = connection.execute(
            """
            SELECT
                c.id,
                c.year,
                c.name AS name,
                c.period AS dates,
                c.start_date AS start_date,
                c.end_date AS end_date,
                c.abstracts_available AS abstracts_available,
                c.is_finished AS is_finished,
                c.url AS url,
                venue.name AS venue,
                venue.url AS venue_url,
                country.iso2 AS country_code
            FROM conference AS c
            LEFT JOIN institution AS venue
                ON venue.id = c.venue_institution_id
            LEFT JOIN country
                ON country.id = venue.country_id
            WHERE c.year = ?
            """,
            (year,),
        ).fetchone()

        if conference is None:
            return None

        organizers = connection.execute(
            """
            SELECT
                p.first_name || ' ' || p.last_name AS name,
                p.url AS url,
                p.email AS email,
                cc.chair_order AS organizer_order
            FROM conference_chair AS cc
            JOIN person AS p
                ON p.id = cc.person_id
            WHERE cc.conference_id = ?
            ORDER BY cc.chair_order
            """,
            (conference["id"],),
        ).fetchall()

    return {
        "year": conference["year"],
        "name": conference["name"],
        "dates": conference["dates"],
        "start_date": conference["start_date"],
        "end_date": conference["end_date"],
        "abstracts_available": bool(conference["abstracts_available"]),
        "is_finished": bool(conference["is_finished"]),
        "url": conference["url"],
        "venue": conference["venue"],
        "venue_url": conference["venue_url"],
        "country_code": conference["country_code"],
        "organizers": [
            {
                "name": organizer["name"],
                "url": organizer["url"],
                "email": organizer["email"],
                "order": organizer["organizer_order"],
            }
            for organizer in organizers
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("year", type=int)
    parser.add_argument("database", nargs="?", default="heart.db")
    args = parser.parse_args()

    result = extract_conference(args.year, args.database)
    print(result)