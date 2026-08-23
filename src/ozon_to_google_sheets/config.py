"""Application configuration loaded explicitly from environment values."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

DEFAULT_OZON_ENDPOINT = "https://api-seller.ozon.ru/v1/finance/accrual/by-day"
DEFAULT_GOOGLE_SHEET_NAME = "testsheet"
EARLIEST_ACCRUAL_DATE = date(2022, 1, 1)
OZON_TIME_ZONE = ZoneInfo("Europe/Moscow")
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
    date_from: date
    date_to: date
    google_sheet_name: str = DEFAULT_GOOGLE_SHEET_NAME
    ozon_endpoint: str = DEFAULT_OZON_ENDPOINT
    log_file: Path = Path("logs/logs.log")


def load_config(
    env_file: Path = Path(".env"),
    *,
    environ: Mapping[str, str] | None = None,
    current_date: date | None = None,
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

    today = current_date or datetime.now(OZON_TIME_ZONE).date()
    configured_from = values.get("OZON_DATE_FROM")
    configured_to = values.get("OZON_DATE_TO")
    date_to = _parse_date("OZON_DATE_TO", configured_to) if configured_to else today
    if date_to > today:
        raise ConfigError("OZON_DATE_TO must not be later than today")

    if configured_from:
        date_from = _parse_date("OZON_DATE_FROM", configured_from)
    elif configured_to:
        date_from = date_to
    else:
        date_from = max(EARLIEST_ACCRUAL_DATE, today - timedelta(days=1))

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
