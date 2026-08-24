from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from ozon_to_google_sheets.config import ConfigError, load_config
from ozon_to_google_sheets.models import AccrualPage, parse_accrual_types, parse_posting_accruals
from ozon_to_google_sheets.service import SyncService
from tests.fakes import FakeOperationsSheet, FakeOzonGateway


def test_package_imports_have_no_filesystem_side_effects(tmp_path: Path) -> None:
    imports = "; ".join(
        f"import ozon_to_google_sheets.{module}"
        for module in (
            "cli",
            "config",
            "google_sheets",
            "logging",
            "models",
            "ozon",
            "parser",
            "service",
        )
    )

    subprocess.run([sys.executable, "-c", imports], cwd=tmp_path, check=True)

    assert not (tmp_path / "logs").exists()


def test_config_loads_dotenv_with_environment_precedence(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "OZON_TOKEN=token-from-file",
                "OZON_CLIENT_ID=12345",
                "GOOGLE_CREDENTIALS_PATH=credentials-for-test.json",
                "GOOGLE_SPREADSHEET_ID=spreadsheet-for-test",
                "GOOGLE_WORKSHEET_ID=0",
                "OZON_DATE_FROM=2026-08-01",
                "OZON_DATE_TO=2026-08-23",
            )
        ),
        encoding="utf-8",
    )
    config = load_config(
        env_file,
        environ={"OZON_TOKEN": "token-from-environment"},
        current_date=date(2026, 8, 23),
    )

    assert config.ozon_token == "token-from-environment"
    assert config.ozon_client_id == "12345"
    assert config.google_credentials == Path("credentials-for-test.json")
    assert config.google_credentials_info is None
    assert config.google_spreadsheet_id == "spreadsheet-for-test"
    assert config.google_worksheet_id == 0
    assert config.date_from == date(2026, 8, 1)
    assert config.date_to == date(2026, 8, 23)


def test_config_reports_all_missing_environment_variables(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as error:
        load_config(tmp_path / ".env", environ={})

    assert str(error.value) == (
        "Missing required environment variables: "
        "OZON_TOKEN, OZON_CLIENT_ID, GOOGLE_SPREADSHEET_ID, GOOGLE_WORKSHEET_ID, "
        "GOOGLE_CREDENTIALS_PATH or GOOGLE_CREDENTIALS_JSON"
    )


def test_config_accepts_inline_service_account_json(tmp_path: Path) -> None:
    config = load_config(
        tmp_path / ".env",
        environ={
            "OZON_TOKEN": "test-token",
            "OZON_CLIENT_ID": "12345",
            "GOOGLE_CREDENTIALS_JSON": (
                '{"type":"service_account","client_email":"test@example.invalid"}'
            ),
            "GOOGLE_SPREADSHEET_ID": "spreadsheet-for-test",
            "GOOGLE_WORKSHEET_ID": "123456",
        },
        current_date=date(2026, 8, 23),
    )

    assert config.google_credentials is None
    assert config.google_credentials_info == {
        "type": "service_account",
        "client_email": "test@example.invalid",
    }
    assert config.google_worksheet_id == 123456


@pytest.mark.parametrize("worksheet_id", ("Operations", "-1"))
def test_config_rejects_invalid_worksheet_id(
    tmp_path: Path,
    worksheet_id: str,
) -> None:
    environ = {
        "OZON_TOKEN": "test-token",
        "OZON_CLIENT_ID": "12345",
        "GOOGLE_CREDENTIALS_PATH": "credentials-for-test.json",
        "GOOGLE_SPREADSHEET_ID": "spreadsheet-for-test",
        "GOOGLE_WORKSHEET_ID": worksheet_id,
    }

    with pytest.raises(
        ConfigError,
        match="GOOGLE_WORKSHEET_ID must be a non-negative integer",
    ):
        load_config(
            tmp_path / ".env",
            environ=environ,
            current_date=date(2026, 8, 23),
        )


@pytest.mark.parametrize(
    ("credentials", "message"),
    (
        (
            {
                "GOOGLE_CREDENTIALS_PATH": "credentials-for-test.json",
                "GOOGLE_CREDENTIALS_JSON": '{"type":"service_account"}',
            },
            "Set exactly one of GOOGLE_CREDENTIALS_PATH or GOOGLE_CREDENTIALS_JSON",
        ),
        (
            {"GOOGLE_CREDENTIALS_JSON": "not-json"},
            "GOOGLE_CREDENTIALS_JSON must contain a valid JSON object",
        ),
        (
            {"GOOGLE_CREDENTIALS_JSON": "[]"},
            "GOOGLE_CREDENTIALS_JSON must contain a valid JSON object",
        ),
    ),
)
def test_config_rejects_ambiguous_or_invalid_google_credentials(
    tmp_path: Path,
    credentials: dict[str, str],
    message: str,
) -> None:
    environ = {
        "OZON_TOKEN": "test-token",
        "OZON_CLIENT_ID": "12345",
        "GOOGLE_SPREADSHEET_ID": "spreadsheet-for-test",
        "GOOGLE_WORKSHEET_ID": "0",
        **credentials,
    }

    with pytest.raises(ConfigError, match=message):
        load_config(
            tmp_path / ".env",
            environ=environ,
            current_date=date(2026, 8, 23),
        )


@pytest.mark.parametrize(
    ("dates", "expected_from", "expected_to"),
    (
        ({}, date(2026, 8, 22), date(2026, 8, 23)),
        ({"OZON_DATE_FROM": "2026-08-20"}, date(2026, 8, 20), date(2026, 8, 23)),
        ({"OZON_DATE_TO": "2026-08-20"}, date(2026, 8, 20), date(2026, 8, 20)),
    ),
)
def test_config_calculates_daily_sync_period(
    tmp_path: Path,
    dates: dict[str, str],
    expected_from: date,
    expected_to: date,
) -> None:
    environ = {
        "OZON_TOKEN": "test-token",
        "OZON_CLIENT_ID": "12345",
        "GOOGLE_CREDENTIALS_PATH": "credentials-for-test.json",
        "GOOGLE_SPREADSHEET_ID": "spreadsheet-for-test",
        "GOOGLE_WORKSHEET_ID": "0",
        **dates,
    }

    config = load_config(
        tmp_path / ".env",
        environ=environ,
        current_date=date(2026, 8, 23),
    )

    assert config.date_from == expected_from
    assert config.date_to == expected_to


@pytest.mark.parametrize(
    ("date_from", "date_to", "message"),
    (
        ("2026/08/01", "2026-08-23", "OZON_DATE_FROM must use YYYY-MM-DD format"),
        ("2021-12-31", "2026-08-23", "OZON_DATE_FROM must not be earlier than 2022-01-01"),
        ("2026-08-24", "2026-08-23", "OZON_DATE_FROM must not be later than OZON_DATE_TO"),
    ),
)
def test_config_validates_accrual_period(
    tmp_path: Path,
    date_from: str,
    date_to: str,
    message: str,
) -> None:
    environ = {
        "OZON_TOKEN": "test-token",
        "OZON_CLIENT_ID": "12345",
        "GOOGLE_CREDENTIALS_PATH": "credentials-for-test.json",
        "GOOGLE_SPREADSHEET_ID": "spreadsheet-for-test",
        "GOOGLE_WORKSHEET_ID": "0",
        "OZON_DATE_FROM": date_from,
        "OZON_DATE_TO": date_to,
    }

    with pytest.raises(ConfigError, match=message):
        load_config(
            tmp_path / ".env",
            environ=environ,
            current_date=date(2026, 8, 23),
        )


def test_config_rejects_future_period(tmp_path: Path) -> None:
    environ = {
        "OZON_TOKEN": "test-token",
        "OZON_CLIENT_ID": "12345",
        "GOOGLE_CREDENTIALS_PATH": "credentials-for-test.json",
        "GOOGLE_SPREADSHEET_ID": "spreadsheet-for-test",
        "GOOGLE_WORKSHEET_ID": "0",
        "OZON_DATE_FROM": "2026-08-24",
        "OZON_DATE_TO": "2026-08-25",
    }

    with pytest.raises(ConfigError, match="OZON_DATE_TO must not be later than today"):
        load_config(
            tmp_path / ".env",
            environ=environ,
            current_date=date(2026, 8, 23),
        )


def test_service_orchestrates_new_operations() -> None:
    accruals = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 42,
                    "accrued_category": "POSTING",
                    "date": "2026-08-23",
                    "unit_number": "posting-for-test",
                    "total_amount": {"amount": "85", "currency": "RUB"},
                    "posting": {
                        "delivery_schema": "FBO",
                        "products": [
                            {
                                "sku": 1001,
                                "commission": {
                                    "commission": {"amount": "-10", "currency": "RUB"},
                                    "commission_ratio": "10",
                                    "sale_amount": {"amount": "100", "currency": "RUB"},
                                    "sale_commission": {
                                        "amount": "-10",
                                        "currency": "RUB",
                                    },
                                    "seller_price": {
                                        "amount": "100",
                                        "currency": "RUB",
                                    },
                                },
                                "delivery": {
                                    "services": [
                                        {
                                            "type_id": 7,
                                            "accrued": {"amount": "-5", "currency": "RUB"},
                                        }
                                    ]
                                },
                            }
                        ],
                    },
                }
            ],
            "last_id": "",
        }
    ).accruals
    accrual_types = parse_accrual_types({"accrual_types": [{"id": 7, "name": "LastMileCourier"}]})
    posting_accruals = parse_posting_accruals(
        {
            "posting_accruals": [
                {
                    "posting_number": "posting-for-test",
                    "accruals": [
                        {
                            "seller_price": {"amount": "100", "currency": "RUB"},
                            "sku": 1001,
                            "type_id": 7,
                            "accrual_date": "2026-08-23",
                            "accrued": {"amount": "-5", "currency": "RUB"},
                            "quantity": 2,
                        }
                    ],
                }
            ]
        }
    )
    ozon = FakeOzonGateway(accruals, accrual_types, posting_accruals)
    sheet = FakeOperationsSheet()
    endpoint = "https://example.invalid/v1/finance/accrual/by-day"
    service = SyncService(
        ozon=ozon,
        sheet=sheet,
        endpoint=endpoint,
        date_from=date(2026, 8, 23),
        date_to=date(2026, 8, 23),
    )

    operation_ids = service.run()

    assert operation_ids == [42]
    assert ozon.calls == [
        ("accruals", endpoint, date(2026, 8, 23), date(2026, 8, 23)),
        ("types", endpoint),
        ("postings", endpoint, ("posting-for-test",)),
    ]
    assert sheet.operation_ids == [42]
    assert len(sheet.rows[0]) == 24
    assert sheet.rows[0][0] == 42
    assert sheet.rows[0][3] == "posting-for-test"
    assert sheet.rows[0][9] == 2


def test_service_stops_before_sheet_upsert_when_ozon_response_is_empty() -> None:
    ozon = FakeOzonGateway()
    sheet = FakeOperationsSheet()
    service = _service(ozon, sheet)

    assert service.run() == []
    assert ozon.calls == [("accruals", service.endpoint, service.date_from, service.date_to)]
    assert sheet.upsert_calls == 0


def test_service_upserts_existing_and_deduplicates_api_accruals() -> None:
    page = AccrualPage.from_api(
        {
            "accruals": [
                _non_item_accrual(42),
                _non_item_accrual(43),
                _non_item_accrual(43),
            ],
            "last_id": "",
        }
    )
    ozon = FakeOzonGateway(page.accruals)
    sheet = FakeOperationsSheet()
    service = _service(ozon, sheet)

    assert service.run() == [42, 43]
    assert ozon.calls == [("accruals", service.endpoint, service.date_from, service.date_to)]
    assert sheet.operation_ids == [42, 43]
    assert len(sheet.rows) == 2
    assert [row[0] for row in sheet.rows] == [42, 43]
    assert [row[3] for row in sheet.rows] == ["service-contract", "service-contract"]


def _service(ozon: FakeOzonGateway, sheet: FakeOperationsSheet) -> SyncService:
    return SyncService(
        ozon=ozon,
        sheet=sheet,
        endpoint="https://example.invalid/v1/finance/accrual/by-day",
        date_from=date(2026, 8, 23),
        date_to=date(2026, 8, 23),
    )


def _non_item_accrual(accrual_id: int) -> dict[str, Any]:
    return {
        "accrual_id": accrual_id,
        "accrued_category": "NON_ITEM",
        "date": "2026-08-23",
        "unit_number": "service-contract",
        "total_amount": {"amount": "-1", "currency": "RUB"},
    }
