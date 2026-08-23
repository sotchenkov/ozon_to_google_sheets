"""Google Sheets adapter around gspread."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import gspread

OPERATION_ID_COLUMN = 3
OPERATION_ID_INDEX = OPERATION_ID_COLUMN - 1
FIRST_DATA_ROW = 2
LAST_COLUMN = "W"


class GoogleSheetsError(RuntimeError):
    """Raised when Google Sheets cannot be accessed or updated."""


class Worksheet(Protocol):
    def col_values(self, col: int) -> list[str]: ...

    def batch_update(
        self,
        data: Sequence[dict[str, Any]],
        *,
        value_input_option: str,
    ) -> Any: ...

    def delete_rows(self, start_index: int, end_index: int | None = None) -> Any: ...

    def update(
        self,
        values: Sequence[Sequence[Any]],
        range_name: str,
        *,
        value_input_option: str,
    ) -> Any: ...


class GoogleSheetsAdapter:
    """Upsert transaction rows in one worksheet by Ozon accrual ID."""

    def __init__(self, worksheet: Worksheet, *, logger: logging.Logger | None = None) -> None:
        self._worksheet = worksheet
        self._logger = logger or logging.getLogger(__name__)

    @classmethod
    def connect(
        cls,
        *,
        credentials_path: Path | None,
        credentials_info: Mapping[str, object] | None,
        spreadsheet_id: str,
        worksheet_name: str,
        logger: logging.Logger | None = None,
    ) -> GoogleSheetsAdapter:
        active_logger = logger or logging.getLogger(__name__)
        if (credentials_path is None) == (credentials_info is None):
            raise GoogleSheetsError(
                "Exactly one Google service-account credential source is required"
            )
        try:
            client = (
                gspread.service_account_from_dict(credentials_info)
                if credentials_info is not None
                else gspread.service_account(filename=str(credentials_path))
            )
            worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        except Exception as error:
            message = (
                "Could not connect to Google spreadsheet "
                f"{spreadsheet_id!r}, worksheet {worksheet_name!r}"
            )
            active_logger.exception(message)
            raise GoogleSheetsError(message) from error

        active_logger.info("Success connecting to Google Sheets")
        return cls(worksheet, logger=active_logger)

    def get_operation_ids(self) -> list[str]:
        return self._worksheet.col_values(OPERATION_ID_COLUMN)[1:]

    def _next_row(self) -> int:
        return len(self._worksheet.col_values(1)) + 1

    def upsert_rows(self, data: list[list[Any]]) -> None:
        if not data:
            return

        rows_by_id = _group_rows_by_operation(data)
        existing_rows = _index_existing_rows(self.get_operation_ids())
        replacements: list[tuple[int, list[Any]]] = []
        rows_to_delete: list[int] = []
        rows_to_append: list[list[Any]] = []

        for operation_id, incoming_rows in rows_by_id.items():
            positions = existing_rows.get(operation_id, [])
            common_count = min(len(positions), len(incoming_rows))
            replacements.extend(
                zip(positions[:common_count], incoming_rows[:common_count], strict=True)
            )
            rows_to_delete.extend(positions[common_count:])
            rows_to_append.extend(incoming_rows[common_count:])

        updates = _build_update_ranges(replacements)
        if updates:
            self._worksheet.batch_update(updates, value_input_option="USER_ENTERED")

        for first_row, last_row in _descending_contiguous_ranges(rows_to_delete):
            self._worksheet.delete_rows(first_row, last_row)

        if rows_to_append:
            first_row = self._next_row()
            last_row = first_row + len(rows_to_append) - 1
            self._worksheet.update(
                range_name=f"A{first_row}:{LAST_COLUMN}{last_row}",
                values=rows_to_append,
                value_input_option="USER_ENTERED",
            )

        for operation_id in rows_by_id:
            self._logger.info("Operation %s synchronized with Google Sheets", operation_id)


def _group_rows_by_operation(data: Sequence[list[Any]]) -> dict[str, list[list[Any]]]:
    rows_by_id: dict[str, list[list[Any]]] = {}
    for row in data:
        if len(row) <= OPERATION_ID_INDEX or row[OPERATION_ID_INDEX] in (None, ""):
            raise ValueError("Every transaction row must contain an operation ID")
        operation_id = str(row[OPERATION_ID_INDEX]).strip()
        rows_by_id.setdefault(operation_id, []).append(row)
    return rows_by_id


def _index_existing_rows(operation_ids: Sequence[str]) -> dict[str, list[int]]:
    rows_by_id: dict[str, list[int]] = {}
    for row_number, operation_id in enumerate(operation_ids, start=FIRST_DATA_ROW):
        normalized = operation_id.strip()
        if normalized:
            rows_by_id.setdefault(normalized, []).append(row_number)
    return rows_by_id


def _build_update_ranges(
    replacements: Sequence[tuple[int, list[Any]]],
) -> list[dict[str, Any]]:
    if not replacements:
        return []

    ordered = sorted(replacements, key=lambda item: item[0])
    updates: list[dict[str, Any]] = []
    first_row = previous_row = ordered[0][0]
    values = [ordered[0][1]]
    for row_number, row in ordered[1:]:
        if row_number == previous_row + 1:
            values.append(row)
        else:
            updates.append(
                {"range": f"A{first_row}:{LAST_COLUMN}{previous_row}", "values": values}
            )
            first_row = row_number
            values = [row]
        previous_row = row_number
    updates.append({"range": f"A{first_row}:{LAST_COLUMN}{previous_row}", "values": values})
    return updates


def _descending_contiguous_ranges(row_numbers: Sequence[int]) -> list[tuple[int, int]]:
    ordered = sorted(set(row_numbers), reverse=True)
    if not ordered:
        return []

    ranges: list[tuple[int, int]] = []
    first_row = last_row = ordered[0]
    for row_number in ordered[1:]:
        if row_number == first_row - 1:
            first_row = row_number
        else:
            ranges.append((first_row, last_row))
            first_row = last_row = row_number
    ranges.append((first_row, last_row))
    return ranges
