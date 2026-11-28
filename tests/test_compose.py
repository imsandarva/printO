import re
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from printo.domain.layout import HALF_WIDTH, LANDSCAPE_HEIGHT, LANDSCAPE_WIDTH, RULE_GRAY
from printo.printing.compose import A4_HEIGHT, A4_WIDTH, compose
from tests.support import marked_pdf


def test_pages_repeat_in_order(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_labeled((200, 300, 400)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [2, 0], 2) == 4
    pages = PdfReader(str(dest)).pages
    assert len(pages) == 4
    assert [int(page.mediabox.width) for page in pages] == [int(A4_WIDTH)] * 4
    assert [_mark(page) for page in pages] == ["2", "0", "2", "0"]


def test_smaller_fit_stays_centered_on_a4(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(marked_pdf())
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0], 2, 50) == 2
    pages = PdfReader(str(dest)).pages
    assert len(pages) == 2
    scale, ox, oy = _expect(200, 800, 0.5)
    for page in pages:
        assert float(page.mediabox.width) == pytest.approx(A4_WIDTH)
        assert float(page.mediabox.height) == pytest.approx(A4_HEIGHT)
        placed = _placement(page.get_contents().get_data())
        assert placed == pytest.approx((scale, 0, 0, scale, ox, oy))


def test_larger_fit_is_cut_to_the_sheet(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(marked_pdf())
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0], 1, 125) == 1
    page = PdfReader(str(dest)).pages[0]
    data = page.get_contents().get_data()
    assert float(page.mediabox.width) == pytest.approx(A4_WIDTH)
    assert float(page.mediabox.height) == pytest.approx(A4_HEIGHT)
    assert data.startswith(f"q\n0.0000 0.0000 {A4_WIDTH:.4f} {A4_HEIGHT:.4f} re W n\n".encode())
    scale, ox, oy = _expect(200, 800, 1.25)
    assert _placement(data) == pytest.approx((scale, 0, 0, scale, ox, oy))


def test_a4_at_full_size_is_copied_through(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(marked_pdf(595, 842))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0], 1, 100) == 1
    data = PdfReader(str(dest)).pages[0].get_contents().get_data()
    assert data == b"0 0 m 10 10 l S"


def test_a_turned_page_stands_up_on_a4(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_turned())
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0], 1, 100) == 1
    page = PdfReader(str(dest)).pages[0]
    assert int(page.rotation or 0) == 0
    assert float(page.mediabox.width) == pytest.approx(A4_WIDTH)
    assert float(page.mediabox.height) == pytest.approx(A4_HEIGHT)
    assert b"0 0 m" in page.get_contents().get_data()


def test_per_page_rotation_only_turns_chosen_pages(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_labeled((200, 400)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0, 1], 1, 100, rotations={1: 90}) == 2
    pages = PdfReader(str(dest)).pages
    assert len(pages) == 2
    assert float(pages[0].mediabox.width) == pytest.approx(A4_WIDTH)
    assert float(pages[1].mediabox.width) == pytest.approx(A4_WIDTH)
    # Page 0 stays upright (200x800 -> scale A4_HEIGHT/800), page 1 turns sideways (800x400 -> scale A4_WIDTH/800).
    p0 = _placement(pages[0].get_contents().get_data())
    p1 = _placement(pages[1].get_contents().get_data())
    assert p0[0] == pytest.approx(A4_HEIGHT / 800)
    assert p1[0] == pytest.approx(A4_WIDTH / 800)
    assert b"-1 1 " in pages[1].get_contents().get_data()


def test_two_pages_share_one_landscape_sheet(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_labeled((200, 400)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0, 1], 1, 100, landscape=True) == 1
    page = PdfReader(str(dest)).pages[0]
    assert float(page.mediabox.width) == pytest.approx(LANDSCAPE_WIDTH)
    assert float(page.mediabox.height) == pytest.approx(LANDSCAPE_HEIGHT)
    placed = _uniform(page.get_contents().get_data())
    assert len(placed) == 2
    assert placed[0][0] == pytest.approx(LANDSCAPE_HEIGHT / 800)
    assert placed[1][0] == pytest.approx(LANDSCAPE_HEIGHT / 800)
    assert _center(placed[0], 200, 800) == pytest.approx((HALF_WIDTH / 2, LANDSCAPE_HEIGHT / 2))
    assert _center(placed[1], 400, 800) == pytest.approx((HALF_WIDTH * 1.5, LANDSCAPE_HEIGHT / 2))
    assert f"{RULE_GRAY:.4f} G".encode() in page.get_contents().get_data()


def test_odd_last_page_leaves_a_blank_half(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_labeled((200, 220, 240)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0, 1, 2], 2, 100, landscape=True) == 4
    pages = PdfReader(str(dest)).pages
    assert len(pages) == 4
    first, second = pages[0].get_contents().get_data(), pages[1].get_contents().get_data()
    assert len(_uniform(first)) == 2 and [_mark(pages[0]), _mark(pages[0], last=True)] == ["0", "1"]
    assert len(_uniform(second)) == 1 and _mark(pages[1]) == "2"


def test_landscape_pairs_the_chosen_pages(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_labeled((200, 220, 240, 260)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0, 2], 1, 100, landscape=True) == 1
    data = PdfReader(str(dest)).pages[0].get_contents().get_data()
    assert _mark_all(data) == ["0", "2"]


def test_landscape_turns_a_page_before_placing_it(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_labeled((200, 200)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0, 1], 1, 100, rotations={1: 90}, landscape=True) == 1
    placed = _uniform(PdfReader(str(dest)).pages[0].get_contents().get_data())
    assert placed[0][0] == pytest.approx(LANDSCAPE_HEIGHT / 800)
    assert placed[1][0] == pytest.approx(HALF_WIDTH / 800)


def test_landscape_keeps_mixed_page_shapes(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_sized(((200, 800), (800, 200))))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0, 1], 1, 100, landscape=True) == 1
    tall, wide = _uniform(PdfReader(str(dest)).pages[0].get_contents().get_data())
    assert tall[0] == pytest.approx(LANDSCAPE_HEIGHT / 800)
    assert wide[0] == pytest.approx(HALF_WIDTH / 800)
    assert _center(tall, 200, 800)[0] == pytest.approx(HALF_WIDTH / 2)
    assert _center(wide, 800, 200)[0] == pytest.approx(HALF_WIDTH * 1.5)


def test_landscape_size_scales_about_the_sheet_centre(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(_labeled((200, 200)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0, 1], 1, 50, landscape=True) == 1
    page = PdfReader(str(dest)).pages[0]
    placed = _uniform(page.get_contents().get_data())
    # Halfway toward the middle of the sheet, and half as large as the normal fit.
    mid = LANDSCAPE_WIDTH / 2
    assert _center(placed[0], 200, 800)[0] == pytest.approx(mid + 0.5 * (HALF_WIDTH / 2 - mid))
    assert placed[0][0] == pytest.approx(0.5 * LANDSCAPE_HEIGHT / 800)
    assert page.get_contents().get_data().startswith(f"q\n0.0000 0.0000 {LANDSCAPE_WIDTH:.4f} {LANDSCAPE_HEIGHT:.4f} re W n\n".encode())


def _labeled(widths: tuple[int, ...]) -> bytes:
    writer = PdfWriter()
    for index, width in enumerate(widths):
        page = writer.add_blank_page(width=width, height=800)
        stream = DecodedStreamObject()
        stream.set_data(f"({index}) Tj".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    return _bytes(writer)


def _turned() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=200)
    stream = DecodedStreamObject()
    stream.set_data(b"0 0 m 10 10 l S")
    page[NameObject("/Contents")] = writer._add_object(stream)
    page.rotation = 90
    return _bytes(writer)


def _sized(pages: tuple[tuple[int, int], ...]) -> bytes:
    writer = PdfWriter()
    for index, (width, height) in enumerate(pages):
        page = writer.add_blank_page(width=width, height=height)
        stream = DecodedStreamObject()
        stream.set_data(f"({index}) Tj".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    return _bytes(writer)


def _bytes(writer: PdfWriter) -> bytes:
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _mark(page, last: bool = False) -> str:
    found = _mark_all(page.get_contents().get_data())
    assert found
    return found[-1] if last else found[0]


def _mark_all(data: bytes) -> list[str]:
    return [item.decode() for item in re.findall(rb"\((\d)\)", data)]


def _expect(width: float, height: float, factor: float) -> tuple[float, float, float]:
    scale = min(A4_WIDTH / width, A4_HEIGHT / height) * factor
    return scale, (A4_WIDTH - width * scale) / 2, (A4_HEIGHT - height * scale) / 2


def _placement(data: bytes) -> tuple[float, ...]:
    found = _uniform(data)
    assert found
    return found[0]


def _uniform(data: bytes) -> list[tuple[float, ...]]:
    found = []
    for match in re.finditer(rb"([0-9.eE+-]+) ([0-9.eE+-]+) ([0-9.eE+-]+) ([0-9.eE+-]+) ([0-9.eE+-]+) ([0-9.eE+-]+) cm", data):
        matrix = tuple(float(part) for part in match.groups())
        if abs(matrix[1]) < 1e-6 and abs(matrix[2]) < 1e-6:
            found.append(matrix)
    return found


def _center(matrix: tuple[float, ...], width: float, height: float) -> tuple[float, float]:
    scale, _b, _c, _d, tx, ty = matrix
    return scale * width / 2 + tx, scale * height / 2 + ty
