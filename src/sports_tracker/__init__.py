"""Foundation package for the Sports Fixtures & Change Tracker."""

from .config import (
    ConfigurationError,
    DatabaseSettings,
    OpenLigaDBSettings,
    load_database_settings,
    load_openligadb_settings,
)

__all__ = [
    "ConfigurationError",
    "DatabaseSettings",
    "OpenLigaDBSettings",
    "load_database_settings",
    "load_openligadb_settings",
]
