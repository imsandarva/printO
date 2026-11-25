"""Place two photos on one A4 sheet: the first near the top, the second just below it.

A photo file is the picture itself. A PDF keeps its page, unless that page is really one photo,
in which case the photo is lifted out so the white around it is not printed twice.
"""

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject

from printo.convert.images import load_rgb, rgb_image
from printo.domain.rotate import rotate_box
from printo.errors import UserError
from printo.messages import citizenship_failed, citizenship_pages, damaged, pdf_locked
from printo.printing.compose import A4_HEIGHT, A4_WIDTH, center_on_a4, clip_sheet, upright_page
from printo.storage.atomic import replace

# 150 dpi matches every other photo in the shop, and stays light on this laptop.
_DPI = 150
_MAX_PX = (1080, 760)
# Room above the first photo, between the two, and at the edges. Not tight to the paper.
_TOP_MM, _SIDE_MM, _GAP_MM, _BOTTOM_MM = 16, 14, 12, 16
_MM = 72 / 25.4
_MIN_PHOTO = 160


@dataclass(frozen=True, slots=True)
class Piece:
    path: Path
    image: bool


def compose_pair(
    top: Piece,
    bottom: Piece,
    dest: Path,
    *,
    pieces_dir: Path | None = None,
    rotations: tuple[int, int] = (0, 0),
    sheet_rotation: int = 0,
) -> list[dict[str, float]]:
    canvas = _Canvas()
    try:
        return canvas.place(top, bottom, dest, pieces_dir=pieces_dir, rotations=rotations, sheet_rotation=sheet_rotation)
    finally:
        canvas.close()


def recompose_pair(
    pieces_dir: Path,
    dest: Path,
    rotations: tuple[int, int] = (0, 0),
    sheet_rotation: int = 0,
) -> list[dict[str, float]]:
    """Rebuild a Citizenship sheet from its saved piece PDFs with updated piece/sheet rotations."""
    top = Piece(pieces_dir / "piece-0.pdf", image=False)
    bottom = Piece(pieces_dir / "piece-1.pdf", image=False)
    return compose_pair(top, bottom, dest, rotations=rotations, sheet_rotation=sheet_rotation)


class _Canvas:
    def __init__(self) -> None:
        self._readers: list[PdfReader] = []
        self._buffers: list[io.BytesIO] = []
        self._writer: PdfWriter | None = None

    def place(
        self,
        top: Piece,
        bottom: Piece,
        dest: Path,
        *,
        pieces_dir: Path | None = None,
        rotations: tuple[int, int] = (0, 0),
        sheet_rotation: int = 0,
    ) -> list[dict[str, float]]:
        self._writer = PdfWriter()
        first, second = self._page(top), self._page(bottom)
        if pieces_dir is not None:
            _save_piece(first, pieces_dir / "piece-0.pdf")
            _save_piece(second, pieces_dir / "piece-1.pdf")
        first_rot = upright_page(first, self._writer, rotations[0])
        second_rot = upright_page(second, self._writer, rotations[1])
        first_size, second_size = _size(first_rot), _size(second_rot)
        above, below = _frames(first_size, second_size)
        sheet = self._writer.add_blank_page(width=A4_WIDTH, height=A4_HEIGHT)
        _stamp(sheet, first_rot, above)
        _stamp(sheet, second_rot, below)
        _keep_a4(sheet)
        clip_sheet(sheet)
        writer = self._writer
        if sheet_rotation % 360:
            writer = PdfWriter()
            turned = upright_page(sheet, writer, sheet_rotation)
            center_on_a4(writer, turned, 1.0)
        _save(writer, dest)
        raw_boxes = [_norm_box(above, first_size), _norm_box(below, second_size)]
        return [rotate_box(box, sheet_rotation, A4_WIDTH / A4_HEIGHT) for box in raw_boxes]

    def close(self) -> None:
        for reader in self._readers:
            closer = getattr(reader, "close", None)
            if closer:
                closer()
        for buffer in self._buffers:
            buffer.close()
        self._readers.clear()
        self._buffers.clear()

    def _page(self, piece: Piece):
        if piece.image:
            return self._embed(load_rgb(piece.path))
        return self._from_pdf(piece.path)

    def _from_pdf(self, path: Path):
        reader = self._open(path)
        if len(reader.pages) != 1:
            raise UserError(citizenship_pages())
        page = _upright(reader.pages[0], self._writer)
        photo = _largest_photo(page)
        if photo is None:
            return page
        return self._embed(photo)

    def _open(self, path: Path) -> PdfReader:
        try:
            reader = PdfReader(str(path), strict=False)
        except Exception:
            raise UserError(damaged()) from None
        self._readers.append(reader)
        if reader.is_encrypted and not _unlock(reader):
            raise UserError(pdf_locked())
        return reader

    def _embed(self, image: Image.Image):
        # The picture becomes its own little page, then that page is scaled into its place on the sheet.
        rgb = image if image.mode == "RGB" else rgb_image(image)
        if rgb is not image:
            image.close()
        try:
            rgb.thumbnail(_MAX_PX, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            rgb.save(buffer, "PDF", resolution=_DPI)
            buffer.seek(0)
        except Exception:
            raise UserError(citizenship_failed()) from None
        finally:
            rgb.close()
        self._buffers.append(buffer)
        reader = PdfReader(buffer)
        self._readers.append(reader)
        return reader.pages[0]


def _largest_photo(page) -> Image.Image | None:
    try:
        found = [item for item in page.images if item.image is not None]
    except Exception:
        return None
    shown = [item for item in found if item.is_displayed] or found
    best, area = None, 0
    for item in shown:
        image = item.image
        if image.width < _MIN_PHOTO or image.height < _MIN_PHOTO:
            continue
        pixels = image.width * image.height
        if pixels > area:
            best, area = image, pixels
    if best is None:
        return None
    try:
        return rgb_image(best)
    except Exception:
        return None


def _unlock(reader: PdfReader) -> bool:
    try:
        return int(reader.decrypt("")) != 0
    except Exception:
        return False


def _upright(page, writer: PdfWriter | None):
    if int(page.rotation or 0) % 360 == 0 or writer is None:
        return page
    clone = page.clone(writer)
    clone.transfer_rotation_to_content()
    return clone


def _size(page) -> tuple[float, float]:
    box = page.mediabox
    return max(float(box.width), 1.0), max(float(box.height), 1.0)


def _frames(top: tuple[float, float], bottom: tuple[float, float]):
    head, side, gap, foot = _TOP_MM * _MM, _SIDE_MM * _MM, _GAP_MM * _MM, _BOTTOM_MM * _MM
    width = A4_WIDTH - 2 * side
    height = (A4_HEIGHT - head - gap - foot) / 2
    top_size, top_scale = _fit(top, width, height)
    bottom_size, bottom_scale = _fit(bottom, width, height)
    top_y = A4_HEIGHT - head - top_size[1]
    bottom_y = top_y - gap - bottom_size[1]
    return (side + (width - top_size[0]) / 2, top_y, top_scale), (side + (width - bottom_size[0]) / 2, bottom_y, bottom_scale)


def _fit(size: tuple[float, float], max_w: float, max_h: float) -> tuple[tuple[float, float], float]:
    scale = min(max_w / size[0], max_h / size[1])
    return (size[0] * scale, size[1] * scale), scale


def _norm_box(frame: tuple[float, float, float], size: tuple[float, float]) -> dict[str, float]:
    x, y, scale = frame
    w_pt, h_pt = size[0] * scale, size[1] * scale
    return {
        "x": round(x / A4_WIDTH, 6),
        "y": round((A4_HEIGHT - (y + h_pt)) / A4_HEIGHT, 6),
        "w": round(w_pt / A4_WIDTH, 6),
        "h": round(h_pt / A4_HEIGHT, 6),
    }


def _stamp(sheet, page, frame: tuple[float, float, float]) -> None:
    x, y, scale = frame
    box = page.mediabox
    left, bottom = float(box.left), float(box.bottom)
    shift = Transformation().scale(scale).translate(x - left * scale, y - bottom * scale)
    sheet.merge_transformed_page(page, shift, expand=False)


def _keep_a4(page) -> None:
    page.mediabox = RectangleObject((0, 0, A4_WIDTH, A4_HEIGHT))
    page.cropbox = RectangleObject((0, 0, A4_WIDTH, A4_HEIGHT))


def _save_piece(page, dest: Path) -> None:
    writer = PdfWriter()
    writer.add_page(page)
    _save(writer, dest)


def _save(writer: PdfWriter, dest: Path) -> None:
    temporary = dest.with_name(dest.name + ".partial")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("wb") as handle:
            writer.write(handle)
        replace(temporary, dest)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
