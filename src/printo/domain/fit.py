"""How large the page sits on the sheet. 100 is the normal fit. 125 is as large as it goes."""

from printo.errors import UserError
from printo.messages import bad_fit

# 40% is still a clear block. Above 100% the page grows and the sheet cuts off the rest.
MIN_FIT = 40
MAX_FIT = 125


def parse_fit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < MIN_FIT or value > MAX_FIT:
        raise UserError(bad_fit(MIN_FIT, MAX_FIT))
    return value
