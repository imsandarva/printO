"""The counter's real files. They are read from disk on each request, so a save is what you see."""

from pathlib import Path

_WEB = Path(__file__).resolve().parents[1] / "web"
_PAGE = _WEB / "counter" / "index.html"
# Kept in step with the counter page in http/pages.py. The hook below is served only here.
_PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; "
        "connect-src 'self'; img-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'"
    ),
}
_ASSET_HEADERS = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
_ASSETS = {
    "/admin/c/counter.css": (_WEB / "counter" / "app.css", "text/css; charset=utf-8"),
    "/admin/c/counter.js": (_WEB / "counter" / "app.js", "text/javascript; charset=utf-8"),
    "/c/common.css": (_WEB / "common.css", "text/css; charset=utf-8"),
    "/favicon.svg": (_WEB / "mark.svg", "image/svg+xml"),
    "/favicon.ico": (_WEB / "mark.svg", "image/svg+xml"),
}
# Not a file in the counter folder, so the shop never serves it and never reloads itself.
_HOOK = b'<script src="/admin/c/preview.js"></script>'
_PREVIEW_JS = b"""\
const source = new EventSource("/admin/events");
source.addEventListener("reload", (event) => {
  let files = [];
  try { files = JSON.parse(event.data).files || []; } catch (error) { files = []; }
  if (files.length && files.every((name) => name.endsWith(".css"))) { restyle(); return; }
  location.reload();
});
function restyle() {
  document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
    const next = new URL(link.href, location.href);
    next.searchParams.set("v", String(Date.now()));
    link.href = next.href;
  });
}
"""


def watched() -> list[Path]:
    return [_PAGE, _WEB / "counter" / "app.css", _WEB / "counter" / "app.js", _WEB / "common.css", _WEB / "mark.svg"]


def page_headers() -> dict[str, str]:
    return dict(_PAGE_HEADERS)


def asset_headers() -> dict[str, str]:
    return dict(_ASSET_HEADERS)


def counter_page() -> bytes | None:
    raw = _read(_PAGE)
    if raw is None or b"/admin/c/preview.js" in raw:
        return raw
    needle = b"</body>"
    if needle in raw:
        return raw.replace(needle, _HOOK + b"\n" + needle, 1)
    return raw + _HOOK


def asset(path: str) -> tuple[bytes, str] | None:
    if path == "/admin/c/preview.js":
        return _PREVIEW_JS, "text/javascript; charset=utf-8"
    found = _ASSETS.get(path)
    if found is None:
        return None
    file, media = found
    raw = _read(file)
    if raw is None:
        return None
    return raw, media


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None
