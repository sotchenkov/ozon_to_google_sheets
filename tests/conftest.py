from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JsonFixtureLoader = Callable[[str], dict[str, Any]]


@pytest.fixture
def load_json_fixture() -> JsonFixtureLoader:
    """Load a fresh copy of an anonymized JSON API response."""

    def load(name: str) -> dict[str, Any]:
        fixture_path = FIXTURES_DIR / name
        with fixture_path.open(encoding="utf-8") as fixture_file:
            payload = json.load(fixture_file)
        if not isinstance(payload, dict):
            raise TypeError(f"JSON fixture {name!r} must contain an object")
        return payload

    return load
