#!/usr/bin/env bash
# spawn-brain.sh — run the mission BRAIN via a real CLI (default: claude opus).
# Produces .tasks/logs/brain-*.log + .tasks/receipts/brain-*.json.
# Without a brain receipt, verify-mission.sh will not greenlight the mission.
#
# Usage (from consuming repo root):
#   bash scripts/spawn-brain.sh <mission-dir|slug> <mission-init|gate0|review>
#       [--provider codex|claude|agent|agy] [--model ID] [--effort VALUE] [--speed VALUE] [--attempt N]
#   bash scripts/spawn-brain.sh <mission-dir|slug> waiver --reason "already on Opus in Cursor"
set -euo pipefail

usage() {
  echo "Usage: spawn-brain.sh <mission> <mission-init|gate0|review|waiver> [--provider NAME] [--model ID] [--effort VALUE] [--speed VALUE] [--attempt N] [--reason TEXT]" >&2
  exit 2
}

[ $# -ge 2 ] || usage
MISSION_IN="$1"
ACTION="$2"
shift 2

MODEL=""
PROVIDER=""
EFFORT="medium"
SPEED=""
ATTEMPT="1"
REASON=""
while [ $# -gt 0 ]; do
  case "$1" in
    --provider) PROVIDER="${2:?}"; shift 2 ;;
    --model) MODEL="${2:?}"; shift 2 ;;
    --effort) EFFORT="${2:?}"; shift 2 ;;
    --speed) SPEED="${2:?}"; shift 2 ;;
    --attempt) ATTEMPT="${2:?}"; shift 2 ;;
    --reason) REASON="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done
case "$ATTEMPT" in *[!0-9]*|'') echo "ERROR: --attempt must be positive" >&2; exit 2 ;; esac
[ "$ATTEMPT" -gt 0 ] || { echo "ERROR: --attempt must be positive" >&2; exit 2; }

ROOT="$(pwd)"
if [ -d "$MISSION_IN" ]; then
  MISSION="$MISSION_IN"
elif [ -d "docs/missions/$MISSION_IN" ]; then
  MISSION="docs/missions/$MISSION_IN"
else
  echo "ERROR: mission not found: $MISSION_IN" >&2
  exit 1
fi
MISSION="${MISSION%/}"
[ -f "$MISSION/GOAL.md" ] || { echo "ERROR: no GOAL.md in $MISSION" >&2; exit 1; }

mkdir -p "$ROOT/.tasks/logs" "$ROOT/.tasks/receipts"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_REL=".tasks/logs/brain-${ACTION}-${TS}.log"
LOG="$ROOT/$LOG_REL"

if [ -z "$MODEL" ]; then
  if [ -f "$ROOT/.tasks/fleet-inventory.json" ]; then
    MODEL="$(python3 -c "import json;print(json.load(open('.tasks/fleet-inventory.json'))['seats']['brain']['model'])" 2>/dev/null || echo opus)"
  else
    MODEL="opus"
  fi
fi
[ -n "$PROVIDER" ] || PROVIDER="claude"
case "$PROVIDER" in codex|claude|agent|agy) ;; *) echo "ERROR: --provider must be codex, claude, agent, or agy" >&2; exit 2 ;; esac
[ -n "$SPEED" ] || { [ "$PROVIDER" = agent ] && SPEED="standard" || SPEED="unknown"; }

write_receipt() {
  local cli="$1" exit_code="$2" argv_json="$3"
  bash "$ROOT/scripts/write-receipt.sh" \
    --role brain \
    --cli "$cli" \
    --model "$MODEL" \
    --mission "$MISSION" \
    --action "$ACTION" --work-unit "$ACTION" \
    --exit "$exit_code" \
    --log "$LOG_REL" \
    --argv "$argv_json"
}

case "$ACTION" in
  waiver)
    [ -n "$REASON" ] || { echo "ERROR: waiver requires --reason '…'" >&2; exit 2; }
    {
      echo "spawn-brain: WAIVER mission=$MISSION model=$MODEL"
      echo "reason: $REASON"
      echo "This is NOT a Claude CLI run."
      echo "----"
      echo "exit=0"
    } | tee "$LOG"
    ARGV="$(python3 -c "import json,sys; print(json.dumps(['waiver','--reason',sys.argv[1]]))" "$REASON")"
    REC="$(write_receipt waiver 0 "$ARGV")"
    echo "receipt=$REC"
    echo "WARNING: waiver recorded. Prefer: bash scripts/spawn-brain.sh $MISSION mission-init"
    exit 0
    ;;
  mission-init|gate0|review) ;;
  *) echo "ERROR: unknown action '$ACTION'" >&2; usage ;;
esac

PROMPT="You are the mission BRAIN for ${MISSION}.
Action: ${ACTION}
Follow docs/missions/ORCHESTRATION.md, docs/missions/MODEL_ROUTING.md, and the matching skill (mission-init or dispatch-worker review).
Read AGENTS.md. Work in the mission folder (GOAL.md, features.json, PROGRESS.md, tasks/).
mission-init: ensure GOAL/features/PROGRESS/tasks/T-001 exist from docs/missions/templates/; status stays draft until GATE 0.
gate0: present feature list + fleet-inventory map; do not dispatch workers.
review: judge git diff by effects only; do not re-implement worker scope.
Append PROGRESS.md pointing at brain log ${LOG_REL}.
Never claim a worker CLI ran unless .tasks/receipts/ proves it."

SPEC_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/execution_spec.py" construct --role brain --mission "$MISSION" --work-unit "$ACTION" --attempt "$ATTEMPT" --provider "$PROVIDER" --model "$MODEL" --effort "$EFFORT" --speed "$SPEED" --repo "$ROOT" --prompt "$PROMPT")" || exit $?
RUN_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' <<<"$SPEC_JSON")"
SPEC_PATH="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])' <<<"$SPEC_JSON")"
SPEC_SHA256="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])' <<<"$SPEC_JSON")"
ARGV_JSON="$(python3 -c "import json; print(json.dumps(['$PROVIDER','--model','$MODEL','--effort','$EFFORT','--speed','$SPEED']))")"

{
  echo "spawn-brain: action=$ACTION provider=$PROVIDER model=$MODEL mission=$MISSION run_id=$RUN_ID log=$LOG_REL"
  echo "prompt: $PROMPT"
  echo "----"
} | tee "$LOG"

set +e
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/execute_provider.py" --spec "$SPEC_PATH" --sha256 "$SPEC_SHA256" >>"$LOG" 2>&1 < /dev/null
EC=$?
set -e

echo "----" | tee -a "$LOG"
echo "exit=$EC" | tee -a "$LOG"
REC="$(bash "$ROOT/scripts/write-receipt.sh" --role brain --cli "$PROVIDER" --model "$MODEL" --mission "$MISSION" --action "$ACTION" --work-unit "$ACTION" --exit "$EC" --log "$LOG_REL" --argv "$ARGV_JSON" --run-id "$RUN_ID" --spec "$SPEC_PATH" --spec-sha256 "$SPEC_SHA256")"
echo "receipt=$REC"
echo "tail:"; tail -20 "$LOG"
exit "$EC"
