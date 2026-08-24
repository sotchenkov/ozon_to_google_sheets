"""Deterministic in-memory substitutes for every external boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import requests

from ozon_to_google_sheets.models import Accrual, AccrualType, PostingAccrual


class FakeResponse:
    """Minimal ``requests.Response`` substitute used by the Ozon client."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: object | None = None,
        json_error: ValueError | None = None,
        text: str = "synthetic response",
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._json_error = json_error
        self.text = text

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHTTPPost:
    """Scripted HTTP callable that records requests and never uses the network."""

    def __init__(
        self,
        outcomes: Sequence[FakeResponse | requests.RequestException],
    ) -> None:
        self._outcomes = iter(outcomes)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            {"url": url, "headers": dict(headers), "json": dict(json), "timeout": timeout}
        )
        try:
            outcome = next(self._outcomes)
        except StopIteration as error:
            raise AssertionError(f"Unexpected HTTP request to {url}") from error
        if isinstance(outcome, requests.RequestException):
            raise outcome
        return outcome


class FakeGspreadClient:
    """Record spreadsheet and worksheet selection without Google credentials."""

    def __init__(self, worksheet: FakeWorksheet) -> None:
        self._worksheet = worksheet
        self.spreadsheet_ids: list[str] = []
        self.worksheet_ids: list[int] = []

    def open_by_key(self, spreadsheet_id: str) -> FakeGspreadClient:
        self.spreadsheet_ids.append(spreadsheet_id)
        return self

    def get_worksheet_by_id(self, worksheet_id: int) -> FakeWorksheet:
        self.worksheet_ids.append(worksheet_id)
        return self._worksheet


class FakeWorksheet:
    """In-memory worksheet with batched write semantics."""

    def __init__(
        self,
        rows: Sequence[Sequence[Any]] | None = None,
        *,
        failure: str | None = None,
    ) -> None:
        self.rows = [list(row) for row in (rows or [])]
        self.failure = failure
        self.get_calls: list[dict[str, str]] = []
        self.batch_update_calls: list[dict[str, Any]] = []

    def get(
        self,
        range_name: str,
        *,
        value_render_option: str,
    ) -> list[list[Any]]:
        self.get_calls.append(
            {
                "range_name": range_name,
                "value_render_option": value_render_option,
            }
        )
        if self.failure == "read":
            raise RuntimeError("fake read failure")
        return [list(row) for row in self.rows]

    def batch_update(
        self,
        data: Sequence[dict[str, Any]],
        *,
        value_input_option: str,
    ) -> None:
        if self.failure == "write":
            raise RuntimeError("fake write failure")
        self.batch_update_calls.append(
            {"data": list(data), "value_input_option": value_input_option}
        )
        for update in data:
            first_row, _ = _range_rows(update["range"])
            for offset, row in enumerate(update["values"]):
                self._set_row(first_row + offset, row)

    def _set_row(self, row_number: int, values: Sequence[Any]) -> None:
        while len(self.rows) < row_number:
            self.rows.append([])
        self.rows[row_number - 1] = list(values)


class FakeOzonGateway:
    """Configurable Ozon gateway for service-level orchestration tests."""

    def __init__(
        self,
        accruals: tuple[Accrual, ...] = (),
        accrual_types: tuple[AccrualType, ...] = (),
        posting_accruals: tuple[PostingAccrual, ...] = (),
        *,
        failures: Mapping[str, Exception] | None = None,
        accruals_by_day: Mapping[date, tuple[Accrual, ...]] | None = None,
        accrual_failures_by_day: Mapping[date, Exception] | None = None,
    ) -> None:
        self._accruals = accruals
        self._accrual_types = accrual_types
        self._posting_accruals = posting_accruals
        self._failures = dict(failures or {})
        self._accruals_by_day = dict(accruals_by_day) if accruals_by_day is not None else None
        self._accrual_failures_by_day = dict(accrual_failures_by_day or {})
        self.calls: list[tuple[Any, ...]] = []

    def get_accruals(
        self,
        endpoint: str,
        date_from: date,
        date_to: date,
    ) -> tuple[Accrual, ...]:
        self.calls.append(("accruals", endpoint, date_from, date_to))
        if error := self._accrual_failures_by_day.get(date_from):
            raise error
        self._raise_for("accruals")
        if self._accruals_by_day is not None:
            if date_from != date_to:
                raise AssertionError("Daily fake requests must use one date")
            return self._accruals_by_day.get(date_from, ())
        return self._accruals

    def get_accrual_types(self, accrual_endpoint: str) -> tuple[AccrualType, ...]:
        self.calls.append(("types", accrual_endpoint))
        self._raise_for("types")
        return self._accrual_types

    def get_posting_accruals(
        self,
        accrual_endpoint: str,
        posting_numbers: Sequence[str],
    ) -> tuple[PostingAccrual, ...]:
        self.calls.append(("postings", accrual_endpoint, tuple(posting_numbers)))
        self._raise_for("postings")
        return self._posting_accruals

    def _raise_for(self, method: str) -> None:
        if error := self._failures.get(method):
            raise error


class FakeOperationsSheet:
    """Recording sheet gateway used by the synchronization service."""

    def __init__(
        self,
        *,
        failure: Exception | None = None,
        schema_failure: Exception | None = None,
    ) -> None:
        self.failure = failure
        self.schema_failure = schema_failure
        self.rows: list[list[Any]] = []
        self.operation_ids: list[int] = []
        self.upsert_batches: list[list[list[Any]]] = []
        self.upsert_calls = 0
        self.ensure_schema_calls = 0

    def ensure_schema(self) -> None:
        self.ensure_schema_calls += 1
        if self.schema_failure is not None:
            raise self.schema_failure

    def upsert_rows(self, data: list[list[Any]]) -> None:
        self.upsert_calls += 1
        if self.failure is not None:
            raise self.failure
        self.upsert_batches.append(data)
        self.rows = data
        self.operation_ids = list(dict.fromkeys(row[0] for row in data))


def _range_rows(range_name: str) -> tuple[int, int]:
    start, end = range_name.split(":")
    return int(start[1:]), int(end[1:])
