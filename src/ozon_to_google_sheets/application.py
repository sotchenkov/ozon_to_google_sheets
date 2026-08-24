"""Environment-driven application composition and process entry point."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from .config import AppConfig, ConfigError, load_config
from .google_sheets import GoogleSheetsAdapter, GoogleSheetsError
from .logging import configure_file_logging
from .models import AccrualIntegrityError, OzonPayloadError
from .ozon import OzonClient, OzonRequestError
from .service import SyncService

EXIT_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_CONFIGURATION_ERROR = 2

class ConcurrentSynchronizationError(RuntimeError):
    """Raised when the same worksheet is already being synchronized locally."""


EXPECTED_RUNTIME_ERRORS = (
    ConcurrentSynchronizationError,
    GoogleSheetsError,
    AccrualIntegrityError,
    OSError,
    OzonPayloadError,
    OzonRequestError,
)


def run(config: AppConfig) -> list[int]:
    logger = configure_file_logging(config.log_file)
    logger.info("The application has been started")
    try:
        with _synchronization_lock(config):
            ozon = OzonClient(config.ozon_token, config.ozon_client_id, logger=logger)
            sheet = GoogleSheetsAdapter.connect(
                credentials_path=config.google_credentials,
                credentials_info=config.google_credentials_info,
                spreadsheet_id=config.google_spreadsheet_id,
                worksheet_id=config.google_worksheet_id,
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
            operation_ids = service.run()
            logger.info(
                "Synchronization completed successfully; Ozon accruals processed: %s",
                len(operation_ids),
            )
            return operation_ids
    finally:
        logger.info("The application has shut down")


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments:
        error_output = sys.stderr if stderr is None else stderr
        print(
            "Error: command-line arguments are not supported; "
            "configure the application through environment variables.",
            file=error_output,
        )
        return EXIT_USAGE_ERROR

    error_output = sys.stderr if stderr is None else stderr
    try:
        config = load_config()
    except ConfigError as error:
        print(f"Configuration error: {error}", file=error_output)
        return EXIT_CONFIGURATION_ERROR

    try:
        operation_ids = run(config)
    except EXPECTED_RUNTIME_ERRORS as error:
        print(f"Synchronization failed: {error}", file=error_output)
        return EXIT_RUNTIME_ERROR

    success_output = sys.stdout if stdout is None else stdout
    print(
        "Synchronization completed successfully. "
        f"Processed Ozon accruals: {len(operation_ids)}.",
        file=success_output,
    )
    return EXIT_SUCCESS


@contextmanager
def _synchronization_lock(config: AppConfig) -> Iterator[None]:
    lock_path = _synchronization_lock_path(config)
    with lock_path.open("a", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            raise ConcurrentSynchronizationError(
                "Another synchronization is already running for this Google "
                "spreadsheet and worksheet. Wait for it to finish before starting a new run."
            ) from error
        yield


def _synchronization_lock_path(config: AppConfig) -> Path:
    sheet_identity = (
        f"{config.google_spreadsheet_id}\0{config.google_worksheet_id}".encode()
    )
    digest = hashlib.sha256(sheet_identity).hexdigest()
    return Path(tempfile.gettempdir()) / f"ozon-to-google-sheets-{digest}.lock"
