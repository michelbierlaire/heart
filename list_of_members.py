from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pycountry


SPECIAL_CODES = {
    "EU": "European Union",
    "INTL": "International partners",
}


def country_name(iso2: str) -> str:
    if iso2 in SPECIAL_CODES:
        return SPECIAL_CODES[iso2]

    country = pycountry.countries.get(alpha_2=iso2)
    return country.name if country is not None else iso2


def extract_members(database: Path | str = "heart.db") -> pd.DataFrame:
    database = Path(database)

    query = """
    SELECT
        c.iso2 AS country_code,
        i.name AS university,
        i.url AS university_url,
        u.name AS department,
        u.url AS department_url,
        p.first_name || ' ' || p.last_name AS representative,
        p.url AS representative_url,
        p.email AS representative_email
    FROM person_role AS pr
    JOIN role AS r ON r.id = pr.role_id
    JOIN person AS p ON p.id = pr.person_id
    JOIN institution AS i ON i.id = pr.institution_id
    LEFT JOIN unit AS u ON u.institution_id = i.id
    JOIN country AS c ON c.id = i.country_id
    WHERE r.name = 'institution_representative'
    ORDER BY c.iso2, i.name, representative
    """

    with sqlite3.connect(database) as connection:
        dataframe = pd.read_sql_query(query, connection)

    dataframe.insert(
        0,
        "country",
        dataframe["country_code"].map(country_name),
    )

    return dataframe


if __name__ == "__main__":
    members = extract_members("heart.db")
    print(members.to_string(index=False))