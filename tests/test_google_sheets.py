from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ozon_to_google_sheets import google_sheets
from ozon_to_google_sheets.google_sheets import GoogleSheetsAdapter, GoogleSheetsError


@pytest.mark.parametrize("credential_source", ("path", "content"))
def test_connect_uses_service_account_and_explicit_sheet_selection(
    monkeypatch: pytest.MonkeyPatch,
    credential_source: str,
) -> None:
    worksheet = FakeWorksheet()
    client = FakeClient(worksheet)
    auth_calls: list[tuple[str, object]] = []

    def service_account(*, filename: str) -> FakeClient:
        auth_calls.append(("path", filename))
        return client

    def service_account_from_dict(credentials: object) -> FakeClient:
        auth_calls.append(("content", credentials))
        return client

    monkeypatch.setattr(google_sheets.gspread, "service_account", service_account)
    monkeypatch.setattr(
        google_sheets.gspread,
        "service_account_from_dict",
        service_account_from_dict,
    )
    credentials_path = Path("credentials-for-test.json") if credential_source == "path" else None
    credentials_info = {"type": "service_account"} if credential_source == "content" else None

    adapter = GoogleSheetsAdapter.connect(
        credentials_path=credentials_path,
        credentials_info=credentials_info,
        spreadsheet_id="spreadsheet-for-test",
        worksheet_name="Operations",
    )

    expected_credentials: object = (
        "credentials-for-test.json" if credential_source == "path" else {"type": "service_account"}
    )
    assert auth_calls == [(credential_source, expected_credentials)]
    assert client.spreadsheet_ids == ["spreadsheet-for-test"]
    assert client.worksheet_names == ["Operations"]
    assert adapter.get_operation_ids() == []


def test_connect_wraps_google_errors_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def service_account(*, filename: str) -> FakeClient:
        raise OSError(f"cannot read {filename}")

    monkeypatch.setattr(google_sheets.gspread, "service_account", service_account)

    with pytest.raises(GoogleSheetsError) as error:
        GoogleSheetsAdapter.connect(
            credentials_path=Path("credentials-for-test.json"),
            credentials_info=None,
            spreadsheet_id="spreadsheet-for-test",
            worksheet_name="Operations",
        )

    assert str(error.value) == (
        "Could not connect to Google spreadsheet 'spreadsheet-for-test', worksheet 'Operations'"
    )
    assert "credentials-for-test.json" not in str(error.value)


class FakeClient:
    def __init__(self, worksheet: FakeWorksheet) -> None:
        self._worksheet = worksheet
        self.spreadsheet_ids: list[str] = []
        self.worksheet_names: list[str] = []

    def open_by_key(self, spreadsheet_id: str) -> FakeClient:
        self.spreadsheet_ids.append(spreadsheet_id)
        return self

    def worksheet(self, worksheet_name: str) -> FakeWorksheet:
        self.worksheet_names.append(worksheet_name)
        return self._worksheet


class FakeWorksheet:
    def col_values(self, col: int) -> list[str]:
        return []

    def batch_update(
        self,
        data: list[dict[str, Any]],
        *,
        value_input_option: str,
    ) -> None:
        raise AssertionError("not expected")

    def delete_rows(self, start_index: int, end_index: int | None = None) -> None:
        raise AssertionError("not expected")

    def update(
        self,
        values: list[list[Any]],
        range_name: str,
        *,
        value_input_option: str,
    ) -> None:
        raise AssertionError("not expected")
