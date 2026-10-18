#!/usr/bin/env bash
# spawn-brain.sh — run the mission BRAIN via a real local CLI.
# Produces UUID-keyed logs + terminal ExecutionReceipts.
# Without a brain receipt, verify-mission.sh will not greenlight the mission.
#
# Usage (from consuming repo root):
#   bash scripts/spawn-brain.sh <mission-dir|slug> <mission-init|gate0|review>
#       [--provider codex|claude|cursor|agent|agy] [--model ID] [--effort VALUE] [--speed VALUE] [--attempt N] [--seat SEAT]
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
_HARNESS_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/harness-path.sh disable=SC1091
if [ -f "$_HARNESS_SCRIPT_DIR/harness-path.sh" ]; then
  . "$_HARNESS_SCRIPT_DIR/harness-path.sh"
elif [ -f "$(pwd -P)/scripts/harness-path.sh" ]; then
  . "$(pwd -P)/scripts/harness-path.sh"
fi
unset _HARNESS_SCRIPT_DIR

# Refuse a bad timing value before any spec is persisted (a bad value would otherwise leave a spec without a receipt).
for _secs_name in SPAWN_BRAIN_TIMEOUT_SECS SPAWN_BRAIN_STALL_SECS SPAWN_BRAIN_IDLE_SECS; do
  _secs_value="${!_secs_name:-}"
  if [ -n "$_secs_value" ] && ! [[ "$_secs_value" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "ERROR: $_secs_name must be a non-negative number" >&2
    exit 2
  fi
done

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
  echo "Usage: spawn-brain.sh <mission> <mission-init|gate0|review> [--provider NAME] [--model ID] [--effort VALUE] [--speed VALUE] [--attempt N] [--seat SEAT]" >&2
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
SEAT="brain"
SEAT_SET="false"
while [ $# -gt 0 ]; do
  case "$1" in
    --provider) PROVIDER="${2:?}"; shift 2 ;;
    --model) MODEL="${2:?}"; shift 2 ;;
    --effort) EFFORT="${2:?}"; shift 2 ;;
    --speed) SPEED="${2:?}"; shift 2 ;;
    --attempt) ATTEMPT="${2:?}"; shift 2 ;;
    --seat) SEAT="${2:?}"; SEAT_SET="true"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done
case "$SEAT" in brain|brain_argon|brain_codex|brain_fable) ;; *) echo "ERROR: --seat must be brain, brain_argon, brain_codex, or brain_fable" >&2; exit 2 ;; esac
[ "$ACTION" = review ] || [ "$SEAT_SET" = false ] || { echo "ERROR: --seat applies to review only" >&2; exit 2; }
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
    --fleet "$FLEET" --seat "$SEAT" --mission-path "$MISSION" --inventory "$ROOT/.tasks/fleet-inventory.json" --root "$ROOT")
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
  [ -n "$EFFORT" ] || EFFORT="high"
  [ -n "$SPEED" ] || { [ "$PROVIDER" = agent ] && SPEED="standard" || SPEED="unknown"; }
fi

if [ "$ACTION" = review ]; then
  ROLE_EFFORT_ARGS=(--role review --fleet "$FLEET" --seat "$SEAT")
else
  ROLE_EFFORT_ARGS=(--role planning)
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" validate-role-effort "${ROLE_EFFORT_ARGS[@]}" --effort "$EFFORT"

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

PROMPT="You are the mission BRAIN for ${MISSION}. Action: ${ACTION}.
Goal for mission-init: GOAL.md, features.json, PROGRESS.md and tasks/T-001.md exist (templates in docs/missions/templates/) and the status stays draft until Gate 0. Goal for gate0: the feature list and the fleet-inventory map are ready for the owner; no worker is dispatched. Goal for review: a verdict on the worker's change, judged by its effects against the task's exit criteria.
Context: AGENTS.md, docs/missions/ORCHESTRATION.md, docs/missions/MODEL_ROUTING.md, the mission folder, and the repo skills in .agents/skills (mission-init, dispatch-worker).
Resources: your CLI's native tools, web search, and subagents where your CLI has them (Claude Code: explorer on Haiku and the read-only code-reviewer; codex: Luna; cursor: Composer; agy: Flash). Delegate wide reading and searching to a cheap subagent and make the decisions yourself.
Acceptance checks: shellcheck scripts/*.sh tests/*.sh, bash tests/run-tests.sh, and bash scripts/verify-mission.sh ${MISSION} (ruff and a type check join when the repo adds them). A worker run counts only when .tasks/receipts/ proves it.
Budget: this one run, under the runner's timeout. Run your checks before you finish and stop when the goal is met. Your log: ${LOG_REL}."

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
  --timeout "$SPAWN_BRAIN_TIMEOUT_SECS" \
  --stall-seconds "${SPAWN_BRAIN_STALL_SECS:-90}" --idle-seconds "${SPAWN_BRAIN_IDLE_SECS:-900}" &
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
