# Workflows

## A customer hands over a file

`POST /upload` with one form field, `file`.

Accepted: PDF, Word (`.doc`, `.docx`), OpenDocument text, Rich Text, and photos (JPEG, PNG, WEBP, GIF, BMP, TIFF, HEIC). The type is read from the bytes, not from the filename. GIF uses the first frame only, so an animation is not printed as a stack of frames.

```bash
curl -s -F "file=@/path/to/file.pdf" http://127.0.0.1:8088/upload
```

```json
{"ok": true, "number": "K7M2", "message": "Received. Please tell the person at the counter your number, K7M2."}
```

The number is enough to say out loud. It cannot be used to download the file. A bad type, an empty file, a locked PDF, a file over 64 MB, a full disk, or too many uploads in a few minutes comes back as `{"ok": false, "message": "..."}` with a sentence that can be shown as-is.

The file then moves `received → converting → ready` on its own. Failures stay in the list with `can_retry: true` when preparing failed, or `can_print: true` when the PDF exists but printing failed.

## The counter

All of these refuse any connection that is not from the laptop itself. A phone gets "This page isn't available."

| Request | What it does |
| --- | --- |
| `GET /admin/health` | The process is up. |
| `GET /admin/printer` | `ready`, `busy`, `off`, `missing`, or `down`, plus a sentence. |
| `GET /admin/jobs` | Newest first. Optional `?status=ready`. |
| `GET /admin/jobs/{id}` | One job. |
| `GET /admin/jobs/{id}/file` | The prepared PDF, once it exists. |
| `POST /admin/jobs/{id}/print` | Body `{"pages": "all", "copies": 1}`. |
| `POST /admin/jobs/{id}/retry` | Prepare again after a conversion failure. |
| `DELETE /admin/jobs/{id}` | Remove it. Cancels the printer job if one was sent. |
| `GET /admin/events` | Server-sent events. A nudge, not the record. On reconnect, load the job list again. |

A job object carries `number`, `name`, `status`, `label`, `message`, `page_count`, `pages`, `copies`, `can_print`, and `can_retry`. `label` and `message` are for a person. `status` is for the program: `received`, `converting`, `ready`, `printing`, `done`, `failed`.

Pages are 1-based: `all`, `2`, `1-3`, `1-3, 5`. Out of range is refused. Copies are 1 to 20. Pages times copies cannot pass 400 sheets.

Printing a `done` job sends it again. That is the reprint. The printer being off refuses the print and leaves the file ready. A second click while it is already `printing` is refused.

`done` / "Sent to the printer." means CUPS took the job and finished sending it. It does not prove a sheet landed in the tray. If the result looks wrong, print it again. If it sits with the printer for 20 minutes, printO cancels it and keeps the file.

## After hours

Printed files are deleted about 2 hours later. Files that were never sent, and failed ones, are deleted after about 24 hours. Nothing is deleted while it is still being prepared or is in the printer queue. A file removed by hand is deleted immediately.

If the laptop loses power, the next start picks up whole files, prepares anything that was mid-conversion, and asks CUPS about anything that was mid-print. It will not call a job done just because the process died after sending it, unless CUPS still has that job as completed.
