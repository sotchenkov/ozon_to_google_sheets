"""Application orchestration independent from concrete external adapters."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .parser import TransactionParser


class Response(Protocol):
    def json(self) -> Mapping[str, Any]: ...


class OzonGateway(Protocol):
    def get_data(self, url: str, request_body: Path | None = None) -> Response: ...


class OperationsSheet(Protocol):
    def get_operation_ids(self) -> list[str]: ...

    def append_rows(self, data: list[list[Any]], operation_ids: list[int]) -> None: ...


@dataclass(slots=True)
class SyncService:
    """Fetch, compare, transform, and append new Ozon operations."""

    ozon: OzonGateway
    sheet: OperationsSheet
    endpoint: str
    request_body: Path | None = None
    logger: logging.Logger | None = None

    def run(self) -> list[int]:
        response = self.ozon.get_data(self.endpoint, self.request_body)
        payload = response.json()
        operation_ids = self._find_new_operation_ids(payload)

        active_logger = self.logger or logging.getLogger(__name__)
        if operation_ids:
            active_logger.info("Found %s new operations", len(operation_ids))
        else:
            active_logger.info("There have been no new operations in the last hour")
            return []

        rows: list[list[Any]] = []
        for operation_id in operation_ids:
            parsed = TransactionParser(payload, operation_id, logger=active_logger).parse()
            if parsed is None:
                raise RuntimeError(f"Operation {operation_id} could not be parsed")
            rows.append(parsed.as_list())

        self.sheet.append_rows(rows, operation_ids)
        return operation_ids

    def _find_new_operation_ids(self, payload: Mapping[str, Any]) -> list[int]:
        existing_ids = self.sheet.get_operation_ids()
        return [
            operation["operation_id"]
            for operation in payload["result"]["operations"]
            if str(operation["operation_id"]) not in existing_ids
        ]
