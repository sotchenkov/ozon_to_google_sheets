from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from ozon_to_google_sheets.models import AccrualPage, parse_accrual_types, parse_posting_accruals
from ozon_to_google_sheets.parser import AccrualTransformer


def test_transformer_emits_every_product_quantity_and_service(caplog: Any) -> None:
    accrual = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 42,
                    "accrued_category": "POSTING",
                    "date": "2026-08-23T12:00:00Z",
                    "unit_number": "posting-1",
                    "total_amount": _money("150.00"),
                    "posting": {
                        "delivery_schema": "FBO",
                        "products": [
                            _product(
                                2002,
                                "60.00",
                                "-6.00",
                                "66.00",
                                "-7.00",
                                "10",
                                [(2, "-1.50"), (2, "-0.50")],
                            ),
                            _product(
                                1001,
                                "100.00",
                                "-10.00",
                                "110.00",
                                "-11.00",
                                "10",
                                [(1, "-2.00"), (2, "-3.00"), (3, "-4.00"), (99, "-9")],
                            ),
                        ],
                    },
                    "container_fees": {"fees": [_fee(4, "-5.00")]},
                }
            ],
            "last_id": "",
        }
    ).accruals[0]
    types = parse_accrual_types(
        {
            "accrual_types": [
                _type(1, "Logistic"),
                _type(2, "LastMileCourier"),
                _type(3, "DeliveryToHandoverPlaceByOzon"),
                _type(4, "ReturnFlowLogistic"),
                _type(99, "FutureOzonService"),
            ]
        }
    )
    posting_accruals = parse_posting_accruals(
        {
            "posting_accruals": [
                _posting("posting-1", 1001, 2),
                _posting("posting-1", 1001, 2),
                _posting("posting-1", 2002, 3),
            ]
        }
    )

    with caplog.at_level(logging.WARNING):
        rows = AccrualTransformer().transform([accrual], types, posting_accruals)

    assert [row.sku for row in rows] == [1001, 2002]
    assert [row.count for row in rows] == [2, 3]
    assert [row.amount for row in rows] == [Decimal("150.00"), Decimal("0")]
    assert rows[0].accruals_for_sale == Decimal("110.00")
    assert rows[0].sale_commission == Decimal("-11.00")
    assert rows[0].sale_commission_percents == "10%"
    assert rows[0].logistics == Decimal("-2.00")
    assert rows[0].last_mile == Decimal("-7.00")
    assert rows[0].reverse_logistics == Decimal("-5.00")
    assert rows[1].last_mile == Decimal("-2.00")
    assert "Unmapped Ozon accrual type 99 (FutureOzonService)" in caplog.text


def test_transformer_handles_item_returns_non_item_and_empty_blocks() -> None:
    page = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 43,
                    "accrued_category": "NON_ITEM",
                    "date": "2026-08-23",
                    "unit_number": "advertising-contract",
                    "total_amount": _money("0"),
                },
                {
                    "accrual_id": 41,
                    "accrued_category": "ITEM",
                    "date": "2026-08-23",
                    "unit_number": "posting-2",
                    "total_amount": _money("-12.00"),
                    "item_fees": {
                        "fees": [
                            {"sku": 3001, "fees": [_fee(5, "-12.00")]},
                            {"sku": 3002, "fees": []},
                        ]
                    },
                },
            ],
            "last_id": "",
        }
    )
    types = parse_accrual_types({"accrual_types": [_type(5, "PickUpPointReturnAcceptance")]})

    rows = AccrualTransformer().transform(page.accruals, types, ())

    assert [row.operation_id for row in rows] == [41, 41, 43]
    assert [row.sku for row in rows] == [3001, 3002, None]
    assert [row.count for row in rows] == [1, 1, 0]
    assert rows[0].refund_processing == Decimal("-12.00")
    assert rows[0].amount == Decimal("-12.00")
    assert rows[1].amount == Decimal("0")
    assert rows[2].amount == Decimal("0")
    assert rows[2].as_list()[3] == "advertising-contract"


def _money(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "RUB"}


def _fee(type_id: int, amount: str) -> dict[str, Any]:
    return {"type_id": type_id, "accrued": _money(amount)}


def _type(type_id: int, name: str) -> dict[str, Any]:
    return {"id": type_id, "name": name, "description": ""}


def _product(
    sku: int,
    sale_amount: str,
    commission: str,
    seller_price: str,
    sale_commission: str,
    ratio: str,
    services: list[tuple[int, str]],
) -> dict[str, Any]:
    return {
        "sku": sku,
        "commission": {
            "commission": _money(commission),
            "commission_ratio": ratio,
            "sale_amount": _money(sale_amount),
            "sale_commission": _money(sale_commission),
            "seller_price": _money(seller_price),
        },
        "delivery": {
            "services": [_fee(type_id, amount) for type_id, amount in services],
            "total_accrued": _money("0"),
        },
    }


def _posting(posting_number: str, sku: int, quantity: int) -> dict[str, Any]:
    return {
        "posting_number": posting_number,
        "accruals": [
            {
                "seller_price": _money("100"),
                "sku": sku,
                "type_id": 1,
                "accrual_date": "2026-08-23",
                "accrued": _money("-1"),
                "quantity": quantity,
            }
        ],
    }
