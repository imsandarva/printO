"""The address of the customer page, drawn so a phone can scan it here.

Joining the wifi does not open the page. The person scans this, or types the address.
"""

import shutil
import sys
from typing import TextIO

import segno

_QUIET = 4
_RESET = "\033[0m"
_FG_DARK = "\033[38;2;0;0;0m"
_FG_LIGHT = "\033[38;2;255;255;255m"
_BG_DARK = "\033[48;2;0;0;0m"
_BG_LIGHT = "\033[48;2;255;255;255m"
_BLOCK = "▀"


def customer_url(ip: str, port: int) -> str:
    host = f"[{ip}]" if ":" in ip and not ip.startswith("[") else ip
    number = int(port)
    if number == 80:
        return f"http://{host}/"
    return f"http://{host}:{number}/"


def show(url: str, out: TextIO | None = None, *, force: bool = False) -> bool:
    target = out or sys.stdout
    rows = _rows(url)
    if not force and not _fits(target, len(rows[0])):
        return False
    target.write(_picture(rows))
    target.flush()
    return True


def _rows(url: str) -> list[list[bool]]:
    # High error correction: a photo of a screen loses a few squares and should still read.
    code = segno.make(url, error="h")
    rows = [[cell == 1 for cell in row] for row in code.matrix_iter(scale=1, border=_QUIET)]
    if len(rows) % 2:
        rows.append([False] * len(rows[0]))
    return rows


def _picture(rows: list[list[bool]]) -> str:
    # Two rows share one character, so a module stays about square. Colors are real black and white,
    # because a dark window would otherwise paint the code in its own colors and a phone could not read it.
    return "\n".join(_line(top, bottom) for top, bottom in zip(rows[0::2], rows[1::2])) + "\n"


def _line(top: list[bool], bottom: list[bool]) -> str:
    return _RESET + "".join(_cell(above, below) for above, below in zip(top, bottom)) + _RESET


def _cell(above: bool, below: bool) -> str:
    fg = _FG_DARK if above else _FG_LIGHT
    bg = _BG_DARK if below else _BG_LIGHT
    return f"{fg}{bg}{_BLOCK}"


def _fits(out: TextIO, width: int) -> bool:
    if not getattr(out, "isatty", lambda: False)():
        return False
    return shutil.get_terminal_size(fallback=(0, 0)).columns >= width
