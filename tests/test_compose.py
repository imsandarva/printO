import re
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

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


def _bytes(writer: PdfWriter) -> bytes:
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _mark(page) -> str:
    match = re.search(rb"\((\d)\)", page.get_contents().get_data())
    assert match
    return match.group(1).decode()


def _expect(width: float, height: float, factor: float) -> tuple[float, float, float]:
    scale = min(A4_WIDTH / width, A4_HEIGHT / height) * factor
    return scale, (A4_WIDTH - width * scale) / 2, (A4_HEIGHT - height * scale) / 2


def _placement(data: bytes) -> tuple[float, ...]:
    match = re.search(rb"([0-9.eE+-]+) ([0-9.eE+-]+) ([0-9.eE+-]+) ([0-9.eE+-]+) ([0-9.eE+-]+) ([0-9.eE+-]+) cm", data)
    assert match
    return tuple(float(part) for part in match.groups())
