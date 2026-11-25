"""A small black-on-white PDF, so the counter has a page to show. Nothing here is sent to a printer."""

import threading

from printo.domain.rotate import rotate_box

_A4_W = 595.2756
_A4_H = 841.8898
_MM = 72 / 25.4
_TOP_MM, _SIDE_MM, _GAP_MM, _BOTTOM_MM = 16, 14, 12, 16
_lock = threading.Lock()
_cache: dict[tuple[int, int], bytes] = {}


def sheet(page_count: int, rotate: int = 0) -> bytes:
    count = max(1, min(int(page_count or 1), 8))
    angle = int(rotate or 0) % 360
    with _lock:
        found = _cache.get((count, angle))
        if found is None:
            found = _build(count, angle)
            _cache[(count, angle)] = found
        return found


def pair_sheet(rotations: tuple[int, int] = (0, 0), sheet_rotation: int = 0) -> tuple[bytes, list[dict[str, float]]]:
    """Build a pure-stdlib sample Citizenship PDF with two orientable vector cards."""
    r0, r1 = int(rotations[0]) % 360, int(rotations[1]) % 360
    rs = int(sheet_rotation) % 360
    s0 = (320.0, 210.0) if r0 in (0, 180) else (210.0, 320.0)
    s1 = (320.0, 210.0) if r1 in (0, 180) else (210.0, 320.0)
    above, below = _frames(s0, s1)
    stream = _card_ops(above, r0, "Front") + b"\n" + _card_ops(below, r1, "Back")
    chunks = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [4 0 R] >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>",
        _page(5, rs),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    raw_boxes = [_norm_box(above), _norm_box(below)]
    boxes = [rotate_box(box, rs, _A4_W / _A4_H) for box in raw_boxes]
    return _wrap(chunks), boxes


def _build(count: int, rotate: int = 0) -> bytes:
    page_ids = [4 + index * 2 for index in range(count)]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    chunks = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {count} /Kids [{kids}] >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>",
    ]
    for number, page_id in enumerate(page_ids, start=1):
        chunks.append(_page(page_id + 1, rotate))
        chunks.append(_text(f"Page {number} of {count}"))
    return _wrap(chunks)


def _page(content_id: int, rotate: int = 0) -> bytes:
    rot = f" /Rotate {rotate}" if rotate % 360 else ""
    return (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]{rot} "
        f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
    ).encode()


def _frames(top: tuple[float, float], bottom: tuple[float, float]):
    head, side, gap, foot = _TOP_MM * _MM, _SIDE_MM * _MM, _GAP_MM * _MM, _BOTTOM_MM * _MM
    width = _A4_W - 2 * side
    height = (_A4_H - head - gap - foot) / 2
    top_w, top_h = _fit(top, width, height)
    bot_w, bot_h = _fit(bottom, width, height)
    top_y = _A4_H - head - top_h
    bot_y = top_y - gap - bot_h
    return (side + (width - top_w) / 2, top_y, top_w, top_h), (side + (width - bot_w) / 2, bot_y, bot_w, bot_h)


def _fit(size: tuple[float, float], max_w: float, max_h: float) -> tuple[float, float]:
    scale = min(max_w / size[0], max_h / size[1])
    return size[0] * scale, size[1] * scale


def _norm_box(frame: tuple[float, float, float, float]) -> dict[str, float]:
    x, y, w, h = frame
    return {"x": round(x / _A4_W, 6), "y": round((_A4_H - (y + h)) / _A4_H, 6), "w": round(w / _A4_W, 6), "h": round(h / _A4_H, 6)}


def _card_ops(frame: tuple[float, float, float, float], angle: int, label: str) -> bytes:
    x, y, w, h = frame
    cx, cy = x + w / 2, y + h / 2
    uw, uh = (h, w) if angle in (90, 270) else (w, h)
    m = {0: "1 0 0 1", 90: "0 -1 1 0", 180: "-1 0 0 -1", 270: "0 1 -1 0"}[angle]
    lines = [
        "q",
        f"{m} {cx:.2f} {cy:.2f} cm",
        "0.93 g",
        f"{-uw / 2:.2f} {-uh / 2:.2f} {uw:.2f} {uh:.2f} re f",
        "0.55 g 1.5 w",
        f"{-uw / 2:.2f} {-uh / 2:.2f} {uw:.2f} {uh:.2f} re S",
        "0.72 g",
        f"{-uw / 2 + 18:.2f} {uh / 2 - 76:.2f} 52 56 re f",
        "0.2 g",
        f"BT /F1 18 Tf {-uw / 2 + 86:.2f} {uh / 2 - 42:.2f} Td ({label}) Tj ET",
        "Q",
    ]
    return "\n".join(lines).encode("latin-1")


def _text(line: str) -> bytes:
    stream = b"BT /F1 22 Tf 64 760 Td (" + _literal(line) + b") Tj ET"
    return b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"


def _literal(text: str) -> bytes:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")


def _wrap(chunks: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(chunks, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(chunks) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer << /Size {len(chunks) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(out)
