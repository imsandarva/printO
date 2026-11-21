# Shared bits for the two shop commands. They stay thin: find the folder, find the port.

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
