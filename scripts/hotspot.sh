# The shop wifi. The Python process never touches this. Start-shop is the only caller.
# It expects ROOT and PORT, and it fills IFACE, PREVIOUS, HOT, SSID, and PASS.

wifi_iface() {
  if [[ -n "${PRINTO_WIFI_IFACE:-}" ]]; then printf '%s\n' "$PRINTO_WIFI_IFACE"; return; fi
  nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi" { print $1; exit }'
}

read_wifi() {
  local file="$ROOT/data/wifi" line key val
  mkdir -p "$ROOT/data"
  if [[ ! -f "$file" ]]; then
    printf 'ssid=printO\npassword=printo123\n' > "$file"
    chmod 600 "$file"
  fi
  SSID="printO"
  PASS="printo123"
  while IFS= read -r line || [[ -n "$line" ]]; do
    key="${line%%=*}"
    val="${line#*=}"
    case "$key" in
      ssid) SSID="$val" ;;
      password) PASS="$val" ;;
    esac
  done < "$file"
  if [[ -z "$SSID" || ${#PASS} -lt 8 ]]; then
    printf '%s\n' "The wifi name or password in data/wifi isn't usable. The password needs at least 8 characters."
    exit 1
  fi
}

note_address() {
  local address="$1" file="$ROOT/data/wifi" tmp
  [[ -f "$file" ]] || return 0
  tmp="$(mktemp)"
  awk -F= -v addr="$address" 'BEGIN { OFS = "=" } $1 == "address" { next } NF { print } END { print "address=" addr }' "$file" > "$tmp"
  mv "$tmp" "$file"
  chmod 600 "$file"
}

remember_previous() {
  PREVIOUS="$(nmcli -t -f NAME,TYPE,DEVICE connection show --active | python3 -c '
import sys
iface = sys.argv[1]
for line in sys.stdin:
    parts = line.rstrip("\n").split(":")
    if len(parts) < 3:
        continue
    device, kind, name = parts[-1], parts[-2], ":".join(parts[:-2])
    if kind == "802-11-wireless" and device == iface and name != "printO":
        print(name)
        break
' "$IFACE")"
}

have_hotspot() {
  nmcli -t -f NAME connection show | grep -Fxq 'printO'
}

shop_address() {
  local ip="" tries=0
  while [[ "$tries" -lt 10 ]]; do
    ip="$(nmcli -g IP4.ADDRESS device show "$IFACE" 2>/dev/null | head -n 1 | cut -d/ -f1 || true)"
    if [[ -n "$ip" ]]; then printf '%s\n' "$ip"; return; fi
    tries=$((tries + 1))
    sleep 0.3
  done
  printf '%s\n' "10.42.0.1"
}

# An older shop answered every website with this computer, so a phone would try to open a page by itself.
# That is gone. A leftover of it would still make the phone ask to sign in, so it comes off before the hotspot starts.
clear_old_portal() {
  local conf="/etc/NetworkManager/dnsmasq-shared.d/printo.conf"
  OLD_PORTAL=0
  if [[ -f "$conf" ]] && ! sudo -n rm -f "$conf" 2>/dev/null; then OLD_PORTAL=1; fi
  if [[ -n "${IFACE:-}" && -n "${PORT:-}" ]]; then
    sudo -n iptables -t nat -D PREROUTING -i "$IFACE" -p tcp --dport 80 -j REDIRECT --to-ports "$PORT" >/dev/null 2>&1 || true
  fi
  sudo -n nft delete table ip printo >/dev/null 2>&1 || true
}

bring_hotspot() {
  command -v nmcli >/dev/null || { printf '%s\n' "This computer can't share a wifi hotspot."; exit 1; }
  IFACE="$(wifi_iface)"
  [[ -n "$IFACE" ]] || { printf '%s\n' "This computer doesn't have a wifi device that can be a hotspot."; exit 1; }
  clear_old_portal
  nmcli radio wifi on >/dev/null
  remember_previous
  if have_hotspot; then
    nmcli connection modify printO connection.interface-name "$IFACE" 802-11-wireless.mode ap \
      802-11-wireless.ssid "$SSID" 802-11-wireless.band bg 802-11-wireless-security.key-mgmt wpa-psk \
      802-11-wireless-security.psk "$PASS" ipv4.method shared ipv4.addresses 10.42.0.1/24 \
      ipv6.method disabled connection.autoconnect no
  else
    nmcli device wifi hotspot ifname "$IFACE" con-name printO ssid "$SSID" password "$PASS" band bg >/dev/null
    nmcli connection modify printO ipv6.method disabled connection.autoconnect no ipv4.addresses 10.42.0.1/24
  fi
  nmcli connection up printO >/dev/null
  HOT=1
}

close_hotspot() {
  clear_old_portal
  nmcli connection down printO >/dev/null 2>&1 || true
  if [[ -n "${PREVIOUS:-}" ]]; then sleep 0.4; nmcli connection up "$PREVIOUS" >/dev/null 2>&1 || true; fi
}
