"""The code in the shop window is the customer page, in black on white."""

import io
import os
import re

import segno

from printo.link import customer_url, show

_CELL = re.compile(r"\033\[38;2;(\d+);(\d+);(\d+)m\033\[48;2;(\d+);(\d+);(\d+)m▀")


def test_the_address_is_the_customer_page():
    assert customer_url("10.42.0.1", 8088) == "http://10.42.0.1:8088/"
    assert customer_url("10.42.0.1", 80) == "http://10.42.0.1/"
    assert customer_url("fe80::1", 8088) == "http://[fe80::1]:8088/"


def test_the_code_is_the_page_with_a_white_margin():
    url = customer_url("10.42.0.1", 8088)
    buf = io.StringIO()
    assert show(url, buf, force=True) is True
    drawn = _read(buf.getvalue())
    expect = _matrix(url)
    assert drawn == expect
    assert drawn[0][0] is False
    assert drawn[4][4] is True


def test_a_log_does_not_get_the_picture():
    buf = io.StringIO()
    assert show("http://10.42.0.1:8088/", buf) is False
    assert buf.getvalue() == ""


def test_a_narrow_window_skips_the_picture(monkeypatch):
    monkeypatch.setattr("printo.link.shutil.get_terminal_size", lambda fallback=(0, 0): os.terminal_size((10, 24)))
    buf = io.StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    assert show("http://10.42.0.1:8088/", buf) is False
    assert buf.getvalue() == ""


def _matrix(url: str) -> list[list[bool]]:
    code = segno.make(url, error="h")
    rows = [[cell == 1 for cell in row] for row in code.matrix_iter(scale=1, border=4)]
    if len(rows) % 2:
        rows.append([False] * len(rows[0]))
    return rows


def _read(picture: str) -> list[list[bool]]:
    found: list[list[bool]] = []
    for line in picture.splitlines():
        cells = _CELL.findall(line)
        assert cells, line
        top, bottom = [], []
        for fr, fg, fb, br, bg, bb in cells:
            top.append((fr, fg, fb) == ("0", "0", "0"))
            bottom.append((br, bg, bb) == ("0", "0", "0"))
        found.append(top)
        found.append(bottom)
    return found
