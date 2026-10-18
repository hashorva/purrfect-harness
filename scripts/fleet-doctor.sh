#!/usr/bin/env bash
set -euo pipefail
case "${BASH_SOURCE[0]}" in
  */*) SCRIPT_DIR="$(cd -- "${BASH_SOURCE[0]%/*}" && pwd)" ;;
  *) SCRIPT_DIR="$(pwd)" ;;
esac
# shellcheck source=scripts/harness-path.sh disable=SC1091
. "$SCRIPT_DIR/harness-path.sh"
missing=0
for tool in git python3 tmux jq shellcheck; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf "ERROR %s: required Gate 0 tool '%s' is not installed on PATH\n" "$tool" "$tool"
    printf "ERROR %s: required Gate 0 tool '%s' is not installed on PATH\n" "$tool" "$tool" >&2
    missing=1
  fi
done
[ "$missing" -eq 0 ] || exit 1
PYTHONDONTWRITEBYTECODE=1 exec python3 "$SCRIPT_DIR/fleet_doctor.py" "$@"
