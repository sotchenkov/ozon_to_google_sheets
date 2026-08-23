"""Local entry point and application composition root."""

from __future__ import annotations

from .config import AppConfig, load_config
from .google_sheets import GoogleSheetsAdapter
from .logging import configure_file_logging
from .ozon import OzonClient
from .service import SyncService


def run(config: AppConfig) -> list[int]:
    logger = configure_file_logging(config.log_file)
    logger.info("The application has been started")
    try:
        ozon = OzonClient(config.ozon_token, config.ozon_client_id, logger=logger)
        sheet = GoogleSheetsAdapter.connect(
            config.google_credentials,
            config.google_sheet_name,
            logger=logger,
        )
        service = SyncService(
            ozon=ozon,
            sheet=sheet,
            endpoint=config.ozon_endpoint,
            request_body=config.request_body,
            logger=logger,
        )
        return service.run()
    finally:
        logger.info("The application has shut down")


def main() -> int:
    run(load_config())
    return 0
