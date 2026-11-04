"""Regression coverage for transaction-safe database connection defaults."""

from __future__ import annotations

from sports_tracker import database
from sports_tracker.config import DatabaseSettings


def test_connect_database_explicitly_disables_autocommit(monkeypatch) -> None:
    observed: dict[str, object] = {}
    sentinel_connection = object()

    def fake_connect(connection_string: str, *, autocommit: bool) -> object:
        observed["connection_string"] = connection_string
        observed["autocommit"] = autocommit
        return sentinel_connection

    settings = DatabaseSettings(
        host="sql.example.test",
        port=1433,
        database="SportsFixturesTracker",
        user="sports_tracker_app",
        password="unit-test-password",
        encrypt="yes",
        trust_server_certificate="yes",
    )
    monkeypatch.setattr(database.pyodbc, "connect", fake_connect)

    connection = database.connect_database(settings)

    assert connection is sentinel_connection
    assert observed["autocommit"] is False
