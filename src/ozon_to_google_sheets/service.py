"""Application orchestration independent from concrete external adapters."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from .models import Accrual, AccrualType, PostingAccrual
from .parser import AccrualTransformer


class OzonGateway(Protocol):
    def get_accruals(
        self,
        endpoint: str,
        date_from: date,
        date_to: date,
    ) -> tuple[Accrual, ...]: ...

    def get_accrual_types(self, accrual_endpoint: str) -> tuple[AccrualType, ...]: ...

    def get_posting_accruals(
        self,
        accrual_endpoint: str,
        posting_numbers: Sequence[str],
    ) -> tuple[PostingAccrual, ...]: ...


class OperationsSheet(Protocol):
    def upsert_rows(self, data: list[list[Any]]) -> None: ...


@dataclass(slots=True)
class SyncService:
    """Fetch, transform, and synchronize Ozon accruals."""

    ozon: OzonGateway
    sheet: OperationsSheet
    endpoint: str
    date_from: date
    date_to: date
    logger: logging.Logger | None = None

    def run(self) -> list[int]:
        active_logger = self.logger or logging.getLogger(__name__)
        accruals = self.ozon.get_accruals(self.endpoint, self.date_from, self.date_to)
        if not accruals:
            active_logger.info(
                "Ozon returned no accruals from %s through %s",
                self.date_from.isoformat(),
                self.date_to.isoformat(),
            )
            return []
        unique_accruals = self._deduplicate_accruals(accruals)
        active_logger.info("Synchronizing %s Ozon accruals", len(unique_accruals))
        accrual_types = (
            self.ozon.get_accrual_types(self.endpoint)
            if any(_has_fees(accrual) for accrual in unique_accruals)
            else ()
        )
        posting_numbers = [
            accrual.unit_number
            for accrual in unique_accruals
            if accrual.unit_number and (accrual.posting.products or accrual.item_fees)
        ]
        posting_accruals = (
            self.ozon.get_posting_accruals(self.endpoint, posting_numbers)
            if posting_numbers
            else ()
        )
        rows = AccrualTransformer(logger=active_logger).transform(
            unique_accruals,
            accrual_types,
            posting_accruals,
        )
        operation_ids = [accrual.accrual_id for accrual in unique_accruals]
        self.sheet.upsert_rows([row.as_list() for row in rows])
        return operation_ids

    @staticmethod
    def _deduplicate_accruals(accruals: Sequence[Accrual]) -> list[Accrual]:
        by_id = {accrual.accrual_id: accrual for accrual in accruals}
        return sorted(by_id.values(), key=lambda item: (item.date, item.accrual_id))


def _has_fees(accrual: Accrual) -> bool:
    return bool(
        accrual.non_item_fee
        or accrual.container_fees
        or any(item.fees for item in accrual.item_fees)
        or any(product.delivery.services for product in accrual.posting.products)
    )
