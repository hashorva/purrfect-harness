#!/usr/bin/env bash
# mission-chain.sh — run an ordered list of tasks for one mission with no model in the loop.
# Usage: bash scripts/mission-chain.sh <mission-dir> <provider:task:feature:attempt[:tier]> ...
# Each task: spawn-worker.sh -> verify-mission.sh --run-id. A failure stops the chain.
# Every step writes one JSON line to .tasks/events.jsonl. The last line is "chain_done" or "chain_stopped".
# Completion is process exit: start this with a background command and wait for its completion notice.
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1
MISSION="${1:?mission dir}"; shift
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
EVENTS="$ROOT/.tasks/events.jsonl"
mkdir -p "$ROOT/.tasks"

emit() { # emit <json-object-body without braces>
  printf '{"time":"%s",%s}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$EVENTS"
}

for spec in "$@"; do
  IFS=: read -r PROV TASK FEATURE ATTEMPT TIER <<< "$spec"
  TIER="${TIER:-economy}"
  OUT="$ROOT/.tasks/chain-$TASK-$ATTEMPT.out"
  emit "\"event\":\"task_start\",\"task\":\"$TASK\",\"provider\":\"$PROV\",\"attempt\":$ATTEMPT"
  (cd "$ROOT" && bash scripts/spawn-worker.sh "$PROV" "$MISSION/tasks/$TASK.md" --tier "$TIER" --feature "$FEATURE" --attempt "$ATTEMPT") > "$OUT" 2>&1
  WRC=$?
  RID="$(grep -m1 -o 'run_id=[0-9a-f-]*' "$OUT" | cut -d= -f2)"
  if [ "$WRC" -ne 0 ] || [ -z "$RID" ]; then
    emit "\"event\":\"task_stopped\",\"task\":\"$TASK\",\"step\":\"worker\",\"exit\":$WRC,\"run_id\":\"$RID\",\"reason\":\"worker exit $WRC\""
    emit "\"event\":\"chain_stopped\",\"task\":\"$TASK\""
    echo "chain_stopped at $TASK (worker, exit $WRC); last lines:"; tail -n 20 "$OUT"
    exit 1
  fi
  (cd "$ROOT" && bash scripts/verify-mission.sh --run-id "$RID" "$MISSION") > "$OUT.verify" 2>&1
  VRC=$?
  if [ "$VRC" -ne 0 ]; then
    emit "\"event\":\"task_stopped\",\"task\":\"$TASK\",\"step\":\"verify\",\"exit\":$VRC,\"run_id\":\"$RID\",\"reason\":\"verify exit $VRC\""
    emit "\"event\":\"chain_stopped\",\"task\":\"$TASK\""
    echo "chain_stopped at $TASK (verify, exit $VRC); last lines:"; tail -n 20 "$OUT.verify"
    exit 1
  fi
  emit "\"event\":\"task_verified\",\"task\":\"$TASK\",\"run_id\":\"$RID\""
done
emit "\"event\":\"chain_done\",\"tasks\":$#"
echo "chain_done: $# tasks"
