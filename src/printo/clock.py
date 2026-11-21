"""Time helpers. Tests pass their own clock so cleanup does not depend on the wall clock."""

from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def stamp(moment: datetime) -> str:
    # Microseconds keep two updates in the same second distinct, and ISO order matches time order.
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def after(clock: Clock, hours: float) -> str:
    return stamp(clock.now() + timedelta(hours=hours))
