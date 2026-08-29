from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import pytest

from ozon_to_google_sheets.models import (
    AccrualIntegrityError,
    AccrualPage,
    parse_accrual_types,
    parse_posting_accruals,
)
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
                    "total_amount": _money("133.00"),
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
    assert [row.amount for row in rows] == [Decimal("133.00"), Decimal("0")]
    assert rows[0].accruals_for_sale == Decimal("110.00")
    assert rows[0].sale_commission == Decimal("-11.00")
    assert rows[0].sale_commission_percents == "10%"
    assert rows[0].logistics == Decimal("-2.00")
    assert rows[0].last_mile == Decimal("-7.00")
    assert rows[0].reverse_logistics == Decimal("-5.00")
    assert rows[0].unrecognized_accruals == Decimal("-9")
    assert rows[1].last_mile == Decimal("-2.00")
    assert (
        "Unmapped Ozon accrual type 99 (FutureOzonService) for operation 42 "
        "was stored as unrecognized accruals"
    ) in caplog.text


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
    assert [row.count for row in rows] == [None, None, None]
    assert rows[0].returns_and_cancellations == Decimal("-12.00")
    assert rows[0].amount == Decimal("-12.00")
    assert rows[1].amount == Decimal("0")
    assert rows[2].amount == Decimal("0")
    assert rows[2].as_list()[3] == "advertising-contract"


def test_transformer_rejects_parent_total_mismatch() -> None:
    accrual = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 44,
                    "date": "2026-08-23",
                    "total_amount": _money("9.00"),
                    "non_item_fee": _fee(1, "-1.00"),
                }
            ]
        }
    ).accruals
    types = parse_accrual_types({"accrual_types": [_type(1, "Logistic")]})

    with pytest.raises(
        AccrualIntegrityError,
        match=r"operation 44 detail total -1\.00.*total_amount 9\.00.*difference 10\.00",
    ):
        AccrualTransformer().transform(accrual, types, ())


def test_transformer_rejects_nonzero_operation_without_monetary_breakdown() -> None:
    accrual = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 45,
                    "date": "2026-08-23",
                    "total_amount": _money("-4.00"),
                }
            ]
        }
    ).accruals

    with pytest.raises(
        AccrualIntegrityError,
        match=r"operation 45 detail total 0.*total_amount -4\.00.*difference -4\.00",
    ):
        AccrualTransformer().transform(accrual, (), ())


def test_transformer_rejects_delivery_breakdown_mismatch() -> None:
    accrual = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 46,
                    "date": "2026-08-23",
                    "total_amount": _money("87.00"),
                    "posting": {
                        "products": [
                            {
                                **_product(
                                    1001,
                                    "100.00",
                                    "-10.00",
                                    "100.00",
                                    "-10.00",
                                    "10",
                                    [(1, "-3.00")],
                                ),
                                "delivery": {
                                    "services": [_fee(1, "-3.00")],
                                    "total_accrued": _money("-5.00"),
                                },
                            }
                        ]
                    },
                }
            ]
        }
    ).accruals
    types = parse_accrual_types({"accrual_types": [_type(1, "Logistic")]})

    with pytest.raises(
        AccrualIntegrityError,
        match=r"operation 46 delivery services total -3\.00.*total_accrued -5\.00.*SKU 1001",
    ):
        AccrualTransformer().transform(accrual, types, ())


def test_transformer_preserves_unknown_type_and_reconciles_total(
    load_json_fixture: Any,
    caplog: Any,
) -> None:
    accrual = AccrualPage.from_api(load_json_fixture("unknown_accrual_type.json")).accruals

    with caplog.at_level(logging.WARNING):
        rows = AccrualTransformer().transform(accrual, (), ())

    assert rows[0].unrecognized_accruals == Decimal("-3.50")
    assert rows[0].amount == Decimal("-3.50")
    assert rows[0].unrecognized_accruals == rows[0].amount
    assert "type 599 (unknown)" in caplog.text


@pytest.mark.parametrize(
    ("type_name", "field"),
    (
        ("Logistic", "logistics"),
        ("LastMileCourier", "last_mile"),
        ("DeliveryToHandoverPlaceByOzon", "last_mile"),
        ("ReturnFlowLogistic", "reverse_logistics"),
        ("PickUpPointReturnAcceptance", "returns_and_cancellations"),
        ("Cancellation", "returns_and_cancellations"),
        ("PayPerClick", "advertising"),
        ("Promotion", "advertising"),
        ("AcceleratedReviewCollection", "advertising"),
        ("PremiumCashbackIndividualPoints", "advertising"),
        ("Acquiring", "acquiring"),
        ("Placements", "storage"),
        ("TemporaryPlacement", "storage"),
        ("ItemPacking", "packaging"),
        ("PackingFee", "packaging"),
        ("PackageCost", "packaging"),
        ("SupplyInbound", "other_services"),
        ("Disposal", "other_services"),
        ("CrossDock", "other_services"),
        ("Compensation", "compensations"),
        ("ItemCompensation", "compensations"),
    ),
)
def test_transformer_maps_every_known_type_to_its_business_category(
    type_name: str,
    field: str,
) -> None:
    accrual = AccrualPage.from_api(
        {
            "accruals": [
                {
                    "accrual_id": 47,
                    "date": "2026-08-23",
                    "total_amount": _money("-1.25"),
                    "non_item_fee": _fee(1, "-1.25"),
                }
            ]
        }
    ).accruals
    types = parse_accrual_types({"accrual_types": [_type(1, type_name)]})

    rows = AccrualTransformer().transform(accrual, types, ())

    assert getattr(rows[0], field) == Decimal("-1.25")
    assert rows[0].unrecognized_accruals == Decimal("0")


def test_transformer_rejects_conflicting_type_catalogue() -> None:
    types = parse_accrual_types(
        {"accrual_types": [_type(1, "Logistic"), _type(1, "FutureOzonService")]}
    )

    with pytest.raises(AccrualIntegrityError, match="type 1 has conflicting names"):
        AccrualTransformer().transform((), types, ())


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
