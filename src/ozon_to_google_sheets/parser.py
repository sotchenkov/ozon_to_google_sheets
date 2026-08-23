"""Deterministically transform Ozon finance accruals into worksheet rows."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence

from .models import (
    Accrual,
    AccrualFee,
    AccrualType,
    PostingAccrual,
    PostingProduct,
    TransactionRow,
)

SERVICE_FIELDS: Mapping[str, str] = {
    # Current /v1/finance/accrual/types names.
    "Fulfillment": "order_assembly",
    "DropoffPVZ": "shipment_processing",
    "DropoffSC": "shipment_processing",
    "DirectFlowTrans": "highway",
    "LastMileCourier": "last_mile",
    "DeliveryToHandoverPlaceByOzon": "last_mile",
    "ReturnFlowTrans": "reverse_highway",
    "ReturnAfterDelivToCustomer": "refund_processing",
    "PickUpPointReturnAcceptance": "refund_processing",
    "ReturnNotDelivToCustomer": "processing_of_cancelled_or_unclaimed_item",
    "Cancellation": "processing_of_cancelled_or_unclaimed_item",
    "ReturnPartGoodsCustomer": "processing_of_unbought_item",
    "Logistic": "logistics",
    "ReturnFlowLogistic": "reverse_logistics",
    # Legacy aliases retained for accounts returning the former system names.
    "MarketplaceServiceItemFulfillment": "order_assembly",
    "MarketplaceServiceItemDropoffPVZ": "shipment_processing",
    "MarketplaceServiceItemDropoffSC": "shipment_processing",
    "MarketplaceServiceItemDirectFlowTrans": "highway",
    "MarketplaceServiceItemDelivToCustomer": "last_mile",
    "MarketplaceServiceItemReturnFlowTrans": "reverse_highway",
    "MarketplaceServiceItemReturnAfterDelivToCustomer": "refund_processing",
    "MarketplaceServiceItemReturnNotDelivToCustomer": (
        "processing_of_cancelled_or_unclaimed_item"
    ),
    "MarketplaceServiceItemReturnPartGoodsCustomer": "processing_of_unbought_item",
    "MarketplaceServiceItemDirectFlowLogistic": "logistics",
    "MarketplaceServiceItemReturnFlowLogistic": "reverse_logistics",
}


class AccrualTransformer:
    """Convert typed API data while preserving the legacy 23-column sheet contract."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def transform(
        self,
        accruals: Sequence[Accrual],
        accrual_types: Sequence[AccrualType],
        posting_accruals: Sequence[PostingAccrual],
    ) -> list[TransactionRow]:
        type_names = {item.type_id: item.name for item in accrual_types}
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

        # The API total belongs to the parent accrual. Store it once so multiple
        # product rows cannot multiply the operation amount in sheet totals.
        rows[0].amount = accrual.total_amount.amount
        return rows

    @staticmethod
    def _base_row(
        accrual: Accrual,
        sku: int | None,
        quantities: Mapping[tuple[str, int], int],
    ) -> TransactionRow:
        operation_date = accrual.date[:10]
        count = quantities.get((accrual.unit_number, sku), 1) if sku is not None else 0
        return TransactionRow(
            operation_date=operation_date,
            operation_type_name=accrual.accrued_category,
            operation_id=accrual.accrual_id,
            posting_number=accrual.unit_number,
            order_date=operation_date,
            delivery_schema=accrual.posting.delivery_schema,
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
                    "Unmapped Ozon accrual type %s (%s) for operation %s",
                    fee.type_id,
                    service_name or "unknown",
                    row.operation_id,
                )
                continue
            setattr(row, field, getattr(row, field) + fee.accrued.amount)


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
