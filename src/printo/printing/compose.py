"""Build the exact PDF the printer should receive: the chosen pages, repeated once per copy.

The MF3010's collate setting defaults to Group, so asking CUPS for copies would print every copy of
page 1 before page 2. Repeating the pages here keeps a 3-page letter in order, for each copy.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from printo.storage.atomic import replace


def compose(source: Path, dest: Path, indexes: list[int], copies: int) -> int:
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted:
        reader.decrypt("")
    writer = PdfWriter()
    for _ in range(copies):
        writer.append(reader, pages=list(indexes))
    temporary = dest.with_name(dest.name + ".partial")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("wb") as handle:
        writer.write(handle)
    replace(temporary, dest)
    return len(indexes) * copies
