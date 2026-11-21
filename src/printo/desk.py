"""The note on the counter that tells a customer how to connect."""

from pathlib import Path

from printo.messages import front_desk


def shop_name(data_dir: Path) -> str:
    """The wifi name customers already joined. Never the password."""
    return _read(data_dir / "wifi").get("ssid", "").strip()


def desk_message(data_dir: Path) -> str:
    found = _read(data_dir / "wifi")
    name = found.get("ssid", "").strip()
    password = found.get("password", "").strip()
    if not name or not password:
        return ""
    return front_desk(name, password, found.get("address", "").strip())


def _read(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    found: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        found[key.strip()] = value.strip()
    return found
