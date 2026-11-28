"""How a page sits on the paper. The preview and the printer both follow this.

Portrait is one page on A4, 210 by 297 millimetres.
Landscape puts two chosen pages on A4 turned sideways, 297 by 210 millimetres.
Each page keeps its shape and is centred in its own half, 148.5 by 210.
The size from the counter then scales that whole sheet about its centre.
Anything past the edge of the paper is cut off. A faint line marks the middle.
"""

_MM = 72 / 25.4
A4_WIDTH = 210 * _MM
A4_HEIGHT = 297 * _MM
LANDSCAPE_WIDTH = A4_HEIGHT
LANDSCAPE_HEIGHT = A4_WIDTH
HALF_WIDTH = LANDSCAPE_WIDTH / 2
HALF_HEIGHT = LANDSCAPE_HEIGHT
# The preview hairline is 8% black. The printed line is the same.
RULE_GRAY = 0.92
RULE_WIDTH = 0.4
RULE_INSET = 1.5 * _MM


def sheet_count(pages: int) -> int:
    """How many landscape sheets a list of chosen pages becomes."""
    return (pages + 1) // 2 if pages > 0 else 0


def pairs(indexes: list[int]) -> list[tuple[int, int | None]]:
    """Pair chosen pages in order. The last page of an odd list has an empty half."""
    grouped: list[tuple[int, int | None]] = []
    for start in range(0, len(indexes), 2):
        right = indexes[start + 1] if start + 1 < len(indexes) else None
        grouped.append((indexes[start], right))
    return grouped


def place_in_half(width: float, height: float, left: float, bottom: float, side: int, factor: float) -> tuple[float, float, float]:
    """Scale and translation that centres one page in its half, then scales the sheet about its centre.

    ``side`` 0 is the left half and 1 is the right. ``left`` and ``bottom`` are the page origin.
    The returned translation is the PDF one: x' = scale * x + tx.
    """
    scale0 = min(HALF_WIDTH / width, HALF_HEIGHT / height)
    scale = scale0 * factor
    cell_cx = HALF_WIDTH * side + HALF_WIDTH / 2
    cell_cy = HALF_HEIGHT / 2
    sheet_cx, sheet_cy = LANDSCAPE_WIDTH / 2, LANDSCAPE_HEIGHT / 2
    final_cx = sheet_cx + factor * (cell_cx - sheet_cx)
    final_cy = sheet_cy + factor * (cell_cy - sheet_cy)
    return scale, final_cx - scale * (left + width / 2), final_cy - scale * (bottom + height / 2)
