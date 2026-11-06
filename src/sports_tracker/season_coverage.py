"""Offline coverage reporting for preserved OpenLigaDB season snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .config import OpenLigaDBSettings
from .openligadb import build_matchday_url


class SeasonCoverageError(ValueError):
    """Raised when a preserved snapshot cannot support a safe coverage count."""


@dataclass(frozen=True)
class MatchdayCoverage:
    """Raw-capture coverage for one expected provider matchday."""

    matchday: int
    expected_fixture_count: int
    snapshot_count: int
    valid_snapshot_count: int
    provider_match_ids: tuple[int, ...]
    invalid_snapshot_count: int
    errors: tuple[str, ...]

    @property
    def retrieved_fixture_count(self) -> int:
        """Return the number of distinct fixture IDs observed in valid raw captures."""

        return len(self.provider_match_ids)

    @property
    def state(self) -> str:
        """Describe local capture evidence without making an import claim."""

        if self.snapshot_count == 0:
            return "not-captured"
        if self.valid_snapshot_count == 0:
            return "invalid-capture"
        if self.retrieved_fixture_count < self.expected_fixture_count:
            return "captured-partial"
        if self.retrieved_fixture_count > self.expected_fixture_count:
            return "captured-count-exceeds-expectation"
        return "captured-complete"


@dataclass(frozen=True)
class SeasonCoverageReport:
    """Configured expectation compared with immutable raw source evidence."""

    expected_matchdays: tuple[int, ...]
    expected_fixtures_per_matchday: int
    matchdays: tuple[MatchdayCoverage, ...]
    additional_local_matchdays: tuple[int, ...]
    duplicate_provider_match_ids: tuple[int, ...]

    @property
    def expected_fixture_count(self) -> int:
        return len(self.expected_matchdays) * self.expected_fixtures_per_matchday

    @property
    def retrieved_fixture_count(self) -> int:
        return len(
            {
                provider_match_id
                for matchday in self.matchdays
                for provider_match_id in matchday.provider_match_ids
            }
        )

    @property
    def missing_matchdays(self) -> tuple[int, ...]:
        return tuple(
            matchday.matchday for matchday in self.matchdays if matchday.snapshot_count == 0
        )

    @property
    def capture_is_complete(self) -> bool:
        return not self.duplicate_provider_match_ids and all(
            matchday.state == "captured-complete" for matchday in self.matchdays
        )


def _snapshot_directories(base_directory: Path, matchday: int) -> tuple[Path, ...]:
    matchday_directory = base_directory / f"matchday-{matchday}"
    if not matchday_directory.is_dir():
        return ()
    return tuple(sorted(path for path in matchday_directory.iterdir() if path.is_dir()))


def _read_snapshot_match_ids(
    directory: Path,
    settings: OpenLigaDBSettings,
    expected_matchday: int,
) -> tuple[int, ...]:
    """Check immutable capture integrity and return only contract-valid provider IDs."""

    try:
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        body = (directory / "response.json").read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeasonCoverageError("snapshot files cannot be read") from exc
    if not isinstance(metadata, dict):
        raise SeasonCoverageError("snapshot metadata is not an object")
    if metadata.get("provider") != "OpenLigaDB":
        raise SeasonCoverageError("snapshot provider is not OpenLigaDB")
    if metadata.get("shortcut") != settings.shortcut or metadata.get("season") != settings.season:
        raise SeasonCoverageError("snapshot competition identity does not match configuration")
    if metadata.get("matchday") != expected_matchday:
        raise SeasonCoverageError("snapshot matchday does not match its directory")
    if metadata.get("url") != build_matchday_url(settings, expected_matchday):
        raise SeasonCoverageError("snapshot URL does not match the configured matchday")
    if metadata.get("byte_count") != len(body):
        raise SeasonCoverageError("snapshot byte count does not match response bytes")
    digest = hashlib.sha256(body).hexdigest()
    if metadata.get("sha256") != digest:
        raise SeasonCoverageError("snapshot SHA-256 does not match response bytes")
    try:
        records = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeasonCoverageError("snapshot response is not valid JSON") from exc
    if not isinstance(records, list):
        raise SeasonCoverageError("snapshot response top level is not a list")

    match_ids: set[int] = set()
    expected_identity = (
        settings.shortcut,
        settings.season,
        settings.expected_league_id,
    )
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise SeasonCoverageError(f"snapshot record {index} is not an object")
        identity = (
            record.get("leagueShortcut"),
            record.get("leagueSeason"),
            record.get("leagueId"),
        )
        if identity != expected_identity:
            raise SeasonCoverageError(
                f"snapshot record {index} has unexpected competition identity"
            )
        provider_match_id = record.get("matchID")
        if (
            isinstance(provider_match_id, bool)
            or not isinstance(provider_match_id, int)
            or provider_match_id <= 0
        ):
            raise SeasonCoverageError(f"snapshot record {index} has no positive matchID")
        if provider_match_id in match_ids:
            raise SeasonCoverageError(f"snapshot response duplicates matchID {provider_match_id}")
        match_ids.add(provider_match_id)
    return tuple(sorted(match_ids))


def _local_matchdays(base_directory: Path) -> tuple[int, ...]:
    if not base_directory.is_dir():
        return ()
    matchdays: set[int] = set()
    for path in base_directory.iterdir():
        if not path.is_dir():
            continue
        match = re.fullmatch(r"matchday-(\d+)", path.name)
        if match is not None and int(match.group(1)) > 0:
            matchdays.add(int(match.group(1)))
    return tuple(sorted(matchdays))


def collect_season_coverage(settings: OpenLigaDBSettings) -> SeasonCoverageReport:
    """Compare configured league-phase coverage with local immutable source captures.

    This is deliberately an offline raw-capture audit. It does not contact OpenLigaDB,
    open SQL Server, infer provider availability, or claim that a captured snapshot was
    successfully imported.
    """

    season_directory = settings.raw_snapshot_directory / settings.shortcut / str(settings.season)
    matchdays: list[MatchdayCoverage] = []
    provider_matchday_index: dict[int, set[int]] = {}
    for matchday in settings.expected_league_phase_matchdays:
        directories = _snapshot_directories(season_directory, matchday)
        provider_match_ids: set[int] = set()
        errors: list[str] = []
        valid_snapshot_count = 0
        for directory in directories:
            try:
                identifiers = _read_snapshot_match_ids(directory, settings, matchday)
            except SeasonCoverageError as exc:
                errors.append(f"{directory.name}: {exc}")
                continue
            valid_snapshot_count += 1
            provider_match_ids.update(identifiers)
        for provider_match_id in provider_match_ids:
            provider_matchday_index.setdefault(provider_match_id, set()).add(matchday)
        matchdays.append(
            MatchdayCoverage(
                matchday=matchday,
                expected_fixture_count=settings.expected_fixtures_per_matchday,
                snapshot_count=len(directories),
                valid_snapshot_count=valid_snapshot_count,
                provider_match_ids=tuple(sorted(provider_match_ids)),
                invalid_snapshot_count=len(directories) - valid_snapshot_count,
                errors=tuple(errors),
            )
        )
    duplicate_provider_match_ids = tuple(
        sorted(
            provider_match_id
            for provider_match_id, matchdays_with_identifier in provider_matchday_index.items()
            if len(matchdays_with_identifier) > 1
        )
    )
    expected_matchdays = settings.expected_league_phase_matchdays
    return SeasonCoverageReport(
        expected_matchdays=expected_matchdays,
        expected_fixtures_per_matchday=settings.expected_fixtures_per_matchday,
        matchdays=tuple(matchdays),
        additional_local_matchdays=tuple(
            matchday
            for matchday in _local_matchdays(season_directory)
            if matchday not in expected_matchdays
        ),
        duplicate_provider_match_ids=duplicate_provider_match_ids,
    )
