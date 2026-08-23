from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ozon_to_google_sheets import google_sheets
from ozon_to_google_sheets.google_sheets import (
    SHEET_HEADER,
    GoogleSheetsAdapter,
    GoogleSheetsError,
    GoogleSheetsSchemaError,
)


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
        worksheet_id=0,
    )

    expected_credentials: object = (
        "credentials-for-test.json" if credential_source == "path" else {"type": "service_account"}
    )
    assert auth_calls == [(credential_source, expected_credentials)]
    assert client.spreadsheet_ids == ["spreadsheet-for-test"]
    assert client.worksheet_ids == [0]
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
            worksheet_id=123456,
        )

    assert str(error.value) == (
        "Could not connect to Google spreadsheet 'spreadsheet-for-test', worksheet ID 123456"
    )
    assert "credentials-for-test.json" not in str(error.value)


def test_empty_sheet_writes_header_and_every_product_in_one_batch() -> None:
    worksheet = FakeWorksheet()
    rows = [
        _sheet_row(42, 1001, count=2, marker="first-product"),
        _sheet_row(42, 2002, count=3, marker="second-product"),
    ]

    GoogleSheetsAdapter(worksheet).upsert_rows(rows)

    assert worksheet.get_calls == [
        {"range_name": "A1:W", "value_render_option": "UNFORMATTED_VALUE"}
    ]
    assert worksheet.batch_update_calls == [
        {
            "data": [
                {
                    "range": "A1:W3",
                    "values": [list(SHEET_HEADER), *rows],
                }
            ],
            "value_input_option": "RAW",
        }
    ]
    assert worksheet.batch_clear_calls == []
    assert worksheet.rows == [list(SHEET_HEADER), *rows]


def test_upsert_preserves_partial_rows_and_appends_after_last_used_row() -> None:
    original_partial_row = ["manual note"]
    trailing_partial_row = ["", "keep this row"]
    existing = _sheet_row(42, 1001, count=1, marker="old")
    worksheet = FakeWorksheet(
        [
            list(SHEET_HEADER),
            original_partial_row,
            existing,
            [],
            trailing_partial_row,
        ]
    )
    updated = _sheet_row(42, 1001, count=2, marker="updated")
    appended = _sheet_row(42, 2002, count=3, marker="new")

    GoogleSheetsAdapter(worksheet).upsert_rows([updated, appended])

    assert worksheet.batch_update_calls == [
        {
            "data": [
                {"range": "A3:W3", "values": [updated]},
                {"range": "A6:W6", "values": [appended]},
            ],
            "value_input_option": "RAW",
        }
    ]
    assert worksheet.rows[1] == original_partial_row
    assert worksheet.rows[4] == trailing_partial_row


def test_upsert_clears_duplicates_and_stale_products_idempotently() -> None:
    current = _sheet_row(42, 1001, count=2, marker="old")
    duplicate = _sheet_row(42, 1001, count=2, marker="duplicate")
    stale = _sheet_row(42, 9999, count=1, marker="stale")
    unrelated = _sheet_row(43, 3003, count=4, marker="unrelated")
    worksheet = FakeWorksheet([list(SHEET_HEADER), current, duplicate, stale, unrelated])
    incoming = _sheet_row(42, 1001, count=2, marker="current")
    adapter = GoogleSheetsAdapter(worksheet)

    adapter.upsert_rows([incoming])

    assert worksheet.batch_update_calls == [
        {
            "data": [{"range": "A2:W2", "values": [incoming]}],
            "value_input_option": "RAW",
        }
    ]
    assert worksheet.batch_clear_calls == [["A3:W4"]]
    assert worksheet.rows[4] == unrelated

    adapter.upsert_rows([incoming])

    assert len(worksheet.batch_update_calls) == 1
    assert len(worksheet.batch_clear_calls) == 1
    assert adapter.get_operation_ids() == ["42", "43"]


def test_partial_matching_header_is_completed() -> None:
    row = _sheet_row(42, 1001, count=2)
    worksheet = FakeWorksheet([list(SHEET_HEADER[:4]), row])

    GoogleSheetsAdapter(worksheet).upsert_rows([row])

    assert worksheet.batch_update_calls == [
        {
            "data": [{"range": "A1:W1", "values": [list(SHEET_HEADER)]}],
            "value_input_option": "RAW",
        }
    ]


def test_mismatched_header_stops_before_writing() -> None:
    worksheet = FakeWorksheet([["wrong header"]])

    with pytest.raises(
        GoogleSheetsSchemaError,
        match="Unexpected header in column 1",
    ):
        GoogleSheetsAdapter(worksheet).upsert_rows([_sheet_row(42, 1001)])

    assert worksheet.batch_update_calls == []
    assert worksheet.batch_clear_calls == []


@pytest.mark.parametrize(
    ("row", "message"),
    (
        (["too", "short"], "has 2 columns; expected 23"),
        (["", "", "", *("" for _ in range(20))], "must contain an operation_id"),
    ),
)
def test_invalid_incoming_rows_stop_before_reading(
    row: list[Any],
    message: str,
) -> None:
    worksheet = FakeWorksheet()

    with pytest.raises(GoogleSheetsSchemaError, match=message):
        GoogleSheetsAdapter(worksheet).upsert_rows([row])

    assert worksheet.get_calls == []


def test_duplicate_incoming_stable_key_stops_before_reading() -> None:
    worksheet = FakeWorksheet()
    row = _sheet_row(42, 1001)

    with pytest.raises(GoogleSheetsSchemaError, match="duplicate key"):
        GoogleSheetsAdapter(worksheet).upsert_rows([row, row])

    assert worksheet.get_calls == []


@pytest.mark.parametrize(
    ("failure", "message"),
    (
        ("read", "Could not read transaction rows from Google Sheets"),
        ("write", "Could not write transaction rows to Google Sheets"),
    ),
)
def test_sheet_api_errors_have_clear_context(failure: str, message: str) -> None:
    worksheet = FakeWorksheet(failure=failure)

    with pytest.raises(GoogleSheetsError, match=message):
        GoogleSheetsAdapter(worksheet).upsert_rows([_sheet_row(42, 1001)])


def test_batch_clear_errors_have_clear_context() -> None:
    row = _sheet_row(42, 1001)
    worksheet = FakeWorksheet([list(SHEET_HEADER), row, row], failure="clear")

    with pytest.raises(
        GoogleSheetsError,
        match="Could not clear duplicate or stale Google Sheets rows",
    ):
        GoogleSheetsAdapter(worksheet).upsert_rows([row])


class FakeClient:
    def __init__(self, worksheet: FakeWorksheet) -> None:
        self._worksheet = worksheet
        self.spreadsheet_ids: list[str] = []
        self.worksheet_ids: list[int] = []

    def open_by_key(self, spreadsheet_id: str) -> FakeClient:
        self.spreadsheet_ids.append(spreadsheet_id)
        return self

    def get_worksheet_by_id(self, worksheet_id: int) -> FakeWorksheet:
        self.worksheet_ids.append(worksheet_id)
        return self._worksheet


class FakeWorksheet:
    def __init__(
        self,
        rows: list[list[Any]] | None = None,
        *,
        failure: str | None = None,
    ) -> None:
        self.rows = [list(row) for row in (rows or [])]
        self.failure = failure
        self.get_calls: list[dict[str, str]] = []
        self.batch_update_calls: list[dict[str, Any]] = []
        self.batch_clear_calls: list[list[str]] = []

    def get(
        self,
        range_name: str,
        *,
        value_render_option: str,
    ) -> list[list[Any]]:
        self.get_calls.append(
            {
                "range_name": range_name,
                "value_render_option": value_render_option,
            }
        )
        if self.failure == "read":
            raise RuntimeError("fake read failure")
        return [list(row) for row in self.rows]

    def batch_update(
        self,
        data: list[dict[str, Any]],
        *,
        value_input_option: str,
    ) -> None:
        if self.failure == "write":
            raise RuntimeError("fake write failure")
        self.batch_update_calls.append({"data": data, "value_input_option": value_input_option})
        for update in data:
            first_row, _ = _range_rows(update["range"])
            for offset, row in enumerate(update["values"]):
                self._set_row(first_row + offset, row)

    def batch_clear(self, ranges: list[str]) -> None:
        if self.failure == "clear":
            raise RuntimeError("fake clear failure")
        self.batch_clear_calls.append(ranges)
        for range_name in ranges:
            first_row, last_row = _range_rows(range_name)
            for row_number in range(first_row, last_row + 1):
                self._set_row(row_number, [])

    def _set_row(self, row_number: int, values: list[Any]) -> None:
        while len(self.rows) < row_number:
            self.rows.append([])
        self.rows[row_number - 1] = list(values)


def _sheet_row(
    operation_id: int,
    sku: int | None,
    *,
    count: int = 0,
    marker: str = "",
) -> list[Any]:
    return [marker, "", operation_id, "", "", "", sku, "", count, *("" for _ in range(14))]


def _range_rows(range_name: str) -> tuple[int, int]:
    start, end = range_name.split(":")
    return int(start[1:]), int(end[1:])
