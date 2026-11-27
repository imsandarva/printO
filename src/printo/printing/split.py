"""Make reusable one-page PDFs from the composed print document."""

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
        target = destination / f"page-{index + 1:04d}.pdf"
        partial = target.with_name(target.name + ".partial")
        with partial.open("wb") as handle:
            writer.write(handle)
        replace(partial, target)
