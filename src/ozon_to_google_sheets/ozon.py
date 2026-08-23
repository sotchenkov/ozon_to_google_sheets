"""Ozon Seller API adapter."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from importlib import resources
from pathlib import Path
from typing import Any

import requests

PostCallable = Callable[..., requests.Response]


class OzonClient:
    """Make authenticated requests to the existing Ozon finance endpoint."""

    def __init__(
        self,
        token: str,
        client_id: str,
        *,
        post: PostCallable = requests.post,
        logger: logging.Logger | None = None,
    ) -> None:
        self._token = token
        self._client_id = client_id
        self._post = post
        self._logger = logger or logging.getLogger(__name__)

    @property
    def headers(self) -> dict[str, str]:
        return {"Client-Id": self._client_id, "Api-Key": self._token}

    def get_data(self, url: str, request_body: Path | None = None) -> requests.Response:
        payload = load_request_body(request_body)
        response = self._post(url, headers=self.headers, data=json.dumps(payload))

        if response.status_code == 200:
            self._logger.info("Success request to %s", url)
        else:
            self._logger.error("Request to %s failed with info: %s", url, response.text)

        return response


def load_request_body(path: Path | None = None) -> Mapping[str, Any]:
    """Load an explicit request file or the package's preserved legacy payload."""

    if path is not None:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)

    resource = resources.files("ozon_to_google_sheets").joinpath("resources/request_body.json")
    return json.loads(resource.read_text(encoding="utf-8"))
