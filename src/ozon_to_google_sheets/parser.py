"""Deterministically transform Ozon finance accruals into worksheet rows."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from .models import (
    Accrual,
    AccrualFee,
    AccrualIntegrityError,
    AccrualType,
    PostingAccrual,
    PostingProduct,
    TransactionRow,
)

DETAIL_FIELDS = (
    "accruals_for_sale",
    "sale_commission",
    "last_mile",
    "refund_processing",
    "processing_of_cancelled_or_unclaimed_item",
    "logistics",
    "reverse_logistics",
    "other_accruals",
)

SERVICE_FIELDS: Mapping[str, str] = {
    # Current /v1/finance/accrual/types names.
    "LastMileCourier": "last_mile",
    "DeliveryToHandoverPlaceByOzon": "last_mile",
    "PickUpPointReturnAcceptance": "refund_processing",
    "Cancellation": "processing_of_cancelled_or_unclaimed_item",
    "Logistic": "logistics",
    "ReturnFlowLogistic": "reverse_logistics",
}


class AccrualTransformer:
    """Convert typed accrual data to the current deterministic sheet format."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def transform(
        self,
        accruals: Sequence[Accrual],
        accrual_types: Sequence[AccrualType],
        posting_accruals: Sequence[PostingAccrual],
    ) -> list[TransactionRow]:
        type_names = _type_names(accrual_types)
        quantities = _posting_quantities(posting_accruals)
        rows: list[TransactionRow] = []
        for accrual in sorted(accruals, key=lambda item: (item.date, item.accrual_id)):
            rows.extend(self._transform_accrual(accrual, type_names, quantities))
        return rows

    def _transform_accrual(
        self,
        accrual: Accrual,
        type_names: Mapping[int, str],
        quantities: Mapping[tuple[str, int], int],
    ) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        rows_by_sku: dict[int, TransactionRow] = {}

        for product in sorted(accrual.posting.products, key=lambda item: item.sku):
            row = self._base_row(accrual, product.sku, quantities)
            self._apply_commission(row, product)
            self._apply_fees(row, product.delivery.services, type_names)
            self._apply_delivery_total(row, product, accrual.accrual_id)
            rows.append(row)
            rows_by_sku.setdefault(product.sku, row)

        for item_fees in sorted(accrual.item_fees, key=lambda item: item.sku):
            row = rows_by_sku.get(item_fees.sku)
            if row is None:
                row = self._base_row(accrual, item_fees.sku, quantities)
                rows.append(row)
                rows_by_sku[item_fees.sku] = row
            self._apply_fees(row, item_fees.fees, type_names)

        if not rows:
            rows.append(self._base_row(accrual, None, quantities))

        if accrual.non_item_fee is not None:
            self._apply_fees(rows[0], (accrual.non_item_fee,), type_names)
        self._apply_fees(rows[0], accrual.container_fees, type_names)

        detail_total = _detail_total(rows)
        if detail_total == 0 and accrual.total_amount.amount != 0 and not _has_details(accrual):
            rows[0].other_accruals = accrual.total_amount.amount
            detail_total = accrual.total_amount.amount
            self._logger.warning(
                "Ozon operation %s has no monetary breakdown; "
                "its total was stored as other accruals",
                accrual.accrual_id,
            )

        if detail_total != accrual.total_amount.amount:
            difference = accrual.total_amount.amount - detail_total
            raise AccrualIntegrityError(
                f"Ozon operation {accrual.accrual_id} detail total {detail_total} "
                f"does not match total_amount {accrual.total_amount.amount}; "
                f"difference {difference}"
            )

        # The API total belongs to the parent accrual. Store it once so multiple
        # product rows cannot multiply the operation amount in sheet totals.
        rows[0].amount = accrual.total_amount.amount
        return rows

    def _base_row(
        self,
        accrual: Accrual,
        sku: int | None,
        quantities: Mapping[tuple[str, int], int],
    ) -> TransactionRow:
        operation_date = accrual.date[:10]
        count = quantities.get((accrual.unit_number, sku)) if sku is not None else None
        if sku is not None and count is None:
            self._logger.warning(
                "Ozon postings have no quantity for operation %s, posting %s, SKU %s; "
                "quantity remains unknown",
                accrual.accrual_id,
                accrual.unit_number or "unknown",
                sku,
            )
        return TransactionRow(
            operation_date=operation_date,
            operation_type_name=accrual.accrued_category,
            operation_id=accrual.accrual_id,
            posting_number=accrual.unit_number or str(accrual.accrual_id),
            sku=sku,
            count=count,
        )

    @staticmethod
    def _apply_commission(row: TransactionRow, product: PostingProduct) -> None:
        commission = product.commission
        row.accruals_for_sale = commission.seller_price.amount
        row.sale_commission = commission.sale_commission.amount
        ratio = commission.commission_ratio.strip()
        if ratio:
            row.sale_commission_percents = ratio if ratio.endswith("%") else f"{ratio}%"

    def _apply_fees(
        self,
        row: TransactionRow,
        fees: Iterable[AccrualFee],
        type_names: Mapping[int, str],
    ) -> None:
        for fee in fees:
            service_name = type_names.get(fee.type_id)
            field = SERVICE_FIELDS.get(service_name or "")
            if field is None:
                self._logger.warning(
                    "Unmapped Ozon accrual type %s (%s) for operation %s "
                    "was stored as other accruals",
                    fee.type_id,
                    service_name or "unknown",
                    row.operation_id,
                )
                field = "other_accruals"
            setattr(row, field, getattr(row, field) + fee.accrued.amount)

    def _apply_delivery_total(
        self,
        row: TransactionRow,
        product: PostingProduct,
        operation_id: int,
    ) -> None:
        total = product.delivery.total_accrued
        if total is None:
            return

        services_total = sum(
            (fee.accrued.amount for fee in product.delivery.services),
            start=Decimal("0"),
        )
        if product.delivery.services:
            if services_total != total.amount:
                raise AccrualIntegrityError(
                    f"Ozon operation {operation_id} delivery services total {services_total} "
                    f"does not match delivery.total_accrued {total.amount} for SKU {product.sku}"
                )
            return

        if total.amount != 0:
            row.other_accruals += total.amount
            self._logger.warning(
                "Ozon operation %s has delivery total %s without service details for SKU %s; "
                "it was stored as other accruals",
                operation_id,
                total.amount,
                product.sku,
            )


def _posting_quantities(
    posting_accruals: Sequence[PostingAccrual],
) -> dict[tuple[str, int], int]:
    quantities: dict[tuple[str, int], int] = {}
    for accrual in posting_accruals:
        key = (accrual.posting_number, accrual.sku)
        quantity = abs(accrual.quantity)
        if quantity > 0:
            quantities[key] = max(quantities.get(key, 0), quantity)
    return quantities


def _type_names(accrual_types: Sequence[AccrualType]) -> dict[int, str]:
    names: dict[int, str] = {}
    for accrual_type in accrual_types:
        existing = names.get(accrual_type.type_id)
        if existing is not None and existing != accrual_type.name:
            raise AccrualIntegrityError(
                f"Ozon accrual type {accrual_type.type_id} has conflicting names "
                f"{existing!r} and {accrual_type.name!r}"
            )
        names[accrual_type.type_id] = accrual_type.name
    return names


def _detail_total(rows: Sequence[TransactionRow]) -> Decimal:
    return sum(
        (getattr(row, field) for row in rows for field in DETAIL_FIELDS),
        start=Decimal("0"),
    )


def _has_details(accrual: Accrual) -> bool:
    return bool(
        accrual.posting.products
        or accrual.item_fees
        or accrual.non_item_fee
        or accrual.container_fees
    )
