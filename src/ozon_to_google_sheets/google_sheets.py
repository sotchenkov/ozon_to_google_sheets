"""Google Sheets adapter around gspread."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import gspread

from .models import TRANSACTION_COLUMNS

SHEET_HEADER = TRANSACTION_COLUMNS
COLUMN_COUNT = len(SHEET_HEADER)
OPERATION_ID_INDEX = SHEET_HEADER.index("operation_id")
SKU_INDEX = SHEET_HEADER.index("sku")
FIRST_DATA_ROW = 2
LAST_COLUMN = "W"
SHEET_RANGE = f"A1:{LAST_COLUMN}"
RowKey = tuple[str, str]


class GoogleSheetsError(RuntimeError):
    """Raised when Google Sheets cannot be accessed or updated."""


class GoogleSheetsSchemaError(GoogleSheetsError):
    """Raised when worksheet or incoming rows do not match the stable schema."""


class Worksheet(Protocol):
    def get(
        self,
        range_name: str,
        *,
        value_render_option: str,
    ) -> Sequence[Sequence[Any]]: ...

    def batch_update(
        self,
        data: Sequence[dict[str, Any]],
        *,
        value_input_option: str,
    ) -> Any: ...

    def batch_clear(self, ranges: Sequence[str]) -> Any: ...


class GoogleSheetsAdapter:
    """Reconcile transaction rows in one worksheet by operation and SKU."""

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
        worksheet_id: int,
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
            worksheet = client.open_by_key(spreadsheet_id).get_worksheet_by_id(worksheet_id)
        except Exception as error:
            message = (
                "Could not connect to Google spreadsheet "
                f"{spreadsheet_id!r}, worksheet ID {worksheet_id}"
            )
            active_logger.exception(message)
            raise GoogleSheetsError(message) from error

        active_logger.info("Success connecting to Google Sheets")
        return cls(worksheet, logger=active_logger)

    def get_operation_ids(self) -> list[str]:
        values = self._read_values()
        return [
            operation_id
            for row in values[FIRST_DATA_ROW - 1 :]
            if (operation_id := _operation_id(row))
        ]

    def upsert_rows(self, data: list[list[Any]]) -> None:
        if not data:
            return

        incoming_rows = _index_incoming_rows(data)
        sheet_values = self._read_values()
        header = sheet_values[0] if sheet_values else []
        replacements: list[tuple[int, list[Any]]] = []
        rows_to_clear: set[int] = set()
        rows_to_append: list[list[Any]] = []

        if _header_needs_update(header):
            replacements.append((1, list(SHEET_HEADER)))

        existing_rows = _index_existing_rows(sheet_values)
        incoming_operation_ids = {key[0] for key in incoming_rows}
        for key, row in incoming_rows.items():
            positions = existing_rows.get(key, [])
            if positions:
                canonical_row = positions[0]
                existing_row = _padded_row(sheet_values[canonical_row - 1])
                if existing_row != row:
                    replacements.append((canonical_row, row))
                rows_to_clear.update(positions[1:])
            else:
                rows_to_append.append(row)

        for key, positions in existing_rows.items():
            if key[0] in incoming_operation_ids and key not in incoming_rows:
                rows_to_clear.update(positions)

        if rows_to_append:
            first_row = max(FIRST_DATA_ROW, _last_nonempty_row(sheet_values) + 1)
            replacements.extend(
                (first_row + offset, row) for offset, row in enumerate(rows_to_append)
            )

        updates = _build_update_ranges(replacements)
        if updates:
            try:
                self._worksheet.batch_update(updates, value_input_option="RAW")
            except Exception as error:
                message = "Could not write transaction rows to Google Sheets"
                self._logger.exception(message)
                raise GoogleSheetsError(message) from error

        clear_ranges = _build_clear_ranges(rows_to_clear)
        if clear_ranges:
            try:
                self._worksheet.batch_clear(clear_ranges)
            except Exception as error:
                message = "Could not clear duplicate or stale Google Sheets rows"
                self._logger.exception(message)
                raise GoogleSheetsError(message) from error

        for operation_id in sorted(incoming_operation_ids):
            self._logger.info("Operation %s synchronized with Google Sheets", operation_id)

    def _read_values(self) -> list[list[Any]]:
        try:
            values = self._worksheet.get(
                SHEET_RANGE,
                value_render_option="UNFORMATTED_VALUE",
            )
        except Exception as error:
            message = "Could not read transaction rows from Google Sheets"
            self._logger.exception(message)
            raise GoogleSheetsError(message) from error
        return [list(row) for row in values]


def _index_incoming_rows(data: Sequence[list[Any]]) -> dict[RowKey, list[Any]]:
    rows_by_key: dict[RowKey, list[Any]] = {}
    for position, source_row in enumerate(data, start=1):
        row = list(source_row)
        if len(row) != COLUMN_COUNT:
            raise GoogleSheetsSchemaError(
                f"Transaction row {position} has {len(row)} columns; expected {COLUMN_COUNT}"
            )
        key = _row_key(row)
        if not key[0]:
            raise GoogleSheetsSchemaError(
                f"Transaction row {position} must contain an operation_id"
            )
        if key in rows_by_key:
            raise GoogleSheetsSchemaError(
                "Transaction rows must have unique operation_id and sku values; "
                f"duplicate key {key!r}"
            )
        rows_by_key[key] = row
    return rows_by_key


def _index_existing_rows(values: Sequence[Sequence[Any]]) -> dict[RowKey, list[int]]:
    rows_by_key: dict[RowKey, list[int]] = {}
    for row_number, row in enumerate(values[FIRST_DATA_ROW - 1 :], start=FIRST_DATA_ROW):
        key = _row_key(row)
        if key[0]:
            rows_by_key.setdefault(key, []).append(row_number)
    return rows_by_key


def _header_needs_update(header: Sequence[Any]) -> bool:
    needs_update = len(header) < COLUMN_COUNT
    for index, expected in enumerate(SHEET_HEADER):
        actual = header[index] if index < len(header) else ""
        if _is_blank(actual):
            needs_update = True
        elif str(actual).strip() != expected:
            raise GoogleSheetsSchemaError(
                f"Unexpected header in column {index + 1}: expected {expected!r}, found {actual!r}"
            )
    return needs_update


def _row_key(row: Sequence[Any]) -> RowKey:
    return (_operation_id(row), _identifier_at(row, SKU_INDEX))


def _operation_id(row: Sequence[Any]) -> str:
    return _identifier_at(row, OPERATION_ID_INDEX)


def _identifier_at(row: Sequence[Any], index: int) -> str:
    if index >= len(row) or _is_blank(row[index]):
        return ""
    value = row[index]
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _padded_row(row: Sequence[Any]) -> list[Any]:
    return [*row[:COLUMN_COUNT], *("" for _ in range(max(0, COLUMN_COUNT - len(row))))]


def _last_nonempty_row(values: Sequence[Sequence[Any]]) -> int:
    return max(
        (row_number for row_number, row in enumerate(values, start=1) if any(map(_has_value, row))),
        default=0,
    )


def _has_value(value: Any) -> bool:
    return not _is_blank(value)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


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
            updates.append({"range": f"A{first_row}:{LAST_COLUMN}{previous_row}", "values": values})
            first_row = row_number
            values = [row]
        previous_row = row_number
    updates.append({"range": f"A{first_row}:{LAST_COLUMN}{previous_row}", "values": values})
    return updates


def _build_clear_ranges(row_numbers: Sequence[int]) -> list[str]:
    ordered = sorted(set(row_numbers))
    if not ordered:
        return []

    ranges: list[tuple[int, int]] = []
    first_row = last_row = ordered[0]
    for row_number in ordered[1:]:
        if row_number == last_row + 1:
            last_row = row_number
        else:
            ranges.append((first_row, last_row))
            first_row = last_row = row_number
    ranges.append((first_row, last_row))
    return [f"A{first_row}:{LAST_COLUMN}{last_row}" for first_row, last_row in ranges]
