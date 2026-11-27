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

shop_preview_port() {
  local port="$1"
  if [[ "$port" =~ ^[0-9]+$ ]] && (( 10#$port < 65534 )); then
    printf '%s\n' "$((10#$port + 2))"
  else
    printf '%s\n' "8090"
  fi
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

# Find listeners through /proc instead of matching a broad process name.  This lets
# the launchers replace this project's normal shop and counter safely, while leaving
# an unrelated program on the same machine alone.
shop_listener_pids() {
  local port="$1" port_hex inode proc fd link
  local -A sockets=() seen=()
  [[ "$port" =~ ^[0-9]+$ ]] && (( port > 0 && port < 65536 )) || return 0
  printf -v port_hex '%04X' "$port"
  while IFS= read -r inode; do sockets["$inode"]=1; done < <(
    awk -v port="$port_hex" 'NR > 1 { split($2, address, ":"); if (toupper(address[2]) == port && $4 == "0A") print $10 }' \
      /proc/net/tcp /proc/net/tcp6 2>/dev/null
  )
  ((${#sockets[@]})) || return 0
  for proc in /proc/[0-9]*; do
    for fd in "$proc"/fd/*; do
      link="$(readlink "$fd" 2>/dev/null || true)"
      [[ "$link" =~ ^socket:\[([0-9]+)\]$ ]] || continue
      inode="${BASH_REMATCH[1]}"
      [[ -n "${sockets[$inode]:-}" ]] || continue
      [[ -n "${seen[${proc##*/}]:-}" ]] && continue
      seen[${proc##*/}]=1
      printf '%s\n' "${proc##*/}"
    done
  done
}

# A direct process can be started from another terminal, but still belongs to this
# checkout when it has this folder as its working directory and runs one of our
# launch commands.  Do not match every Python process: tests and unrelated tools
# often run from this folder too.
shop_runtime_pids() {
  local root="$1" excluded="$2" proc pid cwd command
  for proc in /proc/[0-9]*; do
    pid="${proc##*/}"
    [[ "$pid" == "$excluded" ]] && continue
    cwd="$(readlink -f "$proc/cwd" 2>/dev/null || true)"
    [[ "$cwd" == "$root" ]] || continue
    command="$(tr '\0' ' ' < "$proc/cmdline" 2>/dev/null || true)"
    case " $command " in
      *" -m printo "*|*" -m printo.preview "*|*"*/.venv/bin/printo "*|*"*/scripts/start-shop "*|*"*/shopkeeperpanel "*)
        printf '%s\n' "$pid"
        ;;
    esac
  done
}

shop_is_printo() {
  python3 - "$1" << 'PY'
import json
import sys
import urllib.request

try:
    with urllib.request.urlopen(f"http://127.0.0.1:{int(sys.argv[1])}/admin/health", timeout=0.6) as response:
        body = json.loads(response.read().decode())
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if isinstance(body, dict) and body.get("ok") is True else 1)
PY
}

# The optional boot service uses Restart=on-failure.  Stop it through systemd
# first, otherwise killing its worker could make systemd immediately create a
# replacement while a launcher is trying to take over the same address.
shop_stop_boot_service() {
  command -v systemctl >/dev/null 2>&1 || return 0
  systemctl --user --no-ask-password stop printo.service >/dev/null 2>&1 || true
  systemctl --no-ask-password stop printo.service >/dev/null 2>&1 || sudo -n systemctl stop printo.service >/dev/null 2>&1 || true
}

shop_stop_pids() {
  local signal="$1" pid
  shift
  for pid in "$@"; do kill "-$signal" "$pid" >/dev/null 2>&1 || true; done
}

shop_active_pids() {
  local root="$1" port="$2" preview_port="$3" self="$4" pid
  local -A seen=()
  while IFS= read -r pid; do
    [[ -n "$pid" && "$pid" != "$self" ]] && seen["$pid"]=1
  done < <(shop_runtime_pids "$root" "$self")
  for port in "$port" "$preview_port"; do
    if shop_is_printo "$port"; then
      while IFS= read -r pid; do
        [[ -n "$pid" && "$pid" != "$self" ]] && seen["$pid"]=1
      done < <(shop_listener_pids "$port")
    fi
  done
  ((${#seen[@]})) && printf '%s\n' "${!seen[@]}"
}

# Replace an earlier instance, including one started directly rather than by a
# launcher.  TERM gives the shop a chance to close its database and hotspot; KILL
# is a last resort so the command cannot be held hostage by a stuck old process.
stop_active_shop() {
  local root="$1" port="$2" preview_port="$3" self="${BASHPID:-$$}"
  local -a pids=() remaining=()
  local pid attempt alive
  if shop_is_printo "$port"; then shop_stop_boot_service; fi
  mapfile -t pids < <(shop_active_pids "$root" "$port" "$preview_port" "$self")
  ((${#pids[@]})) || return 0
  printf '%s\n' "Closing the earlier printO shop..."
  shop_stop_pids TERM "${pids[@]}"
  for attempt in {1..30}; do
    remaining=()
    for pid in "${pids[@]}"; do kill -0 "$pid" >/dev/null 2>&1 && remaining+=("$pid"); done
    ((${#remaining[@]})) || return 0
    sleep 0.1
  done
  shop_stop_pids KILL "${remaining[@]}"
  for attempt in {1..10}; do
    alive=0
    for pid in "${remaining[@]}"; do kill -0 "$pid" >/dev/null 2>&1 && alive=1; done
    ((alive)) || return 0
    sleep 0.1
  done
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
