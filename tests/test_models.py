from __future__ import annotations

from dataclasses import fields
from decimal import Decimal

import pytest

from ozon_to_google_sheets.models import (
    TRANSACTION_COLUMNS,
    TRANSACTION_SHEET_HEADER,
    AccrualPage,
    Money,
    OzonPayloadError,
    TransactionRow,
    parse_accrual_types,
    parse_posting_accruals,
)


def test_accrual_page_parses_products_fees_and_container_fees() -> None:
    page = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 42,
                    "accrued_category": "POSTING",
                    "date": "2026-08-23",
                    "unit_number": "posting-1",
                    "total_amount": {"amount": "80.50", "currency": "RUB"},
                    "posting": {
                        "delivery_schema": "FBO",
                        "delivery_speed": 1,
                        "products": [
                            {
                                "sku": 1001,
                                "commission": {
                                    "commission": {"amount": "-12.25", "currency": "RUB"},
                                    "commission_ratio": "12.25",
                                    "sale_amount": {"amount": "100.00", "currency": "RUB"},
                                },
                                "delivery": {
                                    "services": [
                                        {
                                            "type_id": 7,
                                            "accrued": {"amount": "-7.25", "currency": "RUB"},
                                        }
                                    ],
                                    "total_accrued": {
                                        "amount": "-7.25",
                                        "currency": "RUB",
                                    },
                                },
                            }
                        ],
                    },
                    "item_fees": {
                        "fees": [
                            {
                                "sku": 1001,
                                "fees": [
                                    {
                                        "type_id": 8,
                                        "accrued": {"amount": "-1.00", "currency": "RUB"},
                                    }
                                ],
                            }
                        ]
                    },
                    "container_fees": {
                        "fees": [
                            {
                                "type_id": 9,
                                "accrued": {"amount": "-0.50", "currency": "RUB"},
                            }
                        ]
                    },
                }
            ],
            "last_id": "next-page",
        }
    )

    accrual = page.accruals[0]
    assert accrual.accrual_id == 42
    assert accrual.total_amount.amount == Decimal("80.50")
    assert accrual.posting.products[0].sku == 1001
    assert accrual.posting.products[0].delivery.services[0].type_id == 7
    assert accrual.item_fees[0].fees[0].accrued.amount == Decimal("-1.00")
    assert accrual.container_fees[0].accrued.amount == Decimal("-0.50")
    assert page.last_id == "next-page"


def test_accrual_page_accepts_empty_response() -> None:
    assert AccrualPage.from_api({"accruals": [], "last_id": ""}).accruals == ()


def test_accrual_page_reports_field_path_for_invalid_payload() -> None:
    with pytest.raises(
        OzonPayloadError,
        match=r"response\.accruals\[0\]\.accrual_id must be an integer",
    ):
        AccrualPage.from_api(
            {
                "accruals": [
                    {
                        "accrual_id": None,
                        "date": "2026-08-23",
                        "total_amount": {"amount": "0", "currency": "RUB"},
                    }
                ],
                "last_id": "",
            }
        )


def test_type_and_posting_models_parse_empty_and_populated_responses() -> None:
    types = parse_accrual_types(
        {"accrual_types": [{"id": 7, "name": "LastMileCourier", "description": ""}]}
    )
    postings = parse_posting_accruals(
        {
            "posting_accruals": [
                {
                    "posting_number": "posting-1",
                    "accruals": [
                        {
                            "sku": 1001,
                            "quantity": 3,
                            "type_id": 7,
                            "accrual_date": "2026-08-23",
                            "accrued": {"amount": "-7.25", "currency": "RUB"},
                            "seller_price": {"amount": "100", "currency": "RUB"},
                        }
                    ],
                }
            ]
        }
    )

    assert types[0].type_id == 7
    assert postings[0].quantity == 3
    assert parse_accrual_types({"accrual_types": []}) == ()
    assert parse_posting_accruals({"posting_accruals": []}) == ()


def test_transaction_row_converts_exact_money_for_sheet_transport() -> None:
    row = TransactionRow(accruals_for_sale=Decimal("10.20"), amount=Decimal("9.10"))

    values = row.as_list()

    assert len(values) == 23
    assert values[9] == 10.2
    assert values[22] == 9.1


def test_transaction_columns_match_the_row_model() -> None:
    model_fields = tuple(field.name for field in fields(TransactionRow))

    assert len(TRANSACTION_COLUMNS) == 23
    assert all(column in model_fields for column in TRANSACTION_COLUMNS)
    assert "operation_id" in model_fields
    assert "operation_id" not in TRANSACTION_COLUMNS


def test_transaction_sheet_header_is_the_exact_russian_user_schema() -> None:
    assert TRANSACTION_SHEET_HEADER == (
        "Дата начисления",
        "Тип начисления",
        "Номер отправления или идентификатор услуги",
        "Дата принятия заказа в обработку или оказания услуги",
        "Склад отгрузки",
        "SKU",
        "Артикул",
        "Название товара или услуги",
        "Количество",
        "За продажу или возврат до вычета комиссий и услуг",
        "Ставка комиссии",
        "Комиссия за продажу",
        "Сборка заказа",
        "Обработка отправления",
        "Магистраль",
        "Последняя миля",
        "Обратная магистраль",
        "Обработка возврата",
        "Обработка отменённого или невостребованного товара",
        "Обработка невыкупленного товара",
        "Логистика",
        "Обратная логистика",
        "Итого",
    )
    assert len(TRANSACTION_SHEET_HEADER) == len(TRANSACTION_COLUMNS) == 23


@pytest.mark.parametrize("amount", (True, [], "not-a-decimal"))
def test_money_rejects_invalid_decimal_values(amount: object) -> None:
    with pytest.raises(OzonPayloadError, match=r"money\.amount must be a decimal value"):
        Money.from_api({"amount": amount}, "money")


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        ([], "response must be an object"),
        ({"accruals": {}}, "response.accruals must be an array"),
        (
            {"accruals": [{"accrual_id": True, "date": "2026-08-23"}]},
            r"response.accruals\[0\].accrual_id must be an integer",
        ),
    ),
)
def test_accrual_page_rejects_invalid_container_types(
    payload: object,
    message: str,
) -> None:
    with pytest.raises(OzonPayloadError, match=message):
        AccrualPage.from_api(payload)


@pytest.mark.parametrize(
    ("item", "message"),
    (
        ({"id": "not-an-integer", "name": "Logistic"}, "id must be an integer"),
        ({"id": 1, "name": ""}, "name must be a non-empty string"),
        ({"id": 1, "name": 123}, "name must be a string"),
    ),
)
def test_accrual_types_report_invalid_required_fields(
    item: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(OzonPayloadError, match=message):
        parse_accrual_types({"accrual_types": [item]})
