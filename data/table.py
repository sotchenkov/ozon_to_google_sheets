from dataclasses import dataclass
from typing import Any


@dataclass
class Table:
    operation_date: Any = ''
    operation_type_name: str = ''
    operation_id: int = 0
    posting_number: str = ''
    order_date: Any = ''
    delivery_schema: str = ''
    sku: Any = None
    name: str = ''
    count: int = 1
    accruals_for_sale: float = 0.0
    sale_commission_percents: Any = ''
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
