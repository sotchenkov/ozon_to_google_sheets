from __future__ import annotations

import runpy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ozon_to_google_sheets import cli
from ozon_to_google_sheets.config import AppConfig


def test_run_composes_external_adapters_and_sync_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = StubService(result=[910001])
    logger, calls = _patch_composition(monkeypatch, service)
    config = _config(tmp_path)

    result = cli.run(config)

    assert result == [910001]
    assert calls["ozon"][:2] == ("synthetic-token", "synthetic-client")
    assert calls["ozon"][2] is logger
    assert calls["sheet"] == {
        "credentials_path": tmp_path / "synthetic-credentials.json",
        "credentials_info": None,
        "spreadsheet_id": "synthetic-spreadsheet",
        "worksheet_id": 123456,
        "logger": logger,
    }
    assert calls["service"] == {
        "ozon": calls["ozon_adapter"],
        "sheet": calls["sheet_adapter"],
        "endpoint": config.ozon_endpoint,
        "date_from": config.date_from,
        "date_to": config.date_to,
        "logger": logger,
    }
    assert logger.messages == [
        "The application has been started",
        "The application has shut down",
    ]


def test_run_logs_shutdown_when_service_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = StubService(failure=RuntimeError("synthetic synchronization failure"))
    logger, _ = _patch_composition(monkeypatch, service)

    with pytest.raises(RuntimeError, match="synthetic synchronization failure"):
        cli.run(_config(tmp_path))

    assert logger.messages == [
        "The application has been started",
        "The application has shut down",
    ]


def test_main_loads_config_runs_once_and_returns_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    calls: list[AppConfig] = []
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli, "run", lambda value: calls.append(value) or [910001])

    assert cli.main() == 0
    assert calls == [config]


def test_package_module_entrypoint_uses_cli_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "main", lambda: 7)

    with pytest.raises(SystemExit) as error:
        runpy.run_module("ozon_to_google_sheets.__main__", run_name="__main__")

    assert error.value.code == 7


def test_repository_entrypoint_uses_cli_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "main", lambda: 9)
    entrypoint = Path(__file__).parents[1] / "main.py"

    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(entrypoint), run_name="__main__")

    assert error.value.code == 9


class RecordingLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str, *args: object) -> None:
        self.messages.append(message % args if args else message)


class StubService:
    def __init__(
        self,
        *,
        result: list[int] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self._result = result or []
        self._failure = failure
        self.run_calls = 0

    def run(self) -> list[int]:
        self.run_calls += 1
        if self._failure is not None:
            raise self._failure
        return self._result


def _patch_composition(
    monkeypatch: pytest.MonkeyPatch,
    service: StubService,
) -> tuple[RecordingLogger, dict[str, Any]]:
    logger = RecordingLogger()
    calls: dict[str, Any] = {}
    ozon_adapter = object()
    sheet_adapter = object()

    def make_ozon(token: str, client_id: str, *, logger: object) -> object:
        calls["ozon"] = (token, client_id, logger)
        calls["ozon_adapter"] = ozon_adapter
        return ozon_adapter

    def connect_sheet(**options: object) -> object:
        calls["sheet"] = options
        calls["sheet_adapter"] = sheet_adapter
        return sheet_adapter

    def make_service(**options: object) -> StubService:
        calls["service"] = options
        return service

    monkeypatch.setattr(cli, "configure_file_logging", lambda _path: logger)
    monkeypatch.setattr(cli, "OzonClient", make_ozon)
    monkeypatch.setattr(cli, "GoogleSheetsAdapter", SimpleNamespace(connect=connect_sheet))
    monkeypatch.setattr(cli, "SyncService", make_service)
    return logger, calls


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        ozon_token="synthetic-token",
        ozon_client_id="synthetic-client",
        google_credentials=tmp_path / "synthetic-credentials.json",
        google_credentials_info=None,
        google_spreadsheet_id="synthetic-spreadsheet",
        google_worksheet_id=123456,
        date_from=date(2026, 8, 20),
        date_to=date(2026, 8, 21),
        log_file=tmp_path / "logs" / "application.log",
    )
