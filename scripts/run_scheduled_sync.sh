#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x .venv/bin/python ]]; then
  echo "Scheduled sync stopped: .venv/bin/python is unavailable." >&2
  exit 2
fi

exec .venv/bin/python scripts/sync_openligadb.py "$@"
