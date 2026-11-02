"""HTTP retrieval and basic source-contract checks for OpenLigaDB."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .config import ConfigurationError, OpenLigaDBSettings


class OpenLigaDBError(Exception):
    """Base class for safe, user-facing OpenLigaDB errors."""


class OpenLigaDBNetworkError(OpenLigaDBError):
    """Raised when the HTTP request cannot reach or receive a response from the provider."""


class OpenLigaDBHTTPError(OpenLigaDBError):
    """Raised when the provider returns a non-success HTTP status."""


class OpenLigaDBEmptyBodyError(OpenLigaDBError):
    """Raised when a successful provider response has no body."""


class OpenLigaDBInvalidJSONError(OpenLigaDBError):
    """Raised when a successful provider response is not valid JSON."""


class OpenLigaDBContractError(OpenLigaDBError):
    """Raised when the response does not match the basic source contract."""


@dataclass(frozen=True)
class OpenLigaDBResponse:
    """The validated response and the exact bytes returned by OpenLigaDB."""

    records: list[dict[str, Any]]
    body: bytes
    url: str
    status_code: int
    content_type: str | None
    retrieved_at_utc: str


def _validated_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ConfigurationError(
            "OPENLIGADB_BASE_URL must be an HTTP(S) URL without credentials or query parameters"
        )
    return normalized


def build_matchday_url(settings: OpenLigaDBSettings, matchday: int) -> str:
    """Build a URL for one configured competition matchday."""

    if isinstance(matchday, bool) or not isinstance(matchday, int) or matchday <= 0:
        raise ValueError("matchday must be a positive integer")
    base_url = _validated_base_url(settings.base_url)
    shortcut = quote(settings.shortcut, safe="")
    season = quote(str(settings.season), safe="")
    selected_matchday = quote(str(matchday), safe="")
    return f"{base_url}/getmatchdata/{shortcut}/{season}/{selected_matchday}"


def _validate_records(records: Any, settings: OpenLigaDBSettings) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise OpenLigaDBContractError("OpenLigaDB response top level must be a list")

    expected_identity = {
        "leagueShortcut": settings.shortcut,
        "leagueSeason": settings.season,
        "leagueId": settings.expected_league_id,
    }
    validated_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise OpenLigaDBContractError(f"OpenLigaDB record {index} must be an object")
        if "matchID" not in record:
            raise OpenLigaDBContractError(f"OpenLigaDB record {index} is missing matchID")
        for field, expected in expected_identity.items():
            if record.get(field) != expected:
                raise OpenLigaDBContractError(f"OpenLigaDB record {index} has unexpected {field}")
        validated_records.append(record)
    return validated_records


class OpenLigaDBClient:
    """Fetch one OpenLigaDB matchday using an explicit timeout and transport."""

    def __init__(
        self,
        settings: OpenLigaDBSettings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def fetch_matchday(self, matchday: int) -> OpenLigaDBResponse:
        """Fetch and contract-check one matchday without polling or scheduling."""

        url = build_matchday_url(self.settings, matchday)
        client_options: dict[str, Any] = {
            "headers": {"User-Agent": self.settings.user_agent},
            "timeout": httpx.Timeout(self.settings.timeout_seconds),
            "follow_redirects": False,
        }
        if self.transport is not None:
            client_options["transport"] = self.transport

        try:
            with httpx.Client(**client_options) as client:
                response = client.get(url)
        except httpx.RequestError as exc:
            raise OpenLigaDBNetworkError(
                f"OpenLigaDB network request failed for matchday {matchday}: "
                f"{exc.__class__.__name__}"
            ) from exc

        if not 200 <= response.status_code < 300:
            raise OpenLigaDBHTTPError(
                f"OpenLigaDB returned HTTP {response.status_code} for matchday {matchday}"
            )

        body = response.content
        if not body:
            raise OpenLigaDBEmptyBodyError(
                f"OpenLigaDB returned an empty body for matchday {matchday}"
            )
        try:
            decoded = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            raise OpenLigaDBInvalidJSONError(
                f"OpenLigaDB returned invalid JSON for matchday {matchday}"
            ) from exc

        records = _validate_records(decoded, self.settings)
        retrieved_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return OpenLigaDBResponse(
            records=records,
            body=body,
            url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            retrieved_at_utc=retrieved_at_utc,
        )
