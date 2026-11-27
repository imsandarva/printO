import zipfile

import pytest

from printo.convert.sniff import detect
from printo.errors import UserError


def test_headers(tmp_path):
    samples = {
        b"%PDF-1.7\n": ("pdf", ".pdf"),
        b"\xff\xd8\xff\xe0rest": ("image", ".jpg"),
        b"\x89PNG\r\n\x1a\nrest": ("image", ".png"),
        b"GIF89a": ("image", ".gif"),
        b"BM": ("image", ".bmp"),
        b"II*\x00": ("image", ".tiff"),
        b"RIFF\x00\x00\x00\x00WEBP": ("image", ".webp"),
        b"\x00\x00\x00\x18ftypheic" + b"\x00" * 8: ("image", ".heic"),
        b"{\\rtf1 hi}": ("office", ".rtf"),
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16: ("office", ".doc"),
    }
    for blob, expected in samples.items():
        path = tmp_path / "f"
        path.write_bytes(blob)
        assert detect(path) == expected


def test_docx_and_odt_and_not_a_spreadsheet(tmp_path):
    docx = tmp_path / "a.docx"
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    assert detect(docx) == ("office", ".docx")
    odt = tmp_path / "a.odt"
    with zipfile.ZipFile(odt, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
    assert detect(odt) == ("office", ".odt")
    sheet = tmp_path / "a.xlsx"
    with zipfile.ZipFile(sheet, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(UserError) as caught:
        detect(sheet)
    assert "isn't any of those" in caught.value.message


def test_empty_and_text(tmp_path):
    empty = tmp_path / "e"
    empty.write_bytes(b"")
    with pytest.raises(UserError) as caught:
        detect(empty)
    assert "empty" in caught.value.message
    text = tmp_path / "t"
    text.write_bytes(b"hello")
    with pytest.raises(UserError) as caught:
        detect(text)
    assert "PDF" in caught.value.message


def test_named_utf8_text_is_allowed_but_binary_is_not(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# A note\n\nA line to print.\n", encoding="utf-8")
    assert detect(note, note.name) == ("office", ".md")
    binary = tmp_path / "not-really-text.txt"
    binary.write_bytes(b"\x00\xff\x00")
    with pytest.raises(UserError):
        detect(binary, binary.name)
