from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

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
    assert "ORDER BY CASE WHEN m.kickoff_utc IS NULL THEN 1 ELSE 0 END" in statements
    assert "m.kickoff_utc DESC" in statements
    assert "m.provider_match_id DESC" in statements
    match_parameters = [
        parameters for statement, parameters in harness.calls if "OFFSET" in statement
    ]
    assert match_parameters == [(1, 3, True, "%A~%~_~[%", "%A~%~_~[%", 0, 25)]


def test_repository_match_ordering_is_server_side_and_deterministic() -> None:
    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        if "COUNT_BIG(*) AS total" in statement:
            return (("total",), [(3,)])
        if "FROM dbo.matches AS m" in statement:
            assert parameters[-2:] == (0, 2)
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
                [(10, 123, 3, None, None, False, "A", "B", None, None, None)],
            )
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)
    repository = SQLServerRepository(harness.connection)

    repository.matches(
        competition_season_id=None,
        matchday=None,
        finished=True,
        search=None,
        limit=2,
        offset=0,
    )
    repository.matches(
        competition_season_id=None,
        matchday=None,
        finished=False,
        search=None,
        limit=2,
        offset=0,
    )
    repository.matches(
        competition_season_id=None,
        matchday=None,
        finished=None,
        search=None,
        limit=2,
        offset=0,
    )

    item_statements = [statement for statement, _ in harness.calls if "OFFSET" in statement]
    completed_statement, upcoming_statement, all_statement = item_statements
    assert "m.kickoff_utc DESC" in completed_statement
    assert "m.provider_match_id DESC" in completed_statement
    assert "m.kickoff_utc ASC" in upcoming_statement
    assert "m.provider_match_id ASC" in upcoming_statement
    assert "ROW_NUMBER() OVER" in all_statement
    assert "PARTITION BY m.source_match_is_finished" in all_statement
    assert "completed_recency_rank <=" in all_statement
    assert "ordering_group" in all_statement
    assert "CASE WHEN ordering_group = 1 THEN kickoff_utc END" in all_statement
    assert all_statement.index("ORDER BY ordering_group") < all_statement.index("OFFSET")


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


def test_repository_insight_query_preaggregates_goals_and_uses_after90_only() -> None:
    now = datetime(2026, 11, 7, 12)

    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        if "WITH goal_counts AS" in statement:
            assert parameters == (1,)
            return (
                (
                    "match_id",
                    "provider_match_id",
                    "matchday_number",
                    "kickoff_utc",
                    "is_finished",
                    "home_team_provider_id",
                    "away_team_provider_id",
                    "home_team",
                    "away_team",
                    "home_score",
                    "away_score",
                    "observed_goal_events",
                ),
                [(10, 123, 3, now, True, 101, 102, "A", "B", 2, 1, 3)],
            )
        if "latest_successful_sync_at_utc" in statement:
            assert parameters == (1,)
            return (("latest_successful_sync_at_utc",), [(now,)])
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)
    repository = SQLServerRepository(harness.connection)

    rows = repository.insight_rows(1)
    latest = repository.insight_latest_successful_sync(1)

    assert rows[0]["observed_goal_events"] == 3
    assert latest == now.replace(tzinfo=UTC)
    statements = "\n".join(statement for statement, _ in harness.calls)
    assert "WITH goal_counts AS" in statements
    assert "GROUP BY mg.match_id" in statements
    assert "mr.result_type_kind = N'After90Minutes'" in statements


def test_repository_dashboard_summary_and_change_feed_use_deployed_schema() -> None:
    now = datetime(2026, 11, 3, 9, 30)

    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        if "AS total_fixtures" in statement:
            assert parameters == (1,)
            return (
                (
                    "total_fixtures",
                    "finished_fixtures",
                    "upcoming_fixtures",
                ),
                [(18, 18, 0)],
            )
        if "AS goals_recorded" in statement:
            assert parameters == (1,)
            return (("goals_recorded",), [(74,)])
        if "AS detected_changes" in statement:
            assert parameters == (1,)
            return (("detected_changes", "changed_fixtures"), [(2, 1)])
        if (
            "latest_successful_sync_at_utc" in statement
            and "dbo.sync_checkpoints AS sc" in statement
        ):
            assert parameters == (1,)
            return (
                (
                    "latest_successful_sync_at_utc",
                    "latest_successful_snapshot_id",
                    "latest_successful_import_run_id",
                ),
                [(now, 8, 3)],
            )
        if "COUNT_BIG(*) AS total" in statement and "dbo.match_changes AS mc" in statement:
            assert parameters == (1,)
            return (("total",), [(2,)])
        if "ss.sha256 AS snapshot_sha256" in statement:
            assert parameters == (1, 0, 20)
            return (
                (
                    "match_change_id",
                    "match_id",
                    "provider_match_id",
                    "matchday_number",
                    "home_team",
                    "away_team",
                    "field_name",
                    "change_kind",
                    "old_value",
                    "new_value",
                    "observed_at_utc",
                    "source_last_update_utc",
                    "import_run_id",
                    "source_snapshot_id",
                    "snapshot_sha256",
                    "snapshot_retrieved_at_utc",
                ),
                [
                    (
                        5,
                        10,
                        123,
                        3,
                        "Alpha FC",
                        "Beta FC",
                        "match_is_finished",
                        "updated",
                        "false",
                        "true",
                        now,
                        now,
                        3,
                        8,
                        "a" * 64,
                        now,
                    )
                ],
            )
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)
    repository = SQLServerRepository(harness.connection)

    summary = repository.dashboard_summary(1)
    changes, total = repository.match_changes(competition_season_id=1, limit=20, offset=0)

    assert summary == {
        "total_fixtures": 18,
        "finished_fixtures": 18,
        "upcoming_fixtures": 0,
        "goals_recorded": 74,
        "detected_changes": 2,
        "changed_fixtures": 1,
        "latest_successful_sync_at_utc": now.replace(tzinfo=UTC),
        "latest_successful_snapshot_id": 8,
        "latest_successful_import_run_id": 3,
    }
    assert total == 2
    assert changes[0]["snapshot_sha256"] == "a" * 64
    statements = "\n".join(statement for statement, _ in harness.calls)
    assert "m.competition_season_id = ?" in statements
    assert "dbo.match_goals AS mg" in statements
    assert "dbo.match_changes AS mc" in statements
    assert "COUNT_BIG(DISTINCT mc.match_id) AS changed_fixtures" in statements
    assert "sc.competition_season_id = ?" in statements
    assert "INNER JOIN dbo.source_snapshots AS ss" in statements


def test_dashboard_summary_logs_safe_component_context_on_query_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def resolve(statement: str, parameters: tuple[Any, ...]) -> ResultSet:
        assert parameters == (1,)
        if "AS total_fixtures" in statement:
            return (
                (
                    "total_fixtures",
                    "finished_fixtures",
                    "upcoming_fixtures",
                ),
                [(18, 18, 0)],
            )
        if "AS goals_recorded" in statement:
            raise RuntimeError("simulated SQL failure; PWD=not-a-real-secret")
        raise AssertionError(f"Unexpected query: {statement}")

    harness = QueryHarness(resolve)
    repository = SQLServerRepository(harness.connection)
    caplog.set_level("ERROR", logger="sports_tracker.api.repository")

    with pytest.raises(RuntimeError, match="simulated SQL failure"):
        repository.dashboard_summary(1)

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "operation=goal-counts" in messages
    assert "error_type=RuntimeError" in messages
    assert "not-a-real-secret" not in messages


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
