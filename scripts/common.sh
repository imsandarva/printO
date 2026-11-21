# Shared bits for the shop commands. They stay thin: find the folder, find the port, open the counter.

shop_root() {
  cd "$(dirname "$1")/.." && pwd
}

shop_port() {
  local root="$1" port="${PRINTO_PORT:-}"
  if [[ -n "$port" ]]; then printf '%s\n' "$port"; return; fi
  if [[ -f "$root/printo.toml" ]]; then
    port="$(awk -F= '$1 ~ /^[[:space:]]*port[[:space:]]*$/ { gsub(/[^0-9]/, "", $2); print $2; exit }' "$root/printo.toml")"
  fi
  printf '%s\n' "${port:-8088}"
}

shop_port_open() {
  python3 - "$1" << 'PY'
import socket, sys
try:
    socket.create_connection(("127.0.0.1", int(sys.argv[1])), 0.4).close()
except OSError:
    sys.exit(1)
PY
}

shop_healthy() {
  python3 - "$1" << 'PY'
import sys, urllib.request
try:
    urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/admin/health", timeout=1).read()
except Exception:
    sys.exit(1)
PY
}

# A new session, so closing the shop does not close the window with it.
open_window() {
  local target="$1"
  if command -v google-chrome >/dev/null; then setsid google-chrome --app="$target" >/dev/null 2>&1 &
  elif command -v chromium >/dev/null; then setsid chromium --app="$target" >/dev/null 2>&1 &
  elif command -v chromium-browser >/dev/null; then setsid chromium-browser --app="$target" >/dev/null 2>&1 &
  elif command -v firefox >/dev/null; then setsid firefox --new-window "$target" >/dev/null 2>&1 &
  elif command -v xdg-open >/dev/null; then setsid xdg-open "$target" >/dev/null 2>&1 &
  else return 1
  fi
}
