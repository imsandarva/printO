"""Settings come from printo.toml, then environment variables, then built-in defaults."""

import os
import re
import sys
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

_PRINTER = re.compile(r"^[A-Za-z0-9_.-]+$")
_ENV = {
    "host": "PRINTO_HOST",
    "port": "PRINTO_PORT",
    "data_dir": "PRINTO_DATA_DIR",
    "printer": "PRINTO_PRINTER",
    "max_upload_bytes": "PRINTO_MAX_UPLOAD_BYTES",
    "min_free_bytes": "PRINTO_MIN_FREE_BYTES",
    "max_sheets": "PRINTO_MAX_SHEETS",
    "max_copies": "PRINTO_MAX_COPIES",
    "office_timeout_seconds": "PRINTO_OFFICE_TIMEOUT",
    "print_poll_seconds": "PRINTO_PRINT_POLL_SECONDS",
    "print_give_up_seconds": "PRINTO_PRINT_GIVE_UP",
    "print_missing_grace_seconds": "PRINTO_PRINT_MISSING_GRACE",
    "uploads_per_ip": "PRINTO_UPLOADS_PER_IP",
    "uploads_global": "PRINTO_UPLOADS_GLOBAL",
    "upload_window_seconds": "PRINTO_UPLOAD_WINDOW",
    "soffice_bin": "PRINTO_SOFFICE",
}


@dataclass(frozen=True, slots=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    printer: str
    max_upload_bytes: int
    min_free_bytes: int
    max_sheets: int
    max_copies: int
    office_timeout_seconds: int
    print_poll_seconds: float
    print_give_up_seconds: float
    print_missing_grace_seconds: float
    uploads_per_ip: int
    uploads_global: int
    upload_window_seconds: int
    sse_heartbeat_seconds: float
    # Admin is accepted only from the laptop itself. This is not configurable on purpose:
    # opening it to the hotspot would let a customer see everyone else's files.
    admin_hosts: tuple[str, ...]
    soffice_bin: str
    log_max_bytes: int
    log_backups: int
    check_only: bool


def default_settings(data_dir: Path | None = None) -> Settings:
    return Settings(
        host="0.0.0.0",
        port=8088,
        data_dir=(data_dir or Path("data")).expanduser().resolve(),
        printer="MF3010",
        max_upload_bytes=64 * 1024 * 1024,
        min_free_bytes=512 * 1024 * 1024,
        max_sheets=400,
        max_copies=100,
        office_timeout_seconds=120,
        print_poll_seconds=2,
        print_give_up_seconds=1200,
        print_missing_grace_seconds=15,
        uploads_per_ip=30,
        uploads_global=60,
        upload_window_seconds=600,
        sse_heartbeat_seconds=20,
        admin_hosts=("127.0.0.1", "::1", "::ffff:127.0.0.1"),
        soffice_bin="soffice",
        log_max_bytes=1_000_000,
        log_backups=3,
        check_only=False,
    )


def load_settings(argv: list[str] | None = None) -> Settings:
    args = list(sys.argv[1:] if argv is None else argv)
    check_only = _check_flag(args)
    loaded = _overlay(default_settings(), _toml_values(Path("printo.toml")), os.environ)
    sane = _require_sane(loaded)
    return replace(sane, check_only=check_only)


def _check_flag(args: list[str]) -> bool:
    if not args:
        return False
    if args == ["--check"]:
        return True
    raise SystemExit("Start printO with no options. Use --check to see whether the printer is ready.")


def _toml_values(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            loaded = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        raise SystemExit("The settings file printo.toml couldn't be read.") from None
    if not isinstance(loaded, dict):
        raise SystemExit("The settings file printo.toml couldn't be read.")
    return loaded


def _overlay(settings: Settings, file_values: dict, env: object) -> Settings:
    values = {name: getattr(settings, name) for name in _ENV}
    for name in _ENV:
        if name in file_values:
            values[name] = file_values[name]
        env_name = _ENV[name]
        if env_name in env:  # type: ignore[operator]
            values[name] = env[env_name]  # type: ignore[index]
    try:
        return replace(
            settings,
            host=str(values["host"]).strip(),
            port=int(values["port"]),
            data_dir=Path(str(values["data_dir"])).expanduser().resolve(),
            printer=str(values["printer"]).strip(),
            max_upload_bytes=int(values["max_upload_bytes"]),
            min_free_bytes=int(values["min_free_bytes"]),
            max_sheets=int(values["max_sheets"]),
            max_copies=int(values["max_copies"]),
            office_timeout_seconds=int(values["office_timeout_seconds"]),
            print_poll_seconds=float(values["print_poll_seconds"]),
            print_give_up_seconds=float(values["print_give_up_seconds"]),
            print_missing_grace_seconds=float(values["print_missing_grace_seconds"]),
            uploads_per_ip=int(values["uploads_per_ip"]),
            uploads_global=int(values["uploads_global"]),
            upload_window_seconds=int(values["upload_window_seconds"]),
            soffice_bin=str(values["soffice_bin"]).strip() or "soffice",
        )
    except (TypeError, ValueError):
        raise SystemExit("One of the settings isn't a number printO can use.") from None


def _require_sane(settings: Settings) -> Settings:
    if not settings.host or any(ch.isspace() for ch in settings.host):
        _bad("host")
    if not 1 <= settings.port <= 65535:
        _bad("port")
    if not _PRINTER.fullmatch(settings.printer):
        _bad("printer")
    if settings.data_dir == Path("/") or len(settings.data_dir.parts) < 2:
        _bad("data directory")
    _positive("max upload size", settings.max_upload_bytes)
    _positive("free space reserve", settings.min_free_bytes)
    _positive("max sheets", settings.max_sheets)
    _positive("max copies", settings.max_copies)
    if settings.office_timeout_seconds < 5 or settings.print_give_up_seconds < 5:
        _bad("a timeout")
    if settings.print_poll_seconds <= 0 or settings.print_missing_grace_seconds <= 0:
        _bad("a timeout")
    _positive("uploads per phone", settings.uploads_per_ip)
    _positive("uploads overall", settings.uploads_global)
    _positive("upload window", settings.upload_window_seconds)
    return settings


def _positive(name: str, value: int) -> None:
    if value < 1:
        _bad(name)


def _bad(name: str) -> None:
    raise SystemExit(f"The setting for {name} isn't usable.")
