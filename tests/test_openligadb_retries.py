from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from sports_tracker.openligadb import (
    OpenLigaDBClient,
    RetryPolicy,
    build_last_change_url,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        base_url="https://api.openligadb.de",
        shortcut="ucl",
        season="2026",
        expected_league_id=4946,
        timeout_seconds=5.0,
        user_agent="sports-fixtures-change-tracker/0.1 (offline test)",
    )


def test_last_change_url_is_built_from_configured_identity() -> None:
    assert build_last_change_url(_settings(), 3) == (
        "https://api.openligadb.de/getlastchangedate/ucl/2026/3"
    )


def test_retry_policy_rejects_unbounded_values() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        RetryPolicy(max_retries=11)


def test_transient_http_failure_is_retried_with_mock_transport() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            request=request,
            json=[
                {
                    "matchID": 123,
                    "leagueShortcut": "ucl",
                    "leagueSeason": "2026",
                    "leagueId": 4946,
                }
            ],
        )

    client = OpenLigaDBClient(
        _settings(),
        transport=httpx.MockTransport(handler),
        retry_policy=RetryPolicy(
            max_retries=1,
            initial_backoff_seconds=0.01,
            max_backoff_seconds=0.01,
        ),
        sleep=sleeps.append,
    )

    response = client.fetch_matchday(3)

    assert calls == 2
    assert sleeps == [0.01]
    assert len(response.records) == 1


def test_last_change_signal_accepts_only_timezone_aware_values() -> None:
    values = iter(["2026-11-03T09:30:00", "2026-11-03T09:30:00Z"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=next(values))

    client = OpenLigaDBClient(
        _settings(),
        transport=httpx.MockTransport(handler),
        retry_policy=RetryPolicy(max_retries=0),
    )

    naive = client.fetch_last_change(3)
    aware = client.fetch_last_change(3)

    assert naive.reliable is False
    assert aware.reliable is True
    assert aware.changed_at_utc is not None
