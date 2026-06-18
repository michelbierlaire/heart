from __future__ import annotations

import argparse
import csv
import html
import shutil
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from update_database import main as update_database
import pandas as pd

from committe_members import extract_committee
from extract_conference import extract_conference, extract_conference_years
from list_of_members import extract_members


DOCS = Path("docs")
ASSETS = Path("assets")
ABSTRACTS = DOCS / "abstracts"


def esc(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return html.escape(str(value))


def link(label: Any, url: Any) -> str:
    if label is None or pd.isna(label) or not str(label).strip():
        return ""
    if url is not None and not pd.isna(url) and str(url).strip():
        return (
            f'<a href="{esc(url)}" '
            f'target="_blank" rel="noopener noreferrer">'
            f'{esc(label)}</a>'
        )
    return esc(label)


def url_is_alive(url: Any) -> bool:
    """Return True if the URL appears to be reachable."""
    if url is None or pd.isna(url) or not str(url).strip():
        return False

    request = Request(str(url), method="HEAD")
    try:
        with urlopen(request, timeout=5):
            return True
    except HTTPError as error:
        if error.code == 405:
            fallback_request = Request(str(url), method="GET")
            try:
                with urlopen(fallback_request, timeout=5):
                    return True
            except (HTTPError, URLError, TimeoutError):
                return False
        return False
    except (URLError, TimeoutError):
        return False


def conference_webpage_html(conf: dict[str, Any]) -> str:
    """Return the conference webpage paragraph if the link is alive."""
    url = conf.get("url")
    if url is None or pd.isna(url) or not str(url).strip():
        return ""
    if not url_is_alive(url):
        print(
            f"WARNING: Conference webpage for {conf.get('year')} is not reachable: {url}"
        )
        return ""
    return f'<p class="mb-1"><strong>Conference webpage:</strong> {link(url, url)}</p>'


def flag_img(code: Any) -> str:
    if code is None or pd.isna(code) or not str(code).strip():
        return ""
    code = str(code).upper()
    return (
        f'<img class="flag me-2" '
        f'src="assets/flags/svg/{esc(code)}.svg" '
        f'alt="{esc(code)}">'
    )


def clean_docs() -> None:
    """Regenerate docs, but preserve docs/abstracts."""
    DOCS.mkdir(exist_ok=True)

    for path in DOCS.iterdir():
        if path.name == "abstracts":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    if ASSETS.exists():
        shutil.copytree(ASSETS, DOCS / "assets")


def logo_html() -> str:
    logo = DOCS / "assets" / "hEART-LOGO.png"
    if logo.exists():
        return '<img src="assets/hEART-LOGO.png" alt="hEART logo" height="52">'
    return '<span class="fw-semibold fs-3">hEART</span>'


def page(title: str, body: str, active: str = "") -> str:
    def nav(label: str, href: str, key: str) -> str:
        css = "active fw-semibold" if active == key else ""
        return f'<a class="nav-link {css}" href="{href}">{label}</a>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {{ background: #f8f9fa; }}
    main {{ max-width: 1120px; }}
    .flag {{ width: 28px; height: 21px; object-fit: cover; border: 1px solid #ddd; }}
    .paper-title {{ max-width: 680px; }}
    .conference-past {{ background: #ffffff; }}
    .conference-future {{ background: #eaf4ff; }}
    .conference-ongoing {{ background: #fff3cd; border: 2px solid #ff9800; }}
    footer {{ color: #6c757d; }}
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg bg-white border-bottom">
  <div class="container">
    <a class="navbar-brand d-flex align-items-center" href="index.html">{logo_html()}</a>
    <div class="navbar-nav ms-auto">
      {nav("Home", "index.html", "home")}
      {nav("Members", "members.html", "members")}
      {nav("Committee", "committee.html", "committee")}
      {nav("Conferences", "conferences.html", "conferences")}
    </div>
  </div>
</nav>

<main class="container py-4">
{body}
</main>

<footer class="container py-4 small">
  Generated on {date.today().isoformat()} by Michel Bierlaire.
</footer>
</body>
</html>
"""




def read_papers(year: int) -> list[dict[str, str]]:
    csv_file = ABSTRACTS / f"papers_{year}.csv"
    if not csv_file.exists():
        return []

    with csv_file.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def parse_iso_date(value: Any) -> date | None:
    """Parse an ISO date value from the database."""
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return date.fromisoformat(str(value))


def conference_status(conference: dict[str, Any]) -> str:
    """Return 'past', 'ongoing', or 'future' for a conference."""
    today = date.today()
    start_date = parse_iso_date(conference.get("start_date"))
    end_date = parse_iso_date(conference.get("end_date"))

    if start_date is not None and end_date is not None:
        if today < start_date:
            return "future"
        if today <= end_date:
            return "ongoing"
        return "past"

    if bool(conference.get("is_finished")):
        return "past"
    return "future"


def conference_sort_date(conference: dict[str, Any]) -> date:
    """Return the date used to identify the next relevant conference."""
    start_date = parse_iso_date(conference.get("start_date"))
    if start_date is not None:
        return start_date
    return date(int(conference["year"]), 1, 1)


def render_index(conferences: list[dict[str, Any]]) -> None:
    relevant_conferences = [
        conference
        for conference in conferences
        if conference_status(conference) in {"ongoing", "future"}
    ]
    next_conference = (
        min(relevant_conferences, key=conference_sort_date)
        if relevant_conferences
        else None
    )

    next_conference_html = ""
    if next_conference:
        status = conference_status(next_conference)
        heading = (
            "Conference currently ongoing"
            if status == "ongoing"
            else "Next upcoming conference"
        )
        organizers = ", ".join(
            link(org.get("name"), org.get("url"))
            for org in next_conference.get("organizers", [])
        )
        conference_webpage = conference_webpage_html(next_conference)

        next_conference_html = f"""
<div class="card shadow-sm mt-4">
  <div class="card-body">
    <h2 class="h4">{heading}</h2>
    <h3 class="h5">{esc(next_conference.get("name"))}</h3>
    <p class="mb-1"><strong>{esc(next_conference.get("dates"))}</strong></p>
    <p class="mb-1">
      {flag_img(next_conference.get("country_code"))}
      {link(next_conference.get("venue"), next_conference.get("venue_url"))}
    </p>
    {conference_webpage}
    <p class="mb-3"><strong>Organizers:</strong> {organizers}</p>
    <a class="btn btn-outline-primary btn-sm" href="{esc(next_conference.get("year"))}.html">
      View conference
    </a>
  </div>
</div>
"""

    body = f"""
<section class="bg-white p-4 p-md-5 rounded shadow-sm">
  <h1 class="display-6">hEART</h1>
  <p class="lead mb-0">
    European Association for Research in Transportation.
  </p>
</section>
{next_conference_html}
"""
    (DOCS / "index.html").write_text(page("hEART", body, "home"), encoding="utf-8")


def render_members(members: pd.DataFrame) -> None:
    rows = []
    for _, m in members.iterrows():
        rows.append(
            f"""
<tr>
  <td>{flag_img(m.get("country_code"))}{esc(m.get("country"))}</td>
  <td>{link(m.get("university"), m.get("university_url"))}</td>
  <td>{link(m.get("department"), m.get("department_url"))}</td>
  <td>{link(m.get("representative"), m.get("representative_url"))}</td>
</tr>
"""
        )

    body = f"""
<h1>Members</h1>
<div class="table-responsive bg-white rounded shadow-sm">
<table class="table table-hover align-middle mb-0">
<thead class="table-light">
<tr>
  <th>Country</th>
  <th>University</th>
  <th>Department</th>
  <th>Representative</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</div>
"""
    (DOCS / "members.html").write_text(page("hEART members", body, "members"), encoding="utf-8")


def render_committee(committee: pd.DataFrame) -> None:
    rows = []
    for _, c in committee.iterrows():
        rows.append(
            f"""
<tr>
  <td>{link(c.get("name"), c.get("member_url"))}</td>
  <td>{esc(c.get("status"))}</td>
  <td>{link(c.get("department"), c.get("department_url"))}</td>
  <td>{link(c.get("university"), c.get("university_url"))}</td>
</tr>
"""
        )

    body = f"""
<h1>Committee</h1>
<div class="table-responsive bg-white rounded shadow-sm">
<table class="table table-hover align-middle mb-0">
<thead class="table-light">
<tr>
  <th>Name</th>
  <th>Status</th>
  <th>Department</th>
  <th>University</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</div>
"""
    (DOCS / "committee.html").write_text(page("hEART committee", body, "committee"), encoding="utf-8")


def render_conferences(conferences: list[dict[str, Any]]) -> None:
    cards = []
    for c in conferences:
        year = int(c.get("year"))
        status = conference_status(c)
        card_class = f"conference-{status}"
        abstract_status = (
            "Abstracts available"
            if read_papers(year)
            else "No abstracts available"
        )
        cards.append(
            f"""
<div class="col-md-6 col-lg-4">
  <div class="card h-100 shadow-sm {card_class}">
    <div class="card-body">
      <h2 class="h5">
        <a href="{esc(c.get("year"))}.html">
          {esc(c.get("year"))} — {esc(c.get("name"))}
        </a>
      </h2>
      <p class="mb-1">{esc(c.get("dates"))}</p>
      <p class="small text-muted mt-2 mb-0">{abstract_status}</p>
    </div>
  </div>
</div>
"""
        )

    body = f"""
<h1>Conferences</h1>
<div class="row g-3">
{''.join(cards)}
</div>
"""
    (DOCS / "conferences.html").write_text(
        page("hEART conferences", body, "conferences"),
        encoding="utf-8",
    )


def render_conference(conf: dict[str, Any]) -> None:
    year = int(conf["year"])
    papers = read_papers(year)

    organizers = ", ".join(
        link(org.get("name"), org.get("url"))
        for org in conf.get("organizers", [])
    )
    conference_webpage = conference_webpage_html(conf)

    paper_rows = []
    for p in papers:
        pdf_file = p.get("pdf_file", "")
        pdf_path = f"abstracts/{year}/{pdf_file}"

        paper_rows.append(
            f"""
<tr>
  <td>{esc(p.get("authors"))}</td>
  <td class="paper-title">{esc(p.get("title"))}</td>
  <td><a href="{esc(pdf_path)}">PDF</a></td>
</tr>
"""
        )

    papers_html = (
        f"""
<h2 class="h4 mt-4">Abstracts</h2>
<div class="table-responsive bg-white rounded shadow-sm">
<table class="table table-hover align-middle mb-0">
<thead class="table-light">
<tr>
  <th>Authors</th>
  <th>Title</th>
  <th>File</th>
</tr>
</thead>
<tbody>
{''.join(paper_rows)}
</tbody>
</table>
</div>
"""
        if papers
        else '<p class="text-muted mt-4">No abstract list available for this year.</p>'
    )

    body = f"""
<section class="bg-white p-4 rounded shadow-sm">
  <h1>{esc(conf.get("name"))}</h1>
  <p class="lead mb-1">{esc(conf.get("dates"))}</p>
  <p class="mb-1">
    <strong>Venue:</strong>
    {flag_img(conf.get("country_code"))}
    {link(conf.get("venue"), conf.get("venue_url"))}
  </p>
  {conference_webpage}
  <p class="mb-0"><strong>Organizers:</strong> {organizers}</p>
</section>
{papers_html}
"""
    (DOCS / f"{year}.html").write_text(
        page(f"hEART {year}", body, "conferences"),
        encoding="utf-8",
    )


def build_site(database: Path) -> None:
    update_database()
    clean_docs()

    members = extract_members(database)
    committee = extract_committee(database)

    conferences = []
    for year in extract_conference_years(database):
        conference = extract_conference(year, database)
        if conference is not None:
            conferences.append(conference)

    conferences.sort(key=lambda c: c["year"], reverse=True)

    render_index(conferences)
    render_members(members)
    render_committee(committee)
    render_conferences(conferences)

    for conference in conferences:
        render_conference(conference)

    print(f"Generated site in {DOCS.resolve()}")
    print("Preserved docs/abstracts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database", nargs="?", default="heart.db")
    args = parser.parse_args()

    build_site(Path(args.database))