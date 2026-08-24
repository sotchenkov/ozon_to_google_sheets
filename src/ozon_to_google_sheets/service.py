"""Application orchestration independent from concrete external adapters."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
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
    def ensure_schema(self) -> None: ...

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
        operation_ids: dict[int, None] = {}
        accrual_types: tuple[AccrualType, ...] | None = None
        completed_through: date | None = None

        self.sheet.ensure_schema()
        for current_day in _date_range(self.date_from, self.date_to):
            try:
                day_ids, accrual_types = self._sync_day(
                    current_day,
                    accrual_types,
                    active_logger,
                )
            except Exception:
                completed_message = (
                    f"Accruals through {completed_through.isoformat()} are already committed. "
                    if completed_through is not None
                    else "No day was committed. "
                )
                active_logger.exception(
                    "Synchronization failed for %s. %sResume with OZON_DATE_FROM=%s",
                    current_day.isoformat(),
                    completed_message,
                    current_day.isoformat(),
                )
                raise
            operation_ids.update(dict.fromkeys(day_ids))
            completed_through = current_day

        return list(operation_ids)

    def _sync_day(
        self,
        current_day: date,
        accrual_types: tuple[AccrualType, ...] | None,
        logger: logging.Logger,
    ) -> tuple[list[int], tuple[AccrualType, ...] | None]:
        accruals = self.ozon.get_accruals(self.endpoint, current_day, current_day)
        if not accruals:
            logger.info(
                "Ozon returned no accruals for %s",
                current_day.isoformat(),
            )
            return [], accrual_types
        unique_accruals = self._deduplicate_accruals(accruals)
        logger.info(
            "Synchronizing %s Ozon accruals for %s",
            len(unique_accruals),
            current_day.isoformat(),
        )
        if accrual_types is None and any(_has_fees(accrual) for accrual in unique_accruals):
            accrual_types = self.ozon.get_accrual_types(self.endpoint)
        posting_numbers = list(
            dict.fromkeys(
                accrual.unit_number
                for accrual in unique_accruals
                if accrual.unit_number and (accrual.posting.products or accrual.item_fees)
            )
        )
        posting_accruals = (
            self.ozon.get_posting_accruals(self.endpoint, posting_numbers)
            if posting_numbers
            else ()
        )
        rows = AccrualTransformer(logger=logger).transform(
            unique_accruals,
            accrual_types or (),
            posting_accruals,
        )
        operation_ids = [accrual.accrual_id for accrual in unique_accruals]
        self.sheet.upsert_rows([row.as_list() for row in rows])
        return operation_ids, accrual_types

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


def _date_range(date_from: date, date_to: date) -> Iterable[date]:
    current_day = date_from
    while current_day <= date_to:
        yield current_day
        current_day += timedelta(days=1)
