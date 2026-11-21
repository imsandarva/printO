# Architecture

printO is one Python process on the shop laptop. Phones on the shop wifi upload a file. The laptop turns that file into a single PDF, and the person at the counter chooses pages and copies and sends it to the printer already set up in CUPS. Nothing here manages wifi, and there is no screen yet.

Citizenship copies, double-sided books, and the counter screen are intentionally not in this version.

## Pieces

The entrypoint (`printo`) only loads settings and starts the process. `wiring.py` connects the pieces. Each piece does one job.

| Piece | What it owns |
| --- | --- |
| HTTP | `POST /upload` for phones. `/admin/...` for the laptop only. |
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

The process listens on the shop network so phones can upload. Admin routes answer only when the connection comes from the laptop itself (`127.0.0.1` or `::1`). Forwarded-for headers are ignored. There is no API docs page, because that would describe the admin routes to every phone on the wifi. Customers get back a short number and nothing else: no list, no download, no other people's files.

## Power cuts and disk

Uploads and generated PDFs are written to a temporary name in the same folder, fsynced, then renamed. SQLite uses WAL and `synchronous=FULL`. On startup, half-written temp files are deleted, job folders with no row (and rows with no file) are dropped, `converting` jobs are prepared again, and `printing` jobs are checked against CUPS. A print that never received a CUPS id is not called done.

Uploads are refused when free space would fall below 512 MB plus the max file size (64 MB). Each phone is limited to 30 uploads per 10 minutes, and the shop to 60. One document can be at most 400 sheets, counting copies, so a mis-click cannot dump a huge job on a 4 GB laptop.

## Printer

The queue name defaults to `MF3010` (Canon MF3010, USB, mono, no automatic duplex). Copies are repeated inside the PDF because that printer's collate option defaults to Group, which would print every copy of page 1 before page 2. CUPS is asked for a single copy on A4. The Canon driver stays in CUPS; this program does not ship a driver.

If the queue says the printer is off or unplugged, the file is not submitted. Sending it anyway would leave it in CUPS and it could print later, unattended.

## What starts when

At boot, via systemd: this process, and the hotspot as a saved NetworkManager connection. The counter screen is not started here. It will be opened by hand later, against `http://127.0.0.1:8088`.
