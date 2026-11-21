"""Decide whether to keep waiting on a printer job. Pure, so it can be tested without CUPS."""


def interpret(outcome: str, elapsed: float, give_up: float, missing_grace: float) -> str | None:
    """Return ``done``, ``failed``, or None to keep waiting.

    ``completed`` means CUPS finished sending the job. It does not mean paper came out.
    """
    if outcome == "completed":
        return "done"
    if outcome == "aborted":
        return "failed"
    if outcome in {"active", "unknown"}:
        return "failed" if elapsed >= give_up else None
    if elapsed >= missing_grace:
        return "failed"
    return None
