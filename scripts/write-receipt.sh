#!/usr/bin/env bash
# write-receipt.sh — append a machine-checkable dispatch receipt under .tasks/receipts/
# Usage (internal; called by spawn-brain / spawn-worker):
#   bash scripts/write-receipt.sh --role brain|worker --cli NAME --model ID \
#     --mission RELPATH --action NAME --exit N --log RELPATH \
#     [--task RELPATH] [--feature ID] [--tier economy|premium] [--argv JSON_ARRAY] \
#     [--repo ABS_PATH] [--commits-made N] [--dirty-after N]
#
# --commits-made / --dirty-after (worker receipts only): mechanical evidence that
# the workspace actually changed, so verify-mission.sh does not have to trust
# exit=0 alone. Omit for brain receipts (mission-init/gate0/review do not all
# produce a diff — "review" must not).
set -euo pipefail

ROLE=""; CLI=""; MODEL=""; MISSION=""; ACTION=""; EXIT_CODE=""; LOG=""
TASK=""; FEATURE=""; TIER=""; ARGV="[]"; REPO=""
COMMITS_MADE=""; DIRTY_AFTER=""
WORK_UNIT=""; RUN_ID=""; SPEC=""; SPEC_SHA256=""

while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE="${2:?}"; shift 2 ;;
    --cli) CLI="${2:?}"; shift 2 ;;
    --model) MODEL="${2:?}"; shift 2 ;;
    --mission) MISSION="${2:?}"; shift 2 ;;
    --action) ACTION="${2:?}"; shift 2 ;;
    --exit) EXIT_CODE="${2:?}"; shift 2 ;;
    --log) LOG="${2:?}"; shift 2 ;;
    --task) TASK="${2:?}"; shift 2 ;;
    --feature) FEATURE="${2:?}"; shift 2 ;;
    --tier) TIER="${2:?}"; shift 2 ;;
    --argv) ARGV="${2:?}"; shift 2 ;;
    --repo) REPO="${2:?}"; shift 2 ;;
    --commits-made) COMMITS_MADE="${2:?}"; shift 2 ;;
    --dirty-after) DIRTY_AFTER="${2:?}"; shift 2 ;;
    --work-unit) WORK_UNIT="${2:?}"; shift 2 ;;
    --run-id) RUN_ID="${2:?}"; shift 2 ;;
    --spec) SPEC="${2:?}"; shift 2 ;;
    --spec-sha256) SPEC_SHA256="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

: "${ROLE:?}"; : "${CLI:?}"; : "${MODEL:?}"; : "${MISSION:?}"
: "${ACTION:?}"; : "${EXIT_CODE:?}"; : "${LOG:?}"

LINK_COUNT=0
[ -n "$RUN_ID" ] && LINK_COUNT=$((LINK_COUNT + 1))
[ -n "$SPEC" ] && LINK_COUNT=$((LINK_COUNT + 1))
[ -n "$SPEC_SHA256" ] && LINK_COUNT=$((LINK_COUNT + 1))
if [ "$LINK_COUNT" -ne 0 ] && [ "$LINK_COUNT" -ne 3 ]; then
  echo "ERROR: --run-id, --spec, and --spec-sha256 must be supplied together" >&2
  exit 2
fi
LINK_JSON=""
if [ "$LINK_COUNT" -eq 3 ]; then
  : "${WORK_UNIT:?--work-unit is required with execution spec linkage}"
  LINK_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$PWD/scripts/execution_spec.py" receipt-link \
    --run-id "$RUN_ID" --spec "$SPEC" --spec-sha256 "$SPEC_SHA256" --role "$ROLE" \
    --mission "$MISSION" --work-unit "$WORK_UNIT" --provider "$CLI" --model "$MODEL")" || exit $?
fi

ROOT="$(pwd)"
REC_DIR="$ROOT/.tasks/receipts"
mkdir -p "$REC_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SAFE_ACTION="$(echo "$ACTION" | tr '/ ' '__')"
OUT="$REC_DIR/${ROLE}-${SAFE_ACTION}-${TS}.json"

export RECEIPT_OUT="$OUT" RECEIPT_ROLE="$ROLE" RECEIPT_CLI="$CLI" RECEIPT_MODEL="$MODEL"
export RECEIPT_MISSION="$MISSION" RECEIPT_ACTION="$ACTION" RECEIPT_EXIT="$EXIT_CODE"
export RECEIPT_LOG="$LOG" RECEIPT_TASK="$TASK" RECEIPT_FEATURE="$FEATURE"
export RECEIPT_TIER="$TIER" RECEIPT_ARGV="$ARGV" RECEIPT_TS="$TS"
export RECEIPT_REPO="$REPO"
export RECEIPT_COMMITS_MADE="$COMMITS_MADE" RECEIPT_DIRTY_AFTER="$DIRTY_AFTER"
export RECEIPT_LINK_JSON="$LINK_JSON"

python3 - <<'PY'
import json, os
from pathlib import Path
from datetime import datetime, timezone

def opt_int(name):
    v = os.environ.get(name)
    if v is None or v == "":
        return None
    try:
        return int(v)
    except ValueError:
        return None

commits_made = opt_int("RECEIPT_COMMITS_MADE")
dirty_after = opt_int("RECEIPT_DIRTY_AFTER")
workspace_changed = None
if commits_made is not None or dirty_after is not None:
    workspace_changed = bool((commits_made or 0) > 0 or (dirty_after or 0) > 0)

doc = {
    "schema": "purrfect-receipt/v1",
    "role": os.environ["RECEIPT_ROLE"],
    "cli": os.environ["RECEIPT_CLI"],
    "model": os.environ["RECEIPT_MODEL"],
    "mission": os.environ["RECEIPT_MISSION"],
    "action": os.environ["RECEIPT_ACTION"],
    "task": os.environ.get("RECEIPT_TASK") or None,
    "feature": os.environ.get("RECEIPT_FEATURE") or None,
    "tier": os.environ.get("RECEIPT_TIER") or None,
    "repo": os.environ.get("RECEIPT_REPO") or None,
    "log": os.environ["RECEIPT_LOG"],
    "started_at": None,
    "ended_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "exit": int(os.environ["RECEIPT_EXIT"]),
    "argv": json.loads(os.environ.get("RECEIPT_ARGV") or "[]"),
    # False-green evidence (worker receipts only; None = not measured, e.g. brain
    # roles or receipts written before this field existed — verify-mission.sh
    # treats None as unknown/WARN, never as a silent PASS).
    "commits_made": commits_made,
    "dirty_after": dirty_after,
    "workspace_changed": workspace_changed,
}
link_json = os.environ.get("RECEIPT_LINK_JSON")
if link_json:
    link = json.loads(link_json)
    doc.update({
        "run_id": link["run_id"],
        "execution_spec_path": link["execution_spec_path"],
        "execution_spec_sha256": link["execution_spec_sha256"],
        "requested_configuration": link["requested"],
        "resolved_configuration": link["resolved"],
        "observed_configuration": link["observed"],
    })
out = Path(os.environ["RECEIPT_OUT"])
out.write_text(json.dumps(doc, indent=2) + "\n")
slug = os.environ["RECEIPT_MISSION"].rstrip("/").split("/")[-1]
latest = out.parent / f"latest-{os.environ['RECEIPT_ROLE']}-{slug}.json"
latest.write_text(out.read_text())
try:
    print(out.relative_to(Path.cwd()))
except Exception:
    print(out)
PY
