from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def extract_committee(database: Path | str = "heart.db") -> pd.DataFrame:
    database = Path(database)

    query = """
    SELECT
        p.first_name || ' ' || p.last_name AS name,
        p.url AS member_url,
        u.name AS department,
        u.url AS department_url,
        i.name AS university,
        i.url AS university_url,
        MAX(CASE WHEN r.name = 'committee_chair' THEN 1 ELSE 0 END) AS is_chair,
        MAX(CASE WHEN r.name = 'committee_member' THEN 1 ELSE 0 END) AS is_member,
        MAX(CASE WHEN r.name = 'past_committee_member' THEN 1 ELSE 0 END) AS is_past_member
    FROM person AS p
    JOIN person_role AS pr ON pr.person_id = p.id
    JOIN role AS r ON r.id = pr.role_id
    LEFT JOIN unit AS u ON u.id = p.unit_id
    LEFT JOIN institution AS i ON i.id = u.institution_id
    WHERE r.name IN (
        'committee_chair',
        'committee_member',
        'past_committee_member'
    )
    GROUP BY
        p.id,
        p.first_name,
        p.last_name,
        p.url,
        u.name,
        u.url,
        i.name,
        i.url
    ORDER BY
        is_chair DESC,
        is_member DESC,
        is_past_member ASC,
        p.last_name,
        p.first_name
    """

    with sqlite3.connect(database) as connection:
        dataframe = pd.read_sql_query(query, connection)

    inconsistent = dataframe[
        (dataframe["is_member"] == 1)
        & (dataframe["is_past_member"] == 1)
    ]
    if not inconsistent.empty:
        names = ", ".join(inconsistent["name"])
        print(
            "WARNING: The following people are both committee members and past committee members: "
            f"{names}"
        )

    def status(row: pd.Series) -> str:
        labels = []
        if row["is_chair"]:
            labels.append("chair")
        if row["is_member"]:
            labels.append("member")
        if not labels and row["is_past_member"]:
            labels.append("past member")
        return ", ".join(labels)

    dataframe["status"] = dataframe.apply(status, axis=1)

    return dataframe[
        [
            "name",
            "status",
            "member_url",
            "department",
            "department_url",
            "university",
            "university_url",
        ]
    ]


if __name__ == "__main__":
    committee = extract_committee("heart.db")
    print(committee.to_string(index=False))