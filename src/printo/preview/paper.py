"""A small black-on-white PDF, so the counter has a page to show. Nothing here is sent to a printer."""

import threading

_lock = threading.Lock()
_cache: dict[int, bytes] = {}


def sheet(page_count: int) -> bytes:
    count = max(1, min(int(page_count or 1), 8))
    with _lock:
        found = _cache.get(count)
        if found is None:
            found = _build(count)
            _cache[count] = found
        return found


def _build(count: int) -> bytes:
    page_ids = [4 + index * 2 for index in range(count)]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    chunks = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {count} /Kids [{kids}] >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>",
    ]
    for number, page_id in enumerate(page_ids, start=1):
        chunks.append(_page(page_id + 1))
        chunks.append(_text(f"Page {number} of {count}"))
    return _wrap(chunks)


def _page(content_id: int) -> bytes:
    return (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
    ).encode()


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
