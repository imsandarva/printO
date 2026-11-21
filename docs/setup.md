# Setup

Needs Python 3.11 or newer, CUPS, and the MF3010 queue already working (`lpstat -p MF3010`). Word files also need LibreOffice (`soffice` on `PATH`). Photos from iPhones need the HEIC library, which this machine already has; `pillow-heif` is installed with the app.

From this directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/printo --check
.venv/bin/printo
```

`--check` prints one line about the printer and does not start the server. The server listens on port **8088** on all interfaces. Phones use that. The counter uses `http://127.0.0.1:8088/admin/`.

## Open the shop

From this folder, two commands. The first stays running: it starts the shop wifi and printO. A phone joins that wifi and sends a file. Closing it turns the shop wifi off and tries to put the previous wifi back.

```bash
./scripts/start-shop
```

The second only opens the counter on this computer. It does not start another copy of printO.

```bash
./scripts/open-counter
```

The wifi name and password are saved in `data/wifi` the first time (`printO` / `printo123` until you change them). Write them where customers can see them. Letting the page open by itself needs your password once, so phones can use port 80. Without that, the address is `http://10.42.0.1:8088`.

`.venv/bin/printo` still starts the server alone, without touching wifi.

Files, the database, the LibreOffice profile, and the log live in `./data` (or `PRINTO_DATA_DIR`). The log rotates at about 1 MB, three old files kept.

## Settings

A `printo.toml` in the working directory overrides the defaults. Environment variables override the file. Useful ones:

| Variable | Default | Meaning |
| --- | --- | --- |
| `PRINTO_HOST` | `0.0.0.0` | Bind address |
| `PRINTO_PORT` | `8088` | Port |
| `PRINTO_DATA_DIR` | `./data` | Queue and files |
| `PRINTO_PRINTER` | `MF3010` | CUPS queue name |
| `PRINTO_MAX_UPLOAD_BYTES` | 67108864 | Largest upload |
| `PRINTO_MIN_FREE_BYTES` | 536870912 | Refuse uploads below this free space, plus the max upload |
| `PRINTO_MAX_SHEETS` | 400 | Most pages in one file, and most sheets in one print (pages × copies) |
| `PRINTO_MAX_COPIES` | 20 | |
| `PRINTO_PRINTED_KEEP_HOURS` | 2 | |
| `PRINTO_UNPRINTED_KEEP_HOURS` | 24 | |
| `PRINTO_OFFICE_TIMEOUT` | 120 | Seconds before LibreOffice is killed |

Example `printo.toml`:

```toml
printer = "MF3010"
port = 8088
```

Do not put a reverse proxy in front of this port. Admin access is decided by the real client address, and a proxy would make every phone look like the laptop.

## Boot

`deploy/printo.service` is a systemd unit. Copy the project to the shop machine, create a data directory the shop account can write (`/var/lib/printo`), edit `User`, `WorkingDirectory`, and `ExecStart` in the unit, then:

```bash
sudo cp deploy/printo.service /etc/systemd/system/printo.service
sudo systemctl enable --now printo.service
```

The unit restarts the process if it crashes. It does not start a browser.

The hotspot is separate. Create it once in NetworkManager and turn autoconnect on, for example:

```bash
nmcli device wifi hotspot ssid Shop password "choose-a-password" ifname wlan0
nmcli connection modify Hotspot connection.autoconnect yes
```

Confirm the wifi device name on that laptop. After a reboot the hotspot should be up before anyone logs in; that is worth testing once on the real machine. Phones join that wifi and open `http://10.42.0.1:8088`. The laptop's address on its own hotspot is often `10.42.0.1`. `scripts/start-shop` is the same hotspot for a machine that is not starting it at boot, and it does not leave autoconnect on.

## Fonts

PDF files keep the fonts inside them. Word files are drawn by LibreOffice, so a document in Nepali looks right only if that font is installed for the shop account. If a Word file comes out with the wrong letters, install the font and send the file again. Don't convert by rewriting PDFs to "fix" this; that path is deliberately not used.

## Tests

```bash
.venv/bin/pytest
```

The tests do not submit anything to the real printer. They use a stand-in for CUPS.
