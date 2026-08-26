"""Resilient adapter for the supported Ozon Seller finance accrual API."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from typing import Any

import requests

from .models import (
    Accrual,
    AccrualPage,
    AccrualType,
    PostingAccrual,
    parse_accrual_types,
    parse_posting_accruals,
)

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_POSTING_BATCH_SIZE = 100
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

PostCallable = Callable[..., requests.Response]
SleepCallable = Callable[[float], None]


class OzonRequestError(RuntimeError):
    """Base error for an unsuccessful Ozon API request."""


class OzonAPIError(OzonRequestError):
    """Raised when Ozon returns a non-successful HTTP status."""


class OzonResponseError(OzonRequestError):
    """Raised when a successful response is not valid JSON."""


class OzonPaginationError(OzonRequestError):
    """Raised when Ozon returns a cursor that cannot advance pagination."""


class OzonClient:
    """Read finance accruals, their types, and posting quantities from Ozon."""

    def __init__(
        self,
        token: str,
        client_id: str,
        *,
        post: PostCallable = requests.post,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        posting_batch_size: int = DEFAULT_POSTING_BATCH_SIZE,
        sleep: SleepCallable = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if posting_batch_size <= 0:
            raise ValueError("posting_batch_size must be positive")
        self._token = token
        self._client_id = client_id
        self._post = post
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._posting_batch_size = posting_batch_size
        self._sleep = sleep
        self._logger = logger or logging.getLogger(__name__)

    @property
    def headers(self) -> dict[str, str]:
        return {"Client-Id": self._client_id, "Api-Key": self._token}

    def get_accruals(self, endpoint: str, date_from: date, date_to: date) -> tuple[Accrual, ...]:
        """Return every accrual in an inclusive date range."""

        accruals: list[Accrual] = []
        current_date = date_from
        while current_date <= date_to:
            accruals.extend(self._get_accruals_for_day(endpoint, current_date))
            current_date += timedelta(days=1)
        return tuple(accruals)

    def get_accrual_types(self, accrual_endpoint: str) -> tuple[AccrualType, ...]:
        payload = self._post_json(_related_endpoint(accrual_endpoint, "types"), {})
        return parse_accrual_types(payload)

    def get_posting_accruals(
        self,
        accrual_endpoint: str,
        posting_numbers: Sequence[str],
    ) -> tuple[PostingAccrual, ...]:
        """Return posting details in bounded batches; an empty input makes no request."""

        unique_numbers = tuple(dict.fromkeys(number for number in posting_numbers if number))
        if not unique_numbers:
            return ()

        endpoint = _related_endpoint(accrual_endpoint, "postings")
        parsed: list[PostingAccrual] = []
        for index in range(0, len(unique_numbers), self._posting_batch_size):
            batch = unique_numbers[index : index + self._posting_batch_size]
            payload = self._post_json(endpoint, {"posting_numbers": list(batch)})
            parsed.extend(parse_posting_accruals(payload))
        return tuple(parsed)

    def _get_accruals_for_day(self, endpoint: str, accrual_date: date) -> list[Accrual]:
        last_id = ""
        seen_cursors: set[str] = set()
        result: list[Accrual] = []
        while True:
            payload = self._post_json(
                endpoint,
                {"date": accrual_date.isoformat(), "last_id": last_id},
            )
            page = AccrualPage.from_api(payload)
            result.extend(page.accruals)
            next_last_id = page.last_id
            if not next_last_id:
                return result
            if next_last_id == last_id or next_last_id in seen_cursors:
                raise OzonPaginationError(
                    f"Ozon pagination cursor repeated for {accrual_date.isoformat()}: "
                    f"{next_last_id!r}"
                )
            seen_cursors.add(next_last_id)
            last_id = next_last_id

    def _post_json(self, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            try:
                response = self._post(
                    url,
                    headers=self.headers,
                    json=dict(payload),
                    timeout=self._timeout_seconds,
                )
            except (requests.ConnectionError, requests.Timeout) as error:
                if attempt == self._max_retries:
                    raise OzonRequestError(
                        f"Ozon request to {url} failed after {attempts} attempts: "
                        f"{type(error).__name__}"
                    ) from error
                self._retry(url, attempt, type(error).__name__)
                continue

            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as error:
                    raise OzonResponseError(
                        f"Ozon response from {url} is not valid JSON"
                    ) from error
                if not isinstance(data, Mapping):
                    raise OzonResponseError(f"Ozon response from {url} must be a JSON object")
                self._logger.info("Successful request to %s", url)
                return data

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                self._retry(url, attempt, f"HTTP {response.status_code}")
                continue
            raise OzonAPIError(_format_api_error(url, response))

        raise AssertionError("unreachable")

    def _retry(self, url: str, attempt: int, reason: str) -> None:
        delay = min(0.5 * (2**attempt), 2.0)
        self._logger.warning(
            "Temporary Ozon error for %s (%s); retrying in %.1f seconds",
            url,
            reason,
            delay,
        )
        self._sleep(delay)


def _related_endpoint(accrual_endpoint: str, method: str) -> str:
    suffix = "/by-day"
    if not accrual_endpoint.endswith(suffix):
        raise ValueError(f"Ozon accrual endpoint must end with {suffix!r}")
    return f"{accrual_endpoint[: -len(suffix)]}/{method}"


def _format_api_error(url: str, response: requests.Response) -> str:
    detail = response.text.strip()
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, Mapping):
        code = payload.get("code")
        message = payload.get("message")
        parts = [str(value) for value in (code, message) if value not in (None, "")]
        if parts:
            detail = ": ".join(parts)
    if len(detail) > 500:
        detail = f"{detail[:497]}..."
    suffix = f": {detail}" if detail else ""
    return f"Ozon request to {url} returned HTTP {response.status_code}{suffix}"
