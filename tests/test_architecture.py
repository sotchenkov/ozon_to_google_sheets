from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from ozon_to_google_sheets.config import ConfigError, load_config
from ozon_to_google_sheets.google_sheets import GoogleSheetsAdapter
from ozon_to_google_sheets.models import (
    Accrual,
    AccrualPage,
    AccrualType,
    PostingAccrual,
    parse_accrual_types,
    parse_posting_accruals,
)
from ozon_to_google_sheets.service import SyncService


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
                "GOOGLE_WORKSHEET_NAME=Operations",
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
    assert config.google_worksheet_name == "Operations"
    assert config.date_from == date(2026, 8, 1)
    assert config.date_to == date(2026, 8, 23)


def test_config_reports_all_missing_environment_variables(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as error:
        load_config(tmp_path / ".env", environ={})

    assert str(error.value) == (
        "Missing required environment variables: "
        "OZON_TOKEN, OZON_CLIENT_ID, GOOGLE_SPREADSHEET_ID, GOOGLE_WORKSHEET_NAME, "
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
            "GOOGLE_WORKSHEET_NAME": "Operations",
        },
        current_date=date(2026, 8, 23),
    )

    assert config.google_credentials is None
    assert config.google_credentials_info == {
        "type": "service_account",
        "client_email": "test@example.invalid",
    }


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
        "GOOGLE_WORKSHEET_NAME": "Operations",
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
        "GOOGLE_WORKSHEET_NAME": "Operations",
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
        "GOOGLE_WORKSHEET_NAME": "Operations",
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
        "GOOGLE_WORKSHEET_NAME": "Operations",
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
    accrual_types = parse_accrual_types(
        {
            "accrual_types": [
                {"id": 7, "name": "LastMileCourier"}
            ]
        }
    )
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
    ozon = FakeOzon(accruals, accrual_types, posting_accruals)
    sheet = FakeSheet()
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
    assert len(sheet.rows[0]) == 23
    assert sheet.rows[0][2] == 42
    assert sheet.rows[0][8] == 2


def test_service_stops_before_sheet_upsert_when_ozon_response_is_empty() -> None:
    ozon = FakeOzon((), (), ())
    sheet = FakeSheet()
    service = _service(ozon, sheet)

    assert service.run() == []
    assert ozon.calls == [
        ("accruals", service.endpoint, service.date_from, service.date_to)
    ]
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
    ozon = FakeOzon(page.accruals, (), ())
    sheet = FakeSheet()
    service = _service(ozon, sheet)

    assert service.run() == [42, 43]
    assert ozon.calls == [
        ("accruals", service.endpoint, service.date_from, service.date_to)
    ]
    assert sheet.operation_ids == [42, 43]
    assert len(sheet.rows) == 2
    assert [row[2] for row in sheet.rows] == [42, 43]


def test_google_adapter_updates_existing_rows_and_appends_new_rows() -> None:
    worksheet = FakeWorksheet(existing_ids=["42", "42"])
    adapter = GoogleSheetsAdapter(worksheet)
    updated_rows = [_sheet_row(42, "updated-1"), _sheet_row(42, "updated-2")]
    new_rows = [_sheet_row(43, "new")]

    adapter.upsert_rows([*updated_rows, *new_rows])

    assert worksheet.batch_update_calls == [
        {
            "data": [{"range": "A2:W3", "values": updated_rows}],
            "value_input_option": "USER_ENTERED",
        }
    ]
    assert worksheet.update_calls == [{
        "range_name": "A4:W4",
        "values": new_rows,
        "value_input_option": "USER_ENTERED",
    }]
    assert worksheet.delete_calls == []


def test_google_adapter_removes_surplus_rows_for_updated_operation() -> None:
    worksheet = FakeWorksheet(existing_ids=["42", "42", "42", "43"])
    adapter = GoogleSheetsAdapter(worksheet)
    rows = [_sheet_row(42, "updated"), _sheet_row(43, "unchanged")]

    adapter.upsert_rows(rows)

    assert worksheet.delete_calls == [(3, 4)]
    assert worksheet.update_calls == []


def test_google_adapter_appends_rows_when_updated_operation_grows() -> None:
    worksheet = FakeWorksheet(existing_ids=["42"])
    adapter = GoogleSheetsAdapter(worksheet)
    rows = [_sheet_row(42, "updated"), _sheet_row(42, "new-product")]

    adapter.upsert_rows(rows)

    assert worksheet.batch_update_calls[0]["data"] == [
        {"range": "A2:W2", "values": [rows[0]]}
    ]
    assert worksheet.update_calls == [
        {
            "range_name": "A3:W3",
            "values": [rows[1]],
            "value_input_option": "USER_ENTERED",
        }
    ]


class FakeOzon:
    def __init__(
        self,
        accruals: tuple[Accrual, ...],
        accrual_types: tuple[AccrualType, ...],
        posting_accruals: tuple[PostingAccrual, ...],
    ) -> None:
        self._accruals = accruals
        self._accrual_types = accrual_types
        self._posting_accruals = posting_accruals
        self.calls: list[tuple[Any, ...]] = []

    def get_accruals(
        self,
        endpoint: str,
        date_from: date,
        date_to: date,
    ) -> tuple[Accrual, ...]:
        self.calls.append(("accruals", endpoint, date_from, date_to))
        return self._accruals

    def get_accrual_types(self, accrual_endpoint: str) -> tuple[AccrualType, ...]:
        self.calls.append(("types", accrual_endpoint))
        return self._accrual_types

    def get_posting_accruals(
        self,
        accrual_endpoint: str,
        posting_numbers: list[str],
    ) -> tuple[PostingAccrual, ...]:
        self.calls.append(("postings", accrual_endpoint, tuple(posting_numbers)))
        return self._posting_accruals


class FakeSheet:
    def __init__(self) -> None:
        self.rows: list[list[Any]] = []
        self.operation_ids: list[int] = []
        self.upsert_calls = 0

    def upsert_rows(self, data: list[list[Any]]) -> None:
        self.upsert_calls += 1
        self.rows = data
        self.operation_ids = list(dict.fromkeys(row[2] for row in data))


def _service(ozon: FakeOzon, sheet: FakeSheet) -> SyncService:
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


class FakeWorksheet:
    def __init__(self, existing_ids: list[str] | None = None) -> None:
        self._existing_ids = existing_ids or []
        self.batch_update_calls: list[dict[str, Any]] = []
        self.delete_calls: list[tuple[int, int | None]] = []
        self.update_calls: list[dict[str, Any]] = []

    def col_values(self, col: int) -> list[str]:
        if col == 1:
            row_count = 1 + len(self._existing_ids)
            return ["header", *("existing-row" for _ in range(row_count - 1))]
        if col == 3:
            return ["operation-id", *self._existing_ids]
        return []

    def batch_update(
        self,
        data: list[dict[str, Any]],
        *,
        value_input_option: str,
    ) -> None:
        self.batch_update_calls.append(
            {"data": data, "value_input_option": value_input_option}
        )

    def delete_rows(self, start_index: int, end_index: int | None = None) -> None:
        self.delete_calls.append((start_index, end_index))
        last_index = end_index or start_index
        del self._existing_ids[start_index - 2 : last_index - 1]

    def update(
        self,
        values: list[list[Any]],
        range_name: str,
        *,
        value_input_option: str,
    ) -> None:
        self.update_calls.append({
            "range_name": range_name,
            "values": values,
            "value_input_option": value_input_option,
        })
        self._existing_ids.extend(str(row[2]) for row in values)


def _sheet_row(operation_id: int, marker: str) -> list[Any]:
    return [marker, "", operation_id, *("" for _ in range(20))]
