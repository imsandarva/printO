"""Build the exact PDF the printer should receive: the chosen pages, repeated once per copy.

The sheet is always A4, portrait, the paper in the tray. A page keeps its own shape and sits
in the middle of that sheet. Anything past the edge is cut off. The MF3010's collate setting
defaults to Group, so asking CUPS for copies would print every copy of page 1 before page 2.
Repeating the pages here keeps a 3-page letter in order, for each copy.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import DecodedStreamObject, NameObject

from printo.storage.atomic import replace

# 210mm by 297mm, in PDF points. One point is 1/72 inch.
_MM = 72 / 25.4
A4_WIDTH = 210 * _MM
A4_HEIGHT = 297 * _MM
# Word processors and photos round A4 by a point or two. Close enough to leave the page alone.
_SLOP = 2.0


def compose(source: Path, dest: Path, indexes: list[int], copies: int, fit: int = 100) -> int:
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted:
        reader.decrypt("")
    writer = PdfWriter()
    # 100% on a page that is already A4 is copied through, so embedded fonts stay as they are.
    if fit == 100 and all(_is_a4(reader.pages[index]) for index in indexes):
        _copy(writer, reader, indexes, copies)
    else:
        _place(writer, reader, indexes, copies, fit / 100)
    _save(writer, dest)
    return len(indexes) * copies


def _copy(writer: PdfWriter, reader: PdfReader, indexes: list[int], copies: int) -> None:
    for _ in range(copies):
        writer.append(reader, pages=list(indexes))


def _place(writer: PdfWriter, reader: PdfReader, indexes: list[int], copies: int, factor: float) -> None:
    ready = {index: _upright(reader.pages[index], writer) for index in indexes}
    for _ in range(copies):
        for index in indexes:
            _center(writer, ready[index], factor)


def _is_a4(page) -> bool:
    if int(page.rotation or 0) % 360:
        return False
    box = page.mediabox
    left, bottom = float(box.left), float(box.bottom)
    if abs(left) > 1 or abs(bottom) > 1:
        return False
    return abs(float(box.width) - A4_WIDTH) <= _SLOP and abs(float(box.height) - A4_HEIGHT) <= _SLOP


def _upright(page, writer: PdfWriter):
    # A rotated page is stored sideways. Stand it up so it sits on the portrait sheet as it looks.
    if int(page.rotation or 0) % 360 == 0:
        return page
    clone = page.clone(writer)
    clone.transfer_rotation_to_content()
    return clone


def _center(writer: PdfWriter, page, factor: float) -> None:
    box = page.mediabox
    left, bottom = float(box.left), float(box.bottom)
    width, height = max(float(box.width), 1.0), max(float(box.height), 1.0)
    scale, ox, oy = _placement(width, height, factor)
    blank = writer.add_blank_page(width=A4_WIDTH, height=A4_HEIGHT)
    shift = Transformation().scale(scale).translate(ox - left * scale, oy - bottom * scale)
    blank.merge_transformed_page(page, shift, expand=False)
    clip_sheet(blank)


def _placement(width: float, height: float, factor: float) -> tuple[float, float, float]:
    # The whole page, as large as the sheet allows, then the size the counter asked for.
    scale = min(A4_WIDTH / width, A4_HEIGHT / height) * factor
    return scale, (A4_WIDTH - width * scale) / 2, (A4_HEIGHT - height * scale) / 2


def clip_sheet(page) -> None:
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


def _save(writer: PdfWriter, dest: Path) -> None:
    temporary = dest.with_name(dest.name + ".partial")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("wb") as handle:
        writer.write(handle)
    replace(temporary, dest)
