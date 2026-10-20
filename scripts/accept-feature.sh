#!/usr/bin/env bash
set -euo pipefail

RUN_ID=""; SHA=""; ACCEPTED_BY=""; MISSION=""
while [ $# -gt 0 ]; do
  case "$1" in
    --run-id) RUN_ID="${2:-}"; shift 2 ;;
    --verification-sha256) SHA="${2:-}"; shift 2 ;;
    --accepted-by) ACCEPTED_BY="${2:-}"; shift 2 ;;
    -h|--help) echo "Usage: accept-feature.sh --run-id <uuid> --verification-sha256 <hex> --accepted-by <identity> [mission-dir]"; exit 0 ;;
    *) [ -z "$MISSION" ] || { echo "ERROR: only one mission may be supplied" >&2; exit 2; }; MISSION="$1"; shift ;;
  esac
done
PYTHONDONTWRITEBYTECODE=1 python3 "$(pwd -P)/scripts/run_id.py" check "$RUN_ID" || exit 2
[ -n "$RUN_ID" ] && [ -n "$SHA" ] && [ -n "$ACCEPTED_BY" ] || { echo "ERROR: run ID, verification hash, and accepted-by are required" >&2; exit 2; }
ROOT="$(pwd -P)"; [ -n "$MISSION" ] || MISSION="$(bash "$ROOT/scripts/active-mission.sh")"
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/verification_record.py" accept --run-id "$RUN_ID" --verification-sha256 "$SHA" --accepted-by "$ACCEPTED_BY" "$MISSION"
