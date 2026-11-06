from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sports_tracker.api.repository import SQLServerRepository

ResultSet = tuple[tuple[str, ...] | None, list[tuple[Any, ...]]]


class QueryHarness:
    def __init__(self, resolver: Callable[[str, tuple[Any, ...]], ResultSet]) -> None:
        self.resolver = resolver
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.connections: list[Connection] = []

    def connection(self) -> Connection:
        connection = Connection(self)
        self.connections.append(connection)
        return connection


class Cursor:
    def __init__(self, harness: QueryHarness) -> None:
        self.harness = harness
        self.description: list[tuple[str]] | None = None
        self.rows: list[tuple[Any, ...]] = []

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()) -> Cursor:
        parameters = tuple(parameters)
        self.harness.calls.append((statement, parameters))
        columns, rows = self.harness.resolver(statement, parameters)
        self.description = None if columns is None else [(column,) for column in columns]
        self.rows = list(rows)
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def nextset(self) -> bool:
        return False


class Connection:
    def __init__(self, harness: QueryHarness) -> None:
        self.harness = harness
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> Cursor:
        return Cursor(self.harness)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_repository_uses_deployed_competition_and_match_columns() -> None:
    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        del parameters
        if "FROM dbo.competition_seasons AS cs" in statement:
            return (
                (
                    "competition_season_id",
                    "provider",
                    "name",
                    "shortcut",
                    "season",
                    "provider_league_id",
                ),
                [(1, "OpenLigaDB", "UEFA Champions League", "ucl", "2026/27", 4946)],
            )
        if "COUNT_BIG(*) AS total" in statement:
            return (("total",), [(1,)])
        if "FROM dbo.matches AS m" in statement:
            return (
                (
                    "match_id",
                    "provider_match_id",
                    "matchday_number",
                    "stage_name",
                    "kickoff_utc",
                    "is_finished",
                    "home_team",
                    "away_team",
                    "home_score",
                    "away_score",
                    "last_source_update_utc",
                ),
                [(10, 123, 3, None, datetime(2026, 10, 20, 19), True, "A", "B", 2, 1, None)],
            )
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)
    repository = SQLServerRepository(harness.connection)

    competitions = repository.competitions()
    matches, total = repository.matches(
        competition_season_id=1,
        matchday=3,
        finished=True,
        search="A%_[",
        limit=25,
        offset=0,
    )

    assert competitions[0]["provider_league_id"] == 4946
    assert matches[0]["is_finished"] is True
    assert total == 1
    statements = "\n".join(statement for statement, _ in harness.calls)
    assert "c.provider_shortcut" in statements
    assert "cs.source_league_id" in statements
    assert "m.source_match_is_finished" in statements
    assert "mr.result_type_kind" in statements
    match_parameters = [
        parameters for statement, parameters in harness.calls if "OFFSET" in statement
    ]
    assert match_parameters == [(1, 3, True, "%A~%~_~[%", "%A~%~_~[%", 0, 25)]


def test_repository_match_detail_uses_typed_results_and_real_goal_columns() -> None:
    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        assert parameters == (10,)
        if "FROM dbo.matches AS m" in statement:
            return (
                (
                    "match_id",
                    "provider_match_id",
                    "matchday_number",
                    "stage_name",
                    "kickoff_utc",
                    "is_finished",
                    "home_team",
                    "away_team",
                    "home_score",
                    "away_score",
                    "last_source_update_utc",
                    "venue",
                ),
                [(10, 123, 3, None, None, False, "A", "B", None, None, None, None)],
            )
        if "FROM dbo.match_results" in statement:
            return (
                ("result_type", "result_name", "home_score", "away_score"),
                [("HalfTime", "Halftime", None, None)],
            )
        if "FROM dbo.match_goals" in statement:
            return (
                (
                    "provider_goal_id",
                    "score_home",
                    "score_away",
                    "minute",
                    "scorer_name",
                    "is_penalty",
                    "is_own_goal",
                    "is_overtime",
                ),
                [(999, None, None, None, None, None, None, None)],
            )
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)

    match = SQLServerRepository(harness.connection).match(10)

    assert match is not None
    assert match["results"][0]["result_type"] == "HalfTime"
    assert match["results"][0]["home_score"] is None
    assert match["goals"][0]["score_home"] is None
    statements = "\n".join(statement for statement, _ in harness.calls)
    assert "result_type_kind AS result_type" in statements
    assert "score_team1 AS score_home" in statements
    assert "goal_order" not in statements


def test_repository_matchdays_and_checkpoints_use_deployed_schema() -> None:
    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        if "GROUP BY m.competition_season_id" in statement:
            assert parameters == (1,)
            return (
                (
                    "competition_season_id",
                    "matchday_number",
                    "match_count",
                    "finished_count",
                    "unfinished_count",
                    "first_kickoff_utc",
                    "last_kickoff_utc",
                ),
                [(1, 3, 18, 18, 0, None, None)],
            )
        if "COUNT_BIG(*) AS total FROM dbo.sync_checkpoints" in statement:
            return (("total",), [(1,)])
        if "FROM dbo.sync_checkpoints AS sc" in statement:
            assert parameters == (0, 20)
            return (
                (
                    "sync_checkpoint_id",
                    "provider",
                    "scope_key",
                    "matchday_number",
                    "last_source_update_utc",
                    "last_processed_at_utc",
                    "last_successful_snapshot_id",
                    "last_successful_import_run_id",
                ),
                [(1, "OpenLigaDB", "OpenLigaDB:ucl:2026:matchday:3", 3, None, None, 8, 3)],
            )
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)
    repository = SQLServerRepository(harness.connection)

    matchdays = repository.matchdays(1)
    checkpoints, total = repository.sync_checkpoints(20, 0)

    assert matchdays[0]["finished_count"] == 18
    assert total == 1
    assert checkpoints[0]["last_successful_snapshot_id"] == 8
    statements = "\n".join(statement for statement, _ in harness.calls)
    assert "m.source_match_is_finished" in statements
    assert "sc.last_successful_import_run_id" in statements


def test_repository_operations_use_current_provenance_schema() -> None:
    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        del parameters
        if "COUNT_BIG(*) AS total FROM dbo.import_runs" in statement:
            return (("total",), [(1,)])
        if "FROM dbo.import_runs AS ir" in statement:
            return (
                ("import_run_id", "status", "snapshot_sha256", "error_message"),
                [(3, "Succeeded", "a" * 64, None)],
            )
        if "COUNT_BIG(*) AS total FROM dbo.validation_issues" in statement:
            return (("total",), [(1,)])
        if "FROM dbo.validation_issues" in statement:
            return (
                ("validation_issue_id", "message", "provider_match_id"),
                [(5, "safe", 123)],
            )
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)
    repository = SQLServerRepository(harness.connection)

    runs, run_total = repository.import_runs(20, 0)
    issues, issue_total = repository.validation_issues(20, 0)

    assert (run_total, issue_total) == (1, 1)
    assert runs[0]["snapshot_sha256"] == "a" * 64
    assert issues[0]["message"] == "safe"
    statements = "\n".join(statement for statement, _ in harness.calls)
    assert "ss.sha256" in statements
    assert "WHEN ir.error_summary IS NULL THEN NULL" in statements
    assert "ir.error_summary AS error_message" not in statements
    assert "WHEN issue_code = N'database-import-failure'" in statements
    assert "ELSE issue_message" in statements
    assert "source_record_id" in statements


def test_note_writes_commit_and_use_match_note_identity() -> None:
    now = datetime(2026, 11, 6, 10)

    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        del parameters
        if "INSERT INTO dbo.match_notes" in statement:
            return (
                (
                    "note_id",
                    "match_id",
                    "note_text",
                    "created_by",
                    "is_archived",
                    "created_at_utc",
                    "updated_at_utc",
                ),
                [(9, 10, "Review", "tester", False, now, now)],
            )
        if "SET is_archived = 1" in statement:
            return (("match_note_id",), [(9,)])
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)
    repository = SQLServerRepository(harness.connection)

    note = repository.create_note(10, "Review", "tester")
    archived = repository.archive_note(9)

    assert note["note_id"] == 9
    assert archived is True
    assert [connection.commits for connection in harness.connections] == [1, 1]
    assert all(connection.rollbacks == 0 for connection in harness.connections)
    statements = "\n".join(statement for statement, _ in harness.calls)
    assert "inserted.match_note_id AS note_id" in statements
    assert "WHERE match_note_id = ?" in statements
