"""Run read-only PostgreSQL deployment checks without exposing credentials."""

from __future__ import annotations

import argparse
import json
import sys

from sports_tracker.config import load_postgresql_settings
from sports_tracker.postgres import postgresql_connection
from sports_tracker.postgres_preflight import run_preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="public")
    args = parser.parse_args(argv)
    try:
        settings = load_postgresql_settings()
        with postgresql_connection(settings) as connection:
            report = run_preflight(connection, schema=args.schema)
    except Exception as exc:
        print(f"PostgreSQL preflight failed safely ({type(exc).__name__}).", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
