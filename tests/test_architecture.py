from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from ozon_to_google_sheets.cli import parse_config
from ozon_to_google_sheets.google_sheets import GoogleSheetsAdapter
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


def test_cli_preserves_required_arguments() -> None:
    config = parse_config(
        [
            "--ozon_token",
            "token-for-test",
            "--ozon_id",
            "12345",
            "--g_cred",
            "credentials-for-test.json",
        ]
    )

    assert config.ozon_token == "token-for-test"
    assert config.ozon_client_id == "12345"
    assert config.google_credentials == Path("credentials-for-test.json")
    assert config.google_sheet_name == "testsheet"


def test_service_orchestrates_new_operations() -> None:
    payload = {
        "result": {
            "operations": [
                {
                    "operation_date": "2026-08-23T12:00:00.000Z",
                    "operation_type_name": "OperationAgentDeliveredToCustomer",
                    "operation_id": 42,
                    "posting": {
                        "posting_number": "posting-for-test",
                        "delivery_schema": "FBO",
                        "order_date": "2026-08-22T10:00:00.000Z",
                    },
                    "accruals_for_sale": 100.0,
                    "sale_commission": -10.0,
                    "amount": 90.0,
                    "items": [{"sku": 1001, "name": "Synthetic item"}],
                    "services": [
                        {"name": "MarketplaceServiceItemFulfillment", "price": -2.0},
                        {"name": "MarketplaceServiceItemDelivToCustomer", "price": -3.0},
                    ],
                }
            ]
        }
    }
    ozon = FakeOzon(payload)
    sheet = FakeSheet()
    service = SyncService(ozon=ozon, sheet=sheet, endpoint="https://example.invalid/ozon")

    operation_ids = service.run()

    assert operation_ids == [42]
    assert ozon.calls == [("https://example.invalid/ozon", None)]
    assert sheet.operation_ids == [42]
    assert len(sheet.rows[0]) == 23
    assert sheet.rows[0][2] == 42


def test_google_adapter_keeps_legacy_update_range() -> None:
    worksheet = FakeWorksheet()
    adapter = GoogleSheetsAdapter(worksheet)
    rows = [["value"] * 23]

    adapter.append_rows(rows, [42])

    assert worksheet.update_call == {
        "range_name": "A3:W4",
        "values": rows,
        "value_input_option": "USER_ENTERED",
    }


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeOzon:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._response = FakeResponse(payload)
        self.calls: list[tuple[str, Path | None]] = []

    def get_data(self, url: str, request_body: Path | None = None) -> FakeResponse:
        self.calls.append((url, request_body))
        return self._response


class FakeSheet:
    def __init__(self) -> None:
        self.rows: list[list[Any]] = []
        self.operation_ids: list[int] = []

    def get_operation_ids(self) -> list[str]:
        return []

    def append_rows(self, data: list[list[Any]], operation_ids: list[int]) -> None:
        self.rows = data
        self.operation_ids = operation_ids


class FakeWorksheet:
    def __init__(self) -> None:
        self.update_call: dict[str, Any] = {}

    def col_values(self, col: int) -> list[str]:
        return ["header", "existing-row"] if col == 1 else []

    def update(
        self,
        values: list[list[Any]],
        range_name: str,
        *,
        value_input_option: str,
    ) -> None:
        self.update_call = {
            "range_name": range_name,
            "values": values,
            "value_input_option": value_input_option,
        }
