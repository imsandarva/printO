"""Ctrl+C has to close the shop even while a phone still has the page open."""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def test_ctrl_c_closes_the_shop_while_a_phone_is_connected(tmp_path):
    port = _free_port()
    env = os.environ.copy()
    env.update(PRINTO_PORT=str(port), PRINTO_DATA_DIR=str(tmp_path / "data"), PRINTO_PUBLIC_PORT="80", PYTHONUNBUFFERED="1")
    err = tmp_path / "err"
    proc = subprocess.Popen(
        [sys.executable, "-m", "printo"], cwd=tmp_path, env=env,
        stdout=subprocess.DEVNULL, stderr=err.open("wb"),
    )
    held = None
    try:
        _wait_until_listening(port, proc, err)
        held = socket.create_connection(("127.0.0.1", port))
        held.sendall(b"GET /admin/events HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        time.sleep(0.3)
        proc.send_signal(signal.SIGINT)
        code = proc.wait(timeout=8)
    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
        raise
    finally:
        if held is not None:
            held.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
    assert code is not None
    assert proc.poll() is not None


def _wait_until_listening(port: int, proc: subprocess.Popen, err: Path) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(err.read_text(encoding="utf-8", errors="replace")[-800:])
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    if proc.poll() is None:
        proc.kill()
    raise AssertionError("the shop did not start\n" + err.read_text(encoding="utf-8", errors="replace")[-800:])


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port
