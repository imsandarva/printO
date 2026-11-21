from pypdf import PdfReader

from printo.printing.compose import compose
from tests.support import pdf_bytes


def test_pages_repeat_in_order(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(pdf_bytes((200, 300, 400)))
    dest = tmp_path / "to-print.pdf"
    assert compose(source, dest, [2, 0], 2) == 4
    widths = [int(page.mediabox.width) for page in PdfReader(str(dest)).pages]
    assert widths == [400, 200, 400, 200]
