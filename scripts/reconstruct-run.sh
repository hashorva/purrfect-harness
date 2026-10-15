#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
exec env PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/reconstruct_run.py" "$@"
