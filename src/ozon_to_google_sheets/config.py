"""Application configuration loaded explicitly from environment values."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

DEFAULT_OZON_ENDPOINT = "https://api-seller.ozon.ru/v1/finance/accrual/by-day"
EARLIEST_ACCRUAL_DATE = date(2022, 1, 1)
OZON_TIME_ZONE = ZoneInfo("Europe/Moscow")
REQUIRED_ENVIRONMENT_VARIABLES = (
    "OZON_TOKEN",
    "OZON_CLIENT_ID",
    "GOOGLE_SPREADSHEET_ID",
    "GOOGLE_WORKSHEET_ID",
)


class ConfigError(ValueError):
    """Raised when required application configuration is missing."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Values required for one synchronization run."""

    ozon_token: str
    ozon_client_id: str
    google_credentials: Path | None
    google_credentials_info: Mapping[str, object] | None
    google_spreadsheet_id: str
    google_worksheet_id: int
    date_from: date
    date_to: date
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
        key: value for key, value in dotenv_values(env_file).items() if value is not None
    }
    values = {**file_values, **(os.environ if environ is None else environ)}
    credentials_path = values.get("GOOGLE_CREDENTIALS_PATH", "").strip()
    credentials_json = values.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    missing = [name for name in REQUIRED_ENVIRONMENT_VARIABLES if not values.get(name)]
    if not credentials_path and not credentials_json:
        missing.append("GOOGLE_CREDENTIALS_PATH or GOOGLE_CREDENTIALS_JSON")
    if missing:
        names = ", ".join(missing)
        raise ConfigError(f"Missing required environment variables: {names}")

    if credentials_path and credentials_json:
        raise ConfigError("Set exactly one of GOOGLE_CREDENTIALS_PATH or GOOGLE_CREDENTIALS_JSON")
    credentials_info = _parse_credentials_json(credentials_json) if credentials_json else None

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
        google_credentials=Path(credentials_path) if credentials_path else None,
        google_credentials_info=credentials_info,
        google_spreadsheet_id=values["GOOGLE_SPREADSHEET_ID"].strip(),
        google_worksheet_id=_parse_worksheet_id(values["GOOGLE_WORKSHEET_ID"]),
        date_from=date_from,
        date_to=date_to,
    )


def _parse_date(name: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ConfigError(f"{name} must use YYYY-MM-DD format") from error


def _parse_worksheet_id(value: str) -> int:
    try:
        worksheet_id = int(value)
    except ValueError as error:
        raise ConfigError("GOOGLE_WORKSHEET_ID must be a non-negative integer") from error
    if worksheet_id < 0:
        raise ConfigError("GOOGLE_WORKSHEET_ID must be a non-negative integer")
    return worksheet_id


def _parse_credentials_json(value: str) -> Mapping[str, object]:
    try:
        credentials = json.loads(value)
    except json.JSONDecodeError as error:
        raise ConfigError("GOOGLE_CREDENTIALS_JSON must contain a valid JSON object") from error
    if not isinstance(credentials, dict):
        raise ConfigError("GOOGLE_CREDENTIALS_JSON must contain a valid JSON object")
    return credentials
