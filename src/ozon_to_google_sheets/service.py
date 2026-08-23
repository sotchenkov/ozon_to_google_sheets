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
    def get_operation_ids(self) -> list[str]: ...

    def append_rows(self, data: list[list[Any]], operation_ids: list[int]) -> None: ...


@dataclass(slots=True)
class SyncService:
    """Fetch, compare, transform, and append new Ozon accruals."""

    ozon: OzonGateway
    sheet: OperationsSheet
    endpoint: str
    date_from: date
    date_to: date
    logger: logging.Logger | None = None

    def run(self) -> list[int]:
        active_logger = self.logger or logging.getLogger(__name__)
        accruals = self.ozon.get_accruals(self.endpoint, self.date_from, self.date_to)
        new_accruals = self._find_new_accruals(accruals)
        if not new_accruals:
            active_logger.info(
                "No new Ozon accruals from %s through %s",
                self.date_from.isoformat(),
                self.date_to.isoformat(),
            )
            return []

        active_logger.info("Found %s new Ozon accruals", len(new_accruals))
        accrual_types = (
            self.ozon.get_accrual_types(self.endpoint)
            if any(_has_fees(accrual) for accrual in new_accruals)
            else ()
        )
        posting_numbers = [
            accrual.unit_number
            for accrual in new_accruals
            if accrual.unit_number and (accrual.posting.products or accrual.item_fees)
        ]
        posting_accruals = self.ozon.get_posting_accruals(self.endpoint, posting_numbers)
        rows = AccrualTransformer(logger=active_logger).transform(
            new_accruals,
            accrual_types,
            posting_accruals,
        )
        operation_ids = [accrual.accrual_id for accrual in new_accruals]
        self.sheet.append_rows([row.as_list() for row in rows], operation_ids)
        return operation_ids

    def _find_new_accruals(self, accruals: Sequence[Accrual]) -> list[Accrual]:
        existing_ids = set(self.sheet.get_operation_ids())
        seen_ids: set[int] = set()
        result: list[Accrual] = []
        for accrual in sorted(accruals, key=lambda item: (item.date, item.accrual_id)):
            if str(accrual.accrual_id) in existing_ids or accrual.accrual_id in seen_ids:
                continue
            seen_ids.add(accrual.accrual_id)
            result.append(accrual)
        return result


def _has_fees(accrual: Accrual) -> bool:
    return bool(
        accrual.non_item_fee
        or accrual.container_fees
        or any(item.fees for item in accrual.item_fees)
        or any(product.delivery.services for product in accrual.posting.products)
    )
