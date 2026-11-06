"""Compare documented OpenLigaDB season-discovery endpoints without capturing or importing."""

from __future__ import annotations

import argparse
import sys

from sports_tracker.config import ConfigurationError, load_openligadb_settings
from sports_tracker.openligadb import OpenLigaDBClient, OpenLigaDBError


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def _matchdays_text(matchdays: tuple[int, ...]) -> str:
    return ", ".join(str(matchday) for matchday in matchdays) or "none"


def main() -> int:
    build_parser().parse_args()
    try:
        settings = load_openligadb_settings()
        discovery = OpenLigaDBClient(settings).discover_matchdays()
    except (ConfigurationError, OpenLigaDBError) as exc:
        print(f"OpenLigaDB season discovery failed: {exc}", file=sys.stderr)
        return 1

    configured_phase = set(settings.expected_league_phase_matchdays)
    league_phase_matchdays = tuple(
        matchday for matchday in discovery.candidate_matchdays if matchday in configured_phase
    )
    post_league_phase_matchdays = tuple(
        matchday for matchday in discovery.candidate_matchdays if matchday not in configured_phase
    )
    print(f"Available-groups endpoint: {discovery.available_groups_url}")
    print(f"Full-season endpoint: {discovery.full_season_url}")
    print(f"Available-groups matchdays: {_matchdays_text(discovery.available_group_matchdays)}")
    print(f"Full-season matchdays: {_matchdays_text(discovery.full_season_matchdays)}")
    print(f"Discovered league-phase matchdays: {_matchdays_text(league_phase_matchdays)}")
    print(f"Post-league-phase matchdays: {_matchdays_text(post_league_phase_matchdays)}")
    if discovery.warnings:
        print("Discovery warnings:")
        for warning in discovery.warnings:
            print(f"  - {warning}")
    print("No raw snapshot was written and no database import was attempted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
