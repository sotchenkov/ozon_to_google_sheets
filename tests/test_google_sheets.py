from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import requests

from ozon_to_google_sheets import google_sheets
from ozon_to_google_sheets.google_sheets import (
    SHEET_HEADER,
    GoogleSheetsAdapter,
    GoogleSheetsError,
    GoogleSheetsSchemaError,
    ReliableHTTPClient,
)
from ozon_to_google_sheets.models import (
    TRANSACTION_COLUMNS,
)
from tests.fakes import FakeGspreadClient, FakeWorksheet


@pytest.mark.parametrize("credential_source", ("path", "content"))
def test_connect_uses_service_account_and_explicit_sheet_selection(
    monkeypatch: pytest.MonkeyPatch,
    credential_source: str,
) -> None:
    worksheet = FakeWorksheet()
    client = FakeGspreadClient(worksheet)
    auth_calls: list[tuple[str, object, object]] = []

    def service_account(*, filename: str, http_client: object) -> FakeGspreadClient:
        auth_calls.append(("path", filename, http_client))
        return client

    def service_account_from_dict(
        credentials: object,
        *,
        http_client: object,
    ) -> FakeGspreadClient:
        auth_calls.append(("content", credentials, http_client))
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
    assert auth_calls == [(credential_source, expected_credentials, ReliableHTTPClient)]
    assert client.spreadsheet_ids == ["spreadsheet-for-test"]
    assert client.worksheet_ids == [0]
    assert adapter.get_operation_ids() == []


def test_connect_wraps_google_errors_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def service_account(*, filename: str, http_client: object) -> FakeGspreadClient:
        assert http_client is ReliableHTTPClient
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


def test_google_http_client_uses_timeouts_and_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _ScriptedSession(
        [
            _google_response(429, retry_after="7"),
            _google_response(200),
        ]
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(google_sheets.time, "sleep", sleep_calls.append)

    response = ReliableHTTPClient(object(), session=session).request(
        "GET",
        "https://sheets.googleapis.test/values",
    )

    assert response.status_code == 200
    assert [call["timeout"] for call in session.calls] == [(5.0, 30.0), (5.0, 30.0)]
    assert sleep_calls == [7.0]


def test_google_http_client_retries_network_and_server_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _ScriptedSession(
        [
            requests.Timeout("synthetic timeout"),
            _google_response(503),
            _google_response(200),
        ]
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(google_sheets.time, "sleep", sleep_calls.append)

    response = ReliableHTTPClient(object(), session=session).request(
        "GET",
        "https://sheets.googleapis.test/values",
    )

    assert response.status_code == 200
    assert len(session.calls) == 3
    assert sleep_calls == [1.0, 2.0]


@pytest.mark.parametrize("status_code", (408, 599))
def test_google_http_client_retries_all_supported_transient_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    session = _ScriptedSession(
        [
            _google_response(status_code),
            _google_response(200),
        ]
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(google_sheets.time, "sleep", sleep_calls.append)

    response = ReliableHTTPClient(object(), session=session).request(
        "GET",
        "https://sheets.googleapis.test/values",
    )

    assert response.status_code == 200
    assert len(session.calls) == 2
    assert sleep_calls == [1.0]


def test_google_http_client_stops_after_retryable_api_error_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _ScriptedSession([_google_response(503) for _ in range(3)])
    sleep_calls: list[float] = []
    monkeypatch.setattr(google_sheets.time, "sleep", sleep_calls.append)

    with pytest.raises(google_sheets.APIError, match="synthetic Google error"):
        ReliableHTTPClient(object(), session=session).request(
            "GET",
            "https://sheets.googleapis.test/values",
        )

    assert len(session.calls) == 3
    assert sleep_calls == [1.0, 2.0]


def test_google_http_client_stops_after_timeout_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _ScriptedSession([requests.Timeout("synthetic timeout") for _ in range(3)])
    sleep_calls: list[float] = []
    monkeypatch.setattr(google_sheets.time, "sleep", sleep_calls.append)

    with pytest.raises(requests.Timeout, match="synthetic timeout"):
        ReliableHTTPClient(object(), session=session).request(
            "GET",
            "https://sheets.googleapis.test/values",
        )

    assert len(session.calls) == 3
    assert sleep_calls == [1.0, 2.0]


def test_google_http_client_does_not_retry_permanent_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _ScriptedSession([_google_response(400)])
    sleep_calls: list[float] = []
    monkeypatch.setattr(google_sheets.time, "sleep", sleep_calls.append)

    with pytest.raises(google_sheets.APIError):
        ReliableHTTPClient(object(), session=session).request(
            "GET",
            "https://sheets.googleapis.test/values",
        )

    assert len(session.calls) == 1
    assert sleep_calls == []


def test_retry_after_http_date_is_bounded() -> None:
    now = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)

    assert (
        google_sheets._retry_delay(
            "Mon, 24 Aug 2026 10:00:12 GMT",
            1,
            now=now,
        )
        == 12.0
    )
    assert (
        google_sheets._retry_delay(
            "Mon, 24 Aug 2026 10:02:00 GMT",
            1,
            now=now,
        )
        == 30.0
    )


@pytest.mark.parametrize(
    ("credentials_path", "credentials_info"),
    (
        (None, None),
        (Path("credentials-for-test.json"), {"type": "service_account"}),
    ),
)
def test_connect_requires_exactly_one_credential_source(
    credentials_path: Path | None,
    credentials_info: dict[str, object] | None,
) -> None:
    with pytest.raises(
        GoogleSheetsError,
        match="Exactly one Google service-account credential source is required",
    ):
        GoogleSheetsAdapter.connect(
            credentials_path=credentials_path,
            credentials_info=credentials_info,
            spreadsheet_id="spreadsheet-for-test",
            worksheet_id=0,
        )


def test_empty_upsert_initializes_header() -> None:
    worksheet = FakeWorksheet()

    GoogleSheetsAdapter(worksheet).upsert_rows([])

    assert worksheet.get_calls == [
        {"range_name": "A1:U", "value_render_option": "UNFORMATTED_VALUE"}
    ]
    assert worksheet.batch_update_calls == [
        {
            "data": [{"range": "A1:U1", "values": [list(SHEET_HEADER)]}],
            "value_input_option": "RAW",
        }
    ]


def test_schema_check_does_not_rewrite_existing_header() -> None:
    worksheet = FakeWorksheet([list(SHEET_HEADER)])

    GoogleSheetsAdapter(worksheet).ensure_schema()

    assert worksheet.batch_update_calls == []


def test_empty_sheet_writes_header_and_every_product_in_one_batch() -> None:
    worksheet = FakeWorksheet()
    rows = [
        _sheet_row(42, 1001, count=2, marker="first-product"),
        _sheet_row(42, 2002, count=3, marker="second-product"),
    ]

    GoogleSheetsAdapter(worksheet).upsert_rows(rows)

    assert worksheet.get_calls == [
        {"range_name": "A1:U", "value_render_option": "UNFORMATTED_VALUE"}
    ]
    assert worksheet.batch_update_calls == [
        {
            "data": [
                {
                    "range": "A1:U3",
                    "values": [list(SHEET_HEADER), *rows],
                }
            ],
            "value_input_option": "RAW",
        }
    ]
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
                {"range": "A3:U3", "values": [updated]},
                {"range": "A6:U6", "values": [appended]},
            ],
            "value_input_option": "RAW",
        }
    ]
    assert worksheet.rows[1] == original_partial_row
    assert worksheet.rows[4] == trailing_partial_row


def test_upsert_clears_existing_count_when_incoming_quantity_is_unknown() -> None:
    count_index = TRANSACTION_COLUMNS.index("count")
    worksheet = FakeWorksheet([list(SHEET_HEADER), _sheet_row(42, 1001, count=2)])
    incoming = _sheet_row(42, 1001, count=None)
    expected = list(incoming)
    expected[count_index] = ""
    adapter = GoogleSheetsAdapter(worksheet)

    adapter.upsert_rows([incoming])

    assert incoming[count_index] is None
    assert worksheet.batch_update_calls == [
        {
            "data": [{"range": "A2:U2", "values": [expected]}],
            "value_input_option": "RAW",
        }
    ]
    assert worksheet.rows[1][count_index] == ""

    adapter.upsert_rows([incoming])

    assert len(worksheet.batch_update_calls) == 1


def test_fake_worksheet_skips_null_values_like_google_values_api() -> None:
    worksheet = FakeWorksheet([["old", 2]])

    worksheet.batch_update(
        [{"range": "A1:B1", "values": [["new", None]]}],
        value_input_option="RAW",
    )

    assert worksheet.rows == [["new", 2]]


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
            "data": [
                {
                    "range": "A2:U4",
                    "values": [
                        incoming,
                        ["" for _ in SHEET_HEADER],
                        ["" for _ in SHEET_HEADER],
                    ],
                }
            ],
            "value_input_option": "RAW",
        }
    ]
    assert worksheet.rows[4] == unrelated

    adapter.upsert_rows([incoming])

    assert len(worksheet.batch_update_calls) == 1
    assert adapter.get_operation_ids() == ["42", "43"]


def test_upsert_groups_disjoint_duplicate_and_stale_ranges() -> None:
    current = _sheet_row(42, 1001, count=2)
    duplicate = _sheet_row(42, 1001, count=2, marker="duplicate")
    unrelated = _sheet_row(43, 3003, count=1)
    stale = _sheet_row(42, 9999, count=1)
    worksheet = FakeWorksheet([list(SHEET_HEADER), current, duplicate, unrelated, stale])

    GoogleSheetsAdapter(worksheet).upsert_rows([current])

    assert worksheet.batch_update_calls == [
        {
            "data": [
                {"range": "A3:U3", "values": [["" for _ in SHEET_HEADER]]},
                {"range": "A5:U5", "values": [["" for _ in SHEET_HEADER]]},
            ],
            "value_input_option": "RAW",
        }
    ]


def test_numeric_sheet_identifiers_use_stable_text_keys() -> None:
    worksheet = FakeWorksheet(
        [
            list(SHEET_HEADER),
            _sheet_row(42, 1001),
            _sheet_row(43, 1002),
        ]
    )
    worksheet.rows[1][0] = 42.0
    worksheet.rows[1][4] = 1001.0

    adapter = GoogleSheetsAdapter(worksheet)
    adapter.upsert_rows([_sheet_row(42, 1001)])

    assert adapter.get_operation_ids() == ["42", "43"]
    assert worksheet.batch_update_calls == [
        {
            "data": [{"range": "A2:U2", "values": [_sheet_row(42, 1001)]}],
            "value_input_option": "RAW",
        }
    ]


def test_partial_matching_header_is_completed() -> None:
    row = _sheet_row(42, 1001, count=2)
    worksheet = FakeWorksheet([list(SHEET_HEADER[:5]), row])

    GoogleSheetsAdapter(worksheet).upsert_rows([row])

    assert worksheet.batch_update_calls == [
        {
            "data": [{"range": "A1:U1", "values": [list(SHEET_HEADER)]}],
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


@pytest.mark.parametrize(
    ("row", "message"),
    (
        (["too", "short"], "has 2 columns; expected 21"),
        (
            ["", *("" for _ in range(20))],
            "must contain an operation_id",
        ),
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


def test_failed_atomic_batch_preserves_all_existing_rows() -> None:
    current = _sheet_row(42, 1001, count=1, marker="current")
    duplicate = _sheet_row(42, 1001, count=1, marker="duplicate")
    stale = _sheet_row(42, 9999, count=1, marker="stale")
    unrelated = _sheet_row(43, 3003, count=4, marker="unrelated")
    original_rows = [list(SHEET_HEADER), current, duplicate, stale, unrelated]
    worksheet = FakeWorksheet(original_rows, failure="write")
    replacement = _sheet_row(42, 1001, count=2, marker="replacement")

    with pytest.raises(GoogleSheetsError, match="Could not write transaction rows"):
        GoogleSheetsAdapter(worksheet).upsert_rows([replacement])

    assert worksheet.rows == original_rows


def test_large_identifiers_are_written_as_text_and_remain_idempotent() -> None:
    operation_id = 9_007_199_254_740_993
    sku = 9_007_199_254_740_995
    row = _sheet_row(operation_id, sku)
    row[0] = operation_id
    row[4] = sku
    worksheet = FakeWorksheet()
    adapter = GoogleSheetsAdapter(worksheet)

    adapter.upsert_rows([row])
    adapter.upsert_rows([row])

    assert worksheet.rows[1][0] == str(operation_id)
    assert worksheet.rows[1][4] == str(sku)
    assert len(worksheet.batch_update_calls) == 1


def test_distinct_accrual_ids_with_the_same_visible_values_do_not_collide() -> None:
    first = _sheet_row(42, 1001, posting_reference="shared-reference")
    second = _sheet_row(43, 1001, posting_reference="shared-reference")
    worksheet = FakeWorksheet()
    adapter = GoogleSheetsAdapter(worksheet)

    adapter.upsert_rows([first, second])
    adapter.upsert_rows([first, second])

    assert worksheet.rows == [list(SHEET_HEADER), first, second]
    assert len(worksheet.batch_update_calls) == 1
    assert adapter.get_operation_ids() == ["42", "43"]


def _sheet_row(
    operation_id: int,
    sku: int | None,
    *,
    count: int | None = 0,
    marker: str = "",
    operation_date: str = "2026-08-23",
    operation_type: str = "POSTING",
    posting_reference: str = "posting-for-test",
) -> list[Any]:
    return [
        str(operation_id),
        operation_date,
        operation_type,
        posting_reference,
        "" if sku is None else str(sku),
        count,
        "",
        marker,
        *("" for _ in range(13)),
    ]


class _ScriptedSession:
    def __init__(self, outcomes: list[requests.Response | requests.RequestException]) -> None:
        self._outcomes = iter(outcomes)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        try:
            outcome = next(self._outcomes)
        except StopIteration as error:
            raise AssertionError(f"Unexpected HTTP request to {url}") from error
        if isinstance(outcome, requests.RequestException):
            raise outcome
        return outcome


def _google_response(status_code: int, *, retry_after: str | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.url = "https://sheets.googleapis.test/values"
    response._content = (
        b'{"value": "ok"}'
        if status_code < 400
        else (
            '{"error": {"code": '
            f'{status_code}, "message": "synthetic Google error", "status": "ERROR"}}'
        ).encode()
    )
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    return response
