"""HTTP retrieval and basic source-contract checks for OpenLigaDB."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
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


class OpenLigaDBDiscoveryError(OpenLigaDBError):
    """Raised when documented season-discovery endpoints identify no matchdays."""


@dataclass(frozen=True)
class OpenLigaDBResponse:
    """The validated response and the exact bytes returned by OpenLigaDB."""

    records: list[dict[str, Any]]
    body: bytes
    url: str
    status_code: int
    content_type: str | None
    retrieved_at_utc: str


@dataclass(frozen=True)
class OpenLigaDBGroup:
    """One provider-advertised matchday group."""

    group_order_id: int
    group_id: int | None
    group_name: str | None


@dataclass(frozen=True)
class SeasonDiscovery:
    """A source-backed comparison of documented season-discovery endpoints."""

    available_groups_url: str
    full_season_url: str
    available_group_matchdays: tuple[int, ...]
    full_season_matchdays: tuple[int, ...]
    candidate_matchdays: tuple[int, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry policy for transient OpenLigaDB failures."""

    max_retries: int = 0
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 8.0

    def __post_init__(self) -> None:
        if not 0 <= self.max_retries <= 10:
            raise ValueError("max_retries must be between 0 and 10")
        if not math.isfinite(self.initial_backoff_seconds):
            raise ValueError("initial_backoff_seconds must be finite")
        if not math.isfinite(self.max_backoff_seconds):
            raise ValueError("max_backoff_seconds must be finite")
        if self.initial_backoff_seconds <= 0 or self.max_backoff_seconds <= 0:
            raise ValueError("retry backoff values must be greater than zero")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be at least the initial backoff")


@dataclass(frozen=True)
class LastChangeSignal:
    """Provider cache-invalidation signal for one matchday."""

    url: str
    status_code: int
    raw_value: str | None
    changed_at_utc: datetime | None
    reliable: bool
    reason: str


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


def build_season_url(settings: OpenLigaDBSettings) -> str:
    """Build the documented full-season match-data URL."""

    base_url = _validated_base_url(settings.base_url)
    shortcut = quote(settings.shortcut, safe="")
    season = quote(str(settings.season), safe="")
    return f"{base_url}/getmatchdata/{shortcut}/{season}"


def build_available_groups_url(settings: OpenLigaDBSettings) -> str:
    """Build the documented source route listing available season groups."""

    base_url = _validated_base_url(settings.base_url)
    shortcut = quote(settings.shortcut, safe="")
    season = quote(str(settings.season), safe="")
    return f"{base_url}/getavailablegroups/{shortcut}/{season}"


def build_last_change_url(settings: OpenLigaDBSettings, matchday: int) -> str:
    """Build the documented matchday last-change URL."""

    if isinstance(matchday, bool) or not isinstance(matchday, int) or matchday <= 0:
        raise ValueError("matchday must be a positive integer")
    base_url = _validated_base_url(settings.base_url)
    shortcut = quote(settings.shortcut, safe="")
    season = quote(str(settings.season), safe="")
    selected_matchday = quote(str(matchday), safe="")
    return f"{base_url}/getlastchangedate/{shortcut}/{season}/{selected_matchday}"


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


def _validate_available_groups(payload: Any) -> tuple[OpenLigaDBGroup, ...]:
    """Validate provider group metadata without inferring unavailable rounds."""

    if not isinstance(payload, list):
        raise OpenLigaDBContractError(
            "OpenLigaDB available-groups response top level must be a list"
        )
    groups: list[OpenLigaDBGroup] = []
    seen_orders: set[int] = set()
    for index, value in enumerate(payload):
        if not isinstance(value, dict):
            raise OpenLigaDBContractError(f"OpenLigaDB group {index} must be an object")
        group_order_id = value.get("groupOrderID")
        if (
            isinstance(group_order_id, bool)
            or not isinstance(group_order_id, int)
            or group_order_id <= 0
        ):
            raise OpenLigaDBContractError(f"OpenLigaDB group {index} has no positive groupOrderID")
        if group_order_id in seen_orders:
            raise OpenLigaDBContractError(
                f"OpenLigaDB available-groups response duplicates groupOrderID {group_order_id}"
            )
        group_id = value.get("groupID")
        if group_id is not None and (
            isinstance(group_id, bool) or not isinstance(group_id, int) or group_id <= 0
        ):
            raise OpenLigaDBContractError(f"OpenLigaDB group {index} has an invalid groupID")
        group_name = value.get("groupName")
        if group_name is not None and not isinstance(group_name, str):
            raise OpenLigaDBContractError(f"OpenLigaDB group {index} has an invalid groupName")
        normalized_group_name = group_name.strip() if isinstance(group_name, str) else None
        groups.append(
            OpenLigaDBGroup(
                group_order_id=group_order_id,
                group_id=group_id,
                group_name=normalized_group_name or None,
            )
        )
        seen_orders.add(group_order_id)
    return tuple(groups)


def _matchdays_from_season_records(records: list[dict[str, Any]]) -> tuple[int, ...]:
    """Extract only explicit positive source group orders from full-season records."""

    matchdays: set[int] = set()
    for record in records:
        group = record.get("group")
        if not isinstance(group, dict):
            continue
        group_order_id = group.get("groupOrderID")
        if (
            isinstance(group_order_id, int)
            and not isinstance(group_order_id, bool)
            and group_order_id > 0
        ):
            matchdays.add(group_order_id)
    return tuple(sorted(matchdays))


class OpenLigaDBClient:
    """Fetch one OpenLigaDB matchday using an explicit timeout and transport."""

    def __init__(
        self,
        settings: OpenLigaDBSettings,
        transport: httpx.BaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleep = sleep

    def _client_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "headers": {"User-Agent": self.settings.user_agent},
            "timeout": httpx.Timeout(self.settings.timeout_seconds),
            "follow_redirects": False,
        }
        if self.transport is not None:
            options["transport"] = self.transport
        return options

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after is not None:
                try:
                    parsed = float(retry_after)
                except ValueError:
                    parsed = 0.0
                if parsed > 0:
                    return min(parsed, self.retry_policy.max_backoff_seconds)
        exponential = self.retry_policy.initial_backoff_seconds * (2**attempt)
        return min(exponential, self.retry_policy.max_backoff_seconds)

    def _request(self, url: str, operation: str) -> httpx.Response:
        transient_statuses = {429, 500, 502, 503, 504}
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                with httpx.Client(**self._client_options()) as client:
                    response = client.get(url)
            except httpx.RequestError as exc:
                if attempt >= self.retry_policy.max_retries:
                    raise OpenLigaDBNetworkError(
                        f"OpenLigaDB network request failed for {operation}: "
                        f"{exc.__class__.__name__}"
                    ) from exc
                self.sleep(self._retry_delay(None, attempt))
                continue

            if (
                response.status_code in transient_statuses
                and attempt < self.retry_policy.max_retries
            ):
                self.sleep(self._retry_delay(response, attempt))
                continue
            return response
        raise AssertionError("bounded retry loop exhausted without returning")

    def _json_response(self, url: str, operation: str) -> tuple[httpx.Response, Any]:
        response = self._request(url, operation)
        if not 200 <= response.status_code < 300:
            raise OpenLigaDBHTTPError(
                f"OpenLigaDB returned HTTP {response.status_code} for {operation}"
            )
        if not response.content:
            raise OpenLigaDBEmptyBodyError(f"OpenLigaDB returned an empty body for {operation}")
        try:
            return response, json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            raise OpenLigaDBInvalidJSONError(
                f"OpenLigaDB returned invalid JSON for {operation}"
            ) from exc

    def _records_response(self, url: str, operation: str) -> OpenLigaDBResponse:
        response, decoded = self._json_response(url, operation)
        records = _validate_records(decoded, self.settings)
        retrieved_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return OpenLigaDBResponse(
            records=records,
            body=response.content,
            url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            retrieved_at_utc=retrieved_at_utc,
        )

    def fetch_matchday(self, matchday: int) -> OpenLigaDBResponse:
        """Fetch and contract-check one matchday without polling or scheduling."""

        url = build_matchday_url(self.settings, matchday)
        return self._records_response(url, f"matchday {matchday}")

    def fetch_season(self) -> OpenLigaDBResponse:
        """Fetch the documented full-season source view for discovery only."""

        return self._records_response(build_season_url(self.settings), "full season")

    def fetch_available_groups(self) -> tuple[OpenLigaDBGroup, ...]:
        """Fetch the provider's explicitly advertised groups for the configured season."""

        url = build_available_groups_url(self.settings)
        _, decoded = self._json_response(url, "available groups")
        return _validate_available_groups(decoded)

    def discover_matchdays(self) -> SeasonDiscovery:
        """Compare both documented discovery views without treating either as complete truth."""

        available_groups_url = build_available_groups_url(self.settings)
        full_season_url = build_season_url(self.settings)
        warnings: list[str] = []
        available_matchdays: tuple[int, ...] = ()
        full_season_matchdays: tuple[int, ...] = ()

        try:
            available_matchdays = tuple(
                group.group_order_id for group in self.fetch_available_groups()
            )
        except OpenLigaDBError as exc:
            warnings.append(f"available-groups endpoint unavailable ({type(exc).__name__})")

        try:
            full_season_matchdays = _matchdays_from_season_records(self.fetch_season().records)
        except OpenLigaDBError as exc:
            warnings.append(f"full-season endpoint unavailable ({type(exc).__name__})")

        candidate_matchdays = tuple(sorted(set(available_matchdays) | set(full_season_matchdays)))
        if not candidate_matchdays:
            raise OpenLigaDBDiscoveryError(
                "OpenLigaDB season discovery returned no explicit positive matchday groups"
            )
        if available_matchdays and full_season_matchdays:
            available_only = sorted(set(available_matchdays) - set(full_season_matchdays))
            season_only = sorted(set(full_season_matchdays) - set(available_matchdays))
            if available_only:
                warnings.append(
                    "available-groups only matchdays: "
                    + ", ".join(str(matchday) for matchday in available_only)
                )
            if season_only:
                warnings.append(
                    "full-season only matchdays: "
                    + ", ".join(str(matchday) for matchday in season_only)
                )
        return SeasonDiscovery(
            available_groups_url=available_groups_url,
            full_season_url=full_season_url,
            available_group_matchdays=available_matchdays,
            full_season_matchdays=full_season_matchdays,
            candidate_matchdays=candidate_matchdays,
            warnings=tuple(warnings),
        )

    def fetch_last_change(self, matchday: int) -> LastChangeSignal:
        """Fetch the documented cache-invalidation signal for one matchday."""

        url = build_last_change_url(self.settings, matchday)
        response = self._request(url, f"last-change matchday {matchday}")
        if response.status_code in {404, 405}:
            return LastChangeSignal(
                url=url,
                status_code=response.status_code,
                raw_value=None,
                changed_at_utc=None,
                reliable=False,
                reason="last-change endpoint is unsupported for this scope",
            )
        if not 200 <= response.status_code < 300:
            raise OpenLigaDBHTTPError(
                "OpenLigaDB returned HTTP "
                f"{response.status_code} for last-change matchday {matchday}"
            )
        if not response.content:
            return LastChangeSignal(
                url=url,
                status_code=response.status_code,
                raw_value=None,
                changed_at_utc=None,
                reliable=False,
                reason="last-change endpoint returned an empty body",
            )
        try:
            decoded = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            raise OpenLigaDBInvalidJSONError(
                f"OpenLigaDB returned invalid last-change JSON for matchday {matchday}"
            ) from exc
        if decoded is None:
            return LastChangeSignal(
                url=url,
                status_code=response.status_code,
                raw_value=None,
                changed_at_utc=None,
                reliable=False,
                reason="last-change endpoint returned null",
            )
        if not isinstance(decoded, str) or not decoded.strip():
            raise OpenLigaDBContractError(
                "OpenLigaDB last-change response must be an ISO-8601 string or null"
            )

        raw_value = decoded.strip()
        try:
            changed_at = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise OpenLigaDBContractError(
                "OpenLigaDB last-change response is not a valid ISO-8601 timestamp"
            ) from exc
        if changed_at.tzinfo is None:
            return LastChangeSignal(
                url=url,
                status_code=response.status_code,
                raw_value=raw_value,
                changed_at_utc=None,
                reliable=False,
                reason="last-change timestamp has no timezone; full retrieval required",
            )
        return LastChangeSignal(
            url=url,
            status_code=response.status_code,
            raw_value=raw_value,
            changed_at_utc=changed_at.astimezone(UTC),
            reliable=True,
            reason="timezone-aware last-change signal",
        )
