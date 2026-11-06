"""One-shot synchronization, checkpoint inspection, locking, and safe logging."""

from __future__ import annotations

import json
import os
import socket
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sports_tracker.config import OpenLigaDBSettings
from sports_tracker.ingestion import (
    SnapshotImportProcessor,
    SQLServerImportStore,
    load_snapshot,
)
from sports_tracker.openligadb import (
    LastChangeSignal,
    OpenLigaDBClient,
    OpenLigaDBError,
    OpenLigaDBResponse,
    build_last_change_url,
)
from sports_tracker.runtime import ConnectionFactory
from sports_tracker.snapshots import save_raw_snapshot


class SyncError(RuntimeError):
    """Base class for safe synchronization failures."""


class SyncAlreadyRunningError(SyncError):
    """Raised when another process owns the one-shot synchronization lock."""


@dataclass(frozen=True)
class SyncOutcome:
    matchday: int
    status: str
    reason: str
    snapshot_directory: Path | None = None
    snapshot_sha256: str | None = None
    source_last_change_utc: datetime | None = None


class Logger(Protocol):
    def write(self, event: str, **fields: object) -> None: ...


class SafeJsonLogger:
    """Append structured JSON records with bounded local rotation."""

    def __init__(
        self,
        directory: Path,
        *,
        filename: str = "sync.jsonl",
        max_bytes: int = 1_000_000,
        backups: int = 5,
    ) -> None:
        self._directory = directory
        self._path = directory / filename
        self._max_bytes = max_bytes
        self._backups = backups

    def _rotate(self) -> None:
        if not self._path.exists() or self._path.stat().st_size < self._max_bytes:
            return
        oldest = self._path.with_suffix(f"{self._path.suffix}.{self._backups}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self._backups - 1, 0, -1):
            source = self._path.with_suffix(f"{self._path.suffix}.{index}")
            target = self._path.with_suffix(f"{self._path.suffix}.{index + 1}")
            if source.exists():
                source.replace(target)
        self._path.replace(self._path.with_suffix(f"{self._path.suffix}.1"))

    def write(self, event: str, **fields: object) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        self._rotate()
        record = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "event": event,
            **fields,
        }
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=True, default=str, sort_keys=True))
            stream.write("\n")


class RunLock:
    """Atomic lock file that is removed only by its creating process."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._token = uuid4().hex
        self._held = False

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "token": self._token,
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "acquired_at_utc": datetime.now(UTC).isoformat(),
            },
            sort_keys=True,
        ).encode("utf-8")
        try:
            descriptor = os.open(
                self._path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise SyncAlreadyRunningError(
                f"Synchronization lock already exists: {self._path}"
            ) from exc
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)
        self._held = True

    def release(self) -> None:
        if not self._held:
            return
        try:
            contents = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._held = False
            return
        if contents.get("token") == self._token:
            self._path.unlink(missing_ok=True)
        self._held = False

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


class SQLCheckpointReader:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def last_source_update(
        self,
        *,
        provider: str,
        shortcut: str,
        season: int,
        matchday: int,
    ) -> datetime | None:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT sc.last_source_update_utc
                FROM dbo.sync_checkpoints AS sc
                INNER JOIN dbo.competition_seasons AS cs
                    ON cs.competition_season_id = sc.competition_season_id
                INNER JOIN dbo.competitions AS c
                    ON c.competition_id = cs.competition_id
                WHERE sc.provider = ?
                  AND c.provider_shortcut = ?
                  AND cs.season_start_year = ?
                  AND sc.matchday_number = ?;
                """,
                (provider, shortcut, season, matchday),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            value = row[0]
            if value is not None and value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value


def preserve_sync_response(
    response: OpenLigaDBResponse,
    *,
    settings: OpenLigaDBSettings,
    matchday: int,
) -> tuple[Path, str]:
    """Preserve a response through the single Stage 1 immutable snapshot writer."""

    snapshot = save_raw_snapshot(response, settings, matchday)
    return snapshot.directory, snapshot.sha256


class SyncCoordinator:
    """Coordinate cheap change checks, immutable capture, and transactional import."""

    def __init__(
        self,
        *,
        client: OpenLigaDBClient,
        connection_factory: ConnectionFactory,
        logger: Logger,
    ) -> None:
        self._client = client
        self._connection_factory = connection_factory
        self._settings = client.settings
        self._logger = logger
        self._checkpoints = SQLCheckpointReader(connection_factory)

    def _should_fetch(self, signal: LastChangeSignal, checkpoint: datetime | None) -> bool:
        if not signal.reliable or signal.changed_at_utc is None:
            return True
        if checkpoint is None:
            return True
        return signal.changed_at_utc > checkpoint

    def _last_change_signal(self, matchday: int) -> LastChangeSignal:
        try:
            return self._client.fetch_last_change(matchday)
        except OpenLigaDBError as exc:
            self._logger.write(
                "sync_signal_unavailable",
                matchday=matchday,
                error_type=type(exc).__name__,
                action="full_fetch_required",
            )
            return LastChangeSignal(
                url=build_last_change_url(self._settings, matchday),
                status_code=0,
                raw_value=None,
                changed_at_utc=None,
                reliable=False,
                reason="last-change check failed; full retrieval required",
            )

    def synchronize_matchday(self, matchday: int) -> SyncOutcome:
        signal = self._last_change_signal(matchday)
        checkpoint = self._checkpoints.last_source_update(
            provider="OpenLigaDB",
            shortcut=self._settings.shortcut,
            season=self._settings.season,
            matchday=matchday,
        )
        if not self._should_fetch(signal, checkpoint):
            self._logger.write(
                "sync_skipped",
                matchday=matchday,
                reason="source_not_newer_than_checkpoint",
                source_last_change_utc=signal.changed_at_utc,
            )
            return SyncOutcome(
                matchday=matchday,
                status="skipped",
                reason="Source last-change signal is not newer than the checkpoint.",
                source_last_change_utc=signal.changed_at_utc,
            )

        self._logger.write(
            "sync_fetch_started",
            matchday=matchday,
            signal_reliable=signal.reliable,
            signal_reason=signal.reason,
        )
        response = self._client.fetch_matchday(matchday)
        directory, digest = preserve_sync_response(
            response,
            settings=self._settings,
            matchday=matchday,
        )
        parsed = load_snapshot(directory, self._settings)
        parsed = replace(
            parsed,
            source_last_change_utc=(signal.changed_at_utc if signal.reliable else None),
        )
        try:
            with closing(self._connection_factory()) as connection:
                store = SQLServerImportStore(connection)
                processor = SnapshotImportProcessor(store)
                result = processor.import_snapshot(parsed)
        except Exception as exc:
            self._logger.write(
                "sync_import_failed",
                matchday=matchday,
                snapshot_sha256=digest,
                error_type=type(exc).__name__,
            )
            raise SyncError(
                f"Snapshot was preserved but import failed for matchday {matchday}."
            ) from exc
        self._logger.write(
            "sync_import_succeeded",
            matchday=matchday,
            snapshot_sha256=digest,
            import_run_id=getattr(result, "import_run_id", None),
        )
        return SyncOutcome(
            matchday=matchday,
            status="imported",
            reason="New snapshot preserved and imported.",
            snapshot_directory=directory,
            snapshot_sha256=digest,
            source_last_change_utc=signal.changed_at_utc,
        )

    def synchronize(self, matchdays: tuple[int, ...]) -> tuple[SyncOutcome, ...]:
        outcomes: list[SyncOutcome] = []
        for matchday in matchdays:
            try:
                outcomes.append(self.synchronize_matchday(matchday))
            except Exception as exc:
                self._logger.write(
                    "sync_failed",
                    matchday=matchday,
                    error_type=type(exc).__name__,
                )
                outcomes.append(
                    SyncOutcome(
                        matchday=matchday,
                        status="failed",
                        reason=(
                            "Synchronization failed safely for this matchday; "
                            "inspect the structured log."
                        ),
                    )
                )
        return tuple(outcomes)
