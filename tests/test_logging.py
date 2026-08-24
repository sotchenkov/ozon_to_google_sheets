from __future__ import annotations

import logging
from pathlib import Path

from ozon_to_google_sheets.logging import LOGGER_NAME, configure_file_logging


def test_file_logging_creates_parent_and_writes_warning(tmp_path: Path) -> None:
    log_file = tmp_path / "nested" / "application.log"
    logger = configure_file_logging(log_file)

    try:
        logger.warning("synthetic warning %s", 42)
        for handler in logger.handlers:
            handler.flush()

        assert logger.name == LOGGER_NAME
        assert logger.level == logging.WARNING
        assert logger.propagate is False
        assert len(logger.handlers) == 1
        assert "WARNING synthetic warning 42" in log_file.read_text(encoding="utf-8")
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()
