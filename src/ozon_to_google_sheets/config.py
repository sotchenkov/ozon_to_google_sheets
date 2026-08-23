"""Application configuration without environment or import-time I/O."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_OZON_ENDPOINT = "https://api-seller.ozon.ru/v3/finance/transaction/list"
DEFAULT_GOOGLE_SHEET_NAME = "testsheet"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Values required for one synchronization run."""

    ozon_token: str
    ozon_client_id: str
    google_credentials: Path
    google_sheet_name: str = DEFAULT_GOOGLE_SHEET_NAME
    ozon_endpoint: str = DEFAULT_OZON_ENDPOINT
    request_body: Path | None = None
    log_file: Path = Path("logs/logs.log")
