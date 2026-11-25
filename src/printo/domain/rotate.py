"""Clockwise rotation helpers for pages, images, and citizenship card slots."""

from printo.errors import UserError
from printo.messages import validation

VALID_ANGLES = frozenset({0, 90, 180, 270})


def parse_angle(value: object) -> int:
    """Validate an exact quarter-turn clockwise angle."""
    if isinstance(value, bool) or not isinstance(value, int) or value not in VALID_ANGLES:
        raise UserError(validation())
    return value


def parse_rotations(value: object, page_count: int) -> dict[int, int]:
    """Parse 1-based {page: angle} payload into 0-based {index: angle}."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise UserError(validation())
    out: dict[int, int] = {}
    for raw_page, raw_angle in value.items():
        page = _parse_page(raw_page, page_count)
        angle = parse_angle(raw_angle)
        if angle:
            out[page - 1] = angle
    return out


def rotate_box(box: dict[str, float], sheet_angle: int, aspect: float) -> dict[str, float]:
    """Transform a normalized top-left [x, y, w, h] box when the A4 sheet rotates clockwise."""
    angle = parse_angle(sheet_angle)
    x, y, w, h = float(box["x"]), float(box["y"]), float(box["w"]), float(box["h"])
    if angle == 0:
        return {"x": x, "y": y, "w": w, "h": h}
    if angle == 180:
        return {"x": 1.0 - x - w, "y": 1.0 - y - h, "w": w, "h": h}
    h_frac = aspect * aspect
    margin = (1.0 - h_frac) / 2.0
    if angle == 90:
        return {"x": 1.0 - (y + h), "y": margin + h_frac * x, "w": h, "h": h_frac * w}
    return {"x": y, "y": margin + h_frac * (1.0 - (x + w)), "w": h, "h": h_frac * w}


def _parse_page(raw: object, page_count: int) -> int:
    if isinstance(raw, bool):
        raise UserError(validation())
    try:
        page = int(raw) if isinstance(raw, (int, str)) else 0
    except ValueError:
        raise UserError(validation()) from None
    if page < 1 or page > page_count:
        raise UserError(validation())
    return page
