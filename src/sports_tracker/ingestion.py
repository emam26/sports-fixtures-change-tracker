"""Offline snapshot parsing, validation, and transactional SQL Server import."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .config import OpenLigaDBSettings
from .database import database_connection
from .openligadb import build_matchday_url

_LOGGER = logging.getLogger(__name__)

TEAM_ICON_URL_MAX_LENGTH = 2048


class SnapshotValidationError(ValueError):
    """Raised when snapshot metadata or the top-level source contract is unsafe."""


class ImportExecutionError(RuntimeError):
    """Raised when snapshot persistence fails, with the rollback outcome stated safely."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """An actionable source or transformation validation problem."""

    code: str
    message: str
    severity: str = "Error"
    source_record_id: str | None = None
    field_name: str | None = None
    source_value: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Validated metadata written by the Stage 1 snapshot writer."""

    provider: str
    url: str
    shortcut: str
    season: int
    matchday: int
    retrieved_at_utc: datetime
    http_status: int
    content_type: str | None
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class TeamData:
    """Provider-owned team fields observed in a match record."""

    provider_team_id: int
    team_name: str
    short_name: str | None
    tla: str | None
    team_group_name: str | None
    team_icon_url: str | None
    wikidata_id: str | None


@dataclass(frozen=True, slots=True)
class ResultData:
    """One provider result, retaining explicit result type and scores."""

    provider_result_id: int
    result_type_id: int | None
    result_type_kind: str
    result_order_id: int | None
    result_name: str | None
    result_description: str | None
    points_team1: int | None
    points_team2: int | None


@dataclass(frozen=True, slots=True)
class GoalData:
    """One provider goal object using only fields observed in saved snapshots."""

    provider_goal_id: int
    score_team1: int | None
    score_team2: int | None
    match_minute: int | None
    goal_getter_provider_id: int | None
    goal_getter_name: str | None
    scoring_team_provider_id: int | None
    is_penalty: bool | None
    is_own_goal: bool | None
    is_overtime: bool | None
    comment: str | None


@dataclass(frozen=True, slots=True)
class FixtureData:
    """Validated current fixture fields and source child collections."""

    provider_match_id: int
    competition_name: str
    home_team: TeamData
    away_team: TeamData
    matchday_number: int
    source_group_id: int | None
    source_group_order_id: int | None
    source_group_name: str | None
    kickoff_utc: datetime
    match_is_finished: bool
    source_last_update_raw: str | None
    source_time_zone_id: str | None
    location: str | None
    results: tuple[ResultData, ...]
    goals: tuple[GoalData, ...]

    def business_fields(self) -> dict[str, Any]:
        """Return source-owned fields used for current-record comparison."""

        return {
            "home_team_id": self.home_team.provider_team_id,
            "away_team_id": self.away_team.provider_team_id,
            "matchday_number": self.matchday_number,
            "competition_stage": None,
            "source_group_id": self.source_group_id,
            "source_group_order_id": self.source_group_order_id,
            "source_group_name": self.source_group_name,
            "kickoff_utc": self.kickoff_utc,
            "source_match_is_finished": self.match_is_finished,
            "source_last_update_utc": None,
            "source_last_update_raw": self.source_last_update_raw,
            "source_time_zone_id": self.source_time_zone_id,
            "location": self.location,
        }


@dataclass(frozen=True, slots=True)
class ParsedSnapshot:
    """Validated source snapshot ready for transactional persistence."""

    directory: Path
    metadata: SnapshotMetadata
    source_league_id: int
    competition_name: str
    matches: tuple[FixtureData, ...]
    issues: tuple[ValidationIssue, ...]
    source_last_change_utc: datetime | None = None

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "Error")


@dataclass(frozen=True, slots=True)
class MatchState:
    """Current match state returned by an import store."""

    match_id: int
    fields: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChildState:
    """Current result or goal state returned by an import store."""

    child_id: int
    fields: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ImportSummary:
    """Non-secret outcome counters for one snapshot import."""

    status: str
    import_run_id: int | None
    source_snapshot_id: int | None
    matches_seen: int
    matches_inserted: int
    matches_updated: int
    matches_unchanged: int
    matches_rejected: int
    results_seen: int
    goals_seen: int
    changes_recorded: int
    validation_issue_count: int
    issues: tuple[ValidationIssue, ...]


class ImportStore(Protocol):
    """Storage contract used by the importer and isolated unit tests."""

    def begin(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def ensure_snapshot(self, parsed: ParsedSnapshot) -> int: ...

    def ensure_competition(self, provider: str, shortcut: str, name: str) -> int: ...

    def ensure_season(
        self,
        competition_id: int,
        source_league_id: int,
        season: int,
    ) -> int: ...

    def find_successful_run(self, source_snapshot_id: int) -> int | None: ...

    def start_run(
        self,
        parsed: ParsedSnapshot,
        competition_season_id: int,
        source_snapshot_id: int,
        is_replay: bool,
        replay_of_import_run_id: int | None,
    ) -> int: ...

    def record_issues(
        self,
        import_run_id: int,
        source_snapshot_id: int,
        issues: Sequence[ValidationIssue],
    ) -> None: ...

    def finish_run(
        self,
        import_run_id: int,
        status: str,
        counters: ImportSummary,
        failure_phase: str | None = None,
        error_summary: str | None = None,
    ) -> None: ...

    def get_match(self, provider: str, provider_match_id: int) -> MatchState | None: ...

    def upsert_team(self, team: TeamData) -> int: ...

    def insert_match(
        self,
        fixture: FixtureData,
        competition_season_id: int,
        home_team_id: int,
        away_team_id: int,
    ) -> int: ...

    def update_match(
        self,
        match_id: int,
        fixture: FixtureData,
        home_team_id: int,
        away_team_id: int,
    ) -> None: ...

    def get_result(self, match_id: int, provider_result_id: int) -> ChildState | None: ...

    def insert_result(self, match_id: int, result: ResultData) -> int: ...

    def update_result(self, child_id: int, result: ResultData) -> None: ...

    def get_goal(self, match_id: int, provider_goal_id: int) -> ChildState | None: ...

    def insert_goal(self, match_id: int, goal: GoalData, scoring_team_id: int | None) -> int: ...

    def update_goal(self, child_id: int, goal: GoalData, scoring_team_id: int | None) -> None: ...

    def record_change(
        self,
        match_id: int,
        import_run_id: int,
        source_snapshot_id: int,
        field_name: str,
        change_kind: str,
        old_value: Any,
        new_value: Any,
        observed_at_utc: datetime,
    ) -> None: ...

    def advance_checkpoint(
        self,
        parsed: ParsedSnapshot,
        competition_season_id: int,
        source_snapshot_id: int,
        import_run_id: int,
    ) -> None: ...

    def record_failed_run(self, parsed: ParsedSnapshot, error_summary: str) -> None: ...


def _utc_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotValidationError(f"{field_name} must be a non-empty timestamp string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotValidationError(f"{field_name} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SnapshotValidationError(f"{field_name} must include an explicit timezone")
    return parsed.astimezone(UTC)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None)


def _from_database_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _record_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("matchID")
    return str(value) if value is not None else None


def _issue(
    issues: list[ValidationIssue],
    code: str,
    message: str,
    record_id: str | None,
    field_name: str | None = None,
    source_value: Any = None,
    severity: str = "Error",
) -> None:
    issues.append(
        ValidationIssue(
            code=code,
            message=message,
            severity=severity,
            source_record_id=record_id,
            field_name=field_name,
            source_value=None if source_value is None else str(source_value)[:4000],
        )
    )


def _required_int(
    record: Mapping[str, Any],
    key: str,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> int | None:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _issue(
            issues,
            "invalid-positive-integer",
            f"{key} must be a positive integer",
            record_id,
            key,
            value,
        )
        return None
    return value


def _optional_int(
    record: Mapping[str, Any],
    key: str,
    issues: list[ValidationIssue],
    record_id: str | None,
    *,
    nonnegative: bool = False,
) -> int | None:
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or (nonnegative and value < 0):
        descriptor = "a non-negative integer" if nonnegative else "an integer"
        _issue(
            issues,
            "invalid-integer",
            f"{key} must be {descriptor} or null",
            record_id,
            key,
            value,
        )
        return None
    return value


def _required_text(
    record: Mapping[str, Any],
    key: str,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> str | None:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        _issue(issues, "invalid-text", f"{key} must be a non-empty string", record_id, key, value)
        return None
    return value


def _optional_text(
    record: Mapping[str, Any],
    key: str,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _issue(issues, "invalid-text", f"{key} must be a string or null", record_id, key, value)
        return None
    return value


def _normalize_team_icon_url(
    value: Any,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> str | None:
    """Keep only schema-safe external team-icon URLs without exposing embedded data."""

    if value is None:
        return None
    if not isinstance(value, str):
        _issue(
            issues,
            "invalid-team-icon-url",
            "teamIconUrl was omitted because it is not a string",
            record_id,
            "teamIconUrl",
            type(value).__name__,
            severity="Warning",
        )
        return None

    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = urlsplit(normalized)
    except ValueError:
        _issue(
            issues,
            "invalid-team-icon-url",
            "teamIconUrl was omitted because it is not a valid URL",
            record_id,
            "teamIconUrl",
            f"URL ({len(normalized)} characters)",
            severity="Warning",
        )
        return None

    scheme = parsed.scheme.lower()
    if scheme == "data":
        _issue(
            issues,
            "embedded-team-icon-omitted",
            "teamIconUrl was omitted because embedded data URIs are not stored as URLs",
            record_id,
            "teamIconUrl",
            f"data URI ({len(normalized)} characters)",
            severity="Warning",
        )
        return None
    if scheme not in {"http", "https"} or not parsed.netloc:
        _issue(
            issues,
            "invalid-team-icon-url",
            "teamIconUrl was omitted because only absolute HTTP(S) URLs are stored",
            record_id,
            "teamIconUrl",
            f"{scheme or 'no-scheme'} URL ({len(normalized)} characters)",
            severity="Warning",
        )
        return None
    if len(normalized) > TEAM_ICON_URL_MAX_LENGTH:
        _issue(
            issues,
            "team-icon-url-too-long",
            "teamIconUrl was omitted because it exceeds the database URL length limit",
            record_id,
            "teamIconUrl",
            f"{scheme.upper()} URL ({len(normalized)} characters)",
            severity="Warning",
        )
        return None
    return normalized


def _optional_bool(
    record: Mapping[str, Any],
    key: str,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> bool | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        _issue(issues, "invalid-boolean", f"{key} must be boolean or null", record_id, key, value)
        return None
    return value


def _parse_team(
    value: Any,
    team_label: str,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> TeamData | None:
    if not isinstance(value, dict):
        _issue(
            issues,
            "missing-team-object",
            f"{team_label} must be an object",
            record_id,
            team_label,
        )
        return None
    team_id = _required_int(value, "teamId", issues, record_id)
    team_name = _required_text(value, "teamName", issues, record_id)
    if team_id is None or team_name is None:
        return None
    return TeamData(
        provider_team_id=team_id,
        team_name=team_name,
        short_name=_optional_text(value, "shortName", issues, record_id),
        tla=_optional_text(value, "tla", issues, record_id),
        team_group_name=_optional_text(value, "teamGroupName", issues, record_id),
        team_icon_url=_normalize_team_icon_url(value.get("teamIconUrl"), issues, record_id),
        wikidata_id=_optional_text(value, "wikidataId", issues, record_id),
    )


def _parse_result(
    value: Any,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> ResultData | None:
    if not isinstance(value, dict):
        _issue(
            issues,
            "invalid-result-object",
            "matchResults entries must be objects",
            record_id,
            "matchResults",
        )
        return None
    result_id = _required_int(value, "resultID", issues, record_id)
    result_type_kind = _required_text(value, "resultTypeKind", issues, record_id)
    result_type_id = _optional_int(value, "resultTypeID", issues, record_id)
    result_order_id = _optional_int(value, "resultOrderID", issues, record_id, nonnegative=True)
    points_team1 = _optional_int(value, "pointsTeam1", issues, record_id, nonnegative=True)
    points_team2 = _optional_int(value, "pointsTeam2", issues, record_id, nonnegative=True)
    if (points_team1 is None) != (points_team2 is None):
        _issue(
            issues,
            "incomplete-score-pair",
            "pointsTeam1 and pointsTeam2 must both be present or both be null",
            record_id,
            "matchResults",
        )
    if result_id is None or result_type_kind is None:
        return None
    return ResultData(
        provider_result_id=result_id,
        result_type_id=result_type_id,
        result_type_kind=result_type_kind,
        result_order_id=result_order_id,
        result_name=_optional_text(value, "resultName", issues, record_id),
        result_description=_optional_text(value, "resultDescription", issues, record_id),
        points_team1=points_team1,
        points_team2=points_team2,
    )


def _parse_goal(
    value: Any,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> GoalData | None:
    if not isinstance(value, dict):
        _issue(issues, "invalid-goal-object", "goals entries must be objects", record_id, "goals")
        return None
    goal_id = _required_int(value, "goalID", issues, record_id)
    if goal_id is None:
        return None
    score_team1 = _optional_int(value, "scoreTeam1", issues, record_id, nonnegative=True)
    score_team2 = _optional_int(value, "scoreTeam2", issues, record_id, nonnegative=True)
    if (score_team1 is None) != (score_team2 is None):
        _issue(
            issues,
            "incomplete-goal-score-pair",
            "scoreTeam1 and scoreTeam2 must both be present or both be null",
            record_id,
            "goals",
        )
    return GoalData(
        provider_goal_id=goal_id,
        score_team1=score_team1,
        score_team2=score_team2,
        match_minute=_optional_int(value, "matchMinute", issues, record_id, nonnegative=True),
        goal_getter_provider_id=_optional_int(value, "goalGetterID", issues, record_id),
        goal_getter_name=_optional_text(value, "goalGetterName", issues, record_id),
        scoring_team_provider_id=_optional_int(value, "scoringTeamId", issues, record_id),
        is_penalty=_optional_bool(value, "isPenalty", issues, record_id),
        is_own_goal=_optional_bool(value, "isOwnGoal", issues, record_id),
        is_overtime=_optional_bool(value, "isOvertime", issues, record_id),
        comment=_optional_text(value, "comment", issues, record_id),
    )


def _validate_scores(
    fixture: FixtureData,
    issues: list[ValidationIssue],
    record_id: str | None,
) -> None:
    final_result = next(
        (result for result in fixture.results if result.result_type_kind == "After90Minutes"),
        None,
    )
    halftime_result = next(
        (result for result in fixture.results if result.result_type_kind == "HalfTime"),
        None,
    )
    if fixture.match_is_finished and final_result is None:
        _issue(
            issues,
            "finished-match-missing-final-result",
            "finished matches must contain an After90Minutes result",
            record_id,
            "matchResults",
        )
    if (
        final_result is not None
        and halftime_result is not None
        and final_result.points_team1 is not None
        and halftime_result.points_team1 is not None
        and (
            halftime_result.points_team1 > final_result.points_team1
            or halftime_result.points_team2 > final_result.points_team2
        )
    ):
        _issue(
            issues,
            "halftime-score-exceeds-final",
            "half-time scores cannot exceed the corresponding final scores",
            record_id,
            "matchResults",
        )

    previous_score: tuple[int, int] | None = None
    has_overtime_goal = any(goal.is_overtime is True for goal in fixture.goals)
    last_score: tuple[int, int] | None = None
    for goal in fixture.goals:
        if goal.score_team1 is None or goal.score_team2 is None:
            continue
        current_score = (goal.score_team1, goal.score_team2)
        last_score = current_score
        if previous_score is not None and (
            current_score[0] < previous_score[0] or current_score[1] < previous_score[1]
        ):
            _issue(
                issues,
                "goal-cumulative-score-decreased",
                "goal cumulative scores must not decrease through the source goal list",
                record_id,
                "goals",
            )
        previous_score = current_score

    if final_result is None or final_result.points_team1 is None or has_overtime_goal:
        return
    final_score = (final_result.points_team1, final_result.points_team2)
    if last_score is None and final_score != (0, 0):
        _issue(
            issues,
            "result-goal-score-mismatch",
            "a non-zero final score requires corresponding cumulative goal scores",
            record_id,
            "matchResults",
        )
    elif last_score is not None and last_score != final_score:
        _issue(
            issues,
            "result-goal-score-mismatch",
            "After90Minutes scores must match the final cumulative goal scores",
            record_id,
            "matchResults",
        )


def _parse_fixture(
    record: Mapping[str, Any],
    settings: OpenLigaDBSettings,
    matchday: int,
    issues: list[ValidationIssue],
) -> FixtureData | None:
    record_id = _record_id(record)
    match_id = _required_int(record, "matchID", issues, record_id)
    competition_name = _required_text(record, "leagueName", issues, record_id)
    home_team = _parse_team(record.get("team1"), "team1", issues, record_id)
    away_team = _parse_team(record.get("team2"), "team2", issues, record_id)
    kickoff_raw = record.get("matchDateTimeUTC")
    kickoff_utc: datetime | None = None
    try:
        kickoff_utc = _utc_datetime(kickoff_raw, "matchDateTimeUTC")
    except SnapshotValidationError as exc:
        _issue(
            issues,
            "invalid-kickoff-timestamp",
            str(exc),
            record_id,
            "matchDateTimeUTC",
            kickoff_raw,
        )
    match_is_finished = record.get("matchIsFinished")
    if not isinstance(match_is_finished, bool):
        _issue(
            issues,
            "invalid-finished-flag",
            "matchIsFinished must be boolean",
            record_id,
            "matchIsFinished",
            match_is_finished,
        )
        match_is_finished = False

    source_last_update_raw = _optional_text(record, "lastUpdateDateTime", issues, record_id)
    source_time_zone_id = _optional_text(record, "timeZoneID", issues, record_id)
    location = _optional_text(record, "location", issues, record_id)
    group = record.get("group")
    source_group_id = None
    source_group_order_id = None
    source_group_name = None
    if group is not None:
        if not isinstance(group, dict):
            _issue(
                issues,
                "invalid-group-object",
                "group must be an object or null",
                record_id,
                "group",
            )
        else:
            source_group_id = _optional_int(group, "groupID", issues, record_id)
            source_group_order_id = _optional_int(
                group,
                "groupOrderID",
                issues,
                record_id,
                nonnegative=True,
            )
            source_group_name = _optional_text(group, "groupName", issues, record_id)

    results_value = record.get("matchResults")
    results: list[ResultData] = []
    if not isinstance(results_value, list):
        _issue(
            issues,
            "invalid-match-results-collection",
            "matchResults must be a list, including an empty list for an unfinished match",
            record_id,
            "matchResults",
        )
    else:
        seen_result_ids: set[int] = set()
        seen_result_types: set[str] = set()
        for result_value in results_value:
            result = _parse_result(result_value, issues, record_id)
            if result is None:
                continue
            if result.provider_result_id in seen_result_ids:
                _issue(
                    issues,
                    "duplicate-result-id",
                    "provider result ID is duplicated",
                    record_id,
                    "resultID",
                )
            if result.result_type_kind in seen_result_types:
                _issue(
                    issues,
                    "duplicate-result-type",
                    "a match cannot contain duplicate result type kinds",
                    record_id,
                    "resultTypeKind",
                )
            seen_result_ids.add(result.provider_result_id)
            seen_result_types.add(result.result_type_kind)
            results.append(result)

    goals_value = record.get("goals")
    goals: list[GoalData] = []
    if goals_value is None:
        _issue(
            issues,
            "missing-goals-collection",
            "goals collection is absent; treating it as unavailable rather than inventing goals",
            record_id,
            "goals",
            severity="Warning",
        )
    elif not isinstance(goals_value, list):
        _issue(
            issues,
            "invalid-goals-collection",
            "goals must be a list or null",
            record_id,
            "goals",
        )
    else:
        seen_goal_ids: set[int] = set()
        for goal_value in goals_value:
            goal = _parse_goal(goal_value, issues, record_id)
            if goal is None:
                continue
            if goal.provider_goal_id in seen_goal_ids:
                _issue(
                    issues,
                    "duplicate-goal-id",
                    "provider goal ID is duplicated",
                    record_id,
                    "goalID",
                )
            seen_goal_ids.add(goal.provider_goal_id)
            goals.append(goal)

    if (
        home_team is not None
        and away_team is not None
        and home_team.provider_team_id == away_team.provider_team_id
    ):
        _issue(
            issues,
            "same-home-away-team",
            "team1 and team2 must have different provider IDs",
            record_id,
        )
    known_team_ids = {team.provider_team_id for team in (home_team, away_team) if team is not None}
    for goal in goals:
        if (
            goal.scoring_team_provider_id is not None
            and goal.scoring_team_provider_id not in known_team_ids
        ):
            _issue(
                issues,
                "unknown-scoring-team",
                "scoringTeamId must match team1 or team2",
                record_id,
                "scoringTeamId",
                goal.scoring_team_provider_id,
            )

    if (
        match_id is None
        or competition_name is None
        or home_team is None
        or away_team is None
        or kickoff_utc is None
        or any(
            issue.severity == "Error" and issue.source_record_id == record_id for issue in issues
        )
    ):
        return None

    fixture = FixtureData(
        provider_match_id=match_id,
        competition_name=competition_name,
        home_team=home_team,
        away_team=away_team,
        matchday_number=matchday,
        source_group_id=source_group_id,
        source_group_order_id=source_group_order_id,
        source_group_name=source_group_name,
        kickoff_utc=kickoff_utc,
        match_is_finished=match_is_finished,
        source_last_update_raw=source_last_update_raw,
        source_time_zone_id=source_time_zone_id,
        location=location,
        results=tuple(results),
        goals=tuple(goals),
    )
    _validate_scores(fixture, issues, record_id)
    if any(issue.severity == "Error" and issue.source_record_id == record_id for issue in issues):
        return None
    return fixture


def _snapshot_directory(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_file():
        if candidate.name not in {"response.json", "metadata.json"}:
            raise SnapshotValidationError(
                "snapshot path must be a directory or response.json/metadata.json"
            )
        candidate = candidate.parent
    if not candidate.is_dir():
        raise SnapshotValidationError(f"snapshot directory does not exist: {candidate}")
    directory = candidate.resolve()
    if len(str(directory)) > 750:
        raise SnapshotValidationError(
            "snapshot directory exceeds the SQL Server local_directory limit"
        )
    return directory


def _read_metadata(path: Path) -> SnapshotMetadata:
    try:
        raw = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotValidationError("could not read snapshot metadata.json") from exc
    if not isinstance(raw, dict):
        raise SnapshotValidationError("snapshot metadata.json must contain an object")
    try:
        provider = raw["provider"]
        url = raw["url"]
        shortcut = raw["shortcut"]
        season = raw["season"]
        matchday = raw["matchday"]
        retrieved_at_utc = _utc_datetime(raw["retrieved_at_utc"], "retrieved_at_utc")
        http_status = raw["http_status"]
        content_type = raw.get("content_type")
        byte_count = raw["byte_count"]
        sha256 = raw["sha256"]
    except (KeyError, TypeError, ValueError) as exc:
        raise SnapshotValidationError("snapshot metadata.json is missing required fields") from exc
    if not isinstance(provider, str) or not provider.strip():
        raise SnapshotValidationError("snapshot metadata provider must be non-empty")
    if not isinstance(url, str) or not url.strip():
        raise SnapshotValidationError("snapshot metadata URL must be non-empty")
    if not isinstance(shortcut, str) or not shortcut.strip():
        raise SnapshotValidationError("snapshot metadata shortcut must be non-empty")
    if isinstance(season, bool) or not isinstance(season, int):
        raise SnapshotValidationError("snapshot metadata season must be an integer")
    if isinstance(matchday, bool) or not isinstance(matchday, int) or matchday <= 0:
        raise SnapshotValidationError("snapshot metadata matchday must be a positive integer")
    if (
        isinstance(http_status, bool)
        or not isinstance(http_status, int)
        or not 200 <= http_status < 300
    ):
        raise SnapshotValidationError("snapshot metadata HTTP status must be successful")
    if content_type is not None and not isinstance(content_type, str):
        raise SnapshotValidationError("snapshot metadata content_type must be a string or null")
    if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
        raise SnapshotValidationError("snapshot metadata byte_count must be non-negative")
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-fA-F]{64}", sha256) is None:
        raise SnapshotValidationError("snapshot metadata sha256 must be a 64-character hex digest")
    return SnapshotMetadata(
        provider=provider,
        url=url,
        shortcut=shortcut,
        season=season,
        matchday=matchday,
        retrieved_at_utc=retrieved_at_utc,
        http_status=http_status,
        content_type=content_type,
        byte_count=byte_count,
        sha256=sha256.lower(),
    )


def load_snapshot(path: str | Path, settings: OpenLigaDBSettings) -> ParsedSnapshot:
    """Read and validate one immutable local response snapshot."""

    directory = _snapshot_directory(path)
    try:
        directory.resolve().relative_to(settings.raw_snapshot_directory.resolve())
    except ValueError as exc:
        raise SnapshotValidationError("snapshot must be under RAW_SNAPSHOT_DIRECTORY") from exc
    metadata = _read_metadata(directory)
    response_path = directory / "response.json"
    try:
        body = response_path.read_bytes()
    except OSError as exc:
        raise SnapshotValidationError("could not read snapshot response.json") from exc
    digest = hashlib.sha256(body).hexdigest()
    if len(body) != metadata.byte_count:
        raise SnapshotValidationError("snapshot byte_count does not match response.json")
    if digest != metadata.sha256:
        raise SnapshotValidationError("snapshot SHA-256 does not match response.json")
    if metadata.provider != "OpenLigaDB":
        raise SnapshotValidationError("snapshot provider must be OpenLigaDB")
    if metadata.shortcut != settings.shortcut or metadata.season != settings.season:
        raise SnapshotValidationError("snapshot competition identity does not match configuration")
    expected_url = build_matchday_url(settings, metadata.matchday)
    if metadata.url != expected_url:
        raise SnapshotValidationError("snapshot URL does not match configured matchday")
    try:
        records = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise SnapshotValidationError("snapshot response.json is not valid JSON") from exc
    if not isinstance(records, list) or not records:
        raise SnapshotValidationError("snapshot response top level must be a non-empty list")

    first_record = records[0]
    if not isinstance(first_record, dict):
        raise SnapshotValidationError("snapshot records must be JSON objects")
    competition_name = first_record.get("leagueName")
    if not isinstance(competition_name, str) or not competition_name.strip():
        raise SnapshotValidationError("snapshot records must contain a non-empty leagueName")
    issues: list[ValidationIssue] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise SnapshotValidationError(f"snapshot record {index} must be a JSON object")
        identity = (
            record.get("leagueShortcut"),
            record.get("leagueSeason"),
            record.get("leagueId"),
        )
        expected_identity = (settings.shortcut, settings.season, settings.expected_league_id)
        if identity != expected_identity:
            raise SnapshotValidationError(
                f"snapshot record {index} has unexpected competition identity"
            )
        if record.get("leagueName") != competition_name:
            _issue(
                issues,
                "inconsistent-competition-name",
                "leagueName differs within one snapshot",
                _record_id(record),
                "leagueName",
                record.get("leagueName"),
            )

    match_ids: set[int] = set()
    matches: list[FixtureData] = []
    for record in records:
        assert isinstance(record, dict)
        fixture = _parse_fixture(record, settings, metadata.matchday, issues)
        match_id = record.get("matchID")
        if isinstance(match_id, int) and not isinstance(match_id, bool):
            if match_id in match_ids:
                _issue(
                    issues,
                    "duplicate-match-id",
                    "provider match ID is duplicated",
                    str(match_id),
                    "matchID",
                )
            match_ids.add(match_id)
        if fixture is not None:
            matches.append(fixture)
    return ParsedSnapshot(
        directory,
        metadata,
        settings.expected_league_id,
        competition_name,
        tuple(matches),
        tuple(issues),
    )


def _safe_error_summary(error: BaseException) -> str:
    message = str(error)
    message = re.sub(
        r"(?i)(pwd|password)\s*=\s*(?:\{(?:[^}]|\}\})*\}|[^;\s]+)",
        r"\1=<redacted>",
        message,
    )
    return f"{error.__class__.__name__}: {message}"[:4000]


class SQLServerOperationError(RuntimeError):
    """Wrap one SQL operation failure with its non-secret operation name."""

    def __init__(self, operation: str, original_error: BaseException) -> None:
        self.operation = operation
        self.original_error = original_error
        super().__init__(_safe_error_summary(original_error))


class _DiagnosticCursor:
    """Add operation context to cursor errors without retaining SQL parameters."""

    def __init__(self, cursor: Any, operation: str) -> None:
        self._cursor = cursor
        self._operation = operation

    def execute(self, statement: str, parameters: Sequence[Any] = ()) -> Any:
        try:
            return self._cursor.execute(statement, tuple(parameters))
        except Exception as exc:
            raise SQLServerOperationError(self._operation, exc) from exc

    @property
    def description(self) -> Any:
        """Expose the current result-set description without exposing SQL text."""

        try:
            return self._cursor.description
        except Exception as exc:
            raise SQLServerOperationError(self._operation, exc) from exc

    def nextset(self) -> bool:
        """Advance past the current result set and retain operation diagnostics."""

        try:
            return bool(self._cursor.nextset())
        except Exception as exc:
            raise SQLServerOperationError(self._operation, exc) from exc

    def fetchone(self) -> Any:
        try:
            return self._cursor.fetchone()
        except Exception as exc:
            raise SQLServerOperationError(self._operation, exc) from exc


def _serialize_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        return left.astimezone(UTC) == right.astimezone(UTC)
    return left == right


def _diff_fields(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    return [field for field in new if not _values_equal(old.get(field), new[field])]


def _result_fields(result: ResultData) -> dict[str, Any]:
    return {
        "result_type_id": result.result_type_id,
        "result_type_kind": result.result_type_kind,
        "result_order_id": result.result_order_id,
        "result_name": result.result_name,
        "result_description": result.result_description,
        "points_team1": result.points_team1,
        "points_team2": result.points_team2,
    }


def _goal_fields(goal: GoalData, scoring_team_id: int | None) -> dict[str, Any]:
    return {
        "score_team1": goal.score_team1,
        "score_team2": goal.score_team2,
        "match_minute": goal.match_minute,
        "goal_getter_provider_id": goal.goal_getter_provider_id,
        "goal_getter_name": goal.goal_getter_name,
        "scoring_team_id": scoring_team_id,
        "is_penalty": goal.is_penalty,
        "is_own_goal": goal.is_own_goal,
        "is_overtime": goal.is_overtime,
        "comment": goal.comment,
    }


class SnapshotImportProcessor:
    """Apply a parsed snapshot through a transactional import-store contract."""

    def __init__(self, store: ImportStore) -> None:
        self.store = store

    def import_snapshot(self, parsed: ParsedSnapshot) -> ImportSummary:
        self.store.begin()
        import_run_id: int | None = None
        source_snapshot_id: int | None = None
        try:
            source_snapshot_id = self.store.ensure_snapshot(parsed)
            competition_id = self.store.ensure_competition(
                parsed.metadata.provider,
                parsed.metadata.shortcut,
                parsed.competition_name,
            )
            competition_season_id = self.store.ensure_season(
                competition_id,
                parsed.source_league_id,
                parsed.metadata.season,
            )
            previous_run_id = self.store.find_successful_run(source_snapshot_id)
            import_run_id = self.store.start_run(
                parsed,
                competition_season_id,
                source_snapshot_id,
                previous_run_id is not None,
                previous_run_id,
            )
            if parsed.errors:
                rejected = len(
                    {issue.source_record_id for issue in parsed.errors if issue.source_record_id}
                )
                summary = ImportSummary(
                    status="Failed",
                    import_run_id=import_run_id,
                    source_snapshot_id=source_snapshot_id,
                    matches_seen=len(parsed.matches),
                    matches_inserted=0,
                    matches_updated=0,
                    matches_unchanged=0,
                    matches_rejected=rejected,
                    results_seen=0,
                    goals_seen=0,
                    changes_recorded=0,
                    validation_issue_count=len(parsed.issues),
                    issues=parsed.issues,
                )
                self.store.record_issues(import_run_id, source_snapshot_id, parsed.issues)
                self.store.finish_run(
                    import_run_id,
                    "Failed",
                    summary,
                    "validation",
                    "snapshot validation failed",
                )
                self.store.commit()
                return summary

            matches_inserted = 0
            matches_updated = 0
            matches_unchanged = 0
            results_seen = 0
            goals_seen = 0
            changes_recorded = 0
            for fixture in parsed.matches:
                home_team_id = self.store.upsert_team(fixture.home_team)
                away_team_id = self.store.upsert_team(fixture.away_team)
                scoring_team_ids = {
                    fixture.home_team.provider_team_id: home_team_id,
                    fixture.away_team.provider_team_id: away_team_id,
                }
                existing_match = self.store.get_match(
                    parsed.metadata.provider,
                    fixture.provider_match_id,
                )
                is_baseline = existing_match is None
                if is_baseline:
                    match_id = self.store.insert_match(
                        fixture,
                        competition_season_id,
                        home_team_id,
                        away_team_id,
                    )
                    matches_inserted += 1
                else:
                    match_id = existing_match.match_id
                    new_match_fields = fixture.business_fields()
                    changed_match_fields = _diff_fields(existing_match.fields, new_match_fields)
                    if changed_match_fields:
                        self.store.update_match(match_id, fixture, home_team_id, away_team_id)
                        matches_updated += 1
                        for field_name in changed_match_fields:
                            self.store.record_change(
                                match_id,
                                import_run_id,
                                source_snapshot_id,
                                field_name,
                                "Updated",
                                existing_match.fields.get(field_name),
                                new_match_fields[field_name],
                                parsed.metadata.retrieved_at_utc,
                            )
                            changes_recorded += 1
                    else:
                        matches_unchanged += 1

                for result in fixture.results:
                    results_seen += 1
                    existing_result = self.store.get_result(match_id, result.provider_result_id)
                    if existing_result is None:
                        self.store.insert_result(match_id, result)
                        if not is_baseline:
                            for field_name, new_value in _result_fields(result).items():
                                if new_value is not None:
                                    self.store.record_change(
                                        match_id,
                                        import_run_id,
                                        source_snapshot_id,
                                        f"result.{result.provider_result_id}.{field_name}",
                                        "Inserted",
                                        None,
                                        new_value,
                                        parsed.metadata.retrieved_at_utc,
                                    )
                                    changes_recorded += 1
                    else:
                        new_fields = _result_fields(result)
                        changed_fields = _diff_fields(existing_result.fields, new_fields)
                        if changed_fields:
                            self.store.update_result(existing_result.child_id, result)
                            for field_name in changed_fields:
                                self.store.record_change(
                                    match_id,
                                    import_run_id,
                                    source_snapshot_id,
                                    f"result.{result.provider_result_id}.{field_name}",
                                    "Updated",
                                    existing_result.fields.get(field_name),
                                    new_fields[field_name],
                                    parsed.metadata.retrieved_at_utc,
                                )
                                changes_recorded += 1

                for goal in fixture.goals:
                    goals_seen += 1
                    scoring_team_id = scoring_team_ids.get(goal.scoring_team_provider_id)
                    existing_goal = self.store.get_goal(match_id, goal.provider_goal_id)
                    if existing_goal is None:
                        self.store.insert_goal(match_id, goal, scoring_team_id)
                        if not is_baseline:
                            for field_name, new_value in _goal_fields(
                                goal,
                                scoring_team_id,
                            ).items():
                                if new_value is not None:
                                    self.store.record_change(
                                        match_id,
                                        import_run_id,
                                        source_snapshot_id,
                                        f"goal.{goal.provider_goal_id}.{field_name}",
                                        "Inserted",
                                        None,
                                        new_value,
                                        parsed.metadata.retrieved_at_utc,
                                    )
                                    changes_recorded += 1
                    else:
                        new_fields = _goal_fields(goal, scoring_team_id)
                        changed_fields = _diff_fields(existing_goal.fields, new_fields)
                        if changed_fields:
                            self.store.update_goal(existing_goal.child_id, goal, scoring_team_id)
                            for field_name in changed_fields:
                                self.store.record_change(
                                    match_id,
                                    import_run_id,
                                    source_snapshot_id,
                                    f"goal.{goal.provider_goal_id}.{field_name}",
                                    "Updated",
                                    existing_goal.fields.get(field_name),
                                    new_fields[field_name],
                                    parsed.metadata.retrieved_at_utc,
                                )
                                changes_recorded += 1

            self.store.advance_checkpoint(
                parsed,
                competition_season_id,
                source_snapshot_id,
                import_run_id,
            )
            summary = ImportSummary(
                status="Succeeded",
                import_run_id=import_run_id,
                source_snapshot_id=source_snapshot_id,
                matches_seen=len(parsed.matches),
                matches_inserted=matches_inserted,
                matches_updated=matches_updated,
                matches_unchanged=matches_unchanged,
                matches_rejected=0,
                results_seen=results_seen,
                goals_seen=goals_seen,
                changes_recorded=changes_recorded,
                validation_issue_count=len(parsed.issues),
                issues=parsed.issues,
            )
            if parsed.issues:
                self.store.record_issues(import_run_id, source_snapshot_id, parsed.issues)
            self.store.finish_run(import_run_id, "Succeeded", summary)
            self.store.commit()
            return summary
        except Exception as exc:
            operation = getattr(exc, "operation", None) or getattr(
                self.store,
                "last_operation",
                None,
            )
            safe_error = _safe_error_summary(exc)
            error_summary = f"{operation}: {safe_error}" if operation else safe_error
            error_summary = error_summary[:4000]
            failure_location = f" during {operation}" if operation else ""
            _LOGGER.error("Snapshot import failed%s: %s", failure_location, safe_error)
            rollback_succeeded = False
            try:
                self.store.rollback()
            except Exception as rollback_error:
                _LOGGER.error(
                    "Snapshot import rollback failed%s: %s",
                    failure_location,
                    _safe_error_summary(rollback_error),
                )
            else:
                rollback_succeeded = True
            if rollback_succeeded:
                try:
                    self.store.record_failed_run(parsed, error_summary)
                except Exception as failed_run_error:
                    _LOGGER.error(
                        "Failed import run could not be recorded%s: %s",
                        failure_location,
                        _safe_error_summary(failed_run_error),
                    )
            else:
                _LOGGER.error(
                    "Failed import-run provenance was not recorded%s because rollback "
                    "was not confirmed",
                    failure_location,
                )
            transaction_outcome = (
                "the transactional data was rolled back"
                if rollback_succeeded
                else "rollback failed; database state is unconfirmed"
            )
            raise ImportExecutionError(
                f"snapshot import failed{failure_location}: {safe_error}; {transaction_outcome}"
            ) from exc


class SQLServerImportStore:
    """SQL Server implementation of the Stage 3 import-store contract."""

    def __init__(self, connection: Any, provider: str = "OpenLigaDB") -> None:
        self.connection = connection
        self.provider = provider
        self._operation = "SQLServerImportStore.initialization"

    @property
    def last_operation(self) -> str:
        """Return the most recent named SQL operation for safe diagnostics."""

        return self._operation

    @property
    def cursor(self) -> Any:
        try:
            return _DiagnosticCursor(self.connection.cursor(), self._operation)
        except Exception as exc:
            raise SQLServerOperationError(self._operation, exc) from exc

    def begin(self) -> None:
        self._operation = "SQLServerImportStore.begin"
        self.connection.autocommit = False

    def commit(self) -> None:
        self._operation = "SQLServerImportStore.commit"
        self.connection.commit()

    def rollback(self) -> None:
        self._operation = "SQLServerImportStore.rollback"
        self.connection.rollback()

    def _insert_id(self, statement: str, parameters: Sequence[Any]) -> int:
        cursor = self.cursor
        cursor.execute(statement, tuple(parameters))
        # SQL Server may expose DML row-count results before the final SELECT.
        # Advance explicitly until the identity SELECT has an active result set.
        while cursor.description is None:
            if not cursor.nextset():
                raise RuntimeError("SQL Server did not return an identity result set")
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("SQL Server did not return the inserted identity")
        return int(row[0])

    def ensure_snapshot(self, parsed: ParsedSnapshot) -> int:
        self._operation = "SQLServerImportStore.ensure_snapshot"
        metadata = parsed.metadata
        local_directory = str(parsed.directory)
        cursor = self.cursor
        cursor.execute(
            """
            SELECT source_snapshot_id, sha256, retrieved_at_utc
            FROM dbo.source_snapshots
            WHERE provider = ? AND local_directory = ?
            """,
            (metadata.provider, local_directory),
        )
        row = cursor.fetchone()
        retrieved_at = _naive_utc(metadata.retrieved_at_utc)
        if row is not None:
            if str(row[1]).lower() != metadata.sha256 or row[2] != retrieved_at:
                raise RuntimeError(
                    "existing source snapshot metadata does not match the local snapshot"
                )
            return int(row[0])
        return self._insert_id(
            """
            INSERT INTO dbo.source_snapshots
            (
                provider, provider_shortcut, source_league_id, season_start_year,
                matchday_number, source_url, retrieved_at_utc, http_status,
                content_type, byte_count, sha256, local_directory, response_path,
                metadata_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            SELECT CAST(SCOPE_IDENTITY() AS bigint);
            """,
            (
                metadata.provider,
                metadata.shortcut,
                parsed.source_league_id,
                metadata.season,
                metadata.matchday,
                metadata.url,
                retrieved_at,
                metadata.http_status,
                metadata.content_type,
                metadata.byte_count,
                metadata.sha256,
                local_directory,
                str(parsed.directory / "response.json"),
                str(parsed.directory / "metadata.json"),
            ),
        )

    def ensure_competition(self, provider: str, shortcut: str, name: str) -> int:
        self._operation = "SQLServerImportStore.ensure_competition"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT competition_id
            FROM dbo.competitions
            WHERE provider = ? AND provider_shortcut = ?
            """,
            (provider, shortcut),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(row[0])
        return self._insert_id(
            """
            INSERT INTO dbo.competitions (provider, provider_shortcut, competition_name)
            VALUES (?, ?, ?);
            SELECT CAST(SCOPE_IDENTITY() AS bigint);
            """,
            (provider, shortcut, name),
        )

    def ensure_season(self, competition_id: int, source_league_id: int, season: int) -> int:
        self._operation = "SQLServerImportStore.ensure_season"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT competition_season_id
            FROM dbo.competition_seasons
            WHERE competition_id = ? AND source_league_id = ? AND season_start_year = ?
            """,
            (competition_id, source_league_id, season),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(row[0])
        return self._insert_id(
            """
            INSERT INTO dbo.competition_seasons
                (competition_id, source_league_id, season_start_year)
            VALUES (?, ?, ?);
            SELECT CAST(SCOPE_IDENTITY() AS bigint);
            """,
            (competition_id, source_league_id, season),
        )

    def find_successful_run(self, source_snapshot_id: int) -> int | None:
        self._operation = "SQLServerImportStore.find_successful_run"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT TOP (1) import_run_id
            FROM dbo.import_runs
            WHERE source_snapshot_id = ? AND status = 'Succeeded'
            ORDER BY import_run_id;
            """,
            (source_snapshot_id,),
        )
        row = cursor.fetchone()
        return None if row is None else int(row[0])

    def start_run(
        self,
        parsed: ParsedSnapshot,
        competition_season_id: int,
        source_snapshot_id: int,
        is_replay: bool,
        replay_of_import_run_id: int | None,
    ) -> int:
        self._operation = "SQLServerImportStore.start_run"
        return self._insert_id(
            """
            INSERT INTO dbo.import_runs
            (
                provider, competition_season_id, source_snapshot_id, matchday_number,
                requested_url, status, is_replay, replay_of_import_run_id
            )
            VALUES (?, ?, ?, ?, ?, 'Started', ?, ?);
            SELECT CAST(SCOPE_IDENTITY() AS bigint);
            """,
            (
                parsed.metadata.provider,
                competition_season_id,
                source_snapshot_id,
                parsed.metadata.matchday,
                parsed.metadata.url,
                is_replay,
                replay_of_import_run_id,
            ),
        )

    def record_issues(
        self,
        import_run_id: int,
        source_snapshot_id: int,
        issues: Sequence[ValidationIssue],
    ) -> None:
        self._operation = "SQLServerImportStore.record_issues"
        cursor = self.cursor
        for issue in issues:
            cursor.execute(
                """
                INSERT INTO dbo.validation_issues
                (
                    import_run_id, source_snapshot_id, provider, source_record_type,
                    source_record_id, field_name, issue_code, severity, issue_message,
                    source_value
                )
                VALUES (?, ?, ?, 'match', ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_run_id,
                    source_snapshot_id,
                    self.provider,
                    issue.source_record_id,
                    issue.field_name,
                    issue.code,
                    issue.severity,
                    issue.message,
                    issue.source_value,
                ),
            )

    def finish_run(
        self,
        import_run_id: int,
        status: str,
        counters: ImportSummary,
        failure_phase: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        self._operation = "SQLServerImportStore.finish_run"
        cursor = self.cursor
        cursor.execute(
            """
            UPDATE dbo.import_runs
            SET completed_at_utc = SYSUTCDATETIME(),
                status = ?,
                matches_seen = ?,
                matches_inserted = ?,
                matches_updated = ?,
                matches_unchanged = ?,
                matches_rejected = ?,
                results_seen = ?,
                validation_issue_count = ?,
                failure_phase = ?,
                error_summary = ?
            WHERE import_run_id = ?
            """,
            (
                status,
                counters.matches_seen,
                counters.matches_inserted,
                counters.matches_updated,
                counters.matches_unchanged,
                counters.matches_rejected,
                counters.results_seen,
                counters.validation_issue_count,
                failure_phase,
                error_summary,
                import_run_id,
            ),
        )

    def get_match(self, provider: str, provider_match_id: int) -> MatchState | None:
        self._operation = "SQLServerImportStore.get_match"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT
                m.match_id, t1.provider_team_id, t2.provider_team_id,
                m.matchday_number, m.competition_stage, m.source_group_id,
                m.source_group_order_id, m.source_group_name, m.kickoff_utc,
                m.source_match_is_finished, m.source_last_update_utc,
                m.source_last_update_raw, m.source_time_zone_id, m.location
            FROM dbo.matches AS m
            INNER JOIN dbo.teams AS t1 ON t1.team_id = m.home_team_id
            INNER JOIN dbo.teams AS t2 ON t2.team_id = m.away_team_id
            WHERE m.provider = ? AND m.provider_match_id = ?
            """,
            (provider, provider_match_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        fields = {
            "home_team_id": int(row[1]),
            "away_team_id": int(row[2]),
            "matchday_number": row[3],
            "competition_stage": row[4],
            "source_group_id": row[5],
            "source_group_order_id": row[6],
            "source_group_name": row[7],
            "kickoff_utc": _from_database_datetime(row[8]),
            "source_match_is_finished": bool(row[9]),
            "source_last_update_utc": _from_database_datetime(row[10]),
            "source_last_update_raw": row[11],
            "source_time_zone_id": row[12],
            "location": row[13],
        }
        return MatchState(int(row[0]), fields)

    def upsert_team(self, team: TeamData) -> int:
        self._operation = "SQLServerImportStore.upsert_team"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT team_id, team_name, short_name, tla, team_group_name,
                   team_icon_url, wikidata_id
            FROM dbo.teams
            WHERE provider = ? AND provider_team_id = ?
            """,
            (self.provider, team.provider_team_id),
        )
        row = cursor.fetchone()
        values = (
            team.team_name,
            team.short_name,
            team.tla,
            team.team_group_name,
            team.team_icon_url,
            team.wikidata_id,
        )
        if row is not None:
            if tuple(row[1:]) != values:
                cursor.execute(
                    """
                    UPDATE dbo.teams
                    SET team_name = ?, short_name = ?, tla = ?, team_group_name = ?,
                        team_icon_url = ?, wikidata_id = ?, updated_at_utc = SYSUTCDATETIME()
                    WHERE team_id = ?
                    """,
                    (*values, int(row[0])),
                )
            return int(row[0])
        return self._insert_id(
            """
            INSERT INTO dbo.teams
            (
                provider, provider_team_id, team_name, short_name, tla,
                team_group_name, team_icon_url, wikidata_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            SELECT CAST(SCOPE_IDENTITY() AS bigint);
            """,
            (self.provider, team.provider_team_id, *values),
        )

    def insert_match(
        self,
        fixture: FixtureData,
        competition_season_id: int,
        home_team_id: int,
        away_team_id: int,
    ) -> int:
        self._operation = "SQLServerImportStore.insert_match"
        return self._insert_id(
            """
            INSERT INTO dbo.matches
            (
                competition_season_id, provider, provider_match_id, home_team_id,
                away_team_id, matchday_number, source_group_id, source_group_order_id,
                source_group_name, kickoff_utc, source_match_is_finished,
                source_last_update_raw, source_time_zone_id, location
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            SELECT CAST(SCOPE_IDENTITY() AS bigint);
            """,
            (
                competition_season_id,
                self.provider,
                fixture.provider_match_id,
                home_team_id,
                away_team_id,
                fixture.matchday_number,
                fixture.source_group_id,
                fixture.source_group_order_id,
                fixture.source_group_name,
                _naive_utc(fixture.kickoff_utc),
                fixture.match_is_finished,
                fixture.source_last_update_raw,
                fixture.source_time_zone_id,
                fixture.location,
            ),
        )

    def update_match(
        self,
        match_id: int,
        fixture: FixtureData,
        home_team_id: int,
        away_team_id: int,
    ) -> None:
        self._operation = "SQLServerImportStore.update_match"
        self.cursor.execute(
            """
            UPDATE dbo.matches
            SET home_team_id = ?, away_team_id = ?, matchday_number = ?,
                source_group_id = ?, source_group_order_id = ?, source_group_name = ?,
                kickoff_utc = ?, source_match_is_finished = ?,
                source_last_update_raw = ?, source_time_zone_id = ?, location = ?,
                updated_at_utc = SYSUTCDATETIME()
            WHERE match_id = ?
            """,
            (
                home_team_id,
                away_team_id,
                fixture.matchday_number,
                fixture.source_group_id,
                fixture.source_group_order_id,
                fixture.source_group_name,
                _naive_utc(fixture.kickoff_utc),
                fixture.match_is_finished,
                fixture.source_last_update_raw,
                fixture.source_time_zone_id,
                fixture.location,
                match_id,
            ),
        )

    def get_result(self, match_id: int, provider_result_id: int) -> ChildState | None:
        self._operation = "SQLServerImportStore.get_result"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT match_result_id, result_type_id, result_type_kind, result_order_id,
                   result_name, result_description, points_team1, points_team2
            FROM dbo.match_results
            WHERE match_id = ? AND provider_result_id = ?
            """,
            (match_id, provider_result_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ChildState(
            int(row[0]),
            {
                "result_type_id": row[1],
                "result_type_kind": row[2],
                "result_order_id": row[3],
                "result_name": row[4],
                "result_description": row[5],
                "points_team1": row[6],
                "points_team2": row[7],
            },
        )

    def insert_result(self, match_id: int, result: ResultData) -> int:
        self._operation = "SQLServerImportStore.insert_result"
        return self._insert_id(
            """
            INSERT INTO dbo.match_results
            (
                match_id, provider, provider_result_id, result_type_id,
                result_type_kind, result_order_id, result_name, result_description,
                points_team1, points_team2
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            SELECT CAST(SCOPE_IDENTITY() AS bigint);
            """,
            (
                match_id,
                self.provider,
                result.provider_result_id,
                *tuple(_result_fields(result).values()),
            ),
        )

    def update_result(self, child_id: int, result: ResultData) -> None:
        self._operation = "SQLServerImportStore.update_result"
        self.cursor.execute(
            """
            UPDATE dbo.match_results
            SET result_type_id = ?, result_type_kind = ?, result_order_id = ?,
                result_name = ?, result_description = ?, points_team1 = ?, points_team2 = ?
            WHERE match_result_id = ?
            """,
            (*tuple(_result_fields(result).values()), child_id),
        )

    def get_goal(self, match_id: int, provider_goal_id: int) -> ChildState | None:
        self._operation = "SQLServerImportStore.get_goal"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT match_goal_id, score_team1, score_team2, match_minute,
                   goal_getter_provider_id, goal_getter_name, scoring_team_id,
                   is_penalty, is_own_goal, is_overtime, comment
            FROM dbo.match_goals
            WHERE match_id = ? AND provider_goal_id = ?
            """,
            (match_id, provider_goal_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ChildState(
            int(row[0]),
            {
                "score_team1": row[1],
                "score_team2": row[2],
                "match_minute": row[3],
                "goal_getter_provider_id": row[4],
                "goal_getter_name": row[5],
                "scoring_team_id": row[6],
                "is_penalty": row[7],
                "is_own_goal": row[8],
                "is_overtime": row[9],
                "comment": row[10],
            },
        )

    def insert_goal(self, match_id: int, goal: GoalData, scoring_team_id: int | None) -> int:
        self._operation = "SQLServerImportStore.insert_goal"
        return self._insert_id(
            """
            INSERT INTO dbo.match_goals
            (
                match_id, provider, provider_goal_id, score_team1, score_team2,
                match_minute, goal_getter_provider_id, goal_getter_name,
                scoring_team_id, is_penalty, is_own_goal, is_overtime, comment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            SELECT CAST(SCOPE_IDENTITY() AS bigint);
            """,
            (
                match_id,
                self.provider,
                goal.provider_goal_id,
                *tuple(_goal_fields(goal, scoring_team_id).values()),
            ),
        )

    def update_goal(self, child_id: int, goal: GoalData, scoring_team_id: int | None) -> None:
        self._operation = "SQLServerImportStore.update_goal"
        self.cursor.execute(
            """
            UPDATE dbo.match_goals
            SET score_team1 = ?, score_team2 = ?, match_minute = ?,
                goal_getter_provider_id = ?, goal_getter_name = ?, scoring_team_id = ?,
                is_penalty = ?, is_own_goal = ?, is_overtime = ?, comment = ?
            WHERE match_goal_id = ?
            """,
            (*tuple(_goal_fields(goal, scoring_team_id).values()), child_id),
        )

    def record_change(
        self,
        match_id: int,
        import_run_id: int,
        source_snapshot_id: int,
        field_name: str,
        change_kind: str,
        old_value: Any,
        new_value: Any,
        observed_at_utc: datetime,
    ) -> None:
        self._operation = "SQLServerImportStore.record_change"
        self.cursor.execute(
            """
            INSERT INTO dbo.match_changes
            (
                match_id, import_run_id, source_snapshot_id, field_name, change_kind,
                old_value, new_value, observed_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                import_run_id,
                source_snapshot_id,
                field_name[:128],
                change_kind,
                _serialize_value(old_value),
                _serialize_value(new_value),
                _naive_utc(observed_at_utc),
            ),
        )

    def advance_checkpoint(
        self,
        parsed: ParsedSnapshot,
        competition_season_id: int,
        source_snapshot_id: int,
        import_run_id: int,
    ) -> None:
        self._operation = "SQLServerImportStore.advance_checkpoint"
        scope_key = (
            f"{parsed.metadata.provider}:{parsed.metadata.shortcut}:"
            f"{parsed.metadata.season}:matchday:{parsed.metadata.matchday}"
        )
        cursor = self.cursor
        cursor.execute(
            """
            SELECT sync_checkpoint_id
            FROM dbo.sync_checkpoints
            WHERE provider = ? AND scope_key = ?
            """,
            (parsed.metadata.provider, scope_key),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                """
                INSERT INTO dbo.sync_checkpoints
                (
                    provider, competition_season_id, scope_key, matchday_number,
                    last_successful_snapshot_id, last_successful_import_run_id,
                    last_source_update_utc, last_processed_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    parsed.metadata.provider,
                    competition_season_id,
                    scope_key,
                    parsed.metadata.matchday,
                    source_snapshot_id,
                    import_run_id,
                    _naive_utc(parsed.source_last_change_utc),
                    _naive_utc(parsed.metadata.retrieved_at_utc),
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE dbo.sync_checkpoints
                SET last_successful_snapshot_id = ?, last_successful_import_run_id = ?,
                    last_source_update_utc = COALESCE(?, last_source_update_utc),
                    last_processed_at_utc = ?,
                    updated_at_utc = SYSUTCDATETIME()
                WHERE sync_checkpoint_id = ?
                """,
                (
                    source_snapshot_id,
                    import_run_id,
                    _naive_utc(parsed.source_last_change_utc),
                    _naive_utc(parsed.metadata.retrieved_at_utc),
                    int(row[0]),
                ),
            )

    def record_failed_run(self, parsed: ParsedSnapshot, error_summary: str) -> None:
        """Persist failure provenance only after the caller confirms primary rollback."""

        self._operation = "SQLServerImportStore.record_failed_run"
        try:
            snapshot_id = self.ensure_snapshot(parsed)
            competition_id = self.ensure_competition(
                parsed.metadata.provider,
                parsed.metadata.shortcut,
                parsed.competition_name,
            )
            season_id = self.ensure_season(
                competition_id,
                parsed.source_league_id,
                parsed.metadata.season,
            )
            previous_run_id = self.find_successful_run(snapshot_id)
            run_id = self.start_run(
                parsed,
                season_id,
                snapshot_id,
                previous_run_id is not None,
                previous_run_id,
            )
            issue = ValidationIssue("database-import-failure", error_summary, "Error")
            self.record_issues(run_id, snapshot_id, (issue,))
            counters = ImportSummary(
                status="Failed",
                import_run_id=run_id,
                source_snapshot_id=snapshot_id,
                matches_seen=len(parsed.matches),
                matches_inserted=0,
                matches_updated=0,
                matches_unchanged=0,
                matches_rejected=0,
                results_seen=0,
                goals_seen=0,
                changes_recorded=0,
                validation_issue_count=1,
                issues=(issue,),
            )
            self.finish_run(run_id, "Failed", counters, "database", error_summary)
            self.connection.commit()
        except Exception:
            try:
                self.connection.rollback()
            except Exception as provenance_rollback_error:
                _LOGGER.error(
                    "Failed import-run provenance rollback failed: %s",
                    _safe_error_summary(provenance_rollback_error),
                )
            raise


def import_snapshot_with_database(
    parsed: ParsedSnapshot,
    database_settings: Any,
) -> ImportSummary:
    """Import one parsed snapshot using the project's managed database context."""

    with database_connection(database_settings) as connection:
        return SnapshotImportProcessor(
            SQLServerImportStore(connection, parsed.metadata.provider)
        ).import_snapshot(parsed)
