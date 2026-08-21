#!/usr/bin/env bash
# Public machine inventory entry point.  Policy lives in fleet_state.py.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec python3 "$ROOT/scripts/fleet_state.py" inventory "$@"
