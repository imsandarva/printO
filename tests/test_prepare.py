from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from printo.convert.images import prepare_image
from printo.convert.pdf_doc import prepare_pdf
from printo.errors import UserError
from tests.support import jpeg_bytes, pdf_bytes


def test_valid_pdf_is_copied_unchanged(tmp_path):
    raw = pdf_bytes((595,))
    source, dest = tmp_path / "source.pdf", tmp_path / "document.pdf"
    source.write_bytes(raw)
    prepared = prepare_pdf(source, dest, max_sheets=10)
    assert prepared.page_count == 1
    assert dest.read_bytes() == raw


def test_locked_pdf(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.encrypt("secret")
    source = tmp_path / "locked.pdf"
    with source.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(UserError) as caught:
        prepare_pdf(source, tmp_path / "out.pdf", max_sheets=10)
    assert "password" in caught.value.message


def test_photo_lands_on_a4(tmp_path):
    source = tmp_path / "photo.jpg"
    source.write_bytes(jpeg_bytes())
    dest = tmp_path / "document.pdf"
    prepared = prepare_image(source, dest, max_sheets=10)
    assert prepared.page_count == 1
    page = PdfReader(str(dest)).pages[0]
    assert page.mediabox.width == pytest.approx(595, abs=2)
    assert page.mediabox.height == pytest.approx(842, abs=2)


def test_too_many_pages(tmp_path):
    source = tmp_path / "big.pdf"
    source.write_bytes(pdf_bytes((200, 300)))
    with pytest.raises(UserError) as caught:
        prepare_pdf(source, tmp_path / "out.pdf", max_sheets=1)
    assert "too many pages" in caught.value.message


def test_damaged_pdf(tmp_path):
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"%PDF-1.7\nthis is not a pdf")
    with pytest.raises(UserError) as caught:
        prepare_pdf(source, tmp_path / "out.pdf", max_sheets=5)
    assert "damaged" in caught.value.message


def test_png_with_transparency(tmp_path):
    from PIL import Image

    image = Image.new("RGBA", (30, 30), (255, 0, 0, 128))
    source = tmp_path / "a.png"
    image.save(source, "PNG")
    dest = tmp_path / "document.pdf"
    assert prepare_image(source, dest, max_sheets=5).page_count == 1
    assert dest.read_bytes().startswith(b"%PDF")
    assert Path(dest).stat().st_size > 100
