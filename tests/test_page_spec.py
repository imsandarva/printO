"""Page specs the counter can ask for: all, odd, even, or a range."""

import pytest

from printo.domain.pages import parse_pages, selection
from printo.errors import UserError


def test_odd_and_even_pages():
    assert parse_pages("odd", 5) == [0, 2, 4]
    assert parse_pages("even", 5) == [1, 3]
    assert parse_pages("EVEN", 2) == [1]
    assert parse_pages("all", 3) == [0, 1, 2]
    assert parse_pages("2-4", 4) == [1, 2, 3]


def test_landscape_limit_counts_sheets():
    assert selection("all", 5, 2, 100, 6, landscape=True) == [0, 1, 2, 3, 4]
    with pytest.raises(UserError):
        selection("all", 5, 2, 100, 6)
    with pytest.raises(UserError):
        selection("all", 5, 2, 100, 4, landscape=True)


def test_even_needs_a_second_page():
    with pytest.raises(UserError):
        parse_pages("even", 1)
