"""Domain models used by transaction parsing and sheet output."""

from __future__ import annotations

from dataclasses import astuple, dataclass
from typing import Any


@dataclass(slots=True)
class TransactionRow:
    """One Google Sheets row, in the legacy 23-column order."""

    operation_date: str = ""
    operation_type_name: str = ""
    operation_id: int = 0
    posting_number: str = ""
    order_date: str = ""
    delivery_schema: str = ""
    sku: Any = None
    name: str = ""
    count: int = 1
    accruals_for_sale: float = 0.0
    sale_commission_percents: str = ""
    sale_commission: float = 0.0
    order_assembly: float = 0.0
    shipment_processing: float = 0.0
    highway: float = 0.0
    last_mile: float = 0.0
    reverse_highway: float = 0.0
    refund_processing: float = 0.0
    processing_of_cancelled_or_unclaimed_item: float = 0.0
    processing_of_unbought_item: float = 0.0
    logistics: float = 0.0
    reverse_logistics: float = 0.0
    amount: float = 0.0

    def as_list(self) -> list[Any]:
        """Return values in the stable order expected by the worksheet."""

        return list(astuple(self))
