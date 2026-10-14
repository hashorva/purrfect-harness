#!/usr/bin/env bash
# spawn-brain.sh — run the mission BRAIN via a real local CLI.
# Produces UUID-keyed logs + terminal ExecutionReceipts.
# Without a brain receipt, verify-mission.sh will not greenlight the mission.
#
# Usage (from consuming repo root):
#   bash scripts/spawn-brain.sh <mission-dir|slug> <mission-init|gate0|review>
#       [--provider codex|claude|cursor|agent|agy] [--model ID] [--effort VALUE] [--speed VALUE] [--attempt N]
set -euo pipefail

LOCK_PATH=""
LOCK_TOKEN=""
RUNNER_PID=""

# shellcheck disable=SC2317,SC2329  # invoked indirectly by the EXIT trap (old and new code)
cleanup() {
  local exit_code=$? cleanup_failed=0
  trap - EXIT
  set +e
  if [ -n "$RUNNER_PID" ] && kill -0 "$RUNNER_PID" 2>/dev/null; then
    kill -TERM "$RUNNER_PID" 2>/dev/null || true
    for _cleanup_wait in {1..50}; do
      kill -0 "$RUNNER_PID" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "$RUNNER_PID" 2>/dev/null; then
      kill -KILL "$RUNNER_PID" 2>/dev/null || true
    fi
    wait "$RUNNER_PID" 2>/dev/null || true
  fi
  if [ -n "$LOCK_PATH" ] && [ -n "$LOCK_TOKEN" ]; then
    PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" release-lock \
      --root "$ROOT" --workspace "$WORKSPACE" --lock "$LOCK_PATH" --token "$LOCK_TOKEN" \
      >/dev/null 2>&1 || cleanup_failed=1
  fi
  if [ "$cleanup_failed" -ne 0 ]; then
    echo "ERROR: failed to release workspace lock" >&2
    [ "$exit_code" -ne 0 ] || exit_code=1
  fi
  exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

usage() {
  echo "Usage: spawn-brain.sh <mission> <mission-init|gate0|review> [--provider NAME] [--model ID] [--effort VALUE] [--speed VALUE] [--attempt N]" >&2
  exit 2
}

[ $# -ge 2 ] || usage
MISSION_IN="$1"
ACTION="$2"
shift 2

MODEL=""
PROVIDER=""
EFFORT=""
SPEED=""
ATTEMPT="1"
while [ $# -gt 0 ]; do
  case "$1" in
    --provider) PROVIDER="${2:?}"; shift 2 ;;
    --model) MODEL="${2:?}"; shift 2 ;;
    --effort) EFFORT="${2:?}"; shift 2 ;;
    --speed) SPEED="${2:?}"; shift 2 ;;
    --attempt) ATTEMPT="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [ -n "$PROVIDER" ]; then
  ROOT="$(pwd -P)"
  PROVIDER="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/harness_registry.py" persisted-name "$PROVIDER")" || exit $?
fi
case "$ATTEMPT" in *[!0-9]*|'') echo "ERROR: --attempt must be positive" >&2; exit 2 ;; esac
[ "$ATTEMPT" -gt 0 ] || { echo "ERROR: --attempt must be positive" >&2; exit 2; }

ROOT="$(pwd -P)"
if [ -d "$MISSION_IN" ]; then
  MISSION_ABS="$(cd "$MISSION_IN" && pwd -P)"
elif [ -d "docs/missions/$MISSION_IN" ]; then
  MISSION_ABS="$(cd "docs/missions/$MISSION_IN" && pwd -P)"
else
  echo "ERROR: mission not found: $MISSION_IN" >&2
  exit 1
fi
MISSION="${MISSION_ABS#"$ROOT"/}"
[ "$MISSION" != "$MISSION_ABS" ] || { echo "ERROR: mission must be inside this repository" >&2; exit 1; }
[ -f "$MISSION_ABS/GOAL.md" ] || { echo "ERROR: no GOAL.md in $MISSION" >&2; exit 1; }
WORKSPACE="$ROOT"
FLEET="$MISSION_ABS/fleet.json"

case "$ACTION" in
  mission-init|gate0|review) ;;
  *) echo "ERROR: unknown action '$ACTION'" >&2; usage ;;
esac

# Lifecycle, Gate 0/fleet, repository, and cleanliness authorization must all
# pass before a lock, log, ExecutionSpec, or provider process exists.
POLICY_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" validate-brain \
  --root "$ROOT" --workspace "$WORKSPACE" --mission "$MISSION" --fleet "$FLEET" --action "$ACTION")" || exit $?
WRITE_SCOPE_JSON="$(python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["write_scope"],separators=(",",":")))' <<<"$POLICY_JSON")"

if [ "$ACTION" = review ]; then
  RESOLVE_ARGS=(python3 "$ROOT/scripts/fleet_state.py" resolve
    --fleet "$FLEET" --seat brain --mission-path "$MISSION")
  [ -z "$PROVIDER" ] || RESOLVE_ARGS+=(--provider "$PROVIDER")
  [ -z "$MODEL" ] || RESOLVE_ARGS+=(--model "$MODEL")
  [ -z "$EFFORT" ] || RESOLVE_ARGS+=(--effort "$EFFORT")
  [ -z "$SPEED" ] || RESOLVE_ARGS+=(--speed "$SPEED")
  BINDING_JSON="$(PYTHONDONTWRITEBYTECODE=1 "${RESOLVE_ARGS[@]}")" || exit $?
  PROVIDER="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["provider"])' <<<"$BINDING_JSON")"
  MODEL="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["model"])' <<<"$BINDING_JSON")"
  EFFORT="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["effort"])' <<<"$BINDING_JSON")"
  SPEED="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["speed"])' <<<"$BINDING_JSON")"
else
  if [ -f "$ROOT/.tasks/fleet-inventory.json" ] && { [ -z "$PROVIDER" ] || [ -z "$MODEL" ]; }; then
    INVENTORY_BINDING="$(python3 -c "import json; print(json.dumps(json.load(open('.tasks/fleet-inventory.json'))['seats']['brain']))" 2>/dev/null || true)"
    if [ -n "$INVENTORY_BINDING" ]; then
      [ -n "$PROVIDER" ] || PROVIDER="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["provider"])' <<<"$INVENTORY_BINDING")"
      [ -n "$MODEL" ] || MODEL="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["model"])' <<<"$INVENTORY_BINDING")"
    fi
  fi
  [ -n "$PROVIDER" ] || PROVIDER="claude"
  [ -n "$MODEL" ] || MODEL="opus"
  [ -n "$EFFORT" ] || EFFORT="medium"
  [ -n "$SPEED" ] || { [ "$PROVIDER" = agent ] && SPEED="standard" || SPEED="unknown"; }
fi

case "$PROVIDER" in codex|claude|agent|agy) ;; *) echo "ERROR: --provider must be codex, claude, cursor, agent, or agy" >&2; exit 2 ;; esac
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" validate-capability \
  --provider "$PROVIDER" --effort "$EFFORT" --speed "$SPEED"

LOCK_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" acquire-lock \
  --root "$ROOT" --workspace "$WORKSPACE")" || exit $?
LOCK_PATH="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])' <<<"$LOCK_JSON")"
LOCK_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<<"$LOCK_JSON")"
export PURRFECT_DISPATCH_LOCK_PATH="$LOCK_PATH"

mkdir -p "$ROOT/.tasks/logs" "$ROOT/.tasks/receipts"
RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
LOG_REL=".tasks/logs/${RUN_ID}.log"
LOG="$ROOT/$LOG_REL"

PROMPT="You are the mission BRAIN for ${MISSION}.
Action: ${ACTION}
Follow docs/missions/ORCHESTRATION.md, docs/missions/MODEL_ROUTING.md, and the matching skill (mission-init or dispatch-worker review).
Read AGENTS.md. Work in the mission folder (GOAL.md, features.json, PROGRESS.md, tasks/).
mission-init: ensure GOAL/features/PROGRESS/tasks/T-001 exist from docs/missions/templates/; status stays draft until GATE 0.
gate0: present feature list + fleet-inventory map; do not dispatch workers.
review: judge git diff by effects only; do not re-implement worker scope.
Append PROGRESS.md pointing at brain log ${LOG_REL}.
Never claim a worker CLI ran unless .tasks/receipts/ proves it."

SPEC_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/execution_spec.py" construct --run-id "$RUN_ID" --write-scope-json "$WRITE_SCOPE_JSON" --role brain --mission "$MISSION" --work-unit "$ACTION" --attempt "$ATTEMPT" --provider "$PROVIDER" --model "$MODEL" --effort "$EFFORT" --speed "$SPEED" --repo "$ROOT" --prompt "$PROMPT")" || exit $?
RUN_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' <<<"$SPEC_JSON")"
SPEC_PATH="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])' <<<"$SPEC_JSON")"
SPEC_SHA256="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])' <<<"$SPEC_JSON")"

{
  echo "spawn-brain: action=$ACTION provider=$PROVIDER model=$MODEL mission=$MISSION run_id=$RUN_ID log=$LOG_REL"
  echo "prompt: $PROMPT"
  echo "----"
} | tee "$LOG"

SPAWN_BRAIN_TIMEOUT_SECS="${SPAWN_BRAIN_TIMEOUT_SECS:-2400}"
set +e
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/execution_runner.py" \
  --spec "$SPEC_PATH" --spec-sha256 "$SPEC_SHA256" --log "$LOG" \
  --timeout "$SPAWN_BRAIN_TIMEOUT_SECS" &
RUNNER_PID=$!
wait "$RUNNER_PID"
EC=$?
RUNNER_PID=""
set -e
RECEIPT_PATH="$ROOT/.tasks/receipts/${RUN_ID}.json"
if ! PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/execution_receipt.py" validate --receipt "$RECEIPT_PATH" >/dev/null; then
  echo "ERROR: run did not produce a valid terminal ExecutionReceipt" >&2
  EC=125
fi

echo "----" | tee -a "$LOG"
echo "exit=$EC" | tee -a "$LOG"
echo "tail:"; tail -20 "$LOG"
exit "$EC"
