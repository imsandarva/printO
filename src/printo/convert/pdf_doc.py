"""A valid PDF is copied through unchanged, so embedded fonts (including Nepali) stay as they arrived."""

import logging
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from printo.errors import UserError
from printo.messages import damaged, pdf_locked, too_many_pages
from printo.storage.atomic import copy_sealed

log = logging.getLogger("printo.convert")


@dataclass(frozen=True, slots=True)
class Prepared:
    page_count: int


def prepare_pdf(source: Path, dest: Path, max_sheets: int) -> Prepared:
    count = page_count(source, max_sheets)
    if source.resolve() != dest.resolve():
        copy_sealed(source, dest)
    return Prepared(count)


def page_count(path: Path, max_sheets: int | None = None) -> int:
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and not _opens_without_password(reader):
            raise UserError(pdf_locked())
        count = len(reader.pages)
    except UserError:
        raise
    except (PdfReadError, OSError, ValueError, TypeError, KeyError, AssertionError) as exc:
        log.info("unreadable pdf: %s", type(exc).__name__)
        raise UserError(damaged()) from None
    if count < 1:
        raise UserError(damaged())
    if max_sheets is not None and count > max_sheets:
        raise UserError(too_many_pages())
    return count


def _opens_without_password(reader: PdfReader) -> bool:
    try:
        return int(reader.decrypt("")) != 0
    except Exception:
        return False
