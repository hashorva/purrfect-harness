#!/usr/bin/env bash
# active-mission.sh — print the single active mission directory (relative to repo root).
# Active = GOAL.md status is in-progress or awaiting-gate.
# Usage (from a consuming repo root, or pass REPO=):
#   bash scripts/active-mission.sh
#   bash /path/to/harness/scripts/active-mission.sh   # still resolves against cwd
set -euo pipefail

ROOT="${REPO:-$(pwd)}"
MISSIONS="$ROOT/docs/missions"

if [ ! -d "$MISSIONS" ]; then
  echo "ERROR: no docs/missions/ under $ROOT" >&2
  exit 1
fi

ACTIVE=()
while IFS= read -r -d '' goal; do
  dir="$(dirname "$goal")"
  base="$(basename "$dir")"
  [ "$base" = "templates" ] && continue
  status="$(grep -E '^status:' "$goal" | head -1 | sed 's/^status:[[:space:]]*//;s/[[:space:]]*$//' || true)"
  case "$status" in
    in-progress|awaiting-gate) ACTIVE+=("$dir") ;;
  esac
done < <(find "$MISSIONS" -mindepth 2 -maxdepth 2 -name GOAL.md -print0 2>/dev/null)

n=${#ACTIVE[@]}
if [ "$n" -eq 0 ]; then
  echo "ERROR: no active mission (status in-progress|awaiting-gate) under docs/missions/" >&2
  exit 1
fi
if [ "$n" -gt 1 ]; then
  echo "ERROR: multiple active missions — keep exactly one:" >&2
  printf '  %s\n' "${ACTIVE[@]}" >&2
  exit 1
fi

# Print path relative to ROOT when possible
rel="${ACTIVE[0]#"$ROOT"/}"
echo "$rel"
