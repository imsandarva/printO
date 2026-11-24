from pypdf import PdfReader

from printo.printing.compose import compose
from tests.support import marked_pdf, pdf_bytes


def test_pages_repeat_in_order(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(pdf_bytes((200, 300, 400)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [2, 0], 2) == 4
    widths = [int(page.mediabox.width) for page in PdfReader(str(dest)).pages]
    assert widths == [400, 200, 400, 200]


def test_smaller_fit_stays_centered_on_the_same_sheet(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(marked_pdf())
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0], 2, 50) == 2
    pages = PdfReader(str(dest)).pages
    assert [int(page.mediabox.width) for page in pages] == [200, 200]
    assert [int(page.mediabox.height) for page in pages] == [800, 800]
    assert b"0.5 0.0 0.0 0.5 50 200 cm" in pages[0].get_contents().get_data()


def test_larger_fit_is_cut_to_the_sheet(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(marked_pdf())
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [0], 1, 125) == 1
    page = PdfReader(str(dest)).pages[0]
    data = page.get_contents().get_data()
    assert int(page.mediabox.width) == 200 and int(page.mediabox.height) == 800
    assert data.startswith(b"q\n0.0000 0.0000 200.0000 800.0000 re W n\n")
    assert b"1.25 0.0 0.0 1.25 -25 -100 cm" in data
