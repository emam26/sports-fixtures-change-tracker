import hashlib
import json
from pathlib import Path

import httpx
import pytest

from sports_tracker.config import OpenLigaDBSettings
from sports_tracker.openligadb import (
    OpenLigaDBClient,
    OpenLigaDBContractError,
    OpenLigaDBEmptyBodyError,
    OpenLigaDBHTTPError,
    OpenLigaDBInvalidJSONError,
    OpenLigaDBNetworkError,
    OpenLigaDBResponse,
    build_available_groups_url,
    build_season_url,
)
from sports_tracker.snapshots import SnapshotAlreadyExistsError, save_raw_snapshot

RAW_BODY = b'[{"matchID":123,"leagueShortcut":"ucl","leagueSeason":2026,"leagueId":4946}]'


def _settings(tmp_path: Path) -> OpenLigaDBSettings:
    return OpenLigaDBSettings(
        base_url="https://api.openligadb.de",
        shortcut="ucl",
        season=2026,
        expected_league_id=4946,
        timeout_seconds=10.0,
        raw_snapshot_directory=tmp_path / "data" / "raw",
    )


def _response_for(request: httpx.Request, body: bytes = RAW_BODY) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "application/json"},
        content=body,
        request=request,
    )


def _fixed_response(settings: OpenLigaDBSettings) -> OpenLigaDBResponse:
    fetched = OpenLigaDBClient(
        settings,
        transport=httpx.MockTransport(lambda request: _response_for(request)),
    ).fetch_matchday(3)
    return OpenLigaDBResponse(
        records=fetched.records,
        body=fetched.body,
        url=fetched.url,
        status_code=fetched.status_code,
        content_type=fetched.content_type,
        retrieved_at_utc="2026-11-02T12:00:00.000000Z",
    )


def test_builds_the_expected_matchday_endpoint(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        assert request.headers["user-agent"] == settings.user_agent
        return _response_for(request)

    OpenLigaDBClient(settings, transport=httpx.MockTransport(handler)).fetch_matchday(3)

    assert requested_urls == ["https://api.openligadb.de/getmatchdata/ucl/2026/3"]


def test_builds_documented_season_discovery_endpoints(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    assert build_season_url(settings) == "https://api.openligadb.de/getmatchdata/ucl/2026"
    assert (
        build_available_groups_url(settings)
        == "https://api.openligadb.de/getavailablegroups/ucl/2026"
    )


def test_discovery_compares_available_groups_and_full_season_with_mock_transport(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    requested_urls: list[str] = []
    season_body = json.dumps(
        [
            {
                "matchID": 101,
                "leagueShortcut": "ucl",
                "leagueSeason": 2026,
                "leagueId": 4946,
                "group": {"groupOrderID": 1},
            },
            {
                "matchID": 102,
                "leagueShortcut": "ucl",
                "leagueSeason": 2026,
                "leagueId": 4946,
                "group": {"groupOrderID": 3},
            },
        ]
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.endswith("/getavailablegroups/ucl/2026"):
            return _response_for(
                request,
                b'[{"groupID":1,"groupOrderID":1,"groupName":"Matchday 1"},'
                b'{"groupID":3,"groupOrderID":3,"groupName":"Matchday 3"}]',
            )
        if request.url.path.endswith("/getmatchdata/ucl/2026"):
            return _response_for(request, season_body)
        raise AssertionError(f"Unexpected request: {request.url}")

    discovery = OpenLigaDBClient(
        settings,
        transport=httpx.MockTransport(handler),
    ).discover_matchdays()

    assert requested_urls == [
        "https://api.openligadb.de/getavailablegroups/ucl/2026",
        "https://api.openligadb.de/getmatchdata/ucl/2026",
    ]
    assert discovery.available_group_matchdays == (1, 3)
    assert discovery.full_season_matchdays == (1, 3)
    assert discovery.candidate_matchdays == (1, 3)
    assert discovery.warnings == ()


def test_discovery_retains_endpoint_disagreement_without_dropping_candidates(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    season_body = json.dumps(
        [
            {
                "matchID": 101,
                "leagueShortcut": "ucl",
                "leagueSeason": 2026,
                "leagueId": 4946,
                "group": {"groupOrderID": 1},
            },
            {
                "matchID": 103,
                "leagueShortcut": "ucl",
                "leagueSeason": 2026,
                "leagueId": 4946,
                "group": {"groupOrderID": 3},
            },
        ]
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getavailablegroups/ucl/2026"):
            return _response_for(
                request,
                b'[{"groupID":1,"groupOrderID":1,"groupName":"Matchday 1"},'
                b'{"groupID":2,"groupOrderID":2,"groupName":"Matchday 2"}]',
            )
        return _response_for(request, season_body)

    discovery = OpenLigaDBClient(
        settings,
        transport=httpx.MockTransport(handler),
    ).discover_matchdays()

    assert discovery.candidate_matchdays == (1, 2, 3)
    assert any("available-groups only matchdays: 2" in warning for warning in discovery.warnings)
    assert any("full-season only matchdays: 3" in warning for warning in discovery.warnings)


def test_successful_raw_snapshot_preserves_bytes_and_metadata(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    snapshot = save_raw_snapshot(_fixed_response(settings), settings, 3)

    assert snapshot.response_path.read_bytes() == RAW_BODY
    metadata = json.loads(snapshot.metadata_path.read_text(encoding="utf-8"))
    assert metadata["provider"] == "OpenLigaDB"
    assert metadata["url"] == "https://api.openligadb.de/getmatchdata/ucl/2026/3"
    assert metadata["shortcut"] == "ucl"
    assert metadata["season"] == 2026
    assert metadata["matchday"] == 3
    assert metadata["byte_count"] == len(RAW_BODY)
    assert metadata["sha256"] == hashlib.sha256(RAW_BODY).hexdigest()


def test_sha256_calculation_is_stable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot = save_raw_snapshot(_fixed_response(settings), settings, 3)

    assert snapshot.sha256 == hashlib.sha256(RAW_BODY).hexdigest()


def test_existing_snapshot_is_never_overwritten(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    response = _fixed_response(settings)
    first = save_raw_snapshot(response, settings, 3)

    with pytest.raises(SnapshotAlreadyExistsError):
        save_raw_snapshot(response, settings, 3)

    assert first.response_path.read_bytes() == RAW_BODY


def test_invalid_json_raises_a_custom_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    transport = httpx.MockTransport(lambda request: _response_for(request, b"not-json"))

    with pytest.raises(OpenLigaDBInvalidJSONError):
        OpenLigaDBClient(settings, transport=transport).fetch_matchday(3)


def test_empty_body_raises_a_custom_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    transport = httpx.MockTransport(lambda request: _response_for(request, b""))

    with pytest.raises(OpenLigaDBEmptyBodyError):
        OpenLigaDBClient(settings, transport=transport).fetch_matchday(3)


def test_network_failure_raises_a_custom_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("test transport failure", request=request)

    with pytest.raises(OpenLigaDBNetworkError):
        OpenLigaDBClient(settings, transport=httpx.MockTransport(handler)).fetch_matchday(3)


def test_wrong_competition_identity_raises_a_contract_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    wrong_identity = (
        b'[{"matchID":123,"leagueShortcut":"other","leagueSeason":2026,"leagueId":4946}]'
    )
    transport = httpx.MockTransport(lambda request: _response_for(request, wrong_identity))

    with pytest.raises(OpenLigaDBContractError):
        OpenLigaDBClient(settings, transport=transport).fetch_matchday(3)


def test_http_failure_raises_a_custom_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with pytest.raises(OpenLigaDBHTTPError, match="503"):
        OpenLigaDBClient(settings, transport=httpx.MockTransport(handler)).fetch_matchday(3)
