#!/usr/bin/env bash
# verify-mission.sh — verify one immutable worker run, or audit accepted features.
set -euo pipefail
RUN_ID=""; RUN_ID_GIVEN=0; REQUIRE_WORKERS=0; MISSION=""
while [ $# -gt 0 ]; do
  case "$1" in
    --run-id) RUN_ID="${2:-}"; RUN_ID_GIVEN=1; shift 2 ;;
    --require-workers) REQUIRE_WORKERS=1; shift ;;
    -h|--help) echo "Usage: verify-mission.sh [--run-id <uuid>] [--require-workers] [mission-dir]"; exit 0 ;;
    *) [ -z "$MISSION" ] || { echo "ERROR: only one mission may be supplied" >&2; exit 2; }; MISSION="$1"; shift ;;
  esac
done
if [ "$RUN_ID_GIVEN" -eq 1 ]; then
  PYTHONDONTWRITEBYTECODE=1 python3 "$(pwd -P)/scripts/run_id.py" check "$RUN_ID" || exit 2
fi
ROOT="$(pwd -P)"; [ -n "$MISSION" ] || MISSION="$(bash "$ROOT/scripts/active-mission.sh")"
if [ -n "$RUN_ID" ]; then
  [ "$REQUIRE_WORKERS" -eq 0 ] || { echo "ERROR: --require-workers is only valid for mission audit" >&2; exit 2; }
  PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/verification_record.py" verify --run-id "$RUN_ID" "$MISSION"
else
  if [ "$REQUIRE_WORKERS" -eq 1 ]; then set -- audit --require-workers "$MISSION"; else set -- audit "$MISSION"; fi
  PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/verification_record.py" "$@"
fi
