# Workflows

## At the counter

The customer joins the shop wifi. The name and password are in the window where the shop was started, and in `data/wifi` (created the first time the shop starts). They scan the code in that window, or type the address under it, usually `http://10.42.0.1:8088/`. The page opens in the phone's own browser.

They choose their files, check them, and send them. The page confirms when the shop computer has them. Printing still happens here.

On this computer the counter is already open. `scripts/start-shop` opened it, and that same window is the shop: leave it open, and type off to close the shop. If the counter window was closed, `scripts/open-counter` opens it again. Files that arrived while it was closed are already there, under their own names. They choose pages and how many copies, then press Print. The page is shown in grey because the printer is black and white.

Try again prepares a file that failed. Print again sends one that already went, or one the printer refused. Delete moves it to Trash. A second print of a file that is already printing is refused. New files play a short sound after the counter has been clicked once, which is a limit of the browser, and the list updates on its own.

The words on both screens are the sentences from the server.

## A customer sends files

The page is one screen. They can choose several files, add more, and remove a mistake (Undo brings it back; Remove all asks first). Photos and the first page of a PDF are previewed on the phone. Tapping a file opens it there.

Send moves the files together, a few at a time. Each row says whether it is waiting, sending, received, or failed. The shop has a file when that file's upload answers. That is receipt, not printing. If one fails, the others stay received, and Try again sends only the ones that didn't arrive.

`GET /shop` tells the phone the shop name and the largest file it will take. It does not include the wifi password.

## A customer hands over a file

`POST /upload` with one form field, `file`. The page calls this once per file.

Accepted: PDF, Word (`.doc`, `.docx`), OpenDocument text, Rich Text, and photos (JPEG, PNG, WEBP, GIF, BMP, TIFF, HEIC). The type is read from the bytes, not from the filename. A photo is one page, including a phone picture that also carries an HDR gain map. A multi-page TIFF still prints every sheet.

```bash
curl -s -F "file=@/path/to/file.pdf" http://127.0.0.1:8088/upload
```

```json
{"ok": true, "message": "Received."}
```

The phone only learns that the file arrived. It cannot download it, and it is not given a code to read out. A bad type, an empty file, a locked PDF, a file over 64 MB, a full disk, or too many uploads in a few minutes comes back as `{"ok": false, "message": "..."}` with a sentence that can be shown as-is.

The file then moves `received → converting → ready` on its own. Failures stay in the list with `can_retry: true` when preparing failed, or `can_print: true` when the PDF exists but printing failed.

## The counter

All of these refuse any connection that is not from the laptop itself. A phone gets "This page isn't available."

The counter screen puts the file list on the left, the print controls beside it, and the page preview on the right. Files are grouped by the year, then the month, then the day they were sent, newest first. Today’s year, month, and day are open. Older ones are closed until someone opens them. A closed day with something still to print shows a small mark, so it is not easy to miss. In the list, a file’s name is regular weight, a step quieter than the date above it, with the time smaller and softer on the right. A thin line sits between files in the same day, and it steps aside when a file is selected.

| Request | What it does |
| --- | --- |
| `GET /admin/health` | The process is up. |
| `GET /admin/printer` | `ready`, `busy`, `off`, `missing`, or `down`, plus a sentence. |
| `GET /admin/jobs` | Newest first. Optional `?status=ready`. |
| `GET /admin/jobs/{id}` | One job. |
| `GET /admin/jobs/{id}/file` | The prepared PDF, once it exists. |
| `POST /admin/jobs/{id}/print` | Body `{"pages": "all", "copies": 1}`. |
| `POST /admin/jobs/{id}/retry` | Prepare again after a conversion failure. |
| `POST /admin/jobs/{id}/trash` | Move it to Trash. The file stays. A print that already started is cancelled. |
| `POST /admin/jobs/{id}/restore` | Bring it back from Trash. |
| `DELETE /admin/jobs/{id}` | Delete it for good. Only once it is in Trash. Cancels the printer job if one is still going. |
| `GET /admin/events` | Server-sent events. A nudge, not the record. On reconnect, load the job list again. |

A job object carries `name`, `status`, `label`, `message`, `page_count`, `pages`, `copies`, `can_print`, and `can_retry`. In the file list, the counter shows only the file name and when it arrived. When a file is selected, `message` can appear under the name for anything that is not ready yet. `label` and `status` stay on the wire for the program and other views; `status` values are `received`, `converting`, `ready`, `printing`, `done`, `failed`.

Pages are 1-based: `all`, `2`, `1-3`, `1-3, 5`. Out of range is refused. Copies are 1 to 20. Pages times copies cannot pass 400 sheets.

Printing a `done` job sends it again. That is the reprint. The printer being off refuses the print and leaves the file ready. A second click while it is already `printing` is refused.

`done` / "Sent to the printer." means CUPS took the job and finished sending it. It does not prove a sheet landed in the tray. If the result looks wrong, print it again. If it sits with the printer for 20 minutes, printO cancels it and keeps the file.

## Changing the counter

`./shopkeeperpanel` opens the same counter with the same files already in the shop. It does not turn on the hotspot. If printO is not running, it starts only that part in the background. Leave that window open while you change the page; saving updates what you see. Type off when you are done looking.

## Keeping files

A file stays until someone presses Delete. That moves it to Trash, grouped by the day it was sent, the same way as the counter. Nothing is thrown away because it was printed, or because a day has passed. From Trash, Restore puts it back. Select, then Delete, asks first; only a yes removes the file for good. If a copy had already started, the printer is asked to stop.

If the laptop loses power, the next start picks up whole files, prepares anything that was mid-conversion, and asks CUPS about anything that was mid-print. It will not call a job done just because the process died after sending it, unless CUPS still has that job as completed.
