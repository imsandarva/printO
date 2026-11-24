"""Listen for the person to close this window.

Typing off, and asking the window to close, both use the same stop. The process
then finishes and leaves. It must not die on the spot: that is what makes Ubuntu
offer to send a crash report.
"""

import signal
import sys
import threading
from collections.abc import Callable
from typing import TextIO

_WORD = "off"
_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def wants_close(line: str) -> bool:
    return line.strip().casefold() == _WORD


class Console:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdin
        self._on_close: Callable[[], None] = lambda: None
        self._fired = False

    def start(self, on_close: Callable[[], None], *, signals: bool = True) -> None:
        self._on_close = on_close
        if signals:
            listen_for_stop(self.ask)
        threading.Thread(target=self._read, name="close-word", daemon=True).start()

    def ask(self) -> None:
        if self._fired:
            return
        self._fired = True
        self._on_close()

    def _read(self) -> None:
        hint = _can_hint(self._stream)
        try:
            while not self._fired:
                line = self._stream.readline()
                if line == "":
                    return
                if wants_close(line):
                    self.ask()
                    return
                if hint and line.strip():
                    say_how()
        except (OSError, ValueError):
            return


def listen_for_stop(on_stop: Callable[[], None]) -> None:
    if threading.current_thread() is not threading.main_thread():
        return

    def handler(_sig: int, _frame: object) -> None:
        on_stop()
    for sig in _SIGNALS:
        signal.signal(sig, handler)


def ignore_stop_signals() -> None:
    """Leave cleanup alone. A second press must not cut it off halfway."""
    if threading.current_thread() is not threading.main_thread():
        return
    for sig in _SIGNALS:
        signal.signal(sig, signal.SIG_IGN)


def say_how() -> None:
    print("Type off to close it.", flush=True)


def _can_hint(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (OSError, ValueError):
        return False
