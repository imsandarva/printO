"""Logs go to the data folder and to the terminal. They rotate, and they never include file contents."""

import logging
from logging.handlers import RotatingFileHandler

from printo.config import Settings


def setup_logging(settings: Settings) -> None:
    path = settings.data_dir / "logs" / "printo.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("printo")
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(path, maxBytes=settings.log_max_bytes, backupCount=settings.log_backups, encoding="utf-8")
    stream_handler = logging.StreamHandler()
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        log.addHandler(handler)
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    logging.getLogger("PIL").setLevel(logging.WARNING)
