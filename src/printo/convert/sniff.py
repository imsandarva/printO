"""Decide what a file is from its bytes. The phone's filename and content type are not trusted."""

import zipfile
from pathlib import Path

from printo.domain.kinds import IMAGE, OFFICE, PDF
from printo.errors import UserError
from printo.messages import bad_type, empty_file

_HEIF = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"heif", b"mif1", b"msf1"}


def detect(path: Path) -> tuple[str, str]:
    head = path.read_bytes()[:64]
    if not head and path.stat().st_size == 0:
        raise UserError(empty_file())
    found = _from_head(head) or _from_zip(path, head)
    if found is None:
        raise UserError(bad_type())
    return found


def _from_head(head: bytes) -> tuple[str, str] | None:
    if head.startswith(b"%PDF"):
        return PDF, ".pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return IMAGE, ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return IMAGE, ".png"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return IMAGE, ".gif"
    if head.startswith(b"BM"):
        return IMAGE, ".bmp"
    if head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"):
        return IMAGE, ".tiff"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return IMAGE, ".webp"
    if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in _HEIF:
        return IMAGE, ".heic"
    if head.startswith(b"{\\rtf"):
        return OFFICE, ".rtf"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return OFFICE, ".doc"
    return None


def _from_zip(path: Path, head: bytes) -> tuple[str, str] | None:
    if not head.startswith(b"PK\x03\x04"):
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "word/document.xml" in names:
                return OFFICE, ".docx"
            if "mimetype" in names and _odt(archive):
                return OFFICE, ".odt"
    except (zipfile.BadZipFile, OSError):
        return None
    return None


def _odt(archive: zipfile.ZipFile) -> bool:
    info = archive.getinfo("mimetype")
    if info.file_size > 128:
        return False
    return archive.read("mimetype").startswith(b"application/vnd.oasis.opendocument.text")
