from __future__ import annotations

import sys
from pathlib import Path

from scripts import sync_openligadb

from sports_tracker.config import OpenLigaDBSettings, SyncSettings
from sports_tracker.openligadb import RetryPolicy, SeasonDiscovery
from sports_tracker.synchronization import SyncOutcome


def _source_settings(tmp_path: Path) -> OpenLigaDBSettings:
    return OpenLigaDBSettings(
        base_url="https://api.openligadb.de",
        shortcut="ucl",
        season=2026,
        expected_league_id=4946,
        timeout_seconds=10.0,
        raw_snapshot_directory=tmp_path / "raw",
    )


def _sync_settings(tmp_path: Path) -> SyncSettings:
    return SyncSettings(
        matchdays=(3, 4),
        max_retries=2,
        backoff_initial_seconds=0.1,
        backoff_max_seconds=1.0,
        lock_file=tmp_path / "sync.lock",
        log_directory=tmp_path / "logs",
        discover_matchdays=False,
    )


def test_sync_cli_returns_nonzero_after_partial_failure(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    retry_policies: list[RetryPolicy] = []

    class Logger:
        def write(self, event: str, **fields: object) -> None:
            events.append((event, fields))

    class Coordinator:
        def synchronize(self, matchdays: tuple[int, ...]) -> tuple[SyncOutcome, ...]:
            assert matchdays == (3, 4)
            return (
                SyncOutcome(3, "failed", "synthetic failure"),
                SyncOutcome(4, "skipped", "not newer"),
            )

    def create_client(
        settings: OpenLigaDBSettings,
        *,
        retry_policy: RetryPolicy,
    ) -> object:
        assert settings == _source_settings(tmp_path)
        retry_policies.append(retry_policy)
        return object()

    monkeypatch.setattr(
        sync_openligadb,
        "load_openligadb_settings",
        lambda: _source_settings(tmp_path),
    )
    monkeypatch.setattr(
        sync_openligadb,
        "load_sync_settings",
        lambda: _sync_settings(tmp_path),
    )
    monkeypatch.setattr(sync_openligadb, "OpenLigaDBClient", create_client)
    monkeypatch.setattr(sync_openligadb, "SafeJsonLogger", lambda _: Logger())
    monkeypatch.setattr(sync_openligadb, "SyncCoordinator", lambda **_: Coordinator())
    monkeypatch.setattr(sys, "argv", ["sync_openligadb.py"])

    exit_code = sync_openligadb.main()

    assert exit_code == 1
    assert not (tmp_path / "sync.lock").exists()
    assert retry_policies == [
        RetryPolicy(
            max_retries=2,
            initial_backoff_seconds=0.1,
            max_backoff_seconds=1.0,
        )
    ]
    assert events == [
        (
            "sync_matchdays_selected",
            {
                "matchdays": (3, 4),
                "selection_reasons": [
                    {"matchday": 3, "reason": "explicit-configured-matchday"},
                    {"matchday": 4, "reason": "explicit-configured-matchday"},
                ],
            },
        ),
        ("sync_run_started", {"matchdays": (3, 4)}),
        ("sync_run_completed", {"matchday_count": 2, "failed_matchdays": 1}),
    ]
    assert "completed with 1 failed matchday" in capsys.readouterr().out


def test_sync_cli_rejects_duplicate_matchdays(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        sync_openligadb,
        "load_openligadb_settings",
        lambda: _source_settings(tmp_path),
    )
    monkeypatch.setattr(
        sync_openligadb,
        "load_sync_settings",
        lambda: _sync_settings(tmp_path),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["sync_openligadb.py", "--matchday", "3", "--matchday", "3"],
    )

    exit_code = sync_openligadb.main()

    assert exit_code == 1
    assert "must not contain duplicates" in capsys.readouterr().out


def test_sync_cli_discovers_configured_league_phase_matchdays(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class Logger:
        def write(self, event: str, **fields: object) -> None:
            events.append((event, fields))

    class Client:
        settings = _source_settings(tmp_path)

        def discover_matchdays(self) -> SeasonDiscovery:
            return SeasonDiscovery(
                available_groups_url="https://api.openligadb.de/getavailablegroups/ucl/2026",
                full_season_url="https://api.openligadb.de/getmatchdata/ucl/2026",
                available_group_matchdays=tuple(range(1, 10)),
                full_season_matchdays=tuple(range(1, 10)),
                candidate_matchdays=tuple(range(1, 10)),
                warnings=(),
            )

    class Coordinator:
        def synchronize(self, matchdays: tuple[int, ...]) -> tuple[SyncOutcome, ...]:
            assert matchdays == (1, 2, 3)
            return tuple(SyncOutcome(matchday, "skipped", "not newer") for matchday in matchdays)

    class Reader:
        def __init__(self, connection_factory) -> None:
            del connection_factory

        def states(self, **kwargs):
            del kwargs
            return ()

    sync_settings = SyncSettings(
        matchdays=(),
        max_retries=2,
        backoff_initial_seconds=0.1,
        backoff_max_seconds=1.0,
        lock_file=tmp_path / "sync.lock",
        log_directory=tmp_path / "logs",
        discover_matchdays=True,
        include_post_league_phase=False,
    )
    monkeypatch.setattr(
        sync_openligadb,
        "load_openligadb_settings",
        lambda: _source_settings(tmp_path),
    )
    monkeypatch.setattr(sync_openligadb, "load_sync_settings", lambda: sync_settings)
    monkeypatch.setattr(sync_openligadb, "OpenLigaDBClient", lambda *_args, **_kwargs: Client())
    monkeypatch.setattr(sync_openligadb, "SyncMatchdayReader", Reader)
    monkeypatch.setattr(sync_openligadb, "SafeJsonLogger", lambda _: Logger())
    monkeypatch.setattr(sync_openligadb, "SyncCoordinator", lambda **_: Coordinator())
    monkeypatch.setattr(sys, "argv", ["sync_openligadb.py"])

    exit_code = sync_openligadb.main()

    assert exit_code == 0
    assert events[0] == (
        "sync_matchdays_discovered",
        {
            "matchdays": (1, 2, 3),
            "available_group_matchdays": tuple(range(1, 10)),
            "full_season_matchdays": tuple(range(1, 10)),
            "warning_count": 0,
        },
    )
    assert events[1] == (
        "sync_matchdays_selected",
        {
            "matchdays": (1, 2, 3),
            "selection_reasons": [
                {"matchday": 1, "reason": "unseen-discovered-matchday"},
                {"matchday": 2, "reason": "unseen-discovered-matchday"},
                {"matchday": 3, "reason": "unseen-discovered-matchday"},
            ],
        },
    )
    assert events[2] == ("sync_run_started", {"matchdays": (1, 2, 3)})
