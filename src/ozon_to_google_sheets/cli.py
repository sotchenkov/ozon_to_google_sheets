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
            credentials_path=config.google_credentials,
            credentials_info=config.google_credentials_info,
            spreadsheet_id=config.google_spreadsheet_id,
            worksheet_name=config.google_worksheet_name,
            logger=logger,
        )
        service = SyncService(
            ozon=ozon,
            sheet=sheet,
            endpoint=config.ozon_endpoint,
            date_from=config.date_from,
            date_to=config.date_to,
            logger=logger,
        )
        return service.run()
    finally:
        logger.info("The application has shut down")


def main() -> int:
    run(load_config())
    return 0
