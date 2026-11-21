"""Admin routes stay on the laptop. A phone on the hotspot is a customer, even if it guesses the address.

Forwarded-for headers are ignored. There is no proxy in front of this process, and trusting one
would let a customer pretend to be the shop.
"""

from fastapi import Request

from printo.config import Settings
from printo.http.respond import fail
from printo.messages import hidden, too_big, validation

_OVERHEAD = 1024 * 1024


def host_of(request: Request) -> str:
    return request.client.host if request.client else ""


def blocked(request: Request, settings: Settings):
    path = request.url.path
    if path == "/admin" or path.startswith("/admin/"):
        if host_of(request) not in settings.admin_hosts:
            return fail(hidden(), 404)
    if request.method == "POST" and path == "/upload":
        return _too_large(request, settings)
    return None


def _too_large(request: Request, settings: Settings):
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        size = int(raw)
    except ValueError:
        return fail(validation(), 400)
    if size > settings.max_upload_bytes + _OVERHEAD:
        return fail(too_big(), 413)
    return None
