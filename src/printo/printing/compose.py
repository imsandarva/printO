"""Build the exact PDF the printer should receive: the chosen pages, repeated once per copy.

Portrait is one page on A4. Landscape is two chosen pages on one A4 sheet turned sideways.
A page keeps its own shape and is centred. Anything past the edge is cut off. The numbers
live in domain/layout.py, which is also what the preview follows. The MF3010's collate
setting defaults to Group, so asking CUPS for copies would print every copy of page 1
before page 2. Repeating the sheets here keeps each copy in order.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import DecodedStreamObject, NameObject

from printo.domain.layout import (
    A4_HEIGHT,
    A4_WIDTH,
    LANDSCAPE_HEIGHT,
    LANDSCAPE_WIDTH,
    RULE_GRAY,
    RULE_INSET,
    RULE_WIDTH,
    pairs,
    place_in_half,
)
from printo.storage.atomic import replace

# Word processors and photos round A4 by a point or two. Close enough to leave the page alone.
_SLOP = 2.0


def compose(source: Path, dest: Path, indexes: list[int], copies: int, fit: int = 100, rotations: dict[int, int] | None = None, landscape: bool = False) -> int:
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted:
        reader.decrypt("")
    writer = PdfWriter()
    extra = rotations or {}
    if landscape:
        count = _place_landscape(writer, reader, indexes, copies, fit / 100, extra)
    # 100% on an upright page that is already A4 is copied through, so embedded fonts stay as they are.
    elif fit == 100 and all(extra.get(index, 0) % 360 == 0 and _is_a4(reader.pages[index]) for index in indexes):
        _copy(writer, reader, indexes, copies)
        count = len(indexes) * copies
    else:
        _place(writer, reader, indexes, copies, fit / 100, extra)
        count = len(indexes) * copies
    _save(writer, dest)
    return count


def _copy(writer: PdfWriter, reader: PdfReader, indexes: list[int], copies: int) -> None:
    for _ in range(copies):
        writer.append(reader, pages=list(indexes))


def _place(writer: PdfWriter, reader: PdfReader, indexes: list[int], copies: int, factor: float, rotations: dict[int, int]) -> None:
    ready = {index: upright_page(reader.pages[index], writer, rotations.get(index, 0)) for index in indexes}
    for _ in range(copies):
        for index in indexes:
            center_on_a4(writer, ready[index], factor)


def _place_landscape(writer: PdfWriter, reader: PdfReader, indexes: list[int], copies: int, factor: float, rotations: dict[int, int]) -> int:
    ready = {index: upright_page(reader.pages[index], writer, rotations.get(index, 0)) for index in indexes}
    grouped = pairs(indexes)
    for _ in range(copies):
        for left, right in grouped:
            sheet = writer.add_blank_page(width=LANDSCAPE_WIDTH, height=LANDSCAPE_HEIGHT)
            _stamp_half(sheet, ready[left], 0, factor)
            if right is not None:
                _stamp_half(sheet, ready[right], 1, factor)
            _divider(sheet)
            clip_sheet(sheet)
    return len(grouped) * copies


def _stamp_half(sheet, page, side: int, factor: float) -> None:
    box = page.mediabox
    left, bottom = float(box.left), float(box.bottom)
    width, height = max(float(box.width), 1.0), max(float(box.height), 1.0)
    scale, tx, ty = place_in_half(width, height, left, bottom, side, factor)
    sheet.merge_transformed_page(page, Transformation().scale(scale).translate(tx, ty), expand=False)


def _divider(page) -> None:
    # The same faint centre line the preview draws. It stays put when the sheet is scaled.
    contents = page.get_contents()
    reference = page.indirect_reference
    if contents is None or reference is None:
        return
    x = LANDSCAPE_WIDTH / 2
    line = f"q {RULE_GRAY:.4f} G {RULE_WIDTH:.2f} w {x:.4f} {RULE_INSET:.4f} m {x:.4f} {LANDSCAPE_HEIGHT - RULE_INSET:.4f} l S Q\n".encode()
    stream = DecodedStreamObject()
    stream.set_data(contents.get_data() + line)
    page[NameObject("/Contents")] = reference.pdf._add_object(stream)


def _is_a4(page) -> bool:
    if int(page.rotation or 0) % 360:
        return False
    box = page.mediabox
    left, bottom = float(box.left), float(box.bottom)
    if abs(left) > 1 or abs(bottom) > 1:
        return False
    return abs(float(box.width) - A4_WIDTH) <= _SLOP and abs(float(box.height) - A4_HEIGHT) <= _SLOP


def upright_page(page, writer: PdfWriter, extra: int = 0):
    # A rotated page is stored sideways. Apply any extra turn and bake rotation into content.
    total = (int(page.rotation or 0) + extra) % 360
    if total == 0:
        return page
    clone = page.clone(writer)
    if extra % 360:
        clone.rotation = total
    clone.transfer_rotation_to_content()
    return clone


def center_on_a4(writer: PdfWriter, page, factor: float) -> None:
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
