"""Every sentence a person might read. The shop screen and the phone should not invent their own."""

from printo.domain.job import Job
from printo.domain.status import can_print, can_retry, label_for


def received() -> str:
    return "Received."


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
    return "Deleted."


def removed_but_printer() -> str:
    return "Deleted here, but the printer may still finish the copy it already started."


def trashed() -> str:
    return "Moved to Trash."


def trashed_but_printer() -> str:
    return "Moved to Trash. The printer may still finish the copy it already started."


def restored() -> str:
    return "Back at the counter."


def still_kept() -> str:
    return "Move it to Trash first."


def in_trash() -> str:
    return "That file is in Trash."


def running() -> str:
    return "printO is running."


def connected() -> str:
    return "Connected."


def customer_copy() -> dict[str, str]:
    """Every sentence on the customer page. The page fills {name}, {count}, {files}, {size}, {pct}, {done}, {total}, {current}."""
    return {
        "connected_shop": "Connected to shop",
        "connected_named": "Connected to {name}",
        "offline_short": "Not connected",
        "offline": "Connection interrupted. Check your Wi-Fi and try again.",
        "heading": "What would you like to print?",
        "support": "Select documents or photos from your phone.",
        "choose": "Choose files",
        "types": "PDF, Word, and photos",
        "selected": "Selected files",
        "count_one": "1 file",
        "count_many": "{count} files",
        "tally": "{files} · {size}",
        "add": "Add more files",
        "remove_all": "Remove all",
        "remove": "Remove {name}",
        "view": "View {name}",
        "undo": "Undo",
        "removed_one": "Removed {name}",
        "removed_all": "Removed all files",
        "confirm_title": "Remove all files?",
        "confirm_body": "This clears everything you've selected.",
        "cancel": "Cancel",
        "send": "Send to shop",
        "sending": "Sending your files...",
        "keep_open": "Keep this page open while your files are being sent.",
        "waiting": "Waiting",
        "uploading": "Uploading",
        "uploading_pct": "Uploading · {pct}%",
        "received_word": "Received",
        "failed_word": "Failed",
        "retry": "Try again",
        "received_title": "Files received!",
        "received_body": "Your files have been successfully sent to the shop.",
        "collect": "You can now collect your printouts from the shopkeeper.",
        "partial": "{done} of {total} files received",
        "none_received": "These files weren't received.",
        "partial_help": "You can send the rest again.",
        "try_again_send": "You can try again.",
        "send_more": "Send more files",
        "unsupported": "This file type isn't supported.",
        "too_large": "This file is too large to send.",
        "empty": "That file is empty. Please choose the file again.",
        "duplicate": "Already selected.",
        "preview_fail": "Unable to preview this document.",
        "still_send": "This file is selected and can still be sent.",
        "close": "Close",
        "page": "{current} of {total}",
        "zoom_in": "Zoom in",
        "zoom_out": "Zoom out",
        "try_again": "Please try that again in a moment.",
        "opening": "Opening…",
        "noscript": "This page can't run in this browser. Please try a different one.",
    }


def present(job: Job) -> dict:
    return {
        "id": job.id,
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
        "trashed_at": job.trashed_at,
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
