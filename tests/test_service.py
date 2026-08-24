from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from ozon_to_google_sheets.models import AccrualPage, parse_accrual_types
from ozon_to_google_sheets.service import SyncService
from tests.fakes import FakeOperationsSheet, FakeOzonGateway

ENDPOINT = "https://example.invalid/v1/finance/accrual/by-day"
JsonFixtureLoader = Callable[[str], dict[str, Any]]


def test_service_skips_type_catalogue_for_fee_free_product(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    accruals = AccrualPage.from_api(load_json_fixture("ordinary_operation.json")).accruals
    ozon = FakeOzonGateway(accruals)
    sheet = FakeOperationsSheet()

    operation_ids = _service(ozon, sheet).run()

    assert operation_ids == [910001]
    assert [call[0] for call in ozon.calls] == ["accruals", "postings"]
    assert ozon.calls[1] == ("postings", ENDPOINT, ("posting-test-0001",))
    assert sheet.upsert_calls == 1
    assert sheet.rows[0][0] == 910001
    assert sheet.rows[0][3] == "posting-test-0001"


def test_service_fetches_catalogue_and_postings_only_when_required(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    accruals = AccrualPage.from_api(load_json_fixture("fees_and_services.json")).accruals
    accrual_types = parse_accrual_types(load_json_fixture("accrual_types.json"))
    ozon = FakeOzonGateway(accruals, accrual_types)
    sheet = FakeOperationsSheet()

    _service(ozon, sheet).run()

    assert [call[0] for call in ozon.calls] == ["accruals", "types", "postings"]
    assert sheet.rows[0][12] == -5.0
    assert sheet.rows[0][13] == -9.0


def test_service_deduplication_keeps_latest_payload(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    original = AccrualPage.from_api(load_json_fixture("ordinary_operation.json")).accruals[0]
    corrected = replace(
        original,
        accrued_category="CORRECTED",
    )
    ozon = FakeOzonGateway((original, corrected))
    sheet = FakeOperationsSheet()

    operation_ids = _service(ozon, sheet).run()

    assert operation_ids == [910001]
    assert len(sheet.rows) == 1
    assert sheet.rows[0][2] == "CORRECTED"
    assert sheet.rows[0][15] == 82.5


def test_service_stops_before_sheet_when_type_request_fails(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    accruals = AccrualPage.from_api(load_json_fixture("fees_and_services.json")).accruals
    ozon = FakeOzonGateway(
        accruals,
        failures={"types": RuntimeError("synthetic type failure")},
    )
    sheet = FakeOperationsSheet()

    with pytest.raises(RuntimeError, match="synthetic type failure"):
        _service(ozon, sheet).run()

    assert [call[0] for call in ozon.calls] == ["accruals", "types"]
    assert sheet.upsert_calls == 0


def test_service_propagates_sheet_failure_after_fetching_data(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    accruals = AccrualPage.from_api(load_json_fixture("ordinary_operation.json")).accruals
    ozon = FakeOzonGateway(accruals)
    sheet = FakeOperationsSheet(failure=RuntimeError("synthetic sheet failure"))

    with pytest.raises(RuntimeError, match="synthetic sheet failure"):
        _service(ozon, sheet).run()

    assert [call[0] for call in ozon.calls] == ["accruals", "postings"]
    assert sheet.upsert_calls == 1


def test_service_stops_before_ozon_when_sheet_schema_is_invalid() -> None:
    ozon = FakeOzonGateway()
    sheet = FakeOperationsSheet(
        schema_failure=RuntimeError("synthetic schema failure"),
    )

    with pytest.raises(RuntimeError, match="synthetic schema failure"):
        _service(ozon, sheet).run()

    assert sheet.ensure_schema_calls == 1
    assert sheet.upsert_calls == 0
    assert ozon.calls == []


def test_service_commits_each_backfill_day_independently(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    first = AccrualPage.from_api(load_json_fixture("ordinary_operation.json")).accruals
    second = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 910002,
                    "date": "2026-08-21",
                    "unit_number": "service-test-0002",
                    "total_amount": {"amount": "-2", "currency": "RUB"},
                }
            ]
        }
    ).accruals
    first_day = date(2026, 8, 20)
    second_day = date(2026, 8, 21)
    ozon = FakeOzonGateway(accruals_by_day={first_day: first, second_day: second})
    sheet = FakeOperationsSheet()

    operation_ids = _service(ozon, sheet, date_from=first_day, date_to=second_day).run()

    assert operation_ids == [910001, 910002]
    assert [call for call in ozon.calls if call[0] == "accruals"] == [
        ("accruals", ENDPOINT, first_day, first_day),
        ("accruals", ENDPOINT, second_day, second_day),
    ]
    assert [[row[0] for row in batch] for batch in sheet.upsert_batches] == [
        [910001],
        [910002],
    ]


def test_service_keeps_completed_days_when_later_day_fails(
    load_json_fixture: JsonFixtureLoader,
    caplog: pytest.LogCaptureFixture,
) -> None:
    first_day = date(2026, 8, 20)
    failed_day = date(2026, 8, 21)
    first = AccrualPage.from_api(load_json_fixture("ordinary_operation.json")).accruals
    ozon = FakeOzonGateway(
        accruals_by_day={first_day: first},
        accrual_failures_by_day={failed_day: RuntimeError("synthetic late failure")},
    )
    sheet = FakeOperationsSheet()

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="synthetic late failure"):
        _service(ozon, sheet, date_from=first_day, date_to=failed_day).run()

    assert sheet.upsert_calls == 1
    assert [row[0] for row in sheet.upsert_batches[0]] == [910001]
    assert "Accruals through 2026-08-20 are already committed" in caplog.text
    assert "Resume with OZON_DATE_FROM=2026-08-21" in caplog.text


def test_service_reuses_live_type_catalogue_across_backfill_days(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    first_day = date(2026, 8, 20)
    second_day = date(2026, 8, 21)
    first = AccrualPage.from_api(load_json_fixture("cancellation_operation.json")).accruals
    second = AccrualPage.from_api(load_json_fixture("return_operation.json")).accruals
    types = parse_accrual_types(load_json_fixture("accrual_types.json"))
    ozon = FakeOzonGateway(
        accrual_types=types,
        accruals_by_day={first_day: first, second_day: second},
    )
    sheet = FakeOperationsSheet()

    _service(ozon, sheet, date_from=first_day, date_to=second_day).run()

    assert [call[0] for call in ozon.calls] == [
        "accruals",
        "types",
        "postings",
        "accruals",
        "postings",
    ]
    assert sheet.upsert_calls == 2


def _service(
    ozon: FakeOzonGateway,
    sheet: FakeOperationsSheet,
    *,
    date_from: date = date(2026, 8, 20),
    date_to: date = date(2026, 8, 20),
) -> SyncService:
    return SyncService(
        ozon=ozon,
        sheet=sheet,
        endpoint=ENDPOINT,
        date_from=date_from,
        date_to=date_to,
    )
