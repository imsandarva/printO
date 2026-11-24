"""Build the exact PDF the printer should receive: the chosen pages, repeated once per copy.

The MF3010's collate setting defaults to Group, so asking CUPS for copies would print every copy of
page 1 before page 2. Repeating the pages here keeps a 3-page letter in order, for each copy.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import DecodedStreamObject, NameObject

from printo.storage.atomic import replace


def compose(source: Path, dest: Path, indexes: list[int], copies: int, fit: int = 100) -> int:
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted:
        reader.decrypt("")
    writer = PdfWriter()
    # 100% is the page as prepared. Copy it through so embedded fonts stay as they are.
    if fit == 100:
        for _ in range(copies):
            writer.append(reader, pages=list(indexes))
    else:
        _place(writer, reader, indexes, copies, fit / 100)
    temporary = dest.with_name(dest.name + ".partial")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("wb") as handle:
        writer.write(handle)
    replace(temporary, dest)
    return len(indexes) * copies


def _place(writer: PdfWriter, reader: PdfReader, indexes: list[int], copies: int, factor: float) -> None:
    for _ in range(copies):
        for index in indexes:
            _center(writer, reader.pages[index], factor)


def _center(writer: PdfWriter, page, factor: float) -> None:
    box = page.mediabox
    left, bottom = float(box.left), float(box.bottom)
    width, height = float(box.width), float(box.height)
    blank = writer.add_blank_page(width=width, height=height)
    _same_box(blank, left, bottom, float(box.right), float(box.top))
    center_x, center_y = left + width / 2, bottom + height / 2
    placed = Transformation().scale(factor).translate(center_x * (1 - factor), center_y * (1 - factor))
    blank.merge_transformed_page(page, placed, expand=False)
    _keep_rotation(blank, page)
    _cut_to_sheet(blank)


def _same_box(page, left: float, bottom: float, right: float, top: float) -> None:
    if not left and not bottom:
        return
    page.mediabox.lower_left = (left, bottom)
    page.mediabox.upper_right = (right, top)


def _keep_rotation(blank, page) -> None:
    rotation = int(page.rotation or 0)
    if rotation:
        blank.rotation = rotation


def _cut_to_sheet(page) -> None:
    # Anything past the sheet is dropped, the same way the preview hides it.
    contents = page.get_contents()
    reference = page.indirect_reference
    if contents is None or reference is None:
        return
    box = page.mediabox
    clip = f"q\n{float(box.left):.4f} {float(box.bottom):.4f} {float(box.width):.4f} {float(box.height):.4f} re W n\n".encode()
    stream = DecodedStreamObject()
    stream.set_data(clip + contents.get_data() + b"\nQ\n")
    page[NameObject("/Contents")] = reference.pdf._add_object(stream)
