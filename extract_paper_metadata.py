from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from paper_metadata import extract_abstract, paper_key, parse_author_names


def build_metadata(root: Path, year: int | None = None) -> dict[str, dict[str, object]]:
    abstracts = root / "docs" / "abstracts"
    result: dict[str, dict[str, object]] = {}
    for csv_path in sorted(abstracts.glob("papers_*.csv")):
        csv_year = int(csv_path.stem.split("_")[1])
        if year is not None and csv_year != year:
            continue
        with csv_path.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                pdf_file = row.get("pdf_file", "")
                pdf_path = abstracts / str(csv_year) / pdf_file
                extracted_abstract = (
                    extract_abstract(pdf_path) if pdf_path.exists() else ""
                )
                abstract = (
                    extracted_abstract
                    or (row.get("abstract") or "").strip()
                    or (row.get("table_abstract") or "").strip()
                )
                result[paper_key(csv_year, pdf_file)] = {
                    "authors": parse_author_names(row.get("authors", ""), csv_year),
                    "abstract": abstract,
                    "pdf_exists": pdf_path.exists(),
                }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("data/paper_metadata.json"))
    parser.add_argument(
        "--year",
        type=int,
        help="Process only this year's papers CSV.",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge generated records into the existing output JSON.",
    )
    args = parser.parse_args()

    metadata = build_metadata(args.root, args.year)
    if args.merge and args.output.exists():
        with args.output.open(encoding="utf-8") as file:
            existing = json.load(file)
        if not isinstance(existing, dict):
            raise ValueError(f"{args.output} must contain a JSON object.")
        existing.update(metadata)
        metadata = existing

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = len(metadata)
    with_abstract = sum(bool(item["abstract"]) for item in metadata.values())
    print(f"Wrote {total} paper records; extracted {with_abstract} abstracts to {args.output}")


if __name__ == "__main__":
    main()
