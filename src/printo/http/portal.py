"""A phone that just joined asks a known site if the internet is there.

Sending it to our page is what makes the phone open it. Answering the way the
real site would — "yes, you're online" — is what makes the phone show nothing.
"""

from fastapi import Request
from fastapi.responses import RedirectResponse

from printo.config import Settings


def to_portal(request: Request) -> RedirectResponse:
    response = RedirectResponse(portal_target(request), status_code=302)
    response.headers["Cache-Control"] = "no-store"
    return response


def portal_target(request: Request) -> str:
    host = _host(request)
    port = _port(request, request.app.state.ctx.settings)
    if port == 80:
        return f"http://{host}/"
    return f"http://{host}:{port}/"


def _host(request: Request) -> str:
    server = request.scope.get("server") or ("", 0)
    host = str(server[0]) if server else ""
    if host.startswith("::ffff:"):
        host = host[7:]
    if host in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _port(request: Request, settings: Settings) -> int:
    if settings.public_port:
        return settings.public_port
    server = request.scope.get("server") or ("", 80)
    try:
        return int(server[1])
    except (TypeError, ValueError, IndexError):
        return 80
