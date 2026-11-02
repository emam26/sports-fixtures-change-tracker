from pathlib import Path

import pytest

from sports_tracker.config import (
    ConfigurationError,
    DatabaseSettings,
    build_connection_string,
    load_database_settings,
    load_openligadb_settings,
)


def _base_environment() -> dict[str, str]:
    return {
        "SQL_SERVER_HOST": "172.20.80.1",
        "SQL_SERVER_PORT": "1433",
        "SQL_SERVER_DATABASE": "SportsFixturesTracker",
        "SQL_SERVER_USER": "sports_tracker_app",
        "SQL_SERVER_PASSWORD": "unit-test;secret}value",
        "SQL_SERVER_ENCRYPT": "yes",
        "SQL_SERVER_TRUST_CERTIFICATE": "yes",
    }


def test_load_database_settings_from_dotenv(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(f"{key}={value}" for key, value in _base_environment().items()),
        encoding="utf-8",
    )

    settings = load_database_settings(dotenv_path=dotenv_path, environ={})

    assert settings.host == "172.20.80.1"
    assert settings.port == 1433
    assert settings.database == "SportsFixturesTracker"
    assert settings.user == "sports_tracker_app"
    assert settings.password == "unit-test;secret}value"


def test_missing_required_setting_is_rejected(tmp_path: Path) -> None:
    values = _base_environment()
    values.pop("SQL_SERVER_PASSWORD")

    with pytest.raises(ConfigurationError, match="SQL_SERVER_PASSWORD"):
        load_database_settings(dotenv_path=tmp_path / "missing.env", environ=values)


def test_invalid_port_is_rejected(tmp_path: Path) -> None:
    values = _base_environment()
    values["SQL_SERVER_PORT"] = "not-a-port"

    with pytest.raises(ConfigurationError, match="SQL_SERVER_PORT"):
        load_database_settings(dotenv_path=tmp_path / "missing.env", environ=values)


def test_connection_string_escapes_password_and_other_values() -> None:
    settings = DatabaseSettings(
        host="sql.example;host",
        port=1433,
        database="SportsFixturesTracker;copy",
        user="tracker_user",
        password="unit-test;secret}value",
        encrypt="yes",
        trust_server_certificate="yes",
    )

    connection_string = build_connection_string(settings)

    assert "SERVER={tcp:sql.example;host,1433}" in connection_string
    assert "DATABASE={SportsFixturesTracker;copy}" in connection_string
    assert "PWD={unit-test;secret}}value}" in connection_string
    assert ";Encrypt={yes};" in connection_string
    assert ";TrustServerCertificate={yes};" in connection_string


def test_settings_repr_redacts_password() -> None:
    settings = DatabaseSettings(
        host="sql.example",
        port=1433,
        database="SportsFixturesTracker",
        user="tracker_user",
        password="unit-test-password",
        encrypt="yes",
        trust_server_certificate="yes",
    )

    assert "unit-test-password" not in repr(settings)
    assert "<redacted>" in repr(settings)


def test_load_openligadb_settings_from_environment(tmp_path: Path) -> None:
    values = {
        "OPENLIGADB_BASE_URL": "https://api.openligadb.de",
        "OPENLIGADB_SHORTCUT": "ucl",
        "OPENLIGADB_SEASON": "2026",
        "OPENLIGADB_EXPECTED_LEAGUE_ID": "4946",
        "OPENLIGADB_TIMEOUT_SECONDS": "10",
        "RAW_SNAPSHOT_DIRECTORY": "data/raw",
    }

    settings = load_openligadb_settings(
        dotenv_path=tmp_path / "missing.env",
        environ=values,
    )

    assert settings.base_url == "https://api.openligadb.de"
    assert settings.shortcut == "ucl"
    assert settings.season == 2026
    assert settings.expected_league_id == 4946
    assert settings.timeout_seconds == 10.0
    assert settings.raw_snapshot_directory == Path("data/raw")
