"""Transform Ozon transaction payloads into domain rows."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .models import TransactionRow


class TransactionParser:
    """Parse one operation while preserving the current output semantics."""

    def __init__(
        self,
        response: Mapping[str, Any],
        operation_id: int,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._response = response
        self._operation_id = operation_id
        self._logger = logger or logging.getLogger(__name__)

    def parse(self) -> TransactionRow | None:
        for operation in self._response["result"]["operations"]:
            if operation["operation_id"] != self._operation_id:
                continue

            row = TransactionRow()
            try:
                self._parse_head(operation, row)
                self._parse_item(operation, row)
                self._parse_services(operation, row)
            except RuntimeError:
                self._logger.exception("Could not parse operation %s", operation["operation_id"])
                return None

            self._logger.info("Operation %s successfully parsed", operation["operation_id"])
            return row

        return None

    @staticmethod
    def _parse_head(operation: Mapping[str, Any], row: TransactionRow) -> None:
        row.operation_date = operation["operation_date"][:10]
        row.operation_type_name = operation["operation_type_name"]
        row.operation_id = operation["operation_id"]
        row.posting_number = operation["posting"]["posting_number"]
        row.delivery_schema = operation["posting"]["delivery_schema"]
        row.accruals_for_sale = operation["accruals_for_sale"]
        row.sale_commission = operation["sale_commission"]
        row.amount = operation["amount"]

        order_date = operation["posting"]["order_date"]
        row.order_date = order_date[:10] if order_date != "" else row.operation_date

        if row.accruals_for_sale != 0:
            percentage = int(operation["sale_commission"] / row.accruals_for_sale * -100)
            row.sale_commission_percents = f"{percentage}%"

    @staticmethod
    def _parse_item(operation: Mapping[str, Any], row: TransactionRow) -> None:
        if operation["items"]:
            row.sku = operation["items"][0]["sku"]
            row.name = operation["items"][0]["name"]

    @staticmethod
    def _parse_services(operation: Mapping[str, Any], row: TransactionRow) -> None:
        for service in operation["services"]:
            if service["name"] == "MarketplaceServiceItemFulfillment":
                row.order_assembly = service["price"]
            else:
                # The original truthy `or` condition routed every other service here.
                # Preserve that behavior until service mapping is handled as a separate task.
                row.shipment_processing = service["price"]
