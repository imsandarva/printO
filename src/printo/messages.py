"""Every sentence a person might read. The shop screen and the phone should not invent their own."""

from printo.domain.job import Job
from printo.domain.status import can_print, can_retry, label_for


def received(number: str) -> str:
    return f"Received. Please tell the person at the counter your number, {number}."


def too_big() -> str:
    return "That file is too large to receive. Please try a smaller one."


def empty_file() -> str:
    return "That file is empty. Please choose the file again."


def bad_type() -> str:
    return "We can take a PDF, a Word document, or a photo. This one isn't any of those."


def disk_full() -> str:
    return "The shop computer is too full to take new files right now. Please ask at the counter."


def rate_limited() -> str:
    return "A lot of files just came in. Please wait a minute and try again."


def try_again() -> str:
    return "Please try that again in a moment."


def damaged() -> str:
    return "This file looks damaged. Please ask them to send it again."


def pdf_locked() -> str:
    return "This PDF is locked with a password. Please ask for a copy that isn't locked."


def too_many_pages() -> str:
    return "This file has too many pages to print in one go. Please ask them to split it."


def too_many_sheets() -> str:
    return "That's too many sheets at once. Please print fewer pages or fewer copies."


def office_missing() -> str:
    return "Word documents can't be prepared on this computer yet. A PDF or a photo will work."


def office_timeout() -> str:
    return "This document took too long to prepare. Please ask them for a PDF."


def office_failed() -> str:
    return "This document couldn't be prepared. Please ask them for a PDF."


def convert_failed() -> str:
    return "This file couldn't be prepared. Please ask them to send it again."


def incomplete() -> str:
    return "This file didn't finish arriving. Please ask them to send it again."


def unexpected() -> str:
    return "Something went wrong. Please try again."


def hidden() -> str:
    return "This page isn't available."


def validation() -> str:
    return "That doesn't look right. Please try again."


def not_found() -> str:
    return "That file isn't here anymore."


def not_ready() -> str:
    return "This file isn't ready to print yet."


def already_printing() -> str:
    return "This one is already going to the printer."


def no_retry() -> str:
    return "This file doesn't need to be prepared again."


def bad_pages(page_count: int) -> str:
    return f"Those page numbers don't match this file. It has {page_count} pages."


def bad_copies(limit: int) -> str:
    return f"Please choose between 1 and {limit} copies."


def printer_ready() -> str:
    return "The printer is ready."


def printer_busy() -> str:
    return "The printer is working right now."


def printer_off() -> str:
    return "The printer is turned off or unplugged."


def printer_off_action() -> str:
    return "The printer is turned off or unplugged. Turn it on, then try again."


def printer_missing() -> str:
    return "The printer isn't set up on this computer."


def printer_down() -> str:
    return "The printer service isn't responding. The file is still here."


def printing() -> str:
    return "Printing."


def sent() -> str:
    return "Sent to the printer."


def ready() -> str:
    return "Ready to print."


def preparing() -> str:
    return "Getting it ready."


def arrived() -> str:
    return "Just arrived."


def interrupted() -> str:
    return "Printing was interrupted. The file is still here, so you can try again."


def gave_up() -> str:
    return "This has been waiting on the printer for too long. Check the printer, then try again."


def rejected() -> str:
    return "The printer didn't accept this file. It is still here, so you can try again."


def compose_failed() -> str:
    return "This file couldn't be prepared for the printer. Please try again."


def removed() -> str:
    return "Removed."


def removed_but_printer() -> str:
    return "Removed here, but the printer may still finish the copy it already started."


def running() -> str:
    return "printO is running."


def front_desk(name: str, password: str, address: str) -> str:
    line = f"Customers join {name}. The password is {password}."
    if address:
        line += f" If the page doesn't open on its own, they can type {address}."
    return line


def connected() -> str:
    return "Connected."


def present(job: Job) -> dict:
    return {
        "id": job.id,
        "number": job.public_code,
        "name": job.original_name,
        "kind": job.kind,
        "status": job.status,
        "label": label_for(job.status),
        "message": job.message,
        "page_count": job.page_count,
        "pages": job.pages_spec,
        "copies": job.copies,
        "can_print": can_print(job),
        "can_retry": can_retry(job),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def removed_event(job_id: str) -> dict:
    return {"id": job_id, "status": "canceled", "label": "Removed", "message": removed()}


def failure_after_wait(outcome: str) -> str:
    if outcome == "active":
        return gave_up()
    if outcome in {"aborted", "missing"}:
        return interrupted()
    if outcome == "unknown":
        return printer_down()
    return rejected()
