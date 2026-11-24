"""Run the counter on this computer only. The shop, the printer, and wifi stay as they are."""

import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from printo.preview.feed import Hub
from printo.preview.files import watched
from printo.preview.http import Handler
from printo.preview.proxy import ProxyDesk
from printo.preview.scene import Scene
from printo.preview.watch import watch

HOST = "127.0.0.1"
# Two above the shop's port, so this never takes the address the shop is using.
_SHOP_PORT = 8088


class PreviewServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], desk: Scene | ProxyDesk, hub: Hub) -> None:
        self.desk = desk
        self.hub = hub
        super().__init__(address, Handler)


class Preview:
    def __init__(self, server: PreviewServer, stop: threading.Event, watcher: threading.Thread) -> None:
        self.server = server
        self.url = counter_url(server.server_address[1])
        self._stop = stop
        self._watcher = watcher
        self._closed = False

    def wait(self) -> None:
        try:
            self._stop.wait()
        except KeyboardInterrupt:
            return

    def request_close(self) -> None:
        self._stop.set()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self.server.desk.close()
        self.server.shutdown()
        self.server.server_close()
        self._watcher.join(timeout=1)


def start(port: int = 0, delay: float = 0.9, *, sample: bool = False, shop_port: int | None = None) -> Preview:
    stop = threading.Event()
    hub = Hub()
    desk: Scene | ProxyDesk = Scene(hub.publish, delay=delay) if sample else ProxyDesk(_need_shop_port(shop_port))
    server = PreviewServer((HOST, port), desk, hub)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, name="counter-preview", daemon=True).start()
    watcher = threading.Thread(target=_watch, args=(hub, stop), name="counter-watch", daemon=True)
    watcher.start()
    return Preview(server, stop, watcher)


def listen_port() -> int:
    port = _shop_port() + 2
    return port if port < 65536 else _SHOP_PORT + 2


def counter_url(port: int) -> str:
    return f"http://{HOST}:{port}/admin/"


def _shop_port() -> int:
    # The same two places scripts/common.sh looks, so a custom shop port is left alone.
    env = os.environ.get("PRINTO_PORT", "").strip()
    if env.isdigit():
        return _usable(int(env))
    found = _toml_port(Path("printo.toml"))
    return found if found is not None else _SHOP_PORT


def _toml_port(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() == "port":
            digits = "".join(ch for ch in value if ch.isdigit())
            return _usable(int(digits)) if digits else None
    return None


def _usable(port: int) -> int:
    return port if 0 < port < 65536 else _SHOP_PORT


def already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"{counter_url(port)}health", timeout=0.4) as response:
            body = json.loads(response.read().decode())
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return body.get("preview") is True


def _need_shop_port(shop_port: int | None) -> int:
    if shop_port is None:
        raise ValueError("shop_port is required unless sample is true")
    return shop_port


def _watch(hub: Hub, stop: threading.Event) -> None:
    watch(watched(), lambda names: hub.publish("reload", {"files": names}), stop)
