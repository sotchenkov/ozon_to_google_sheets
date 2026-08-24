from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from ozon_to_google_sheets.models import AccrualPage, Money, parse_accrual_types
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
    assert sheet.rows[0][2] == "posting-test-0001"


def test_service_fetches_catalogue_and_postings_only_when_required(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    accruals = AccrualPage.from_api(load_json_fixture("fees_and_services.json")).accruals
    accrual_types = parse_accrual_types(load_json_fixture("accrual_types.json"))
    ozon = FakeOzonGateway(accruals, accrual_types)
    sheet = FakeOperationsSheet()

    _service(ozon, sheet).run()

    assert [call[0] for call in ozon.calls] == ["accruals", "types", "postings"]
    assert sheet.rows[0][20] == -5.0
    assert sheet.rows[0][21] == -9.0


def test_service_deduplication_keeps_latest_payload(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    original = AccrualPage.from_api(load_json_fixture("ordinary_operation.json")).accruals[0]
    corrected = replace(
        original,
        total_amount=Money(Decimal("99.25"), "RUB"),
    )
    ozon = FakeOzonGateway((original, corrected))
    sheet = FakeOperationsSheet()

    operation_ids = _service(ozon, sheet).run()

    assert operation_ids == [910001]
    assert len(sheet.rows) == 1
    assert sheet.rows[0][22] == 99.25


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


def _service(ozon: FakeOzonGateway, sheet: FakeOperationsSheet) -> SyncService:
    return SyncService(
        ozon=ozon,
        sheet=sheet,
        endpoint=ENDPOINT,
        date_from=date(2026, 8, 20),
        date_to=date(2026, 8, 20),
    )
