from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sports_tracker.config import OpenLigaDBSettings
from sports_tracker.openligadb import (
    LastChangeSignal,
    OpenLigaDBInvalidJSONError,
    OpenLigaDBResponse,
)
from sports_tracker.snapshots import SnapshotAlreadyExistsError
from sports_tracker.synchronization import (
    RunLock,
    SQLCheckpointReader,
    SyncAlreadyRunningError,
    SyncCoordinator,
    SyncOutcome,
    preserve_sync_response,
)


def _settings(tmp_path: Path) -> OpenLigaDBSettings:
    return OpenLigaDBSettings(
        base_url="https://api.openligadb.de",
        shortcut="ucl",
        season=2026,
        expected_league_id=4946,
        timeout_seconds=10.0,
        raw_snapshot_directory=tmp_path / "raw",
    )


def _response(body: bytes, matchday: int) -> OpenLigaDBResponse:
    return OpenLigaDBResponse(
        records=[],
        body=body,
        status_code=200,
        content_type="application/json; charset=utf-8",
        url=f"https://api.openligadb.de/getmatchdata/ucl/2026/{matchday}",
        retrieved_at_utc="2026-11-03T09:30:00Z",
    )


def test_lock_prevents_overlapping_runs(tmp_path: Path) -> None:
    path = tmp_path / "sync.lock"
    first = RunLock(path)
    second = RunLock(path)

    first.acquire()
    try:
        with pytest.raises(SyncAlreadyRunningError):
            second.acquire()
    finally:
        first.release()

    assert not path.exists()


def test_lock_does_not_remove_another_owners_file(tmp_path: Path) -> None:
    path = tmp_path / "sync.lock"
    lock = RunLock(path)
    lock.acquire()
    path.write_text(json.dumps({"token": "replacement"}), encoding="utf-8")

    lock.release()

    assert path.exists()


def test_checkpoint_reader_uses_deployed_competition_columns() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.statement = ""
            self.parameters: tuple[object, ...] = ()

        def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
            self.statement = statement
            self.parameters = parameters

        def fetchone(self) -> tuple[datetime]:
            return (datetime(2026, 11, 3, 9, 30),)

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def cursor(self) -> Cursor:
            return self.cursor_instance

        def close(self) -> None:
            return None

    connection = Connection()
    reader = SQLCheckpointReader(lambda: connection)  # type: ignore[arg-type]

    value = reader.last_source_update(
        provider="OpenLigaDB",
        shortcut="ucl",
        season=2026,
        matchday=3,
    )

    assert value == datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
    assert "c.provider_shortcut = ?" in connection.cursor_instance.statement
    assert "cs.season_start_year = ?" in connection.cursor_instance.statement
    assert connection.cursor_instance.parameters == ("OpenLigaDB", "ucl", 2026, 3)


def test_sync_capture_preserves_exact_bytes_and_hash(tmp_path: Path) -> None:
    body = b'[{"matchID":123}]'
    settings = _settings(tmp_path)

    directory, digest = preserve_sync_response(
        _response(body, 3),
        settings=settings,
        matchday=3,
    )

    assert directory.parent == settings.raw_snapshot_directory / "ucl" / "2026" / "matchday-3"
    assert (directory / "response.json").read_bytes() == body
    assert digest == hashlib.sha256(body).hexdigest()
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["sha256"] == digest
    assert metadata["byte_count"] == len(body)
    assert metadata["retrieved_at_utc"] == "2026-11-03T09:30:00Z"


def test_sync_capture_never_overwrites_same_snapshot(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    response = _response(b"[]", 4)
    preserve_sync_response(response, settings=settings, matchday=4)

    with pytest.raises(SnapshotAlreadyExistsError, match="already exists"):
        preserve_sync_response(response, settings=settings, matchday=4)


def test_coordinator_passes_validated_settings_to_snapshot_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    signal = LastChangeSignal(
        url="https://api.openligadb.de/getlastchangedate/ucl/2026/3",
        status_code=200,
        raw_value="2026-11-03T09:30:00Z",
        changed_at_utc=datetime(2026, 11, 3, 9, 30, tzinfo=UTC),
        reliable=True,
        reason="timezone-aware last-change signal",
    )

    class Client:
        def __init__(self) -> None:
            self.settings = settings

        def fetch_last_change(self, matchday: int) -> LastChangeSignal:
            assert matchday == 3
            return signal

        def fetch_matchday(self, matchday: int) -> OpenLigaDBResponse:
            assert matchday == 3
            return _response(b"[]", matchday)

    class Logger:
        def write(self, event: str, **fields: object) -> None:
            del event, fields

    loaded: dict[str, Any] = {}
    snapshot_directory = tmp_path / "snapshot"

    @dataclass(frozen=True)
    class Parsed:
        source_last_change_utc: datetime | None = None

    parsed = Parsed()

    def fake_load_snapshot(path: Path, received: OpenLigaDBSettings):
        loaded.update(path=path, settings=received)
        return parsed

    class Processor:
        def __init__(self, store: object) -> None:
            del store

        def import_snapshot(self, received: object):
            assert received.source_last_change_utc == signal.changed_at_utc
            return SimpleNamespace(import_run_id=7)

    monkeypatch.setattr(
        "sports_tracker.synchronization.preserve_sync_response",
        lambda response, *, settings, matchday: (snapshot_directory, "a" * 64),
    )
    monkeypatch.setattr("sports_tracker.synchronization.load_snapshot", fake_load_snapshot)
    monkeypatch.setattr("sports_tracker.synchronization.SQLServerImportStore", lambda _: object())
    monkeypatch.setattr("sports_tracker.synchronization.SnapshotImportProcessor", Processor)

    connection = SimpleNamespace(close=lambda: None)
    coordinator = SyncCoordinator(
        client=Client(),  # type: ignore[arg-type]
        connection_factory=lambda: connection,
        logger=Logger(),
    )
    coordinator._checkpoints = SimpleNamespace(last_source_update=lambda **_: None)

    outcome = coordinator.synchronize_matchday(3)

    assert outcome.status == "imported"
    assert loaded == {"path": snapshot_directory, "settings": settings}


def test_partial_failure_does_not_prevent_later_matchdays(monkeypatch) -> None:
    coordinator = object.__new__(SyncCoordinator)
    coordinator._logger = SimpleNamespace(write=lambda *args, **kwargs: None)

    def synchronize_matchday(matchday: int) -> SyncOutcome:
        if matchday == 3:
            raise RuntimeError("synthetic failure")
        return SyncOutcome(matchday, "imported", "ok")

    monkeypatch.setattr(coordinator, "synchronize_matchday", synchronize_matchday)

    outcomes = coordinator.synchronize((3, 4))

    assert [(item.matchday, item.status) for item in outcomes] == [
        (3, "failed"),
        (4, "imported"),
    ]


def test_reliable_last_change_skips_only_when_not_newer() -> None:
    coordinator = object.__new__(SyncCoordinator)
    checkpoint = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)

    unchanged = LastChangeSignal(
        url="https://api.openligadb.de/getlastchangedate/ucl/2026/3",
        status_code=200,
        raw_value="2026-11-03T09:30:00Z",
        changed_at_utc=checkpoint,
        reliable=True,
        reason="source timestamp",
    )
    newer = LastChangeSignal(
        raw_value="2026-11-03T09:30:01Z",
        url="https://api.openligadb.de/getlastchangedate/ucl/2026/3",
        status_code=200,
        changed_at_utc=checkpoint + timedelta(seconds=1),
        reliable=True,
        reason="source timestamp",
    )

    assert coordinator._should_fetch(unchanged, checkpoint) is False
    assert coordinator._should_fetch(newer, checkpoint) is True


def test_unreliable_last_change_never_causes_skip() -> None:
    coordinator = object.__new__(SyncCoordinator)
    checkpoint = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
    signal = LastChangeSignal(
        url="https://api.openligadb.de/getlastchangedate/ucl/2026/3",
        status_code=404,
        raw_value=None,
        changed_at_utc=None,
        reliable=False,
        reason="endpoint unsupported",
    )

    assert coordinator._should_fetch(signal, checkpoint) is True


def test_failed_last_change_check_falls_back_to_full_retrieval(tmp_path: Path) -> None:
    class Client:
        settings = _settings(tmp_path)

        def fetch_last_change(self, matchday: int) -> LastChangeSignal:
            del matchday
            raise OpenLigaDBInvalidJSONError("synthetic malformed signal")

    events: list[tuple[str, dict[str, object]]] = []
    coordinator = object.__new__(SyncCoordinator)
    coordinator._client = Client()
    coordinator._settings = Client.settings
    coordinator._logger = SimpleNamespace(
        write=lambda event, **fields: events.append((event, fields))
    )

    signal = coordinator._last_change_signal(3)

    assert signal.reliable is False
    assert signal.changed_at_utc is None
    assert signal.url.endswith("/getlastchangedate/ucl/2026/3")
    assert events == [
        (
            "sync_signal_unavailable",
            {
                "matchday": 3,
                "error_type": "OpenLigaDBInvalidJSONError",
                "action": "full_fetch_required",
            },
        )
    ]
