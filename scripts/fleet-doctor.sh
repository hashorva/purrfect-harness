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
python_version="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
if [[ "$python_version" =~ ^([0-9]+)\.([0-9]+)$ ]]; then
  python_major="${BASH_REMATCH[1]}"
  python_minor="${BASH_REMATCH[2]}"
  if (( 10#$python_major < 3 || (10#$python_major == 3 && 10#$python_minor < 12) )); then
    python_version="${python_major}.${python_minor}"
  else
    python_version=""
  fi
else
  python_version="unknown"
fi
if [ -n "$python_version" ]; then
  printf 'ERROR python3: Python 3.12 or newer is required (found %s)\n' "$python_version"
  printf 'ERROR python3: Python 3.12 or newer is required (found %s)\n' "$python_version" >&2
  exit 1
fi
PYTHONDONTWRITEBYTECODE=1 exec python3 "$SCRIPT_DIR/fleet_doctor.py" "$@"
