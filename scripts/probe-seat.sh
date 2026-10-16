#!/usr/bin/env bash
# probe-seat.sh — run one frozen fleet seat in an empty Git folder.
# Usage: scripts/probe-seat.sh <seat> [--fleet PATH] [--timeout 120] [--out-root .tasks/probes] [--dry-run]
# Classes: ok, no-turn, mcp-init-wait, permission-wait, input-wait, auth, limit, unknown.
# Evidence is saved beneath .tasks/probes. Step 0: search the CLI's GitHub issues for the exact symptom first.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec env PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/probe_seat.py" "$@"
