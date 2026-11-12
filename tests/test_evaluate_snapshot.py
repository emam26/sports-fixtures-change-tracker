from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from scripts import evaluate_snapshot

from sports_tracker.config import OpenLigaDBSettings


def test_evaluation_cli_passes_validated_source_settings_to_loader(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "response.json").write_bytes(b"[]")
    settings = OpenLigaDBSettings(
        base_url="https://api.openligadb.de",
        shortcut="ucl",
        season=2026,
        expected_league_id=4946,
        timeout_seconds=10.0,
        raw_snapshot_directory=tmp_path,
    )
    observed: dict[str, object] = {}

    def fake_load_snapshot(
        path: Path,
        received_settings: OpenLigaDBSettings,
        *,
        allow_conflicting_nonfinal_results: bool = False,
    ):
        observed["path"] = path
        observed["settings"] = received_settings
        observed["allow_conflicting_nonfinal_results"] = allow_conflicting_nonfinal_results
        return SimpleNamespace(matches=())

    monkeypatch.setattr(evaluate_snapshot, "load_openligadb_settings", lambda: settings)
    monkeypatch.setattr(evaluate_snapshot, "load_snapshot", fake_load_snapshot)
    monkeypatch.setattr(sys, "argv", ["evaluate_snapshot.py", str(snapshot)])

    assert evaluate_snapshot.main() == 0
    assert observed == {
        "path": snapshot.resolve(),
        "settings": settings,
        "allow_conflicting_nonfinal_results": False,
    }


def test_evaluation_cli_explicitly_enables_conflict_quarantine(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "response.json").write_bytes(b"[]")
    settings = OpenLigaDBSettings(
        base_url="https://api.openligadb.de",
        shortcut="ucl",
        season=2026,
        expected_league_id=4946,
        timeout_seconds=10.0,
        raw_snapshot_directory=tmp_path,
    )
    observed: dict[str, object] = {}

    def fake_load_snapshot(
        path: Path,
        received_settings: OpenLigaDBSettings,
        *,
        allow_conflicting_nonfinal_results: bool = False,
    ):
        observed["path"] = path
        observed["settings"] = received_settings
        observed["allow_conflicting_nonfinal_results"] = allow_conflicting_nonfinal_results
        return SimpleNamespace(matches=())

    monkeypatch.setattr(evaluate_snapshot, "load_openligadb_settings", lambda: settings)
    monkeypatch.setattr(evaluate_snapshot, "load_snapshot", fake_load_snapshot)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_snapshot.py",
            str(snapshot),
            "--allow-conflicting-nonfinal-results",
        ],
    )

    assert evaluate_snapshot.main() == 0
    assert observed == {
        "path": snapshot.resolve(),
        "settings": settings,
        "allow_conflicting_nonfinal_results": True,
    }
