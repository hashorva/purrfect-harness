#!/usr/bin/env bash
# spawn-brain.sh — run the mission BRAIN via a real CLI (default: claude opus).
# Produces .tasks/logs/brain-*.log + .tasks/receipts/brain-*.json.
# Without a brain receipt, verify-mission.sh will not greenlight the mission.
#
# Usage (from consuming repo root):
#   bash scripts/spawn-brain.sh <mission-dir|slug> <mission-init|gate0|review>
#       [--model opus|fable|...]
#   bash scripts/spawn-brain.sh <mission-dir|slug> waiver --reason "already on Opus in Cursor"
set -euo pipefail

usage() {
  echo "Usage: spawn-brain.sh <mission> <mission-init|gate0|review|waiver> [--model ID] [--reason TEXT]" >&2
  exit 2
}

[ $# -ge 2 ] || usage
MISSION_IN="$1"
ACTION="$2"
shift 2

MODEL=""
REASON=""
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="${2:?}"; shift 2 ;;
    --reason) REASON="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

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

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: CLI '$1' not on PATH." >&2
    exit 127
  }
}

write_receipt() {
  local cli="$1" exit_code="$2" argv_json="$3"
  bash "$ROOT/scripts/write-receipt.sh" \
    --role brain \
    --cli "$cli" \
    --model "$MODEL" \
    --mission "$MISSION" \
    --action "$ACTION" \
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

need claude

PROMPT="You are the mission BRAIN for ${MISSION}.
Action: ${ACTION}
Follow docs/missions/ORCHESTRATION.md, docs/missions/MODEL_ROUTING.md, and the matching skill (mission-init or dispatch-worker review).
Read AGENTS.md. Work in the mission folder (GOAL.md, features.json, PROGRESS.md, tasks/).
mission-init: ensure GOAL/features/PROGRESS/tasks/T-001 exist from docs/missions/templates/; status stays draft until GATE 0.
gate0: present feature list + fleet-inventory map; do not dispatch workers.
review: judge git diff by effects only; do not re-implement worker scope.
Append PROGRESS.md pointing at brain log ${LOG_REL}.
Never claim a worker CLI ran unless .tasks/receipts/ proves it."

ARGV_JSON="$(python3 -c "import json; print(json.dumps(['claude','-p','--model','$MODEL','--allowedTools','Read,Write,Edit,Bash']))")"

{
  echo "spawn-brain: action=$ACTION model=$MODEL mission=$MISSION log=$LOG_REL"
  echo "prompt: $PROMPT"
  echo "----"
} | tee "$LOG"

set +e
claude -p --model "$MODEL" \
  --allowedTools "Read,Write,Edit,Bash" \
  "$PROMPT" >>"$LOG" 2>&1
EC=$?
set -e

echo "----" | tee -a "$LOG"
echo "exit=$EC" | tee -a "$LOG"
REC="$(write_receipt claude "$EC" "$ARGV_JSON")"
echo "receipt=$REC"
echo "tail:"; tail -20 "$LOG"
exit "$EC"
