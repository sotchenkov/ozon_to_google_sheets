"""Application configuration loaded explicitly from environment values."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_OZON_ENDPOINT = "https://api-seller.ozon.ru/v3/finance/transaction/list"
DEFAULT_GOOGLE_SHEET_NAME = "testsheet"
REQUIRED_ENVIRONMENT_VARIABLES = (
    "OZON_TOKEN",
    "OZON_CLIENT_ID",
    "GOOGLE_CREDENTIALS_PATH",
)


class ConfigError(ValueError):
    """Raised when required application configuration is missing."""


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


def load_config(
    env_file: Path = Path(".env"),
    *,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    """Load configuration from a dotenv file and the process environment."""

    file_values = {
        key: value
        for key, value in dotenv_values(env_file).items()
        if value is not None
    }
    values = {**file_values, **(os.environ if environ is None else environ)}
    missing = [name for name in REQUIRED_ENVIRONMENT_VARIABLES if not values.get(name)]
    if missing:
        names = ", ".join(missing)
        raise ConfigError(f"Missing required environment variables: {names}")

    return AppConfig(
        ozon_token=values["OZON_TOKEN"],
        ozon_client_id=values["OZON_CLIENT_ID"],
        google_credentials=Path(values["GOOGLE_CREDENTIALS_PATH"]),
    )
