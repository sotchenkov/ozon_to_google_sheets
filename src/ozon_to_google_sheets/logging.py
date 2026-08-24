"""Explicit runtime logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER_NAME = "ozon_to_google_sheets"


def configure_file_logging(log_file: Path) -> logging.Logger:
    """Create the application logger when a run starts, never on import."""

    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(name)s %(asctime)s %(levelname)s %(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger
