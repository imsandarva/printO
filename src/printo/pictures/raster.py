"""One grey picture of one PDF page, about as large as the sheet on the counter.

The picture is what the counter scrolls. Turning a page, or laying two side by side,
happens later, over this picture. The original file is not opened again for that.
"""

import io
from pathlib import Path

import fitz
from PIL import Image

# Long enough to stay sharp on the counter, including the 125% size, and small enough to keep.
EDGE = 1500
QUALITY = 74


def open_pdf(source: Path | bytes) -> fitz.Document:
    if isinstance(source, bytes):
        return fitz.open(stream=source, filetype="pdf")
    return fitz.open(source)


def jpeg_page(doc: fitz.Document, page: int) -> bytes:
    if page < 1 or page > doc.page_count:
        raise ValueError("page")
    sheet = doc[page - 1]
    rect = sheet.rect
    long_edge = max(float(rect.width), float(rect.height)) or 1.0
    # The page's own turn is already in the rectangle, so the picture stands the way the file does.
    pixmap = sheet.get_pixmap(matrix=fitz.Matrix(EDGE / long_edge, EDGE / long_edge), colorspace=fitz.csGRAY, alpha=False)
    return pixmap.tobytes("jpeg", jpg_quality=QUALITY)


def render_bytes(data: bytes, page: int) -> bytes:
    doc = open_pdf(data)
    try:
        return jpeg_page(doc, page)
    finally:
        doc.close()


def _blank() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (32, 45), 255).save(buffer, "JPEG", quality=70)
    return buffer.getvalue()


# A page that cannot be pictured still counts as done, so the counter is not left waiting on it.
BLANK_JPEG = _blank()
