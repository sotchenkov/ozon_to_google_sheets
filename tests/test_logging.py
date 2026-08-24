from __future__ import annotations

import logging
from pathlib import Path

from ozon_to_google_sheets.logging import LOGGER_NAME, configure_file_logging


def test_file_logging_creates_parent_and_writes_info_and_warning(tmp_path: Path) -> None:
    log_file = tmp_path / "nested" / "application.log"
    logger = configure_file_logging(log_file)

    try:
        logger.info("synthetic info %s", 21)
        logger.warning("synthetic warning %s", 42)
        for handler in logger.handlers:
            handler.flush()

        assert logger.name == LOGGER_NAME
        assert logger.level == logging.INFO
        assert logger.propagate is False
        assert len(logger.handlers) == 1
        contents = log_file.read_text(encoding="utf-8")
        assert "INFO synthetic info 21" in contents
        assert "WARNING synthetic warning 42" in contents
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()
