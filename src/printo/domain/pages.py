"""Turn a page request like ``1-3, 5`` into zero-based page indexes, in the order to print."""

from printo.domain.layout import sheet_count
from printo.errors import UserError
from printo.messages import bad_copies, bad_pages, too_many_sheets


def selection(spec: str, page_count: int, copies: int, max_copies: int, max_sheets: int, landscape: bool = False) -> list[int]:
    copies = _copies(copies, max_copies)
    indexes = parse_pages(spec, page_count)
    # Landscape prints two chosen pages on each sheet, so the limit counts those sheets.
    units = sheet_count(len(indexes)) if landscape else len(indexes)
    if units * copies > max_sheets:
        raise UserError(too_many_sheets())
    return indexes


def parse_pages(spec: str, page_count: int) -> list[int]:
    if not isinstance(spec, str) or len(spec) > 4000:
        raise UserError(bad_pages(page_count))
    text = spec.strip().lower()
    if text in {"", "all"}:
        return list(range(page_count)) if page_count > 0 else _bad(page_count)
    # Named sets stay short on the wire. The counter offers these beside a single from–to range.
    if text in {"odd", "even"}:
        return _half(text, page_count)
    indexes: list[int] = []
    for token in text.split(","):
        indexes.extend(_span(token.strip(), page_count))
    if not indexes:
        _bad(page_count)
    return indexes


def _half(text: str, page_count: int) -> list[int]:
    if page_count < 1:
        return _bad(page_count)
    odd = text == "odd"
    indexes = [index for index in range(page_count) if ((index + 1) % 2 == 1) is odd]
    return indexes or _bad(page_count)


def _copies(copies: int, max_copies: int) -> int:
    if isinstance(copies, bool) or not isinstance(copies, int) or copies < 1 or copies > max_copies:
        raise UserError(bad_copies(max_copies))
    return copies


def _span(token: str, page_count: int) -> range:
    if not token:
        _bad(page_count)
    parts = token.split("-")
    if len(parts) == 1:
        number = _number(parts[0], page_count)
        return range(number - 1, number)
    if len(parts) == 2:
        start, end = _number(parts[0], page_count), _number(parts[1], page_count)
        if start > end:
            _bad(page_count)
        return range(start - 1, end)
    return _bad(page_count)


def _number(raw: str, page_count: int) -> int:
    text = raw.strip()
    if not text.isdigit():
        _bad(page_count)
    value = int(text)
    if value < 1 or value > page_count:
        _bad(page_count)
    return value


def _bad(page_count: int) -> range:
    raise UserError(bad_pages(page_count))

