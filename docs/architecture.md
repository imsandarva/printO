# Architecture

printO is one Python process on the shop laptop. Phones on the shop wifi open a page and send a file. The laptop turns that file into a single PDF. The person at the counter opens their own page, on this computer only, chooses pages and copies, and sends it to the printer already set up in CUPS. Nothing here manages wifi.

Citizenship puts a front and a back on one A4 sheet. Double-sided books are intentionally not in this version.


## Pieces

The entrypoint (`printo`) only loads settings and starts the process. `wiring.py` connects the pieces. Each piece does one job. The process does not manage wifi. `scripts/start-shop` does, and it is the thing you leave open.

| Piece | What it owns |
| --- | --- |
| HTTP | `POST /upload` for phones. `/admin/...` for the laptop only. |
| Screens | The phone page and the counter. Plain files served by this process, so there is no second program and no build step to keep in memory. The phone page is one screen: choose, review, send, and see that the shop received the files. Previews are drawn on the page itself, on the phone and on the counter, so the browser's PDF window never frames a sheet. |
| Ingest | Writes the upload to a temporary name, fsyncs it, then renames it into the job folder, then records the job. |
| Store | One SQLite table for state. The file bytes stay on disk. Files are kept by name, not by a spoken code. A queue that also has unused visit columns from an earlier layout is still opened; those columns are left in place. A queue from a still newer layout is refused. |
| Converter | One worker. PDFs are checked and copied, photos become A4 PDFs, and office or named UTF-8 text files go through LibreOffice, then that process exits. |
| Print | Builds the exact PDF (chosen pages, repeated per copy) and hands it to CUPS. |
| Print runner | Feeds one confirmed page to CUPS at a time and sleeps while no run is waiting. |

Sent files stay until someone at the counter deletes them. Delete moves a file to Trash: it leaves the counter, and the bytes stay until it is deleted from Trash. Nothing is deleted because it was printed, or because a few hours or days have passed. A half-written upload is still dropped the next time the shop starts, because it never became a file.

Idle, the process is waiting: no timer walks the queue, and LibreOffice is not running.

## Why everything becomes a PDF

Page counts, page ranges (all, odd, even, or a from–to span), copies, and the printer then share one path. A valid PDF is copied through unchanged, so fonts embedded in the file (Nepali included) are not rebuilt. Photos are placed on a white A4 page at 150 dpi, which is enough for this laser and much lighter than 300 dpi. A photo is one page: a later frame that is only an HDR gain map, a depth image, or a thumbnail is not printed. A multi-page TIFF still prints every sheet. Word-style documents and named UTF-8 text files are the only ones that start LibreOffice. Text uploads are restricted to `.txt`, `.md`, `.csv`, and `.tsv`, and are decoded before acceptance, so a video or arbitrary binary cannot masquerade as a printable text file.

LibreOffice is heavy, and it lies about success: it can exit 0 and write nothing, and two copies will fight over one profile. So it runs one at a time, with its own profile under the data folder (the shop account's fonts are still used), and the result is kept only if it is a real PDF. On a timeout the whole process group is killed.

## Job states

`received → converting → ready → waiting → printing → done`

`converting` can become `failed`; a print run may move through `waiting`, `printing`, `stopping`, and `stopped`. A failed conversion can be retried. A failed print, or a job already sent, can be sent again. Delete moves a job to Trash and safely stops further pages; any page already with CUPS is allowed to finish. The row and the files stay. Deleting it from Trash is what removes them. A job in Trash can be put back.

Two clicks cannot both print the same file: the status change happens in one SQLite write (`BEGIN IMMEDIATE`), and the second click finds the row already `printing`.

Print runs are intentionally page-by-page. printO stages the selected pages as a reusable one-page PDF per source page, then sends exactly one CUPS job at a time. A page is counted only after CUPS confirms it. Stop never cancels the CUPS job: it marks the run as stopping, lets the current sheet finish, and does not send the next one. Progress is stored after every confirmed page, so Continue resumes at the next page and Reprint last page can cover an uncertain sheet. Only one run feeds the printer at once; later runs wait in request order. Printer trouble pauses the run without skipping a page. After a restart, a waiting, printing, or stopping run becomes stopped rather than resuming unattended.

## Who can see what

The process listens on the shop network so phones can upload. Admin routes answer only when the connection comes from the laptop itself (`127.0.0.1` or `::1`). Forwarded-for headers are ignored. There is no API docs page. Any other address answers that the page isn't available. Customers get back that the file arrived, and nothing else: no list, no download, no other people's files, no code to read out. `GET /shop` returns the wifi name they already joined, and not the password. The counter page is under `/admin`, so a phone cannot open it. Files on the counter are named by the file itself. The phone confirms receipt.

## How a customer opens the page

The shop computer is the hotspot. It does not answer for other websites, and joining the wifi does not open a page on the phone. `scripts/start-shop` prints a code in that window, with the address under it, usually `http://10.42.0.1:8088/`. The customer joins the wifi, then scans the code or types the address. The phone's own browser opens the send page.

The code is drawn in black on white, two rows to a character, so a dark window can still be scanned and the squares stay about square. High error correction is used, because a photo of a screen loses a few squares. If the window is too narrow to draw it, the address is still printed. The wifi name and password are in that same window.

## Power cuts and disk

Uploads and generated PDFs are written to a temporary name in the same folder, fsynced, then renamed. SQLite uses WAL and `synchronous=FULL`. On startup, half-written temp files are deleted, job folders with no row (and rows with no file) are dropped, `converting` jobs are prepared again, and any active print run is marked stopped so the counter never guesses about a sheet that may still be in the printer.

Uploads are refused when free space would fall below 512 MB plus the max file size (64 MB). Each phone is limited to 30 uploads per 10 minutes, and the shop to 60. One document can be at most 400 sheets, counting copies, so a mis-click cannot dump a huge job on a 4 GB laptop.

## Printer

The queue name defaults to `MF3010` (Canon MF3010, USB, mono, no automatic duplex). Copies are repeated inside the PDF because that printer's collate option defaults to Group, which would print every copy of page 1 before page 2. CUPS is asked for a single copy on A4. The Canon driver stays in CUPS; this program does not ship a driver.

If the queue says the printer is off or unplugged, the file is not submitted. Sending it anyway would leave it in CUPS and it could print later, unattended.

## What starts when

`scripts/start-shop` is the shop. It turns this computer into the hotspot, prints the customer code in that same window, starts this process, and opens the counter. Type off in that window to stop. The shop finishes what it was doing, even if a phone still has the page open, then turns the hotspot off and tries to put the previous wifi back. Asking the window to close does that same stop. The process leaves on its own, so Ubuntu does not treat it as a crash.

`scripts/open-counter` only opens the counter again, if that window was closed. It does not start a second copy.

`./shopkeeperpanel` is a small local server for changing the counter page while you watch it update. It serves the counter's HTML, CSS, and JavaScript from disk, and forwards everything else to the real printO on the shop port—jobs, previews, print, Trash, printer status, and live updates. If printO is not running, it starts that process without wifi, in its own session, and stops it again when this window closes. It listens on another port so it can sit beside a running shop. Type off to close it. Sample files in memory exist only for automated tests.

At boot, via systemd: this process, and the hotspot as a saved NetworkManager connection. The counter is not started there. The preview on the counter is grey because the MF3010 prints black and white. It shows only the pages that will print. Changing All, even, odd, or a custom range keeps the open file and dissolves the sheet into that set.

Citizenship is two single pages on one sheet. The first file chosen sits near the top, with room above it, and the second sits just below, with a gap between them. A photo uses the picture itself. A single-page PDF uses that page, or the photo inside it when the page is really just a photo. The result is a normal file named Citizenship_1.pdf, then Citizenship_2.pdf, and so on, so it can be previewed and printed like any other file. Its two source pieces and normalized slot boxes (`piece-0.pdf`, `piece-1.pdf`, and `pair.json`) stay in the job folder so either photo or the whole sheet can be rotated independently without altering the original uploads.

The sheet on the counter is always A4, portrait, 210 by 297 millimetres, the paper in the tray. It does not grow wide or thin to match a file. The page keeps its own shape and sits in the middle of that sheet. The size slider scales the page already drawn on the sheet. The paper does not move, and the page is not drawn again while the slider moves, so it stays in step with the pointer. 100% is the normal fit: the whole page, as large as that sheet allows. The slider stops at 125% for every file. Anything past the edge of the sheet is cut off, in the preview and in the PDF that is printed, so the two match. A page that is already A4, at 100%, is still copied through unchanged. The stored file is left as it was, so a later size starts from the full page again.

Each page is pictured once, as a small grey image, as soon as the file is ready. Page 1 is made first, then the rest, and the pictures are kept in the job folder until the file is deleted. The counter shows those pictures. It does not open the file to draw a page. Turning a page, or laying the next one beside it, only moves the picture already saved. Scrolling away can drop the copy on screen; the saved picture stays, so scrolling back is immediate. The first time a large new file is opened, one line shows how many pictures are ready. That line does not come back later.

Those choices stay a short list: which pages, how each one is turned, how large it sits, and whether two share a landscape sheet. Print turns and centers the real pages the same way, and cuts off whatever passes the edge. A single photo is the exception: it is placed again from the original picture, so a sideways photo fills the sheet instead of carrying the white around it. That new picture is what the counter shows, the same moment the turn is saved. A Citizenship sheet is built again from its two saved pieces. The file in the queue is left as it arrived until then.

## Two pages on a landscape sheet

The landscape button beside rotate (keyboard **L**) puts two chosen pages on one A4 landscape sheet, 297 by 210 millimetres. Each page keeps its own shape and sits in its half, 148.5 by 210, with a faint line between them. The saved pictures are placed into that shape, so the sheet changes with the click. A half whose picture is not ready yet stays empty and light. A picture is never stretched to fill the new shape.

Print follows the same layout (`domain/layout.py`). Chosen pages are paired in order, a turn is applied before a page is placed, and the size slider scales the whole sheet about its centre. Anything past the paper is cut off. An odd last page leaves the right half blank. Stop, the progress line, and the sheet limit count these sheets, and each copy sends those sheets again. Turning landscape on does not clear a page the shopkeeper had selected.
