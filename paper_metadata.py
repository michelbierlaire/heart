from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


ABSTRACT_HEADING = re.compile(
    r"^\s*(?:\d+\s+)?(?:abstract|short\s+summary|summary|résumé|resume)\s*:?(?:\s+(.*))?$",
    re.IGNORECASE,
)
ABSTRACT_STOP = re.compile(
    r"^\s*(?:keywords?|key\s+words?|\d+\s*[.]?\s+introduction|"
    r"[IVX]+\s*[.]\s+introduction|introduction|background|1\s*[.]?\s+background)\b",
    re.IGNORECASE,
)


def paper_key(year: int, pdf_file: str) -> str:
    return f"{year}/{pdf_file}"


def paper_page_filename(pdf_file: str, title: str = "") -> str:
    stem = Path(pdf_file).stem or title
    slug = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    return f"{slug or 'paper'}.html"


def _clean_author(value: str) -> str:
    value = re.sub(r"\[[^\]]*\]", "", value)
    value = re.sub(r"[\u2020\u2021*]+", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ,;:")
    value = re.sub(r"\s+\d+$", "", value).strip()
    return value


def parse_author_names(raw: str, year: int | None = None) -> list[str]:
    """Turn the archive's mixed author formats into names only."""
    if not raw:
        return []

    without_affiliations = re.sub(r"\([^)]*\)", "", raw)
    without_affiliations = re.sub(r"\s+", " ", without_affiliations).strip()

    if year == 2022:
        tokens = [token.strip() for token in without_affiliations.split(",") if token.strip()]
        parts = [f"{tokens[i + 1]} {tokens[i]}" for i in range(0, len(tokens) - 1, 2)]
    elif ";" in without_affiliations:
        parts = without_affiliations.split(";")
        parts = [re.sub(r",\s*", " ", part) for part in parts]
    else:
        parts = re.split(r"\s+and\s+|\s*&\s*|,\s*", without_affiliations)

    names: list[str] = []
    for part in parts:
        name = _clean_author(part)
        if not name or name.lower().startswith("author "):
            continue
        if name not in names:
            names.append(name)
    return names


def _join_text_lines(lines: list[str]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or re.fullmatch(r"\d+", line):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if current and current[-1].endswith("-") and line[:1].isalnum():
            current[-1] = current[-1][:-1] + line
        else:
            current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs).strip()


def extract_abstract(pdf_path: Path) -> str:
    """Extract an explicitly labelled abstract or short summary, if present."""
    try:
        result = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "5", "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0 or not result.stdout.strip():
        return ""

    lines = result.stdout.replace("\f", "\n").splitlines()
    start: int | None = None
    initial: list[str] = []
    for index, line in enumerate(lines):
        match = ABSTRACT_HEADING.match(line)
        if match:
            start = index + 1
            remainder = (match.group(1) or "").strip()
            if remainder:
                initial.append(remainder)
            break
    if start is None:
        return ""

    abstract_lines = initial[:]
    for line in lines[start:]:
        if ABSTRACT_STOP.match(line):
            break
        abstract_lines.append(line)

    abstract = _join_text_lines(abstract_lines)
    return abstract if len(abstract) >= 40 else ""


def load_paper_metadata(path: Path = Path("data/paper_metadata.json")) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data
