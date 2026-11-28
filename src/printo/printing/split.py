"""Make reusable one-sheet PDFs from the composed print document."""

import json
import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from printo.storage.atomic import replace


def split_pages(source: Path, destination: Path, indexes: list[int]) -> None:
    """Keep one rendered PDF for each source page; copies reuse those small files."""
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(source), strict=False)
    first: dict[int, int] = {}
    for position, index in enumerate(indexes):
        first.setdefault(index, position)
    for index, position in first.items():
        writer = PdfWriter()
        writer.add_page(reader.pages[position])
        _write_pdf(destination / f"page-{index + 1:04d}.pdf", writer)


def split_sheets(source: Path, destination: Path, sheets: int) -> None:
    """Keep one landscape sheet PDF. Later copies submit those same files again."""
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(source), strict=False)
    count = min(sheets, len(reader.pages))
    for index in range(count):
        writer = PdfWriter()
        writer.add_page(reader.pages[index])
        _write_pdf(destination / f"page-{index + 1:04d}.pdf", writer)
    _write_plan(destination, count)


def _write_pdf(target: Path, writer: PdfWriter) -> None:
    partial = target.with_name(target.name + ".partial")
    with partial.open("wb") as handle:
        writer.write(handle)
    replace(partial, target)


def _write_plan(destination: Path, sheets: int) -> None:
    target = destination / "plan.json"
    partial = target.with_name(target.name + ".partial")
    partial.write_text(json.dumps({"sheets": sheets}), encoding="utf-8")
    replace(partial, target)
