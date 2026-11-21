from printo.printing.cups import Cups, CommandResult, job_outcome, parse_job_alerts, parse_printer
from printo.printing.outcome import interpret

_ACTIVE = """MF3010-16               sandarva3      2028544   Thu 26 Mar 2026 07:53:00 PM +0545
	Alerts: printer-stopped
	queued for MF3010
"""
_DONE = """MF3010-15               sandarva3       411648   Wed 23 Apr 2025 09:39:59 AM +0545
	Status: 
	Alerts: processing-to-stop-point
	queued for MF3010
MF3010-2                sandarva3         1024   Wed 23 Apr 2025 09:00:00 AM +0545
	Alerts: job-completed-successfully
	queued for MF3010
"""


def test_job_ids_do_not_partially_match():
    assert job_outcome(_ACTIVE, _DONE, "MF3010-16") == "active"
    assert job_outcome(_ACTIVE, _DONE, "MF3010-1") == "missing"
    assert job_outcome(_ACTIVE, _DONE, "MF3010-15") == "aborted"
    assert job_outcome(_ACTIVE, _DONE, "MF3010-2") == "completed"
    assert "MF3010-15" in parse_job_alerts(_DONE)
    assert "MF3010-1" not in parse_job_alerts(_DONE)


def test_printer_lines():
    off = "printer MF3010 disabled since Wed 23 Apr 2025 09:42:00 AM +0545 -\n\tUnplugged or turned off\n"
    assert parse_printer(off, "", 0)[0] == "off"
    idle = "printer MF3010 is idle.  enabled since Sat 21 Nov 2026 08:00:00 AM +0545\n"
    assert parse_printer(idle, "", 0)[0] == "ready"
    busy = "printer MF3010 now printing MF3010-4 since Sat 21 Nov 2026 08:00:00 AM +0545\n"
    assert parse_printer(busy, "", 0)[0] == "busy"
    assert parse_printer("", 'lpstat: Invalid destination name in list "NoSuch".', 1)[0] == "missing"


def test_waiting_rules():
    assert interpret("completed", 0, 100, 15) == "done"
    assert interpret("aborted", 1, 100, 15) == "failed"
    assert interpret("active", 10, 100, 15) is None
    assert interpret("active", 100, 100, 15) == "failed"
    assert interpret("unknown", 20, 100, 15) is None
    assert interpret("missing", 2, 100, 15) is None
    assert interpret("missing", 15, 100, 15) == "failed"


def test_cancel_refuses_anything_that_is_not_a_cups_id():
    calls: list[list[str]] = []

    def runner(args, _timeout):
        calls.append(args)
        return CommandResult(0, "", "")

    cups = Cups("MF3010", runner=runner)
    assert cups.cancel("../etc/passwd") is False
    assert cups.cancel("-n") is False
    assert cups.cancel("MF3010-4") is True
    assert calls == [["cancel", "MF3010-4"]]
