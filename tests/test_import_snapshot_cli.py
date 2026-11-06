from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pyodbc
from scripts import import_snapshot


def test_connection_failure_is_reported_without_driver_details(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    snapshot = tmp_path / "snapshot"
    parsed = SimpleNamespace(issues=(), errors=())

    class FailingConnection:
        def __enter__(self):
            raise pyodbc.ProgrammingError("login failed; PWD=not-a-real-secret")

        def __exit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback

    monkeypatch.setattr(import_snapshot, "load_openligadb_settings", lambda: object())
    monkeypatch.setattr(import_snapshot, "load_snapshot", lambda path, settings: parsed)
    monkeypatch.setattr(import_snapshot, "load_database_settings", lambda: object())
    monkeypatch.setattr(
        import_snapshot,
        "database_connection",
        lambda _settings: FailingConnection(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["import_snapshot.py", "--snapshot", str(snapshot)],
    )

    exit_code = import_snapshot.main()
    captured = capsys.readouterr()

    assert exit_code == 3
    assert "could not access the configured database" in captured.err
    assert "not-a-real-secret" not in captured.err
