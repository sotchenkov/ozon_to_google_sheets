"""Application configuration loaded explicitly from environment values."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_OZON_ENDPOINT = "https://api-seller.ozon.ru/v1/finance/accrual/by-day"
DEFAULT_GOOGLE_SHEET_NAME = "testsheet"
EARLIEST_ACCRUAL_DATE = date(2022, 1, 1)
REQUIRED_ENVIRONMENT_VARIABLES = (
    "OZON_TOKEN",
    "OZON_CLIENT_ID",
    "GOOGLE_CREDENTIALS_PATH",
    "OZON_DATE_FROM",
    "OZON_DATE_TO",
)


class ConfigError(ValueError):
    """Raised when required application configuration is missing."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Values required for one synchronization run."""

    ozon_token: str
    ozon_client_id: str
    google_credentials: Path
    date_from: date
    date_to: date
    google_sheet_name: str = DEFAULT_GOOGLE_SHEET_NAME
    ozon_endpoint: str = DEFAULT_OZON_ENDPOINT
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

    date_from = _parse_date("OZON_DATE_FROM", values["OZON_DATE_FROM"])
    date_to = _parse_date("OZON_DATE_TO", values["OZON_DATE_TO"])
    if date_from < EARLIEST_ACCRUAL_DATE:
        raise ConfigError("OZON_DATE_FROM must not be earlier than 2022-01-01")
    if date_from > date_to:
        raise ConfigError("OZON_DATE_FROM must not be later than OZON_DATE_TO")

    return AppConfig(
        ozon_token=values["OZON_TOKEN"],
        ozon_client_id=values["OZON_CLIENT_ID"],
        google_credentials=Path(values["GOOGLE_CREDENTIALS_PATH"]),
        date_from=date_from,
        date_to=date_to,
    )


def _parse_date(name: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ConfigError(f"{name} must use YYYY-MM-DD format") from error
