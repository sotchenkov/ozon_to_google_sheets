from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from ozon_to_google_sheets.models import (
    TRANSACTION_SHEET_HEADER,
    AccrualPage,
    parse_accrual_types,
    parse_posting_accruals,
)
from ozon_to_google_sheets.parser import AccrualTransformer

JsonFixtureLoader = Callable[[str], dict[str, Any]]


def test_ordinary_operation_maps_current_commission_fields(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    page = AccrualPage.from_api(load_json_fixture("ordinary_operation.json"))

    rows = AccrualTransformer().transform(page.accruals, (), ())

    assert len(rows) == 1
    row = rows[0]
    assert row.operation_id == 910001
    assert row.operation_date == "2026-08-20"
    assert row.posting_number == "posting-test-0001"
    assert row.sku == 100001
    assert row.count is None
    assert row.accruals_for_sale == Decimal("100.00")
    assert row.sale_commission_percents == "12.5%"
    assert row.sale_commission == Decimal("-12.50")
    assert row.logistics == Decimal("-5.00")
    assert row.unrecognized_accruals == Decimal("0")
    assert row.amount == Decimal("82.50")

    sheet_values = dict(zip(TRANSACTION_SHEET_HEADER, row.as_list(), strict=True))
    assert sheet_values["ID операции"] == 910001
    assert sheet_values["Дата начисления"] == "2026-08-20"
    assert sheet_values["Тип начисления"] == "POSTING"
    assert sheet_values["Номер отправления или идентификатор услуги"] == "posting-test-0001"
    assert sheet_values["SKU"] == 100001
    assert sheet_values["Количество"] is None
    assert sheet_values["Выручка"] == 100.0
    assert sheet_values["Ставка комиссии"] == "12.5%"
    assert sheet_values["Комиссия Ozon"] == -12.5
    assert sheet_values["Итого"] == 82.5


def test_multiple_products_keep_quantities_and_parent_total_once(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    page = AccrualPage.from_api(load_json_fixture("multiple_products.json"))
    posting_accruals = parse_posting_accruals(load_json_fixture("quantity_greater_than_one.json"))

    rows = AccrualTransformer().transform(page.accruals, (), posting_accruals)

    assert [row.sku for row in rows] == [100002, 100003]
    assert [row.count for row in rows] == [3, 2]
    assert [row.amount for row in rows] == [Decimal("228.00"), Decimal("0")]
    assert sum(row.amount for row in rows) == Decimal("228.00")


def test_commissions_and_services_map_to_stable_sheet_columns(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    page = AccrualPage.from_api(load_json_fixture("fees_and_services.json"))
    accrual_types = parse_accrual_types(load_json_fixture("accrual_types.json"))

    rows = AccrualTransformer().transform(page.accruals, accrual_types, ())

    assert len(rows) == 1
    row = rows[0]
    assert row.accruals_for_sale == Decimal("100.00")
    assert row.sale_commission == Decimal("-11.50")
    assert row.logistics == Decimal("-5.00")
    assert row.last_mile == Decimal("-2.00")
    assert row.returns_and_cancellations == Decimal("-1.00")
    assert row.reverse_logistics == Decimal("-9.00")
    assert row.amount == Decimal("71.50")


def test_return_and_cancellation_share_one_business_category(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    return_page = AccrualPage.from_api(load_json_fixture("return_operation.json"))
    cancellation_page = AccrualPage.from_api(load_json_fixture("cancellation_operation.json"))
    accrual_types = parse_accrual_types(load_json_fixture("accrual_types.json"))

    rows = AccrualTransformer().transform(
        (*return_page.accruals, *cancellation_page.accruals),
        accrual_types,
        (),
    )

    assert [row.operation_id for row in rows] == [910030, 910031]
    assert rows[0].returns_and_cancellations == Decimal("-18.00")
    assert rows[1].returns_and_cancellations == Decimal("-7.00")


def test_missing_optional_fields_receive_documented_defaults(
    load_json_fixture: JsonFixtureLoader,
) -> None:
    page = AccrualPage.from_api(load_json_fixture("missing_fields.json"))

    rows = AccrualTransformer().transform(page.accruals, (), ())

    assert page.last_id == ""
    assert page.accruals[0].accrued_category == ""
    assert page.accruals[0].total_amount.amount == Decimal("0")
    assert rows[0].operation_id == 910040
    assert rows[0].posting_number == "910040"
    assert rows[0].sku is None
    assert rows[0].count is None
    assert rows[0].amount == Decimal("0")


def test_empty_response_produces_no_rows(load_json_fixture: JsonFixtureLoader) -> None:
    page = AccrualPage.from_api(load_json_fixture("empty_response.json"))

    assert page.accruals == ()
    assert AccrualTransformer().transform(page.accruals, (), ()) == []
