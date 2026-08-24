from __future__ import annotations

import argparse
import csv
import io
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from paper_metadata import parse_author_names


MAX_BYTES = 5 * 1024 * 1024


def conference_info(database: Path) -> dict[int, tuple[str, str]]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT year, name, period FROM conference").fetchall()
    return {int(year): (str(name), str(period or "")) for year, name, period in rows}


def paper_rows(root: Path):
    abstracts = root / "docs" / "abstracts"
    for csv_path in sorted(abstracts.glob("papers_*.csv")):
        year = int(csv_path.stem.split("_")[1])
        with csv_path.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                pdf_file = row.get("pdf_file", "")
                pdf_path = abstracts / str(year) / pdf_file
                if pdf_file and pdf_path.exists():
                    yield year, row, pdf_path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def normalize_with_ghostscript(input_path: Path, output_path: Path) -> None:
    setting = "/ebook" if input_path.stat().st_size >= MAX_BYTES else "/prepress"
    result = run(
        [
            shutil.which("gs") or "gs",
            "-q",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7",
            f"-dPDFSETTINGS={setting}",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-dEmbedAllFonts=true",
            "-dSubsetFonts=true",
            "-dNOPAUSE",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            str(input_path),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1000:])


def has_searchable_text(path: Path) -> bool:
    result = run([shutil.which("pdftotext") or "pdftotext", "-f", "1", "-l", "1", str(path), "-"])
    return result.returncode == 0 and bool(result.stdout.strip())


def has_type3_font(path: Path) -> bool:
    result = run([shutil.which("pdffonts") or "pdffonts", str(path)])
    return "Type 3" in result.stdout


def has_reference_heading(path: Path) -> bool:
    result = run([shutil.which("pdftotext") or "pdftotext", str(path), "-"])
    return bool(
        re.search(
            r"(?im)^\s*(references|bibliography)\s*:?\s*$", result.stdout
        )
    )


def reference_note_page(width: float, height: float):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_name = "Helvetica"
    embedded_font = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    if embedded_font.exists():
        try:
            pdfmetrics.registerFont(TTFont("HeartReferenceNote", str(embedded_font)))
            font_name = "HeartReferenceNote"
        except (OSError, ValueError):
            pass
    stream = io.BytesIO()
    canvas_obj = canvas.Canvas(stream, pagesize=(width, height))
    canvas_obj.setFont(font_name, 16)
    canvas_obj.drawString(54, height - 72, "References")
    canvas_obj.setFont(font_name, 10)
    canvas_obj.drawString(
        54,
        height - 102,
        "The archived submission did not contain a separately labelled references section.",
    )
    canvas_obj.save()
    stream.seek(0)
    from pypdf import PdfReader

    return PdfReader(stream).pages[0]


def append_reference_note(path: Path, root: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    with tempfile.TemporaryDirectory(dir=root / "tmp", prefix="references-") as temp_name:
        temp_path = Path(temp_name) / "reference-note.pdf"
        reader = PdfReader(str(path))
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        last = writer.pages[-1]
        writer.add_page(
            reference_note_page(float(last.mediabox.width), float(last.mediabox.height))
        )
        if reader.metadata:
            writer.add_metadata(dict(reader.metadata))
        with temp_path.open("wb") as file:
            writer.write(file)
        os.replace(temp_path, path)


def ocr_pdf(input_path: Path, output_path: Path, temp_dir: Path) -> None:
    """Create a searchable image PDF for a source with no extractable text."""
    prefix = temp_dir / "page"
    rendered = run(
        [
            shutil.which("pdftoppm") or "pdftoppm",
            "-png",
            "-r",
            "120",
            str(input_path),
            str(prefix),
        ]
    )
    if rendered.returncode != 0:
        raise RuntimeError(rendered.stderr[-1000:])

    page_images = sorted(temp_dir.glob("page-*.png"))
    if not page_images:
        raise RuntimeError("pdftoppm produced no page images")
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for index, image in enumerate(page_images):
        base = temp_dir / f"ocr-{index:04d}"
        result = run(
            [shutil.which("tesseract") or "tesseract", str(image), str(base), "pdf"]
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-1000:])
        reader = PdfReader(str(base) + ".pdf")
        for page in reader.pages:
            writer.add_page(page)
    with output_path.open("wb") as file:
        writer.write(file)


def citation_overlay(width: float, height: float, citation: str):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_name = "Helvetica"
    embedded_font = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    if embedded_font.exists():
        try:
            pdfmetrics.registerFont(TTFont("HeartCitation", str(embedded_font)))
            font_name = "HeartCitation"
        except (OSError, ValueError):
            pass

    stream = io.BytesIO()
    canvas_obj = canvas.Canvas(stream, pagesize=(width, height))
    font_size = 7.0
    max_width = max(width - 72, 100)
    while font_size > 4.5 and stringWidth(citation, font_name, font_size) > max_width:
        font_size -= 0.25
    canvas_obj.setFont(font_name, font_size)
    canvas_obj.setFillColorRGB(0.25, 0.25, 0.25)
    canvas_obj.drawString(36, height - 18, citation)
    canvas_obj.setStrokeColorRGB(0.78, 0.78, 0.78)
    canvas_obj.setLineWidth(0.35)
    canvas_obj.line(36, height - 23, width - 36, height - 23)
    canvas_obj.save()
    stream.seek(0)
    from pypdf import PdfReader

    return PdfReader(stream).pages[0]


def write_metadata(
    input_path: Path,
    output_path: Path,
    title: str,
    authors: list[str],
    subject: str,
    keywords: str,
    citation: str,
    add_citation: bool = True,
) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(input_path))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    if add_citation and writer.pages:
        first = writer.pages[0]
        first_text = first.extract_text() or ""
        if "In: hEART " not in first_text:
            overlay = citation_overlay(
                float(first.mediabox.width), float(first.mediabox.height), citation
            )
            first.merge_page(overlay)
    writer.add_metadata(
        {
            "/Title": title,
            "/Author": "; ".join(authors) or "hEART",
            "/Subject": subject,
            "/Keywords": keywords,
        }
    )
    with output_path.open("wb") as file:
        writer.write(file)


def process_one(
    root: Path,
    database: Path,
    year: int,
    row: dict[str, str],
    pdf_path: Path,
    info: dict[int, tuple[str, str]],
    force_raster: bool = False,
) -> str:
    title = str(row.get("title") or "Untitled paper")
    authors = parse_author_names(row.get("authors", ""), year)
    conference_name, dates = info.get(year, (f"hEART {year}", str(year)))
    citation = f"In: {conference_name}, {dates}."
    subject = f"{conference_name}; {dates}"
    keywords = f"hEART, transportation research, conference paper, {year}"

    with tempfile.TemporaryDirectory(dir=root / "tmp", prefix="pdfs-") as temp_name:
        temp_dir = Path(temp_name)
        normalized = temp_dir / "normalized.pdf"
        normalize_with_ghostscript(pdf_path, normalized)
        source = normalized
        if force_raster or not has_searchable_text(source):
            ocr = temp_dir / "ocr.pdf"
            ocr_pdf(source, ocr, temp_dir)
            source = ocr
        output = temp_dir / "final.pdf"
        write_metadata(source, output, title, authors, subject, keywords, citation)

        if output.stat().st_size > MAX_BYTES:
            compressed = temp_dir / "compressed.pdf"
            run_result = run(
                [
                    shutil.which("gs") or "gs",
                    "-q",
                    "-sDEVICE=pdfwrite",
                    "-dCompatibilityLevel=1.7",
                    "-dPDFSETTINGS=/screen",
                    "-dDetectDuplicateImages=true",
                    "-dCompressFonts=true",
                    "-dEmbedAllFonts=true",
                    "-dSubsetFonts=true",
                    "-dNOPAUSE",
                    "-dBATCH",
                    f"-sOutputFile={compressed}",
                    str(output),
                ]
            )
            if run_result.returncode == 0 and compressed.exists():
                write_metadata(
                    compressed,
                    output,
                    title,
                    authors,
                    subject,
                    keywords,
                    citation,
                    add_citation=False,
                )
        os.replace(output, pdf_path)

    return pdf_path.as_posix()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--database", type=Path, default=Path("heart.db"))
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--repair-fonts-and-size",
        action="store_true",
        help="Re-rasterize only PDFs still over 5 MB or containing Type 3 fonts.",
    )
    parser.add_argument("--files", nargs="*", help="Process only these PDF paths.")
    parser.add_argument(
        "--add-reference-sections",
        action="store_true",
        help="Append a labelled archival note where no References/Bibliography heading exists.",
    )
    args = parser.parse_args()

    (args.root / "tmp").mkdir(exist_ok=True)
    if args.add_reference_sections:
        paths = [
            pdf
            for year_dir in (args.root / "docs" / "abstracts").glob("[0-9]*")
            for pdf in year_dir.glob("*.pdf")
            if not has_reference_heading(pdf)
        ]
        for index, pdf in enumerate(paths, start=1):
            append_reference_note(pdf, args.root)
            if index % 50 == 0 or index == len(paths):
                print(f"Added reference notes to {index}/{len(paths)} PDFs")
        return

    info = conference_info(args.database)
    rows = list(paper_rows(args.root))
    if args.files:
        selected = {Path(path).resolve() for path in args.files}
        rows = [item for item in rows if item[2].resolve() in selected]
    if args.repair_fonts_and_size:
        rows = [
            item
            for item in rows
            if item[2].stat().st_size >= MAX_BYTES or has_type3_font(item[2])
        ]
    if args.limit:
        rows = rows[: args.limit]
    failures: list[tuple[Path, str]] = []
    for index, (year, row, pdf_path) in enumerate(rows, start=1):
        try:
            process_one(
                args.root,
                args.database,
                year,
                row,
                pdf_path,
                info,
                force_raster=args.repair_fonts_and_size,
            )
        except Exception as error:  # noqa: BLE001 - keep processing the archive
            failures.append((pdf_path, str(error)))
        if index % 50 == 0 or index == len(rows):
            print(f"Processed {index}/{len(rows)} PDFs")
    if failures:
        print(f"Failures: {len(failures)}")
        for path, error in failures:
            print(f"- {path}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
