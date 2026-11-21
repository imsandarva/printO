# Architecture

printO is one Python process on the shop laptop. Phones on the shop wifi open a page and send a file. The laptop turns that file into a single PDF. The person at the counter opens their own page, on this computer only, chooses pages and copies, and sends it to the printer already set up in CUPS. Nothing here manages wifi.

Citizenship copies and double-sided books are intentionally not in this version.

## Pieces

The entrypoint (`printo`) only loads settings and starts the process. `wiring.py` connects the pieces. Each piece does one job. The process does not manage wifi. `scripts/start-shop` does, and it is the thing you leave open.

| Piece | What it owns |
| --- | --- |
| HTTP | `POST /upload` for phones. `/admin/...` for the laptop only. |
| Screens | The phone page and the counter. Plain files served by this process, so there is no second program and no build step to keep in memory. The phone page is one screen: choose, review, send, and see that the shop received the files. Previews are drawn on the phone. |
| Ingest | Writes the upload to a temporary name, fsyncs it, then renames it into the job folder, then records the job. |
| Store | One SQLite table for state. The file bytes stay on disk. |
| Converter | One worker. PDF is checked and copied. Photos become an A4 PDF. Word goes through LibreOffice, then that process exits. |
| Print | Builds the exact PDF (chosen pages, repeated per copy) and hands it to CUPS. |
| Watch | Follows that one CUPS job until CUPS is done with it. Sleeps only while a job is actually printing. |
| Cleanup | Deletes old files. Printed files go after 2 hours, others after 24. |

Idle, the process is waiting: no timer walks the queue, and LibreOffice is not running.

## Why everything becomes a PDF

Page counts, page ranges, copies, and the printer then share one path. A valid PDF is copied through unchanged, so fonts embedded in the file (Nepali included) are not rebuilt. Photos are placed on a white A4 page at 150 dpi, which is enough for this laser and much lighter than 300 dpi. Word and similar files are the only ones that start LibreOffice.

LibreOffice is heavy, and it lies about success: it can exit 0 and write nothing, and two copies will fight over one profile. So it runs one at a time, with its own profile under the data folder (the shop account's fonts are still used), and the result is kept only if it is a real PDF. On a timeout the whole process group is killed.

## Job states

`received → converting → ready → printing → done`

`converting` or `printing` can become `failed`. A failed conversion can be retried. A failed print, or a job already sent, can be sent again. Removing a job deletes the row and the files, and cancels the CUPS job if one was submitted.

Two clicks cannot both print the same file: the status change happens in one SQLite write (`BEGIN IMMEDIATE`), and the second click finds the row already `printing`.

`done` means CUPS finished with the job. On this USB laser that means the data was accepted and sent, not that a person watched the page come out. The counter message says "Sent to the printer." If CUPS reports the job aborted, or the laptop died mid-print, the file stays and can be sent again. A job still sitting in CUPS after 20 minutes is cancelled and marked failed, so it cannot surprise anyone later.

## Who can see what

The process listens on the shop network so phones can upload. Admin routes answer only when the connection comes from the laptop itself (`127.0.0.1` or `::1`). Forwarded-for headers are ignored. There is no API docs page. Any other address answers that the page isn't available. Customers get back a short number and nothing else: no list, no download, no other people's files. `GET /shop` returns the wifi name they already joined, and not the password. The counter page is under `/admin`, so a phone cannot open it. The number still identifies the file on the counter. The phone confirms receipt instead of asking the customer to read a number out.

## How a customer opens the page

The shop computer is the hotspot. It does not answer for other websites, and joining the wifi does not open a page on the phone. `scripts/start-shop` prints a code in that window, with the address under it, usually `http://10.42.0.1:8088/`. The customer joins the wifi, then scans the code or types the address. The phone's own browser opens the send page.

The code is drawn in black on white, two rows to a character, so a dark window can still be scanned and the squares stay about square. High error correction is used, because a photo of a screen loses a few squares. If the window is too narrow to draw it, the address is still printed. The wifi name and password are in that same window and on the counter.

## Power cuts and disk

Uploads and generated PDFs are written to a temporary name in the same folder, fsynced, then renamed. SQLite uses WAL and `synchronous=FULL`. On startup, half-written temp files are deleted, job folders with no row (and rows with no file) are dropped, `converting` jobs are prepared again, and `printing` jobs are checked against CUPS. A print that never received a CUPS id is not called done.

Uploads are refused when free space would fall below 512 MB plus the max file size (64 MB). Each phone is limited to 30 uploads per 10 minutes, and the shop to 60. One document can be at most 400 sheets, counting copies, so a mis-click cannot dump a huge job on a 4 GB laptop.

## Printer

The queue name defaults to `MF3010` (Canon MF3010, USB, mono, no automatic duplex). Copies are repeated inside the PDF because that printer's collate option defaults to Group, which would print every copy of page 1 before page 2. CUPS is asked for a single copy on A4. The Canon driver stays in CUPS; this program does not ship a driver.

If the queue says the printer is off or unplugged, the file is not submitted. Sending it anyway would leave it in CUPS and it could print later, unattended.

## What starts when

`scripts/start-shop` is the shop. It turns this computer into the hotspot, prints the customer code in that same window, starts this process, and opens the counter. Press Ctrl+C there to stop. That closes the page even if a phone still has it open, turns the hotspot off, and tries to put the previous wifi back.

`scripts/open-counter` only opens the counter again, if that window was closed. It does not start a second copy.

At boot, via systemd: this process, and the hotspot as a saved NetworkManager connection. The counter is not started there. The preview on the counter is grey because the MF3010 prints black and white.
