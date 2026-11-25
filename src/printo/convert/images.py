"""Place a photo on a white A4 page. Phone pictures are rotated from their EXIF tag first."""

from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from printo.convert.pdf_doc import Prepared, page_count
from printo.errors import UserError
from printo.messages import damaged, too_many_pages
from printo.storage.atomic import replace

# Registered once so HEIC photos from phones open through the normal image reader.
register_heif_opener()

# 150 dpi is enough for this laser and far lighter than 300 dpi on a small laptop.
_DPI = 150
_A4_MM = (210, 297)
_MARGIN_MM = 10
# A scan can be many sheets. A photo cannot: later frames are an HDR gain map, depth, or thumbnail.
_STACKED = "TIFF"
_CW_ROTATE = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


def load_rgb(source: Path) -> Image.Image:
    """One upright RGB photo. The caller closes it."""
    try:
        with Image.open(source) as image:
            return rgb_image(ImageOps.exif_transpose(image) or image)
    except Exception:
        raise UserError(damaged()) from None


def rgb_image(image: Image.Image) -> Image.Image:
    return _rgb(image)


def prepare_image(source: Path, dest: Path, max_sheets: int) -> Prepared:
    frames = _frames(source, max_sheets)
    dest.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(dest, "PDF", resolution=_DPI, save_all=True, append_images=frames[1:])
    _close(frames)
    return Prepared(page_count(dest, max_sheets))


def rotate_image(source: Path, dest: Path, angle: int) -> None:
    """Re-render a single photo rotated clockwise by 0/90/180/270 onto a fresh A4 PDF."""
    rgb = load_rgb(source)
    try:
        turned = _turn_cw(rgb, angle)
    finally:
        rgb.close()
    page = _place_on_a4(turned)
    temporary = dest.with_name(dest.name + ".partial")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        page.save(temporary, "PDF", resolution=_DPI)
        replace(temporary, dest)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        page.close()


def _sheet_count(image: Image.Image) -> int:
    if image.format == _STACKED:
        return int(getattr(image, "n_frames", 1))
    return 1


def _frames(source: Path, max_sheets: int) -> list[Image.Image]:
    frames: list[Image.Image] = []
    try:
        with Image.open(source) as image:
            count = _sheet_count(image)
            if count > max_sheets:
                raise UserError(too_many_pages())
            for index in range(count):
                image.seek(index)
                frames.append(_on_a4(image))
    except UserError:
        _close(frames)
        raise
    except Exception:
        _close(frames)
        raise UserError(damaged()) from None
    if not frames:
        raise UserError(damaged())
    return frames


def _on_a4(image: Image.Image) -> Image.Image:
    return _place_on_a4(_rgb(ImageOps.exif_transpose(image) or image))


def _place_on_a4(rgb: Image.Image) -> Image.Image:
    page = _page()
    margin = _px(_MARGIN_MM)
    width, height = page.size[0] - 2 * margin, page.size[1] - 2 * margin
    try:
        rgb.thumbnail((width, height), Image.Resampling.LANCZOS)
        page.paste(rgb, ((page.size[0] - rgb.size[0]) // 2, (page.size[1] - rgb.size[1]) // 2))
    finally:
        rgb.close()
    return page


def _turn_cw(image: Image.Image, angle: int) -> Image.Image:
    op = _CW_ROTATE.get(angle % 360)
    return image.transpose(op) if op is not None else image.copy()


def _rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image.copy()
    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        return background
    return image.convert("RGB")


def _page() -> Image.Image:
    return Image.new("RGB", (_px(_A4_MM[0]), _px(_A4_MM[1])), "white")


def _px(mm: float) -> int:
    return max(1, round(mm / 25.4 * _DPI))


def _close(frames: list[Image.Image]) -> None:
    for frame in frames:
        frame.close()
