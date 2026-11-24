"""Make sure the real shop is up before the counter asks it for files."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from printo.preview.serve import _shop_port

_HOST = "127.0.0.1"
_ROOT = Path(__file__).resolve().parents[3]
_WAIT_SECONDS = 30


@dataclass
class ShopSession:
    port: int
    _process: subprocess.Popen[str] | None

    @property
    def spawned(self) -> bool:
        return self._process is not None

    def close(self) -> None:
        if self._process is None:
            return
        process, self._process = self._process, None
        _stop(process)


def ensure_shop() -> ShopSession:
    port = _shop_port()
    if live_shop(port):
        return ShopSession(port, None)
    if _port_open(port):
        raise SystemExit(f"Port {port} is already taken, but printO is not answering there.")
    process, notes, reader = _spawn(port)
    try:
        ready = _wait_live(port, process)
    except KeyboardInterrupt:
        _stop(process)
        reader.join(timeout=1)
        raise SystemExit(0) from None
    if ready:
        return ShopSession(port, process)
    _stop(process)
    reader.join(timeout=1)
    raise SystemExit(_reason(notes))


def live_shop(port: int) -> bool:
    body = _health(port)
    return body is not None and body.get("ok") is True and body.get("preview") is not True


def _health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{_HOST}:{port}/admin/health", timeout=1) as response:
            return json.loads(response.read().decode())
    except (OSError, ValueError, urllib.error.URLError):
        return None


def _port_open(port: int) -> bool:
    try:
        socket.create_connection((_HOST, port), 0.4).close()
        return True
    except OSError:
        return False


def _wait_live(port: int, process: subprocess.Popen[str]) -> bool:
    deadline = time.monotonic() + _WAIT_SECONDS
    while time.monotonic() < deadline:
        if live_shop(port):
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.25)
    return False


def _spawn(port: int) -> tuple[subprocess.Popen[str], list[str], threading.Thread]:
    binary = _ROOT / ".venv" / "bin" / "printo"
    command = [str(binary)] if binary.is_file() else [sys.executable, "-m", "printo"]
    env = os.environ.copy()
    src = _ROOT / "src"
    env["PYTHONPATH"] = f"{src}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(src)
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PRINTO_PORT", str(port))
    notes: list[str] = []
    # Its own session, so this window's close key reaches the counter, not printO.
    # The counter asks printO to stop once the person is done.
    process = subprocess.Popen(
        command, cwd=_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    reader = threading.Thread(target=_collect, args=(process, notes), name="printo-notes", daemon=True)
    reader.start()
    return process, notes, reader


def _collect(process: subprocess.Popen[str], notes: list[str]) -> None:
    stream = process.stderr
    if stream is None:
        return
    for line in stream:
        text = line.strip()
        if text:
            notes.append(text)


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _reap(process)


def _reap(process: subprocess.Popen[str]) -> None:
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return


def _reason(notes: list[str]) -> str:
    # Skip a traceback frame and keep the sentence a person can act on.
    for line in reversed(notes):
        if line.startswith("Traceback") or line.startswith("File ") or line.startswith("raise "):
            continue
        return line
    return "printO stopped before the counter could open."