import pytest

from printo.domain.pages import parse_pages, selection
from printo.errors import UserError


def test_page_specs():
    assert parse_pages("all", 4) == [0, 1, 2, 3]
    assert parse_pages("  ", 2) == [0, 1]
    assert parse_pages("2", 4) == [1]
    assert parse_pages("1-3, 5", 5) == [0, 1, 2, 4]
    assert parse_pages("1,1", 2) == [0, 0]


@pytest.mark.parametrize("spec", ["0", "3-1", "6", "1-", "a", "1-2-3", ","])
def test_bad_pages(spec):
    with pytest.raises(UserError) as caught:
        parse_pages(spec, 5)
    assert "5 pages" in caught.value.message


def test_sheet_budget():
    assert selection("1-2", 4, 2, 20, 400) == [0, 1]
    with pytest.raises(UserError) as caught:
        selection("all", 10, 3, 20, 20)
    assert "too many sheets" in caught.value.message
    with pytest.raises(UserError):
        selection("all", 2, 0, 20, 400)
    with pytest.raises(UserError):
        selection("all", 2, True, 20, 400)  # type: ignore[arg-type]
