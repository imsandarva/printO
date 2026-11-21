"""Pick the one converter for this file and leave document.pdf next to the original."""

from pathlib import Path

from printo.config import Settings
from printo.convert.images import prepare_image
from printo.convert.office import Office
from printo.convert.pdf_doc import Prepared, prepare_pdf
from printo.domain.kinds import IMAGE, OFFICE, PDF
from printo.errors import UserError
from printo.messages import bad_type


def prepare(source: Path, dest: Path, kind: str, settings: Settings, office: Office, profile: Path) -> Prepared:
    if kind == PDF:
        return prepare_pdf(source, dest, settings.max_sheets)
    if kind == IMAGE:
        return prepare_image(source, dest, settings.max_sheets)
    if kind == OFFICE:
        return office.convert(source, dest, profile)
    raise UserError(bad_type())
