

"""Export the HEART SQLite database to human-readable YAML files.

This script is intended to be run once after migrating the old MySQL dump to
``heart.db``. It exports the normalized SQLite content to YAML files that can
then become the source of truth for the project.

Typical use:

    uv run export_to_yaml.py heart.db data

It creates:


    data/countries.yml
    data/institutions.yml
    data/units.yml
    data/people.yml
    data/roles.yml
    data/keywords.yml
    data/conferences.yml

Countries are exported with ISO 3166-1 alpha-2 codes when available. Legacy
non-country groupings such as the European Union and international partners
are exported with project-specific pseudo-codes.

The output is deliberately redundant enough to be readable: for example,
people contain their roles and keywords directly, even though the SQLite
schema stores them in association tables.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml


DEFAULT_DATABASE = "heart.db"
DEFAULT_OUTPUT_DIRECTORY = "data"


def slugify(*parts: object) -> str:
    """Create a stable, readable identifier from text fragments."""
    text = "_".join(str(part) for part in parts if part is not None and str(part).strip())
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "item"


def remove_none_values(data: dict[str, Any]) -> dict[str, Any]:
    """Remove keys with None, empty strings, or empty lists."""
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if value == "":
            continue
        if value == []:
            continue
        cleaned[key] = value
    return cleaned


def fetch_all(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Return query results as a list of dictionaries."""
    cursor = connection.execute(query, parameters)
    return [dict(row) for row in cursor.fetchall()]


def write_yaml(path: Path, data: Any) -> None:
    """Write data as readable YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            data,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )


def make_unique_slug(base: str, existing: set[str]) -> str:
    """Return a slug that is unique within an existing set."""
    candidate = base
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{counter}"
        counter += 1
    existing.add(candidate)
    return candidate


def build_country_slugs(connection: sqlite3.Connection) -> dict[int, str]:
    """Build stable YAML ids for countries and non-country groupings."""
    rows = fetch_all(connection, "SELECT id, iso2 FROM country ORDER BY iso2")
    used: set[str] = set()
    return {
        row["id"]: make_unique_slug(slugify(row["iso2"]), used)
        for row in rows
    }


def build_institution_slugs(
    connection: sqlite3.Connection,
    country_slugs: dict[int, str],
) -> dict[int, str]:
    """Build stable YAML ids for institutions."""
    rows = fetch_all(
        connection,
        """
        SELECT institution.id,
               institution.name,
               institution.acronym,
               institution.country_id
        FROM institution
        ORDER BY institution.name
        """,
    )
    used: set[str] = set()
    result: dict[int, str] = {}
    for row in rows:
        base = slugify(row["acronym"] or row["name"])
        if not base or base == "item":
            base = slugify(row["name"], country_slugs[row["country_id"]])
        result[row["id"]] = make_unique_slug(base, used)
    return result


def build_unit_slugs(
    connection: sqlite3.Connection,
    institution_slugs: dict[int, str],
) -> dict[int, str]:
    """Build stable YAML ids for units."""
    rows = fetch_all(
        connection,
        """
        SELECT unit.id,
               unit.name,
               unit.acronym,
               unit.institution_id
        FROM unit
        ORDER BY unit.name
        """,
    )
    used: set[str] = set()
    result: dict[int, str] = {}
    for row in rows:
        base = slugify(institution_slugs[row["institution_id"]], row["acronym"] or row["name"])
        result[row["id"]] = make_unique_slug(base, used)
    return result


def build_person_slugs(connection: sqlite3.Connection) -> dict[int, str]:
    """Build stable YAML ids for people."""
    rows = fetch_all(
        connection,
        """
        SELECT id, first_name, last_name
        FROM person
        ORDER BY last_name, first_name, id
        """,
    )
    used: set[str] = set()
    return {
        row["id"]: make_unique_slug(slugify(row["first_name"], row["last_name"]), used)
        for row in rows
    }


def build_conference_slugs(connection: sqlite3.Connection) -> dict[int, str]:
    """Build stable YAML ids for conferences."""
    rows = fetch_all(
        connection,
        """
        SELECT id, year, name
        FROM conference
        ORDER BY year, name
        """,
    )
    used: set[str] = set()
    return {
        row["id"]: make_unique_slug(slugify("heart", row["year"], row["name"]), used)
        for row in rows
    }


def export_countries(
    connection: sqlite3.Connection,
    output_directory: Path,
    country_slugs: dict[int, str],
) -> None:
    """Export countries."""
    rows = fetch_all(
        connection,
        """
        SELECT id, old_id, iso2
        FROM country
        ORDER BY iso2
        """,
    )
    countries = [
        remove_none_values(
            {
                "id": country_slugs[row["id"]],
                "iso2": row["iso2"],
                "legacy_id": row["old_id"],
            }
        )
        for row in rows
    ]
    write_yaml(output_directory / "countries.yml", countries)


def export_institutions(
    connection: sqlite3.Connection,
    output_directory: Path,
    country_slugs: dict[int, str],
    institution_slugs: dict[int, str],
) -> None:
    """Export institutions."""
    rows = fetch_all(
        connection,
        """
        SELECT id, old_id, name, acronym, url, country_id, is_heart_member
        FROM institution
        ORDER BY name
        """,
    )
    institutions = [
        remove_none_values(
            {
                "id": institution_slugs[row["id"]],
                "name": row["name"],
                "acronym": row["acronym"],
                "url": row["url"],
                "country": country_slugs[row["country_id"]],
                "is_heart_member": bool(row["is_heart_member"]),
                "legacy_id": row["old_id"],
            }
        )
        for row in rows
    ]
    write_yaml(output_directory / "institutions.yml", institutions)


def export_units(
    connection: sqlite3.Connection,
    output_directory: Path,
    institution_slugs: dict[int, str],
    unit_slugs: dict[int, str],
) -> None:
    """Export units."""
    rows = fetch_all(
        connection,
        """
        SELECT id, old_id, name, acronym, url, institution_id
        FROM unit
        ORDER BY name
        """,
    )
    units = [
        remove_none_values(
            {
                "id": unit_slugs[row["id"]],
                "name": row["name"],
                "acronym": row["acronym"],
                "url": row["url"],
                "institution": institution_slugs[row["institution_id"]],
                "legacy_id": row["old_id"],
            }
        )
        for row in rows
    ]
    write_yaml(output_directory / "units.yml", units)


def roles_for_person(
    connection: sqlite3.Connection,
    person_id: int,
    institution_slugs: dict[int, str],
    conference_slugs: dict[int, str],
) -> list[dict[str, Any]]:
    """Return readable role assignments for one person."""
    rows = fetch_all(
        connection,
        """
        SELECT role.name AS role,
               person_role.institution_id,
               person_role.conference_id,
               person_role.start_year,
               person_role.end_year,
               person_role.role_order,
               person_role.legacy_id,
               person_role.comment
        FROM person_role
        JOIN role ON role.id = person_role.role_id
        WHERE person_role.person_id = ?
        ORDER BY role.name, person_role.start_year, person_role.role_order
        """,
        (person_id,),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            remove_none_values(
                {
                    "role": row["role"],
                    "institution": institution_slugs.get(row["institution_id"]),
                    "conference": conference_slugs.get(row["conference_id"]),
                    "start_year": row["start_year"],
                    "end_year": row["end_year"],
                    "order": row["role_order"],
                    "legacy_id": row["legacy_id"],
                    "comment": row["comment"],
                }
            )
        )
    return result


def keywords_for_person(connection: sqlite3.Connection, person_id: int) -> list[str]:
    """Return the keywords attached to one person."""
    rows = fetch_all(
        connection,
        """
        SELECT keyword.name
        FROM person_keyword
        JOIN keyword ON keyword.id = person_keyword.keyword_id
        WHERE person_keyword.person_id = ?
        ORDER BY keyword.name
        """,
        (person_id,),
    )
    return [row["name"] for row in rows]


def export_people(
    connection: sqlite3.Connection,
    output_directory: Path,
    unit_slugs: dict[int, str],
    person_slugs: dict[int, str],
    institution_slugs: dict[int, str],
    conference_slugs: dict[int, str],
) -> None:
    """Export people with roles and keywords."""
    rows = fetch_all(
        connection,
        """
        SELECT id, old_id, title, first_name, last_name, email, url, unit_id, comment, active
        FROM person
        ORDER BY last_name, first_name, id
        """,
    )
    people = []
    for row in rows:
        people.append(
            remove_none_values(
                {
                    "id": person_slugs[row["id"]],
                    "title": row["title"],
                    "first_name": row["first_name"],
                    "last_name": row["last_name"],
                    "email": row["email"],
                    "url": row["url"],
                    "unit": unit_slugs.get(row["unit_id"]),
                    "active": bool(row["active"]),
                    "roles": roles_for_person(
                        connection,
                        row["id"],
                        institution_slugs,
                        conference_slugs,
                    ),
                    "keywords": keywords_for_person(connection, row["id"]),
                    "comment": row["comment"],
                    "legacy_id": row["old_id"],
                }
            )
        )
    write_yaml(output_directory / "people.yml", people)


def export_roles(connection: sqlite3.Connection, output_directory: Path) -> None:
    """Export available roles."""
    rows = fetch_all(connection, "SELECT name FROM role ORDER BY name")
    write_yaml(output_directory / "roles.yml", [row["name"] for row in rows])


def export_keywords(connection: sqlite3.Connection, output_directory: Path) -> None:
    """Export available keywords."""
    rows = fetch_all(connection, "SELECT name FROM keyword ORDER BY name")
    write_yaml(output_directory / "keywords.yml", [row["name"] for row in rows])


def chairs_for_conference(
    connection: sqlite3.Connection,
    conference_id: int,
    person_slugs: dict[int, str],
) -> list[dict[str, Any]]:
    """Return chairs attached to one conference."""
    rows = fetch_all(
        connection,
        """
        SELECT person_id, chair_order
        FROM conference_chair
        WHERE conference_id = ?
        ORDER BY chair_order
        """,
        (conference_id,),
    )
    return [
        {
            "person": person_slugs[row["person_id"]],
            "order": row["chair_order"],
        }
        for row in rows
    ]


def export_conferences(
    connection: sqlite3.Connection,
    output_directory: Path,
    institution_slugs: dict[int, str],
    person_slugs: dict[int, str],
    conference_slugs: dict[int, str],
) -> None:
    """Export conferences."""
    rows = fetch_all(
        connection,
        """
        SELECT id,
               old_id,
               year,
               name,
               url,
               venue_institution_id,
               period,
               is_finished,
               abstracts_available,
               comments
        FROM conference
        ORDER BY year, name
        """,
    )
    conferences = []
    for row in rows:
        conferences.append(
            remove_none_values(
                {
                    "id": conference_slugs[row["id"]],
                    "year": row["year"],
                    "name": row["name"],
                    "url": row["url"],
                    "venue": institution_slugs.get(row["venue_institution_id"]),
                    "period": row["period"],
                    "is_finished": bool(row["is_finished"]),
                    "abstracts_available": bool(row["abstracts_available"]),
                    "chairs": chairs_for_conference(connection, row["id"], person_slugs),
                    "comments": row["comments"],
                    "legacy_id": row["old_id"],
                }
            )
        )
    write_yaml(output_directory / "conferences.yml", conferences)


def export_database(database_path: Path, output_directory: Path) -> None:
    """Export the whole database to YAML files."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        country_slugs = build_country_slugs(connection)
        institution_slugs = build_institution_slugs(connection, country_slugs)
        unit_slugs = build_unit_slugs(connection, institution_slugs)
        person_slugs = build_person_slugs(connection)
        conference_slugs = build_conference_slugs(connection)

        export_countries(connection, output_directory, country_slugs)
        export_institutions(connection, output_directory, country_slugs, institution_slugs)
        export_units(connection, output_directory, institution_slugs, unit_slugs)
        export_roles(connection, output_directory)
        export_keywords(connection, output_directory)
        export_conferences(
            connection,
            output_directory,
            institution_slugs,
            person_slugs,
            conference_slugs,
        )
        export_people(
            connection,
            output_directory,
            unit_slugs,
            person_slugs,
            institution_slugs,
            conference_slugs,
        )
    finally:
        connection.close()


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Export the HEART SQLite database to YAML files."
    )
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path(DEFAULT_DATABASE),
        help=f"SQLite database to export. Default: {DEFAULT_DATABASE}.",
    )
    parser.add_argument(
        "output_directory",
        nargs="?",
        type=Path,
        default=Path(DEFAULT_OUTPUT_DIRECTORY),
        help=f"Directory where YAML files are written. Default: {DEFAULT_OUTPUT_DIRECTORY}.",
    )
    return parser.parse_args()


def main() -> None:
    """Command-line entry point."""
    args = parse_arguments()
    if not args.database.exists():
        raise FileNotFoundError(f"Database not found: {args.database}")

    export_database(args.database, args.output_directory)
    print(f"YAML files written to: {args.output_directory}")


if __name__ == "__main__":
    main()