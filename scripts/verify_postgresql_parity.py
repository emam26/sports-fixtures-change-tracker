"""Print a read-only parity report for the SQL Server and PostgreSQL databases."""

from __future__ import annotations

import argparse
import json
import sys

from sports_tracker.config import load_database_settings, load_postgresql_settings
from sports_tracker.database import database_connection
from sports_tracker.postgres import postgresql_connection
from sports_tracker.postgres_parity import build_parity_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-schema", default="dbo")
    parser.add_argument("--target-schema", default="public")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source_settings = load_database_settings()
        target_settings = load_postgresql_settings()
        with database_connection(source_settings) as source_connection:
            with postgresql_connection(target_settings) as target_connection:
                report = build_parity_report(
                    source_connection,
                    target_connection,
                    source_schema=args.source_schema,
                    target_schema=args.target_schema,
                )
    except Exception as exc:
        print(f"PostgreSQL parity check failed safely ({type(exc).__name__}).", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "MATCH" else 2


if __name__ == "__main__":
    raise SystemExit(main())
