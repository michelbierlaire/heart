from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from update_database import create_database
import pandas as pd
import yaml

from committe_members import extract_committee
from extract_conference import extract_conference, extract_conference_years
from list_of_members import extract_members
from paper_metadata import (
    load_paper_metadata,
    paper_key,
    paper_page_filename,
    parse_author_names,
)


DOCS = Path("docs")
ASSETS = Path("assets")
ABSTRACTS = DOCS / "abstracts"
DATA = Path("data")
CONTENT = DATA / "content.yml"
PAPER_METADATA = DATA / "paper_metadata.json"
SITE_URL = "https://heart-web.org"


def read_content() -> dict[str, Any]:
    """Read editorial content from data/content.yml."""
    if not CONTENT.exists():
        return {}
    with CONTENT.open(encoding="utf-8") as file:
        content = yaml.safe_load(file)
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise ValueError(f"{CONTENT} must contain a YAML mapping.")
    return content


def home_intro_html(content: dict[str, Any]) -> str:
    """Return the introductory HTML for the home page."""
    home = content.get("home", {})
    if not isinstance(home, dict):
        return ""

    title = home.get("title")
    paragraphs = home.get("paragraphs", [])
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]

    if not title and not paragraphs:
        return ""

    title_html = f'<h2 class="h4 mt-4">{esc(title)}</h2>' if title else ""
    paragraphs_html = "\n".join(
        f'<p class="mb-2">{esc(paragraph)}</p>'
        for paragraph in paragraphs
        if paragraph is not None and str(paragraph).strip()
    )
    return f"""
<section class="institutional-card p-4 mt-4">
  {title_html}
  {paragraphs_html}
</section>
"""


def esc(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return html.escape(str(value))


def url_path(path: str) -> str:
    return "/".join(quote(part) for part in path.split("/"))


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

    for landing_page in ABSTRACTS.glob("**/*.html"):
        landing_page.unlink()

    for path in DOCS.iterdir():
        if path.name == "abstracts":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    if ASSETS.exists():
        shutil.copytree(ASSETS, DOCS / "assets")
    cname = Path("CNAME")
    if cname.exists():
        (DOCS / "CNAME").write_text(
            cname.read_text(encoding="utf-8").rstrip("\r\n"), encoding="utf-8"
        )


def logo_html(relative_root: str = "") -> str:
    logo = DOCS / "assets" / "hEART-LOGO.png"
    if logo.exists():
        return f'<img src="{relative_root}assets/hEART-LOGO.png" alt="hEART logo" height="52">'
    return '<span class="fw-semibold fs-3">hEART</span>'


def page(
    title: str,
    body: str,
    active: str = "",
    canonical_url: str | None = None,
    relative_root: str = "",
    head_extra: str = "",
) -> str:
    def nav(label: str, href: str, key: str) -> str:
        css = "active fw-semibold" if active == key else ""
        return f'<a class="nav-link {css}" href="{relative_root}{href}">{label}</a>'

    canonical = (
        f'  <link rel="canonical" href="{esc(canonical_url)}">\n'
        if canonical_url
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
{canonical}{head_extra}
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="{relative_root}assets/css/heart.css">
</head>
<body>
<header class="site-header">
  <div class="container py-3">
    <div class="d-flex flex-column flex-lg-row align-items-lg-center justify-content-between gap-3">
      <a class="navbar-brand d-flex align-items-center text-decoration-none" href="{relative_root}index.html">
        {logo_html(relative_root)}
        <div class="ms-3">
          <div class="brand-title">hEART</div>
          <div class="brand-subtitle">European Association for Research in Transportation</div>
        </div>
      </a>
      <nav class="navbar navbar-expand p-0">
        <div class="navbar-nav ms-lg-auto">
          {nav("Home", "index.html", "home")}
          {nav("Members", "members.html", "members")}
          {nav("Committee", "committee.html", "committee")}
          {nav("Conferences", "conferences.html", "conferences")}
        </div>
      </nav>
    </div>
  </div>
</header>

<main class="container py-4">
{body}
</main>

<footer class="container py-4 small">
  <div class="d-flex flex-column flex-md-row justify-content-between gap-2">
    <span><strong>hEART</strong> — European Association for Research in Transportation</span>
    <span>Generated on {date.today().isoformat()} by Michel Bierlaire.</span>
  </div>
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
    intro_html = home_intro_html(read_content())
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
<div class="institutional-card mt-4">
  <div class="card-body p-4">
    <h2 class="h4 section-title">{heading}</h2>
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
<section class="hero p-4 p-md-5">
  <h1 class="display-5 mb-2">hEART</h1>
  <p class="lead mb-1">European Association for Research in Transportation</p>
  <p class="mb-0">Promoting excellence in transportation research in Europe.</p>
</section>
{intro_html}
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
<h1 class="section-title">Members</h1>
<div class="table-responsive institutional-card">
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
<h1 class="section-title">Committee</h1>
<div class="table-responsive institutional-card">
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
        has_abstracts = bool(read_papers(year))
        abstract_status = "Abstracts available" if has_abstracts else "No abstracts available"
        abstract_badge_class = "badge-abstracts" if has_abstracts else "badge-no-abstracts"
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
      <span class="badge rounded-pill {abstract_badge_class} mt-2">{abstract_status}</span>
    </div>
  </div>
</div>
"""
        )

    body = f"""
<h1 class="section-title">Conferences</h1>
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
    metadata = load_paper_metadata(PAPER_METADATA)
    for p in papers:
        pdf_file = p.get("pdf_file", "")
        pdf_path = url_path(f"abstracts/{year}/{pdf_file}")
        landing_path = f"abstracts/{year}/{paper_page_filename(pdf_file, p.get('title', ''))}"
        pdf_exists = (ABSTRACTS / str(year) / pdf_file).exists()
        paper_title = esc(p.get("title"))
        authors = metadata.get(paper_key(year, pdf_file), {}).get("authors", [])
        author_text = ", ".join(authors) or str(p.get("authors") or "")
        title_cell = f'<a href="{esc(landing_path)}">{paper_title}</a>'
        pdf_cell = (
            f'<a href="{esc(pdf_path)}">PDF</a>'
            if pdf_exists
            else '<span class="text-muted">PDF unavailable</span>'
        )

        paper_rows.append(
            f"""
<tr>
  <td>{esc(author_text)}</td>
  <td class="paper-title">{title_cell}</td>
  <td>{pdf_cell}</td>
</tr>
"""
        )

    papers_html = (
        f"""
<h2 class="h4 section-title mt-4">Abstracts</h2>
<div class="table-responsive institutional-card">
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
<section class="institutional-card p-4">
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
        page(
            f"hEART {year}",
            body,
            "conferences",
            canonical_url=f"{SITE_URL}/{year}.html",
        ),
        encoding="utf-8",
    )


def render_paper(
    conf: dict[str, Any], paper: dict[str, str], metadata: dict[str, Any]
) -> str:
    year = int(conf["year"])
    pdf_file = paper.get("pdf_file", "")
    pdf_path = quote(pdf_file)
    landing_filename = paper_page_filename(pdf_file, paper.get("title", ""))
    landing_path = f"abstracts/{year}/{landing_filename}"
    canonical_url = f"{SITE_URL}/{landing_path}"
    authors = metadata.get("authors") or parse_author_names(paper.get("authors", ""), year)
    abstract = str(metadata.get("abstract") or "").strip()
    pdf_exists = bool(pdf_file) and (ABSTRACTS / str(year) / pdf_file).exists()
    pdf_url = f"{SITE_URL}/abstracts/{year}/{url_path(pdf_file)}" if pdf_exists else ""
    title = paper.get("title", "")
    conference_name = str(conf.get("name") or "")
    publication_year = str(year)
    citation = f"{'; '.join(authors)} ({publication_year}). {title}. In: {conference_name}."
    citation_authors = "\n".join(
        f'  <meta name="citation_author" content="{esc(author)}">' for author in authors
    )
    scholarly_data = {
        "@context": "https://schema.org",
        "@type": "ScholarlyArticle",
        "name": title,
        "headline": title,
        "author": [{"@type": "Person", "name": author} for author in authors],
        "abstract": abstract,
        "datePublished": publication_year,
        "url": canonical_url,
        "mainEntityOfPage": canonical_url,
        "isPartOf": {
            "@type": "Event",
            "name": conference_name,
            "startDate": str(conf.get("start_date") or publication_year),
        },
    }
    if pdf_url:
        scholarly_data["encoding"] = {
            "@type": "MediaObject",
            "contentUrl": pdf_url,
            "encodingFormat": "application/pdf",
        }
    citation_pdf_tag = (
        f'\n  <meta name="citation_pdf_url" content="{esc(pdf_url)}">'
        if pdf_url
        else ""
    )
    head_extra = f"""  <meta name="citation_title" content="{esc(title)}">
{citation_authors}
  <meta name="citation_publication_date" content="{publication_year}">
  <meta name="citation_conference_title" content="{esc(conference_name)}">
{citation_pdf_tag}
  <script type="application/ld+json">{json.dumps(scholarly_data, ensure_ascii=False)}</script>"""
    abstract_html = (
        "\n".join(f"<p>{esc(paragraph)}</p>" for paragraph in abstract.split("\n\n"))
        if abstract
        else '<p class="text-muted">The archived PDF does not contain an explicitly labelled abstract or short summary.</p>'
    )
    pdf_action = (
        f'<a class="btn btn-primary" href="{esc(pdf_path)}">Download the PDF</a>'
        if pdf_exists
        else '<span class="text-muted">The source PDF is not present in the current archive.</span>'
    )
    body = f"""
<article class="institutional-card p-4 p-md-5">
  <p class="text-muted mb-2"><a href="../../{year}.html">hEART {year} conference papers</a></p>
  <h1>{esc(title)}</h1>
  <p class="lead">{esc(", ".join(authors))}</p>
  <dl class="row mb-4">
    <dt class="col-sm-3">Conference</dt>
    <dd class="col-sm-9">{esc(conference_name)} ({publication_year})</dd>
    <dt class="col-sm-3">Publication year</dt>
    <dd class="col-sm-9">{publication_year}</dd>
  </dl>
  <section aria-labelledby="abstract-heading">
    <h2 id="abstract-heading" class="h4 section-title">Abstract</h2>
    {abstract_html}
  </section>
  <div class="mt-4">{pdf_action}</div>
  <section class="mt-5" aria-labelledby="citation-heading">
    <h2 id="citation-heading" class="h4 section-title">How to cite</h2>
    <p>{esc(citation)}</p>
  </section>
</article>
"""
    output = DOCS / "abstracts" / str(year) / landing_filename
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        page(
            title,
            body,
            "conferences",
            canonical_url=canonical_url,
            relative_root="../../",
            head_extra=head_extra,
        ),
        encoding="utf-8",
    )
    return canonical_url


def render_discovery_files(conferences: list[dict[str, Any]]) -> None:
    urls = [f"{SITE_URL}/", f"{SITE_URL}/conferences.html"]
    urls.extend(f"{SITE_URL}/{int(conf['year'])}.html" for conf in conferences)
    for conf in conferences:
        year = int(conf["year"])
        for paper in read_papers(year):
            pdf_file = paper.get("pdf_file", "")
            urls.append(
                f"{SITE_URL}/abstracts/{year}/{paper_page_filename(pdf_file, paper.get('title', ''))}"
            )
            # Keep the HTML abstract page as the sitemap's article URL. The
            # corresponding PDF is linked through citation_pdf_url, which lets
            # Google Scholar associate the full text with the bibliographic
            # metadata instead of processing the PDF as a separate article.
    urlset = "\n".join(
        f"  <url><loc>{html.escape(url, quote=True)}</loc></url>"
        for url in sorted(set(urls))
    )
    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urlset}\n</urlset>\n",
        encoding="utf-8",
    )
    (DOCS / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: https://heart-web.org/sitemap.xml\n",
        encoding="utf-8",
    )


def build_site(database: Path) -> None:
    create_database(database, DATA)
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

    metadata = load_paper_metadata(PAPER_METADATA)
    for conference in conferences:
        render_conference(conference)
        year = int(conference["year"])
        for paper in read_papers(year):
            render_paper(
                conference,
                paper,
                metadata.get(paper_key(year, paper.get("pdf_file", "")), {}),
            )

    render_discovery_files(conferences)

    print(f"Generated site in {DOCS.resolve()}")
    print("Preserved docs/abstracts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database", nargs="?", default="heart.db")
    args = parser.parse_args()

    build_site(Path(args.database))
