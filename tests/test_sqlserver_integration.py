from __future__ import annotations

import os
from contextlib import closing

import pytest

from sports_tracker.api.repository import SQLServerRepository
from sports_tracker.runtime import open_sql_server_connection

pytestmark = pytest.mark.sqlserver


@pytest.mark.skipif(
    os.getenv("RUN_SQLSERVER_INTEGRATION") != "yes",
    reason="requires explicit opt-in and the deployed SQL Server test database",
)
def test_deployed_schema_has_expected_twelve_tables() -> None:
    expected = {
        "competitions",
        "competition_seasons",
        "teams",
        "source_snapshots",
        "matches",
        "match_results",
        "match_goals",
        "import_runs",
        "validation_issues",
        "match_changes",
        "sync_checkpoints",
        "match_notes",
    }
    with closing(open_sql_server_connection()) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT name
            FROM sys.tables
            WHERE schema_id = SCHEMA_ID('dbo');
            """
        )
        actual = {row[0] for row in cursor.fetchall()}

    assert actual == expected

    fixtures, total = SQLServerRepository(open_sql_server_connection).matches(
        competition_season_id=None, matchday=None, finished=None, search=None, limit=50, offset=0
    )
    assert len(fixtures) == min(total, 50)
