"""Create the HEART SQLite database from YAML files.

Inverse of export_to_yaml.py.

Typical use:

    uv run update_database.py data heart.db
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import yaml


DEFAULT_INPUT_DIRECTORY = "data"
DEFAULT_DATABASE = "heart.db"


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_yaml_list(path: Path) -> list[Any]:
    data = load_yaml(path)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a YAML list.")
    return data


def sqlite_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    return value


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS conference_chair;
        DROP TABLE IF EXISTS person_keyword;
        DROP TABLE IF EXISTS person_role;
        DROP TABLE IF EXISTS conference;
        DROP TABLE IF EXISTS person;
        DROP TABLE IF EXISTS unit;
        DROP TABLE IF EXISTS institution;
        DROP TABLE IF EXISTS country;
        DROP TABLE IF EXISTS keyword;
        DROP TABLE IF EXISTS role;

        CREATE TABLE country (
            id INTEGER PRIMARY KEY,
            old_id TEXT,
            iso2 TEXT NOT NULL
        );

        CREATE TABLE institution (
            id INTEGER PRIMARY KEY,
            old_id INTEGER,
            name TEXT NOT NULL,
            acronym TEXT,
            url TEXT,
            country_id INTEGER NOT NULL,
            is_heart_member INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(country_id) REFERENCES country(id)
        );

        CREATE TABLE unit (
            id INTEGER PRIMARY KEY,
            old_id INTEGER,
            name TEXT NOT NULL,
            acronym TEXT,
            url TEXT,
            institution_id INTEGER NOT NULL,
            FOREIGN KEY(institution_id) REFERENCES institution(id)
        );

        CREATE TABLE person (
            id INTEGER PRIMARY KEY,
            old_id INTEGER,
            title TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT,
            url TEXT,
            unit_id INTEGER,
            comment TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(unit_id) REFERENCES unit(id)
        );

        CREATE TABLE role (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE keyword (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE person_role (
            id INTEGER PRIMARY KEY,
            person_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            institution_id INTEGER,
            conference_id INTEGER,
            start_year INTEGER,
            end_year INTEGER,
            role_order INTEGER,
            legacy_id INTEGER,
            comment TEXT,
            FOREIGN KEY(person_id) REFERENCES person(id),
            FOREIGN KEY(role_id) REFERENCES role(id),
            FOREIGN KEY(institution_id) REFERENCES institution(id),
            FOREIGN KEY(conference_id) REFERENCES conference(id)
        );

        CREATE TABLE person_keyword (
            person_id INTEGER NOT NULL,
            keyword_id INTEGER NOT NULL,
            PRIMARY KEY(person_id, keyword_id),
            FOREIGN KEY(person_id) REFERENCES person(id),
            FOREIGN KEY(keyword_id) REFERENCES keyword(id)
        );

        CREATE TABLE conference (
            id INTEGER PRIMARY KEY,
            old_id INTEGER,
            year INTEGER NOT NULL,
            name TEXT NOT NULL,
            url TEXT,
            venue_institution_id INTEGER,
            period TEXT,
            start_date TEXT,
            end_date TEXT,
            is_finished INTEGER NOT NULL DEFAULT 0,
            abstracts_available INTEGER NOT NULL DEFAULT 0,
            comments TEXT,
            FOREIGN KEY(venue_institution_id) REFERENCES institution(id)
        );

        CREATE TABLE conference_chair (
            conference_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            chair_order INTEGER NOT NULL,
            PRIMARY KEY(conference_id, person_id),
            FOREIGN KEY(conference_id) REFERENCES conference(id),
            FOREIGN KEY(person_id) REFERENCES person(id)
        );
        """
    )


def enumerate_ids(items: list[dict[str, Any]]) -> dict[str, int]:
    return {item["id"]: index for index, item in enumerate(items, start=1)}


def insert_countries(connection: sqlite3.Connection, data_dir: Path) -> dict[str, int]:
    countries = load_yaml_list(data_dir / "countries.yml")
    ids = enumerate_ids(countries)

    for country in countries:
        connection.execute(
            """
            INSERT INTO country(id, old_id, iso2)
            VALUES (?, ?, ?)
            """,
            (
                ids[country["id"]],
                country.get("legacy_id"),
                country["iso2"],
            ),
        )

    return ids


def insert_institutions(
    connection: sqlite3.Connection,
    data_dir: Path,
    country_ids: dict[str, int],
) -> dict[str, int]:
    institutions = load_yaml_list(data_dir / "institutions.yml")
    ids = enumerate_ids(institutions)

    for institution in institutions:
        connection.execute(
            """
            INSERT INTO institution(
                id,
                old_id,
                name,
                acronym,
                url,
                country_id,
                is_heart_member
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids[institution["id"]],
                institution.get("legacy_id"),
                institution["name"],
                institution.get("acronym"),
                institution.get("url"),
                country_ids[institution["country"]],
                int(bool(institution.get("is_heart_member", False))),
            ),
        )

    return ids


def insert_units(
    connection: sqlite3.Connection,
    data_dir: Path,
    institution_ids: dict[str, int],
) -> dict[str, int]:
    units = load_yaml_list(data_dir / "units.yml")
    ids = enumerate_ids(units)

    for unit in units:
        connection.execute(
            """
            INSERT INTO unit(id, old_id, name, acronym, url, institution_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ids[unit["id"]],
                unit.get("legacy_id"),
                unit["name"],
                unit.get("acronym"),
                unit.get("url"),
                institution_ids[unit["institution"]],
            ),
        )

    return ids


def insert_roles(connection: sqlite3.Connection, data_dir: Path) -> dict[str, int]:
    roles = load_yaml_list(data_dir / "roles.yml")
    ids = {role: index for index, role in enumerate(roles, start=1)}

    for role in roles:
        connection.execute(
            """
            INSERT INTO role(id, name)
            VALUES (?, ?)
            """,
            (ids[role], role),
        )

    return ids


def insert_keywords(connection: sqlite3.Connection, data_dir: Path) -> dict[str, int]:
    keywords = load_yaml_list(data_dir / "keywords.yml")
    ids = {keyword: index for index, keyword in enumerate(keywords, start=1)}

    for keyword in keywords:
        connection.execute(
            """
            INSERT INTO keyword(id, name)
            VALUES (?, ?)
            """,
            (ids[keyword], keyword),
        )

    return ids


def insert_conferences(
    connection: sqlite3.Connection,
    data_dir: Path,
    institution_ids: dict[str, int],
) -> dict[str, int]:
    conferences = load_yaml_list(data_dir / "conferences.yml")
    ids = enumerate_ids(conferences)

    for conference in conferences:
        connection.execute(
            """
            INSERT INTO conference(
                id,
                old_id,
                year,
                name,
                url,
                venue_institution_id,
                period,
                start_date,
                end_date,
                is_finished,
                abstracts_available,
                comments
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids[conference["id"]],
                conference.get("legacy_id"),
                conference["year"],
                conference["name"],
                conference.get("url"),
                institution_ids.get(conference.get("venue")),
                conference.get("period"),
                sqlite_value(conference.get("start_date")),
                sqlite_value(conference.get("end_date")),
                int(bool(conference.get("is_finished", False))),
                int(bool(conference.get("abstracts_available", False))),
                conference.get("comments"),
            ),
        )

    return ids


def insert_people(
    connection: sqlite3.Connection,
    data_dir: Path,
    unit_ids: dict[str, int],
    role_ids: dict[str, int],
    keyword_ids: dict[str, int],
    institution_ids: dict[str, int],
    conference_ids: dict[str, int],
) -> dict[str, int]:
    people = load_yaml_list(data_dir / "people.yml")
    person_ids = enumerate_ids(people)

    for person in people:
        connection.execute(
            """
            INSERT INTO person(
                id,
                old_id,
                title,
                first_name,
                last_name,
                email,
                url,
                unit_id,
                comment,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_ids[person["id"]],
                person.get("legacy_id"),
                person.get("title"),
                person["first_name"],
                person["last_name"],
                person.get("email"),
                person.get("url"),
                unit_ids.get(person.get("unit")),
                person.get("comment"),
                int(bool(person.get("active", True))),
            ),
        )

    person_role_id = 1
    for person in people:
        person_id = person_ids[person["id"]]

        for role in person.get("roles", []):
            role_name = role["role"]
            connection.execute(
                """
                INSERT INTO person_role(
                    id,
                    person_id,
                    role_id,
                    institution_id,
                    conference_id,
                    start_year,
                    end_year,
                    role_order,
                    legacy_id,
                    comment
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    person_role_id,
                    person_id,
                    role_ids[role_name],
                    institution_ids.get(role.get("institution")),
                    conference_ids.get(role.get("conference")),
                    role.get("start_year"),
                    role.get("end_year"),
                    role.get("order"),
                    role.get("legacy_id"),
                    role.get("comment"),
                ),
            )
            person_role_id += 1

        for keyword in person.get("keywords", []):
            connection.execute(
                """
                INSERT INTO person_keyword(person_id, keyword_id)
                VALUES (?, ?)
                """,
                (person_id, keyword_ids[keyword]),
            )

    return person_ids


def insert_conference_chairs(
    connection: sqlite3.Connection,
    data_dir: Path,
    conference_ids: dict[str, int],
    person_ids: dict[str, int],
) -> None:
    conferences = load_yaml_list(data_dir / "conferences.yml")

    for conference in conferences:
        conference_id = conference_ids[conference["id"]]

        for chair in conference.get("chairs", []):
            person_slug = chair["person"]
            connection.execute(
                """
                INSERT INTO conference_chair(conference_id, person_id, chair_order)
                VALUES (?, ?, ?)
                """,
                (
                    conference_id,
                    person_ids[person_slug],
                    chair.get("order", 1),
                ),
            )


def create_database(database_path: Path, data_dir: Path) -> None:
    if database_path.exists():
        database_path.unlink()

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        create_schema(connection)

        country_ids = insert_countries(connection, data_dir)
        institution_ids = insert_institutions(connection, data_dir, country_ids)
        unit_ids = insert_units(connection, data_dir, institution_ids)
        role_ids = insert_roles(connection, data_dir)
        keyword_ids = insert_keywords(connection, data_dir)
        conference_ids = insert_conferences(connection, data_dir, institution_ids)
        person_ids = insert_people(
            connection,
            data_dir,
            unit_ids,
            role_ids,
            keyword_ids,
            institution_ids,
            conference_ids,
        )
        insert_conference_chairs(connection, data_dir, conference_ids, person_ids)

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the HEART SQLite database from YAML files."
    )
    parser.add_argument(
        "input_directory",
        nargs="?",
        type=Path,
        default=Path(DEFAULT_INPUT_DIRECTORY),
        help=f"Directory containing YAML files. Default: {DEFAULT_INPUT_DIRECTORY}.",
    )
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path(DEFAULT_DATABASE),
        help=f"SQLite database to create. Default: {DEFAULT_DATABASE}.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    required_files = [
        "conferences.yml",
        "countries.yml",
        "institutions.yml",
        "keywords.yml",
        "people.yml",
        "roles.yml",
        "units.yml",
    ]

    for filename in required_files:
        path = args.input_directory / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required YAML file: {path}")

    create_database(args.database, args.input_directory)
    print(f"Created {args.database} from YAML files in {args.input_directory}")


if __name__ == "__main__":
    main()