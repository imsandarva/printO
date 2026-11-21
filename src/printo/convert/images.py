"""Place a photo on a white A4 page. Phone pictures are rotated from their EXIF tag first."""

from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from printo.convert.pdf_doc import Prepared, page_count
from printo.errors import UserError
from printo.messages import damaged, too_many_pages

# Registered once so HEIC photos from phones open through the normal image reader.
register_heif_opener()

# 150 dpi is enough for this laser and far lighter than 300 dpi on a small laptop.
_DPI = 150
_A4_MM = (210, 297)
_MARGIN_MM = 10


def prepare_image(source: Path, dest: Path, max_sheets: int) -> Prepared:
    frames = _frames(source, max_sheets)
    dest.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(dest, "PDF", resolution=_DPI, save_all=True, append_images=frames[1:])
    for frame in frames:
        frame.close()
    return Prepared(page_count(dest, max_sheets))


def _frames(source: Path, max_sheets: int) -> list[Image.Image]:
    frames: list[Image.Image] = []
    try:
        with Image.open(source) as image:
            # An animation is one frame. Printing every frame would waste a stack of paper.
            count = 1 if image.format == "GIF" else int(getattr(image, "n_frames", 1))
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
    rgb = _rgb(ImageOps.exif_transpose(image) or image)
    page = _page()
    margin = _px(_MARGIN_MM)
    width, height = page.size[0] - 2 * margin, page.size[1] - 2 * margin
    rgb.thumbnail((width, height), Image.Resampling.LANCZOS)
    page.paste(rgb, ((page.size[0] - rgb.size[0]) // 2, (page.size[1] - rgb.size[1]) // 2))
    rgb.close()
    return page


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
