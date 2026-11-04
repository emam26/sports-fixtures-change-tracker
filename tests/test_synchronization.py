from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from sports_tracker.openligadb import LastChangeSignal
from sports_tracker.synchronization import (
    RunLock,
    SyncAlreadyRunningError,
    SyncCoordinator,
    SyncError,
    preserve_sync_response,
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


def test_sync_capture_preserves_exact_bytes_and_hash(tmp_path: Path) -> None:
    body = b'[{"matchID":123}]'
    response = SimpleNamespace(
        body=body,
        status_code=200,
        raw_value="2026-11-03T09:30:00Z",
        content_type="application/json; charset=utf-8",
        url="https://api.openligadb.de/getmatchdata/ucl/2026/3",
        retrieved_at_utc=datetime(2026, 11, 3, 9, 30, tzinfo=UTC),
    )

    directory, digest = preserve_sync_response(
        response,
        root=tmp_path,
        shortcut="ucl",
        season="2026",
        matchday=3,
    )

    assert (directory / "response.json").read_bytes() == body
    assert digest == hashlib.sha256(body).hexdigest()
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["sha256"] == digest
    assert metadata["byte_count"] == len(body)


def test_sync_capture_never_overwrites_same_snapshot(tmp_path: Path) -> None:
    response = SimpleNamespace(
        body=b"[]",
        status_code=200,
        raw_value="2026-11-03T09:30:01Z",
        content_type="application/json",
        url="https://api.openligadb.de/getmatchdata/ucl/2026/4",
        retrieved_at_utc=datetime(2026, 11, 3, 9, 30, tzinfo=UTC),
    )
    arguments = {
        "root": tmp_path,
        "shortcut": "ucl",
        "season": "2026",
        "matchday": 4,
    }
    preserve_sync_response(response, **arguments)

    with pytest.raises(SyncError, match="already exists"):
        preserve_sync_response(response, **arguments)


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
