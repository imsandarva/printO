"""The shop name customers already joined. The password stays out of this."""

from pathlib import Path


def shop_name(data_dir: Path) -> str:
    """The wifi name customers already joined. Never the password."""
    return _read(data_dir / "wifi").get("ssid", "").strip()


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
