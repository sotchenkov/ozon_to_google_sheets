from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

import pytest
import requests

from ozon_to_google_sheets.ozon import (
    OzonAPIError,
    OzonClient,
    OzonPaginationError,
    OzonRequestError,
    OzonResponseError,
)

ENDPOINT = "https://example.invalid/v1/finance/accrual/by-day"


def test_client_fetches_inclusive_period_and_follows_last_id() -> None:
    post = FakePost(
        [
            FakeResponse(payload=_page([_accrual(1)], "cursor-1")),
            FakeResponse(payload=_page([_accrual(2)], "")),
            FakeResponse(payload=_page([], "")),
        ]
    )
    client = OzonClient("token", "client", post=post, sleep=no_sleep)

    accruals = client.get_accruals(ENDPOINT, date(2026, 8, 22), date(2026, 8, 23))

    assert [accrual.accrual_id for accrual in accruals] == [1, 2]
    assert [call["json"] for call in post.calls] == [
        {"date": "2026-08-22", "last_id": ""},
        {"date": "2026-08-22", "last_id": "cursor-1"},
        {"date": "2026-08-23", "last_id": ""},
    ]
    assert all(call["timeout"] == 30.0 for call in post.calls)


def test_client_rejects_repeated_pagination_cursor() -> None:
    post = FakePost(
        [
            FakeResponse(payload=_page([], "cursor-1")),
            FakeResponse(payload=_page([], "cursor-1")),
        ]
    )
    client = OzonClient("token", "client", post=post, sleep=no_sleep)

    with pytest.raises(OzonPaginationError, match="cursor repeated"):
        client.get_accruals(ENDPOINT, date(2026, 8, 23), date(2026, 8, 23))


def test_client_retries_only_temporary_failures_with_timeout() -> None:
    post = FakePost(
        [
            requests.Timeout("synthetic timeout"),
            FakeResponse(status_code=503, payload={"message": "temporary"}),
            FakeResponse(payload=_page([], "")),
        ]
    )
    sleeps: list[float] = []
    client = OzonClient(
        "token",
        "client",
        post=post,
        timeout_seconds=12.5,
        max_retries=2,
        sleep=sleeps.append,
    )

    assert client.get_accruals(ENDPOINT, date(2026, 8, 23), date(2026, 8, 23)) == ()
    assert sleeps == [0.5, 1.0]
    assert post.calls[-1]["timeout"] == 12.5


def test_client_does_not_retry_authentication_error() -> None:
    post = FakePost(
        [FakeResponse(status_code=401, payload={"code": 7, "message": "invalid credentials"})]
    )
    client = OzonClient("token", "client", post=post, max_retries=2, sleep=no_sleep)

    with pytest.raises(OzonAPIError, match=r"HTTP 401: 7: invalid credentials"):
        client.get_accrual_types(ENDPOINT)

    assert len(post.calls) == 1


def test_client_limits_connection_retries() -> None:
    post = FakePost([requests.ConnectionError("offline"), requests.ConnectionError("offline")])
    client = OzonClient("token", "client", post=post, max_retries=1, sleep=no_sleep)

    with pytest.raises(OzonRequestError, match="failed after 2 attempts: ConnectionError"):
        client.get_accrual_types(ENDPOINT)


def test_client_reports_invalid_success_payload() -> None:
    post = FakePost([FakeResponse(json_error=ValueError("not json"))])
    client = OzonClient("token", "client", post=post, sleep=no_sleep)

    with pytest.raises(OzonResponseError, match="is not valid JSON"):
        client.get_accrual_types(ENDPOINT)


def test_client_fetches_types_and_batches_unique_postings() -> None:
    post = FakePost(
        [
            FakeResponse(
                payload={
                    "accrual_types": [
                        {"id": 7, "name": "LastMileCourier"}
                    ]
                }
            ),
            FakeResponse(payload={"posting_accruals": [_posting("posting-1", 2)]}),
            FakeResponse(payload={"posting_accruals": [_posting("posting-3", 4)]}),
        ]
    )
    client = OzonClient(
        "token",
        "client",
        post=post,
        posting_batch_size=2,
        sleep=no_sleep,
    )

    accrual_types = client.get_accrual_types(ENDPOINT)
    posting_accruals = client.get_posting_accruals(
        ENDPOINT,
        ["posting-1", "posting-2", "posting-1", "posting-3"],
    )

    assert accrual_types[0].type_id == 7
    assert [item.quantity for item in posting_accruals] == [2, 4]
    assert post.calls[0]["url"].endswith("/types")
    assert post.calls[1]["json"] == {"posting_numbers": ["posting-1", "posting-2"]}
    assert post.calls[2]["json"] == {"posting_numbers": ["posting-3"]}


def test_client_skips_posting_request_for_empty_input() -> None:
    post = FakePost([])
    client = OzonClient("token", "client", post=post, sleep=no_sleep)

    assert client.get_posting_accruals(ENDPOINT, []) == ()
    assert post.calls == []


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: object | None = None,
        json_error: ValueError | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._json_error = json_error
        self.text = "synthetic response"

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakePost:
    def __init__(self, outcomes: list[FakeResponse | requests.RequestException]) -> None:
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
        outcome = next(self._outcomes)
        if isinstance(outcome, requests.RequestException):
            raise outcome
        return outcome


def _page(accruals: list[dict[str, Any]], last_id: str) -> dict[str, Any]:
    return {"accruals": accruals, "last_id": last_id}


def _accrual(accrual_id: int) -> dict[str, Any]:
    return {
        "accrual_id": accrual_id,
        "accrued_category": "NON_ITEM",
        "date": "2026-08-23",
        "unit_number": "service-1",
        "total_amount": {"amount": "1.00", "currency": "RUB"},
    }


def _posting(posting_number: str, quantity: int) -> dict[str, Any]:
    return {
        "posting_number": posting_number,
        "accruals": [
            {
                "seller_price": {"amount": "100", "currency": "RUB"},
                "sku": 1001,
                "type_id": 7,
                "accrual_date": "2026-08-23",
                "accrued": {"amount": "-5", "currency": "RUB"},
                "quantity": quantity,
            }
        ],
    }


def no_sleep(_: float) -> None:
    pass
