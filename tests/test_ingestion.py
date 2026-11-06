import copy
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from sports_tracker.config import OpenLigaDBSettings
from sports_tracker.ingestion import (
    TEAM_ICON_URL_MAX_LENGTH,
    ChildState,
    FixtureData,
    GoalData,
    ImportExecutionError,
    ImportSummary,
    MatchState,
    ParsedSnapshot,
    ResultData,
    SnapshotImportProcessor,
    SnapshotValidationError,
    TeamData,
    ValidationIssue,
    load_snapshot,
)


def _settings(tmp_path: Path) -> OpenLigaDBSettings:
    return OpenLigaDBSettings(
        base_url="https://api.openligadb.de",
        shortcut="ucl",
        season=2026,
        expected_league_id=4946,
        timeout_seconds=10.0,
        raw_snapshot_directory=tmp_path / "data" / "raw",
    )


def _record(
    *,
    final_score: tuple[int, int] = (2, 1),
    finished: bool = True,
    match_id: int = 101,
    missing_team_id: bool = False,
    home_team_id: int = 10,
    away_team_id: int = 20,
    kickoff_utc: str | None = "2026-10-20T19:00:00Z",
    location: str | None = None,
    final_result_description: str = "Official-time result",
    home_team_icon_url: str | None = "https://example.test/home.png",
    away_team_icon_url: str | None = "https://example.test/away.png",
) -> dict[str, Any]:
    goals = [
        {
            "goalID": 1001,
            "scoreTeam1": 1,
            "scoreTeam2": 0,
            "matchMinute": 20,
            "goalGetterID": 501,
            "goalGetterName": "Forward One",
            "scoringTeamId": home_team_id,
            "isPenalty": False,
            "isOwnGoal": False,
            "isOvertime": False,
            "comment": None,
        },
        {
            "goalID": 1002,
            "scoreTeam1": 1,
            "scoreTeam2": 1,
            "matchMinute": 45,
            "goalGetterID": 502,
            "goalGetterName": "Forward Two",
            "scoringTeamId": away_team_id,
            "isPenalty": False,
            "isOwnGoal": False,
            "isOvertime": False,
            "comment": None,
        },
        {
            "goalID": 1003,
            "scoreTeam1": final_score[0],
            "scoreTeam2": final_score[1],
            "matchMinute": 70,
            "goalGetterID": 503,
            "goalGetterName": "Forward Three",
            "scoringTeamId": home_team_id,
            "isPenalty": False,
            "isOwnGoal": False,
            "isOvertime": False,
            "comment": None,
        },
    ]
    record: dict[str, Any] = {
        "matchID": match_id,
        "leagueId": 4946,
        "leagueName": "UEFA Champions League",
        "leagueSeason": 2026,
        "leagueShortcut": "ucl",
        "matchDateTime": "2026-10-20T21:00:00",
        "matchDateTimeUTC": kickoff_utc,
        "lastUpdateDateTime": "2026-10-20T22:58:45.61",
        "matchIsFinished": finished,
        "timeZoneID": None,
        "location": location,
        "group": {"groupName": "3.Spieltag", "groupOrderID": 3, "groupID": 50857},
        "team1": {
            "teamId": None if missing_team_id else home_team_id,
            "teamName": "Home FC",
            "shortName": "Home",
            "teamGroupName": None,
            "teamIconUrl": home_team_icon_url,
            "tla": "HOM",
            "wikidataId": None,
        },
        "team2": {
            "teamId": away_team_id,
            "teamName": "Away FC",
            "shortName": "Away",
            "teamGroupName": None,
            "teamIconUrl": away_team_icon_url,
            "tla": "AWA",
            "wikidataId": None,
        },
        "matchResults": []
        if not finished
        else [
            {
                "resultID": 2001,
                "resultName": "Halftime",
                "pointsTeam1": 1,
                "pointsTeam2": 1,
                "resultOrderID": 1,
                "resultTypeID": 1,
                "resultTypeKind": "HalfTime",
                "resultDescription": "Half-time result",
            },
            {
                "resultID": 2002,
                "resultName": "Final",
                "pointsTeam1": final_score[0],
                "pointsTeam2": final_score[1],
                "resultOrderID": 2,
                "resultTypeID": 2,
                "resultTypeKind": "After90Minutes",
                "resultDescription": final_result_description,
            },
        ],
        "goals": [] if not finished else goals,
    }
    return record


def _write_snapshot(
    tmp_path: Path,
    records: list[dict[str, Any]],
    *,
    retrieved_at: str = "2026-11-02T09:47:17.942020Z",
    matchday: int = 3,
) -> Path:
    settings = _settings(tmp_path)
    body = json.dumps(records, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    timestamp_token = retrieved_at.replace(":", "-").replace(".", "-")
    directory = (
        settings.raw_snapshot_directory
        / "ucl"
        / "2026"
        / f"matchday-{matchday}"
        / f"{timestamp_token}-{digest[:12]}"
    )
    directory.mkdir(parents=True)
    (directory / "response.json").write_bytes(body)
    (directory / "metadata.json").write_text(
        json.dumps(
            {
                "provider": "OpenLigaDB",
                "url": f"https://api.openligadb.de/getmatchdata/ucl/2026/{matchday}",
                "shortcut": "ucl",
                "season": 2026,
                "matchday": matchday,
                "retrieved_at_utc": retrieved_at,
                "http_status": 200,
                "content_type": "application/json",
                "byte_count": len(body),
                "sha256": digest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return directory


class MemoryStore:
    """Transactional in-memory test double for importer behavior."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {
            "snapshots": {},
            "competitions": {},
            "seasons": {},
            "teams": {},
            "matches": {},
            "results": {},
            "goals": {},
            "runs": [],
            "issues": [],
            "changes": [],
            "checkpoints": {},
            "next_id": defaultdict(int),
        }
        self.backup: dict[str, Any] | None = None
        self.rollback_count = 0
        self.fail_rollback = False
        self.fail_at: str | None = None
        self.failed_run_attempts = 0
        self.operation_log: list[str] = []

    def _id(self, kind: str) -> int:
        self.state["next_id"][kind] += 1
        return self.state["next_id"][kind]

    def _fail(self, name: str) -> None:
        if self.fail_at == name:
            raise RuntimeError(f"synthetic {name} failure")

    def begin(self) -> None:
        self.backup = copy.deepcopy(self.state)

    def commit(self) -> None:
        self.backup = None

    def rollback(self) -> None:
        self.rollback_count += 1
        if self.fail_rollback:
            raise RuntimeError("synthetic rollback failure")
        if self.backup is not None:
            self.state = self.backup
            self.backup = None

    def ensure_snapshot(self, parsed: ParsedSnapshot) -> int:
        key = str(parsed.directory)
        if key not in self.state["snapshots"]:
            self.state["snapshots"][key] = self._id("snapshot")
        return self.state["snapshots"][key]

    def ensure_competition(self, provider: str, shortcut: str, name: str) -> int:
        key = (provider, shortcut)
        if key not in self.state["competitions"]:
            self.state["competitions"][key] = self._id("competition")
        return self.state["competitions"][key]

    def ensure_season(self, competition_id: int, source_league_id: int, season: int) -> int:
        key = (competition_id, source_league_id, season)
        if key not in self.state["seasons"]:
            self.state["seasons"][key] = self._id("season")
        return self.state["seasons"][key]

    def find_successful_run(self, source_snapshot_id: int) -> int | None:
        for run in self.state["runs"]:
            if run["snapshot_id"] == source_snapshot_id and run["status"] == "Succeeded":
                return run["id"]
        return None

    def start_run(
        self,
        parsed: ParsedSnapshot,
        competition_season_id: int,
        source_snapshot_id: int,
        is_replay: bool,
        replay_of_import_run_id: int | None,
    ) -> int:
        run_id = self._id("run")
        self.state["runs"].append(
            {
                "id": run_id,
                "snapshot_id": source_snapshot_id,
                "status": "Started",
                "is_replay": is_replay,
                "replay_of": replay_of_import_run_id,
            }
        )
        return run_id

    def record_issues(
        self,
        import_run_id: int,
        source_snapshot_id: int,
        issues: tuple[ValidationIssue, ...] | list[ValidationIssue],
    ) -> None:
        self.state["issues"].extend((import_run_id, source_snapshot_id, issue) for issue in issues)

    def finish_run(
        self,
        import_run_id: int,
        status: str,
        counters: ImportSummary,
        failure_phase: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        for run in self.state["runs"]:
            if run["id"] == import_run_id:
                run.update({"status": status, "counters": counters, "error": error_summary})

    def get_match(self, provider: str, provider_match_id: int) -> MatchState | None:
        return self.state["matches"].get((provider, provider_match_id))

    def upsert_team(self, team: TeamData) -> int:
        self.operation_log.append("upsert_team")
        key = ("OpenLigaDB", team.provider_team_id)
        if key not in self.state["teams"]:
            self.state["teams"][key] = self._id("team")
        return self.state["teams"][key]

    def insert_match(
        self,
        fixture: FixtureData,
        competition_season_id: int,
        home_team_id: int,
        away_team_id: int,
    ) -> int:
        self.operation_log.append("insert_match")
        self._fail("insert_match")
        match_id = self._id("match")
        self.state["matches"][("OpenLigaDB", fixture.provider_match_id)] = MatchState(
            match_id, fixture.business_fields()
        )
        return match_id

    def update_match(
        self,
        match_id: int,
        fixture: FixtureData,
        home_team_id: int,
        away_team_id: int,
    ) -> None:
        self._fail("update_match")
        key = next(
            key for key, value in self.state["matches"].items() if value.match_id == match_id
        )
        self.state["matches"][key] = MatchState(match_id, fixture.business_fields())

    def get_result(self, match_id: int, provider_result_id: int) -> ChildState | None:
        return self.state["results"].get((match_id, provider_result_id))

    def insert_result(self, match_id: int, result: ResultData) -> int:
        self.operation_log.append("insert_result")
        self._fail("insert_result")
        child_id = self._id("result")
        self.state["results"][(match_id, result.provider_result_id)] = ChildState(
            child_id,
            {
                "result_type_id": result.result_type_id,
                "result_type_kind": result.result_type_kind,
                "result_order_id": result.result_order_id,
                "result_name": result.result_name,
                "result_description": result.result_description,
                "points_team1": result.points_team1,
                "points_team2": result.points_team2,
            },
        )
        return child_id

    def update_result(self, child_id: int, result: ResultData) -> None:
        self._fail("update_result")
        for key, state in self.state["results"].items():
            if state.child_id == child_id:
                self.state["results"][key] = ChildState(child_id, _result_fields_for_test(result))

    def get_goal(self, match_id: int, provider_goal_id: int) -> ChildState | None:
        return self.state["goals"].get((match_id, provider_goal_id))

    def insert_goal(
        self,
        match_id: int,
        goal: GoalData,
        scoring_team_id: int | None,
    ) -> int:
        self.operation_log.append("insert_goal")
        self._fail("insert_goal")
        child_id = self._id("goal")
        self.state["goals"][(match_id, goal.provider_goal_id)] = ChildState(
            child_id, _goal_fields_for_test(goal, scoring_team_id)
        )
        return child_id

    def update_goal(
        self,
        child_id: int,
        goal: GoalData,
        scoring_team_id: int | None,
    ) -> None:
        self._fail("update_goal")
        for key, state in self.state["goals"].items():
            if state.child_id == child_id:
                self.state["goals"][key] = ChildState(
                    child_id,
                    _goal_fields_for_test(goal, scoring_team_id),
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
        self._fail("record_change")
        self.state["changes"].append((match_id, field_name, change_kind, old_value, new_value))

    def advance_checkpoint(
        self,
        parsed: ParsedSnapshot,
        competition_season_id: int,
        source_snapshot_id: int,
        import_run_id: int,
    ) -> None:
        self.operation_log.append("advance_checkpoint")
        self._fail("advance_checkpoint")
        key = (parsed.metadata.provider, parsed.metadata.matchday)
        self.state["checkpoints"][key] = (source_snapshot_id, import_run_id)

    def record_failed_run(self, parsed: ParsedSnapshot, error_summary: str) -> None:
        self.failed_run_attempts += 1
        snapshot_id = self.ensure_snapshot(parsed)
        competition_id = self.ensure_competition(
            parsed.metadata.provider, parsed.metadata.shortcut, parsed.competition_name
        )
        season_id = self.ensure_season(
            competition_id,
            parsed.source_league_id,
            parsed.metadata.season,
        )
        previous = self.find_successful_run(snapshot_id)
        run_id = self.start_run(parsed, season_id, snapshot_id, previous is not None, previous)
        issue = ValidationIssue("database-import-failure", error_summary, "Error")
        self.record_issues(run_id, snapshot_id, (issue,))
        self.finish_run(
            run_id,
            "Failed",
            _empty_summary(run_id, snapshot_id, (issue,)),
            "database",
            error_summary,
        )
        self.commit()


def _result_fields_for_test(result: ResultData) -> dict[str, Any]:
    return {
        "result_type_id": result.result_type_id,
        "result_type_kind": result.result_type_kind,
        "result_order_id": result.result_order_id,
        "result_name": result.result_name,
        "result_description": result.result_description,
        "points_team1": result.points_team1,
        "points_team2": result.points_team2,
    }


def _goal_fields_for_test(goal: GoalData, scoring_team_id: int | None) -> dict[str, Any]:
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


def _empty_summary(
    run_id: int,
    snapshot_id: int,
    issues: tuple[ValidationIssue, ...] = (),
) -> ImportSummary:
    return ImportSummary(
        status="Failed",
        import_run_id=run_id,
        source_snapshot_id=snapshot_id,
        matches_seen=0,
        matches_inserted=0,
        matches_updated=0,
        matches_unchanged=0,
        matches_rejected=0,
        results_seen=0,
        goals_seen=0,
        changes_recorded=0,
        validation_issue_count=len(issues),
        issues=issues,
    )


def test_load_snapshot_parses_observed_results_and_goals(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(tmp_path, [_record()])

    parsed = load_snapshot(directory, settings)

    assert parsed.errors == ()
    assert parsed.matches[0].results[0].result_type_kind == "HalfTime"
    assert parsed.matches[0].results[1].result_type_kind == "After90Minutes"
    assert len(parsed.matches[0].goals) == 3
    assert parsed.matches[0].goals[-1].score_team1 == 2


def test_team_icon_url_preserves_schema_safe_http_url(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    icon_url = "https://images.example.test/teams/home.png?version=1"
    directory = _write_snapshot(tmp_path, [_record(home_team_icon_url=icon_url)])

    parsed = load_snapshot(directory, settings)

    assert parsed.errors == ()
    assert parsed.matches[0].home_team.team_icon_url == icon_url
    assert not any(issue.field_name == "teamIconUrl" for issue in parsed.issues)


def test_embedded_team_icon_is_omitted_without_blocking_team_or_match_import(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    embedded_icon = "data:image/jpeg;base64," + "A" * 4096
    directory = _write_snapshot(tmp_path, [_record(home_team_icon_url=embedded_icon)])

    parsed = load_snapshot(directory, settings)

    assert parsed.errors == ()
    assert parsed.matches[0].home_team.team_icon_url is None
    issue = next(issue for issue in parsed.issues if issue.code == "embedded-team-icon-omitted")
    assert issue.severity == "Warning"
    assert issue.source_value == f"data URI ({len(embedded_icon)} characters)"
    assert embedded_icon not in f"{issue.message} {issue.source_value}"

    store = MemoryStore()
    summary = SnapshotImportProcessor(store).import_snapshot(parsed)

    assert summary.status == "Succeeded"
    assert len(store.state["teams"]) == 2
    assert len(store.state["matches"]) == 1


def test_oversized_team_icon_url_is_omitted_without_retaining_its_value(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    oversized_icon = "https://images.example.test/" + "a" * TEAM_ICON_URL_MAX_LENGTH
    assert len(oversized_icon) > TEAM_ICON_URL_MAX_LENGTH
    directory = _write_snapshot(tmp_path, [_record(home_team_icon_url=oversized_icon)])

    parsed = load_snapshot(directory, settings)

    assert parsed.errors == ()
    assert parsed.matches[0].home_team.team_icon_url is None
    issue = next(issue for issue in parsed.issues if issue.code == "team-icon-url-too-long")
    assert issue.severity == "Warning"
    assert issue.source_value == f"HTTPS URL ({len(oversized_icon)} characters)"
    assert oversized_icon not in f"{issue.message} {issue.source_value}"


def test_initial_import_and_duplicate_replay_are_idempotent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(tmp_path, [_record()])
    parsed = load_snapshot(directory, settings)
    store = MemoryStore()
    processor = SnapshotImportProcessor(store)

    first = processor.import_snapshot(parsed)
    replay = processor.import_snapshot(parsed)

    assert first.status == "Succeeded"
    assert first.matches_inserted == 1
    assert first.changes_recorded == 0
    assert replay.status == "Succeeded"
    assert replay.matches_inserted == 0
    assert replay.matches_unchanged == 1
    assert replay.changes_recorded == 0
    assert len(store.state["matches"]) == 1
    assert len(store.state["results"]) == 2
    assert len(store.state["goals"]) == 3
    assert store.state["changes"] == []


def test_distinct_snapshots_with_identical_bytes_preserve_provenance(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    first_directory = _write_snapshot(tmp_path, [_record()])
    second_directory = _write_snapshot(
        tmp_path,
        [_record()],
        retrieved_at="2026-11-02T10:24:16.317565Z",
    )
    assert first_directory != second_directory

    store = MemoryStore()
    processor = SnapshotImportProcessor(store)
    first = processor.import_snapshot(load_snapshot(first_directory, settings))
    second = processor.import_snapshot(load_snapshot(second_directory, settings))

    assert first.status == "Succeeded"
    assert second.status == "Succeeded"
    assert second.matches_inserted == 0
    assert second.matches_unchanged == 1
    assert second.changes_recorded == 0
    assert len(store.state["snapshots"]) == 2
    assert len(store.state["runs"]) == 2
    assert len(store.state["matches"]) == 1
    assert len(store.state["results"]) == 2
    assert len(store.state["goals"]) == 3
    assert store.state["changes"] == []


def test_updated_score_creates_field_level_change_history(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first_directory = _write_snapshot(tmp_path, [_record()])
    second_directory = _write_snapshot(
        tmp_path,
        [_record(final_score=(3, 1))],
        retrieved_at="2026-11-02T10:24:16.317565Z",
    )
    store = MemoryStore()
    processor = SnapshotImportProcessor(store)

    processor.import_snapshot(load_snapshot(first_directory, settings))
    summary = processor.import_snapshot(load_snapshot(second_directory, settings))

    assert summary.matches_updated == 0
    assert summary.changes_recorded >= 2
    assert any("points_team1" in change[1] for change in store.state["changes"])
    assert len(store.state["matches"]) == 1


def test_kickoff_and_location_updates_create_exact_match_changes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first_directory = _write_snapshot(tmp_path, [_record()])
    second_directory = _write_snapshot(
        tmp_path,
        [
            _record(
                kickoff_utc="2026-10-20T20:00:00Z",
                location="National Stadium",
            )
        ],
        retrieved_at="2026-11-02T10:24:16.317565Z",
    )
    store = MemoryStore()
    processor = SnapshotImportProcessor(store)

    processor.import_snapshot(load_snapshot(first_directory, settings))
    summary = processor.import_snapshot(load_snapshot(second_directory, settings))

    assert summary.matches_updated == 1
    assert summary.changes_recorded == 2
    assert {change[1] for change in store.state["changes"]} == {
        "kickoff_utc",
        "location",
    }


def test_result_detail_correction_is_recorded_once(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first_directory = _write_snapshot(tmp_path, [_record()])
    second_directory = _write_snapshot(
        tmp_path,
        [_record(final_result_description="Corrected official result")],
        retrieved_at="2026-11-02T10:24:16.317565Z",
    )
    store = MemoryStore()
    processor = SnapshotImportProcessor(store)

    processor.import_snapshot(load_snapshot(first_directory, settings))
    correction = processor.import_snapshot(load_snapshot(second_directory, settings))
    replay = processor.import_snapshot(load_snapshot(second_directory, settings))

    assert correction.changes_recorded == 1
    assert store.state["changes"][0][1] == "result.2002.result_description"
    assert replay.changes_recorded == 0
    assert len(store.state["changes"]) == 1


def test_results_added_after_match_finishes_are_not_fabricated_early(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    unfinished_directory = _write_snapshot(tmp_path, [_record(finished=False)])
    finished_directory = _write_snapshot(
        tmp_path,
        [_record(finished=True)],
        retrieved_at="2026-11-02T10:24:16.317565Z",
    )
    store = MemoryStore()
    processor = SnapshotImportProcessor(store)

    unfinished = processor.import_snapshot(load_snapshot(unfinished_directory, settings))
    assert unfinished.results_seen == 0
    assert store.state["results"] == {}

    finished = processor.import_snapshot(load_snapshot(finished_directory, settings))

    assert finished.status == "Succeeded"
    assert finished.results_seen == 2
    assert len(store.state["results"]) == 2
    assert len(store.state["goals"]) == 3
    assert any(change[1] == "source_match_is_finished" for change in store.state["changes"])
    assert any(change[2] == "Inserted" for change in store.state["changes"])


def test_omitted_match_is_not_treated_as_deleted(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first_directory = _write_snapshot(
        tmp_path,
        [_record(match_id=101), _record(match_id=102)],
    )
    second_directory = _write_snapshot(
        tmp_path,
        [_record(match_id=101)],
        retrieved_at="2026-11-02T10:24:16.317565Z",
    )
    store = MemoryStore()
    processor = SnapshotImportProcessor(store)

    processor.import_snapshot(load_snapshot(first_directory, settings))
    summary = processor.import_snapshot(load_snapshot(second_directory, settings))

    assert summary.status == "Succeeded"
    assert summary.matches_seen == 1
    assert summary.matches_unchanged == 1
    assert len(store.state["matches"]) == 2
    assert store.state["changes"] == []


def test_unfinished_match_keeps_results_absent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(tmp_path, [_record(finished=False)])
    parsed = load_snapshot(directory, settings)
    store = MemoryStore()

    summary = SnapshotImportProcessor(store).import_snapshot(parsed)

    assert summary.status == "Succeeded"
    assert summary.results_seen == 0
    assert store.state["results"] == {}


def test_unfinished_match_with_no_kickoff_is_retained_as_unscheduled(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(
        tmp_path,
        [_record(finished=False, kickoff_utc=None)],
    )

    parsed = load_snapshot(directory, settings)
    store = MemoryStore()
    summary = SnapshotImportProcessor(store).import_snapshot(parsed)

    assert parsed.matches[0].kickoff_utc is None
    assert any(issue.code == "missing-kickoff-timestamp" for issue in parsed.issues)
    assert summary.status == "Succeeded"
    assert summary.results_seen == 0
    assert store.state["matches"]
    assert next(iter(store.state["matches"].values())).fields["kickoff_utc"] is None


def test_invalid_record_is_recorded_and_does_not_load_fixture(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(tmp_path, [_record(missing_team_id=True)])
    parsed = load_snapshot(directory, settings)
    store = MemoryStore()

    summary = SnapshotImportProcessor(store).import_snapshot(parsed)

    assert summary.status == "Failed"
    assert summary.validation_issue_count > 0
    assert store.state["matches"] == {}
    assert store.state["checkpoints"] == {}
    assert store.state["issues"]


def test_duplicate_match_ids_fail_the_snapshot_atomically(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(tmp_path, [_record(), _record()])
    parsed = load_snapshot(directory, settings)
    store = MemoryStore()

    summary = SnapshotImportProcessor(store).import_snapshot(parsed)

    assert summary.status == "Failed"
    assert any(issue.code == "duplicate-match-id" for issue in summary.issues)
    assert store.state["matches"] == {}
    assert store.state["results"] == {}
    assert store.state["goals"] == {}
    assert store.state["changes"] == []
    assert store.state["checkpoints"] == {}


def test_transaction_failure_rolls_back_fixture_changes_and_records_failure(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    first_directory = _write_snapshot(tmp_path, [_record()])
    second_directory = _write_snapshot(
        tmp_path,
        [_record(final_score=(3, 1))],
        retrieved_at="2026-11-02T10:24:16.317565Z",
    )
    store = MemoryStore()
    processor = SnapshotImportProcessor(store)
    initial = processor.import_snapshot(load_snapshot(first_directory, settings))
    assert initial.status == "Succeeded"

    committed_state = {
        name: copy.deepcopy(store.state[name])
        for name in ("teams", "matches", "results", "goals", "changes", "checkpoints")
    }

    # final_score changes are persisted through the result row, not the fixture row.
    store.fail_at = "update_result"
    with pytest.raises(
        ImportExecutionError,
        match="transactional data was rolled back",
    ) as update_error:
        processor.import_snapshot(load_snapshot(second_directory, settings))

    assert isinstance(update_error.value.__cause__, RuntimeError)
    assert str(update_error.value.__cause__) == "synthetic update_result failure"
    assert "update_result" in str(update_error.value)
    assert store.rollback_count == 1
    for name, committed_value in committed_state.items():
        assert store.state[name] == committed_value

    failed_runs = [run for run in store.state["runs"] if run["status"] == "Failed"]
    assert len(failed_runs) == 1
    assert failed_runs[0]["error"] == "RuntimeError: synthetic update_result failure"

    # Fail after result, goal, and change writes to prove that late transactional
    # mutations are also rolled back and the prior checkpoint remains current.
    store.fail_at = "advance_checkpoint"
    with pytest.raises(
        ImportExecutionError,
        match="transactional data was rolled back",
    ) as checkpoint_error:
        processor.import_snapshot(load_snapshot(second_directory, settings))

    assert isinstance(checkpoint_error.value.__cause__, RuntimeError)
    assert str(checkpoint_error.value.__cause__) == "synthetic advance_checkpoint failure"
    assert store.rollback_count == 2
    for name, committed_value in committed_state.items():
        assert store.state[name] == committed_value

    failed_runs = [run for run in store.state["runs"] if run["status"] == "Failed"]
    assert len(failed_runs) == 2
    assert {run["error"] for run in failed_runs} == {
        "RuntimeError: synthetic update_result failure",
        "RuntimeError: synthetic advance_checkpoint failure",
    }

    store.fail_at = None
    retry = processor.import_snapshot(load_snapshot(second_directory, settings))

    assert retry.status == "Succeeded"
    assert retry.matches_unchanged == 1
    assert retry.changes_recorded == 2
    match_id = next(iter(store.state["matches"].values())).match_id
    assert store.state["results"][(match_id, 2002)].fields["points_team1"] == 3
    assert store.state["goals"][(match_id, 1003)].fields["score_team1"] == 3
    assert {change[1] for change in store.state["changes"]} == {
        "result.2002.points_team1",
        "goal.1003.score_team1",
    }
    checkpoint = store.state["checkpoints"][("OpenLigaDB", 3)]
    assert checkpoint == (retry.source_snapshot_id, retry.import_run_id)
    assert len([run for run in store.state["runs"] if run["status"] == "Failed"]) == 2


def test_failed_import_rolls_back_new_team_and_fixture_rows_before_recording_provenance(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(
        tmp_path,
        [_record(match_id=102, home_team_id=30, away_team_id=40)],
    )
    store = MemoryStore()
    store.fail_at = "advance_checkpoint"

    with pytest.raises(
        ImportExecutionError,
        match="transactional data was rolled back",
    ) as failure:
        SnapshotImportProcessor(store).import_snapshot(load_snapshot(directory, settings))

    assert isinstance(failure.value.__cause__, RuntimeError)
    assert str(failure.value.__cause__) == "synthetic advance_checkpoint failure"
    assert store.operation_log == [
        "upsert_team",
        "upsert_team",
        "insert_match",
        "insert_result",
        "insert_result",
        "insert_goal",
        "insert_goal",
        "insert_goal",
        "advance_checkpoint",
    ]
    assert store.state["teams"] == {}
    assert store.state["matches"] == {}
    assert store.state["results"] == {}
    assert store.state["goals"] == {}
    assert store.state["changes"] == []
    assert store.state["checkpoints"] == {}
    assert len(store.state["snapshots"]) == 1
    assert len(store.state["competitions"]) == 1
    assert len(store.state["seasons"]) == 1
    assert store.failed_run_attempts == 1
    assert [run["status"] for run in store.state["runs"]] == ["Failed"]
    assert store.state["runs"][0]["error"] == "RuntimeError: synthetic advance_checkpoint failure"
    failure_issue = store.state["issues"][0][2]
    assert failure_issue.code == "database-import-failure"
    assert failure_issue.source_value is None


def test_insert_match_failure_runs_after_new_team_upserts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(
        tmp_path,
        [_record(match_id=102, home_team_id=30, away_team_id=40)],
    )
    store = MemoryStore()
    store.fail_at = "insert_match"

    with pytest.raises(
        ImportExecutionError,
        match="transactional data was rolled back",
    ) as failure:
        SnapshotImportProcessor(store).import_snapshot(load_snapshot(directory, settings))

    assert isinstance(failure.value.__cause__, RuntimeError)
    assert str(failure.value.__cause__) == "synthetic insert_match failure"
    assert store.operation_log == ["upsert_team", "upsert_team", "insert_match"]
    assert store.state["teams"] == {}
    assert store.state["matches"] == {}
    assert store.state["results"] == {}
    assert store.state["goals"] == {}
    assert store.state["changes"] == []
    assert store.state["checkpoints"] == {}
    assert [run["status"] for run in store.state["runs"]] == ["Failed"]


def test_rollback_failure_does_not_claim_success_or_commit_failure_provenance(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(tmp_path, [_record()])
    store = MemoryStore()
    store.fail_at = "insert_match"
    store.fail_rollback = True

    with pytest.raises(
        ImportExecutionError,
        match="rollback failed; database state is unconfirmed",
    ) as failure:
        SnapshotImportProcessor(store).import_snapshot(load_snapshot(directory, settings))

    assert isinstance(failure.value.__cause__, RuntimeError)
    assert str(failure.value.__cause__) == "synthetic insert_match failure"
    assert store.rollback_count == 1
    assert store.failed_run_attempts == 0
    assert len(store.state["teams"]) == 2
    assert [run["status"] for run in store.state["runs"]] == ["Started"]


def test_invalid_snapshot_top_level_is_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = _write_snapshot(tmp_path, {"not": "a list"})  # type: ignore[arg-type]

    with pytest.raises(SnapshotValidationError, match="top level"):
        load_snapshot(directory, settings)
