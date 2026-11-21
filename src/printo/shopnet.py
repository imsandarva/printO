"""What the shop hotspot's name server should say.

A phone asks some other site whether the internet is there, over IPv4 and IPv6
at the same time. If the IPv6 answer waits on a server this computer can no
longer reach, the phone gives up and never opens the page. Both answers have
to come back at once, and both have to be this computer.
"""

import re
import socket

_V4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_KIND = {"A": 1, "AAAA": 28}


def dns_config(ip: str) -> str:
    if not _ipv4(ip):
        raise SystemExit("The shop wifi didn't get an address this computer can use.")
    # `::` is the empty IPv6 answer. It is what stops the phone waiting.
    return f"no-resolv\nno-hosts\naddress=/#/{ip}\naddress=/#/::\n"


def records(server: str, name: str, kind: str, timeout: float = 1.5, port: int = 53) -> list[str] | None:
    """Addresses from one name server, or None if it does not answer in time."""
    query = _query(name, _KIND[kind])
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(query, (server, port))
        packet, _peer = sock.recvfrom(2048)
    except (TimeoutError, OSError):
        return None
    finally:
        sock.close()
    return _addresses(packet, _KIND[kind])


def _ipv4(ip: str) -> bool:
    if not _V4.fullmatch(ip):
        return False
    try:
        return all(0 <= int(part) <= 255 and str(int(part)) == part for part in ip.split("."))
    except ValueError:
        return False


def _query(name: str, kind: int) -> bytes:
    labels = b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.split(".") if part)
    return b"\x13\x37\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + labels + b"\x00" + kind.to_bytes(2, "big") + b"\x00\x01"


def _addresses(packet: bytes, kind: int) -> list[str]:
    if len(packet) < 12:
        return []
    count = int.from_bytes(packet[6:8], "big")
    try:
        _label, offset = _name(packet, 12)
        offset += 4
    except (IndexError, ValueError):
        return []
    found: list[str] = []
    for _ in range(count):
        try:
            _label, offset = _name(packet, offset)
            typ = int.from_bytes(packet[offset:offset + 2], "big")
            length = int.from_bytes(packet[offset + 8:offset + 10], "big")
            raw = packet[offset + 10:offset + 10 + length]
            offset += 10 + length
        except (IndexError, ValueError):
            break
        if typ != kind:
            continue
        if kind == 1 and len(raw) == 4:
            found.append(socket.inet_ntop(socket.AF_INET, raw))
        elif kind == 28 and len(raw) == 16:
            found.append(socket.inet_ntop(socket.AF_INET6, raw))
    return found


def _name(packet: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    jumped = False
    end = offset
    for _ in range(20):
        if offset >= len(packet):
            raise ValueError(offset)
        length = packet[offset]
        if length == 0:
            if not jumped:
                end = offset + 1
            return ".".join(labels), end
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if not jumped:
                end = offset + 2
            offset = pointer
            jumped = True
            continue
        offset += 1
        labels.append(packet[offset:offset + length].decode("ascii", "replace"))
        offset += length
        if not jumped:
            end = offset
    raise ValueError(offset)
