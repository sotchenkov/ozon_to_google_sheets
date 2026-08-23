"""Google Sheets adapter around gspread."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import gspread


class Worksheet(Protocol):
    def col_values(self, col: int) -> list[str]: ...

    def update(
        self,
        values: Sequence[Sequence[Any]],
        range_name: str,
        *,
        value_input_option: str,
    ) -> Any: ...


class GoogleSheetsAdapter:
    """Read operation IDs and append transaction rows to one worksheet."""

    def __init__(self, worksheet: Worksheet, *, logger: logging.Logger | None = None) -> None:
        self._worksheet = worksheet
        self._logger = logger or logging.getLogger(__name__)

    @classmethod
    def connect(
        cls,
        credentials: Path,
        sheet_name: str,
        *,
        logger: logging.Logger | None = None,
    ) -> GoogleSheetsAdapter:
        active_logger = logger or logging.getLogger(__name__)
        try:
            client = gspread.service_account(str(credentials))
            worksheet = client.open(sheet_name).sheet1
        except ConnectionError:
            active_logger.exception("Connection error to Google Sheets")
            raise

        active_logger.info("Success connecting to Google Sheets")
        return cls(worksheet, logger=active_logger)

    def get_operation_ids(self) -> list[str]:
        return self._worksheet.col_values(3)[1:]

    def _next_row(self) -> int:
        return len(self._worksheet.col_values(1)) + 1

    def append_rows(self, data: list[list[Any]], operation_ids: list[int]) -> None:
        first_row = self._next_row()
        try:
            # Keep the historical range calculation; sheet logic is outside this task.
            last_row = first_row + len(data)
            self._worksheet.update(
                range_name=f"A{first_row}:W{last_row}",
                values=data,
                value_input_option="USER_ENTERED",
            )
        except RuntimeError:
            for operation_id in operation_ids:
                self._logger.exception(
                    "Could not send an update request to Google Sheets for operation %s",
                    operation_id,
                )
            return

        for operation_id in operation_ids:
            self._logger.info("Operation %s added to Google Sheets", operation_id)
