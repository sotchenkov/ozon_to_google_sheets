"""Command-line interface and composition root."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .config import AppConfig
from .google_sheets import GoogleSheetsAdapter
from .logging import configure_file_logging
from .ozon import OzonClient
from .service import SyncService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ozon_token", type=str, required=True)
    parser.add_argument("--ozon_id", type=int, required=True)
    parser.add_argument("--g_cred", type=str, required=True)
    return parser


def parse_config(argv: Sequence[str] | None = None) -> AppConfig:
    args = build_parser().parse_args(argv)
    return AppConfig(
        ozon_token=args.ozon_token,
        ozon_client_id=str(args.ozon_id),
        google_credentials=Path(args.g_cred),
    )


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


def main(argv: Sequence[str] | None = None) -> int:
    run(parse_config(argv))
    return 0
