"""Typing off closes the window. Anything else leaves it up."""

import io
import threading

from printo.console import Console, wants_close


def test_only_the_word_off_counts():
    assert wants_close("off") and wants_close("  OFF\n")
    assert not wants_close("offline") and not wants_close("") and not wants_close("turn off")


def test_console_closes_when_the_word_arrives():
    done = threading.Event()
    Console(io.StringIO("hello\noff\n")).start(done.set, signals=False)
    assert done.wait(timeout=1)


def test_console_stays_open_without_the_word():
    done = threading.Event()
    Console(io.StringIO("hello\n")).start(done.set, signals=False)
    assert not done.wait(timeout=0.2)
