#!/usr/bin/env bash
# spawn-worker.sh — run a WORKER_TASK via a real local CLI agent (Mac Mini / studio).
# Usage (from the consuming repo root):
#   bash scripts/spawn-worker.sh [<codex|agent|agy|claude>] <path-to-task.md> \
#        [--provider NAME] [--tier economy|premium] [--model ID] [--effort VALUE] [--speed VALUE] [--attempt N] [--feature F00X] [--repo PATH] \
#        [extra prompt...]
#
# Model resolution authority:
#   mission fleet.json seat selected by provider+tier. --model/--effort/--speed
#   are equality assertions only and can never rebind the frozen mission.
#
# Cursor: premium=Grok (fallback Composer), economy=Composer.
# Phase 1 permits only this repository as the worker workspace; external --repo
# targets fail before authorization persistence or provider launch.
# Logs to .tasks/logs/<task-basename>-<utc>.log and receipts to .tasks/receipts/.
# Orchestrators read exit + tail + receipt — never the full transcript.
#
# Self-edit safety: re-exec from a temp snapshot on first entry so a worker that
# edits scripts/spawn-worker.sh cannot kill the running wrapper (bash re-reads
# the live file by byte offset after the CLI returns).
if [ -z "${SPAWN_WORKER_SNAPSHOT:-}" ]; then
  _snap="$(mktemp -t spawn-worker.XXXXXX)"
  cp "${BASH_SOURCE[0]}" "$_snap"
  chmod +x "$_snap"
  export SPAWN_WORKER_SNAPSHOT="$_snap"
  exec bash "$_snap" "$@"
fi
set -euo pipefail

# Delete only the snapshot copy — never the real scripts/spawn-worker.sh. The
# same EXIT cleanup also owns the workspace lock after it is acquired.
SNAPSHOT_TO_DELETE=""
if [ "$0" = "$SPAWN_WORKER_SNAPSHOT" ]; then
  SNAPSHOT_TO_DELETE="$SPAWN_WORKER_SNAPSHOT"
fi
LOCK_PATH=""
LOCK_TOKEN=""
PROVIDER_PID=""

cleanup() {
  local exit_code=$? cleanup_failed=0
  trap - EXIT
  set +e
  if [ -n "$PROVIDER_PID" ] && kill -0 "$PROVIDER_PID" 2>/dev/null; then
    kill -TERM "-$PROVIDER_PID" 2>/dev/null || kill -TERM "$PROVIDER_PID" 2>/dev/null || true
    for _cleanup_wait in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "-$PROVIDER_PID" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "-$PROVIDER_PID" 2>/dev/null; then
      kill -KILL "-$PROVIDER_PID" 2>/dev/null || kill -KILL "$PROVIDER_PID" 2>/dev/null || true
    fi
    wait "$PROVIDER_PID" 2>/dev/null || true
  fi
  if [ -n "$LOCK_PATH" ] && [ -n "$LOCK_TOKEN" ]; then
    PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" release-lock \
      --root "$ROOT" --workspace "$WORKSPACE" --lock "$LOCK_PATH" --token "$LOCK_TOKEN" \
      >/dev/null 2>&1 || cleanup_failed=1
  fi
  [ -z "$SNAPSHOT_TO_DELETE" ] || rm -f "$SNAPSHOT_TO_DELETE"
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
  echo "Usage: spawn-worker.sh [provider] <task.md> --provider NAME [--model ID] [--effort VALUE] [--speed VALUE] [--attempt N]" >&2
  exit 2
}

[ $# -ge 1 ] || usage
WORKER=""
if [[ "$1" == codex || "$1" == agent || "$1" == agy || "$1" == claude ]]; then
  WORKER="$1"
  shift
fi
[ $# -ge 1 ] || usage
TASK="$1"
shift

TIER=""
MODEL_OVERRIDE=""
EFFORT="medium"
SPEED=""
ATTEMPT="1"
FEATURE=""
REPO_IN=""
EXTRA_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --provider) PROVIDER_FLAG="${2:?}"; shift 2 ;;
    --tier) TIER="${2:?}"; shift 2 ;;
    --model) MODEL_OVERRIDE="${2:?}"; shift 2 ;;
    --effort) EFFORT="${2:?}"; shift 2 ;;
    --speed) SPEED="${2:?}"; shift 2 ;;
    --attempt) ATTEMPT="${2:?}"; shift 2 ;;
    --feature) FEATURE="${2:?}"; shift 2 ;;
    --repo) REPO_IN="${2:?}"; shift 2 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done
EXTRA="${EXTRA_ARGS[*]:-}"
[ -n "${PROVIDER_FLAG:-}" ] && {
  [ -z "$WORKER" ] || [ "$WORKER" = "$PROVIDER_FLAG" ] || { echo "ERROR: positional provider and --provider disagree" >&2; exit 2; }
  WORKER="$PROVIDER_FLAG"
}
[ -n "$WORKER" ] || usage
case "$WORKER" in codex|claude|agent|agy) ;; *) usage ;; esac
case "$ATTEMPT" in *[!0-9]*|'') echo "ERROR: --attempt must be positive" >&2; exit 2 ;; esac
[ "$ATTEMPT" -gt 0 ] || { echo "ERROR: --attempt must be positive" >&2; exit 2; }

ROOT="$(pwd -P)"
[ -f "$TASK" ] || { echo "ERROR: task file not found: $TASK" >&2; exit 1; }
TASK_ABS="$(cd "$(dirname "$TASK")" && pwd -P)/$(basename "$TASK")"
TASK_REL="${TASK_ABS#"$ROOT"/}"
BASE="$(basename "$TASK" .md)"

# Worker workspace: Phase 1 rejects every external repository target.
if [ -n "$REPO_IN" ]; then
  # Quoted ~/... is not expanded by the calling shell — expand manually.
  REPO_IN="${REPO_IN/#\~/$HOME}"
  WORKSPACE="$(cd "$REPO_IN" 2>/dev/null && pwd)" || true
  if [ -z "$WORKSPACE" ] || [ ! -d "$WORKSPACE" ]; then
    echo "ERROR: --repo path not found: $REPO_IN" >&2
    exit 1
  fi
else
  WORKSPACE="$ROOT"
fi
[ "$WORKSPACE" = "$ROOT" ] || {
  echo "ERROR: cross-repository execution is disabled in Phase 1" >&2
  exit 1
}

# Infer mission from task path when under docs/missions/<slug>/tasks/
MISSION=""
if [[ "$TASK_REL" == docs/missions/*/tasks/* ]]; then
  MISSION="$(echo "$TASK_REL" | awk -F/ '{print $1"/"$2"/"$3}')"
fi
if [ -z "$MISSION" ] && [ -x "$ROOT/scripts/active-mission.sh" ]; then
  MISSION="$(bash "$ROOT/scripts/active-mission.sh" 2>/dev/null || true)"
fi
[ -n "$MISSION" ] || MISSION="docs/missions/unknown"

# Default tier when omitted: premium for agent (Grok-first), economy for others
if [ -z "$TIER" ]; then
  case "$WORKER" in
    agent) TIER="premium" ;;
    *) TIER="economy" ;;
  esac
fi

case "$TIER" in
  economy|premium) ;;
  *) echo "ERROR: --tier must be economy|premium (got '$TIER')" >&2; exit 2 ;;
esac

[ -n "$SPEED" ] || { [ "$WORKER" = agent ] && SPEED="standard" || SPEED="unknown"; }

case "$WORKER" in
  agent) FLEET_SEAT="cursor.$TIER" ;;
  codex|agy|claude) FLEET_SEAT="$WORKER.$TIER" ;;
esac
if [[ "$MISSION" = /* ]]; then
  FLEET="$MISSION/fleet.json"
else
  FLEET="$ROOT/$MISSION/fleet.json"
fi

# This is the mounted authorization gate. It runs before the lock, log/spec
# persistence, and provider adapter so every rejection is mechanically pre-launch.
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" validate-worker \
  --root "$ROOT" --workspace "$WORKSPACE" --mission "$MISSION" --fleet "$FLEET" \
  --task "$TASK_ABS" --feature "$FEATURE" --work-unit "$BASE"

RESOLVE_ARGS=(python3 "$ROOT/scripts/fleet_state.py" resolve
  --fleet "$FLEET" --seat "$FLEET_SEAT" --mission-path "$MISSION"
  --provider "$WORKER" --effort "$EFFORT" --speed "$SPEED")
[ -z "$MODEL_OVERRIDE" ] || RESOLVE_ARGS+=(--model "$MODEL_OVERRIDE")
BINDING_JSON="$(PYTHONDONTWRITEBYTECODE=1 "${RESOLVE_ARGS[@]}")" || exit $?
MODEL="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["model"])' <<<"$BINDING_JSON")"
[ -n "$MODEL" ] || { echo "ERROR: frozen fleet returned an empty model" >&2; exit 1; }
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" validate-capability \
  --provider "$WORKER" --effort "$EFFORT" --speed "$SPEED"

LOCK_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" acquire-lock \
  --root "$ROOT" --workspace "$WORKSPACE")" || exit $?
LOCK_PATH="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])' <<<"$LOCK_JSON")"
LOCK_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<<"$LOCK_JSON")"
export PURRFECT_DISPATCH_LOCK_PATH="$LOCK_PATH"

mkdir -p "$ROOT/.tasks/logs" "$ROOT/.tasks/receipts"
# Timestamped logs: nested/stub runs of the same task basename must not clobber
# the real dispatch transcript (that happened on T-001 / F007).
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_REL=".tasks/logs/${BASE}-${STAMP}.log"
LOG="$ROOT/$LOG_REL"

PROMPT_TASK="$TASK_REL"
PROMPT="Read ${PROMPT_TASK} and complete it exactly. Follow AGENTS.md and the skills the task names. Do not touch files outside the allow-list. Append a PROGRESS.md entry in the mission folder."
[ -z "$EXTRA" ] || PROMPT+=" $EXTRA"

SPEC_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/execution_spec.py" construct --role worker --mission "$MISSION" --feature "$FEATURE" --work-unit "$BASE" --attempt "$ATTEMPT" --provider "$WORKER" --model "$MODEL" --effort "$EFFORT" --speed "$SPEED" --repo "$WORKSPACE" --prompt "$PROMPT")" || exit $?
RUN_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' <<<"$SPEC_JSON")"
SPEC_PATH="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])' <<<"$SPEC_JSON")"
SPEC_SHA256="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])' <<<"$SPEC_JSON")"

{
  echo "spawn-worker: worker=$WORKER tier=$TIER model=$MODEL task=$TASK_REL feature=${FEATURE:-} mission=$MISSION run_id=$RUN_ID log=$LOG_REL repo=$WORKSPACE"
  echo "prompt: $PROMPT"
  echo "----"
} | tee "$LOG"

# False-green evidence: capture workspace git state before the CLI runs so we
# can prove afterward whether anything actually changed. exit=0 alone has
# already produced silent no-op "successes" (agy flag-parsing bug, a mocked
# stub reporting green with no edits) — see dispatch-worker/SKILL.md.
GIT_BEFORE="$(git -C "$WORKSPACE" rev-parse HEAD 2>/dev/null || echo '')"

# --- portable watchdog -------------------------------------------------------
# macOS ships neither `timeout` nor `gtimeout`, so bound the run ourselves.
# A worker CLI that finishes its work and then never exits is indistinguishable
# from one still working, because the receipt is written only AFTER the process
# ends: a real dispatch (cursor `agent`) sat at 0.0% CPU for 79 minutes after it
# had already committed, while the mission looked "still running" and no receipt
# existed at all. Bound every lane; `agy` additionally self-limits via
# --print-timeout. Set SPAWN_WORKER_TIMEOUT_SECS=0 to disable.
SPAWN_WORKER_TIMEOUT_SECS="${SPAWN_WORKER_TIMEOUT_SECS:-2400}"   # 40 min
TIMEOUT_EXIT=124                                                  # GNU timeout convention

# Usage: <cmd> & watchdog_wait $!   → returns the child's exit code, or 124 on timeout.
watchdog_wait() {
  local pid="$1" waited=0
  if [ "$SPAWN_WORKER_TIMEOUT_SECS" -le 0 ]; then
    wait "$pid"
    return $?
  fi
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge "$SPAWN_WORKER_TIMEOUT_SECS" ]; then
      echo "spawn-worker: TIMEOUT after ${SPAWN_WORKER_TIMEOUT_SECS}s — terminating pid $pid." | tee -a "$LOG"
      echo "spawn-worker: the CLI may have completed its work before hanging — inspect git log/status in $WORKSPACE before re-dispatching." | tee -a "$LOG"
      kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      sleep 5
      if kill -0 "-$pid" 2>/dev/null; then kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true; fi
      wait "$pid" 2>/dev/null || true
      return "$TIMEOUT_EXIT"
    fi
    sleep 5
    waited=$((waited + 5))
  done
  wait "$pid"
}

# Provider grammar and process launch are owned solely by the shared adapter.
set +e
set -m
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/execute_provider.py" --spec "$SPEC_PATH" --sha256 "$SPEC_SHA256" >>"$LOG" 2>&1 < /dev/null &
PROVIDER_PID=$!
set +m
watchdog_wait "$PROVIDER_PID"
EC=$?
PROVIDER_PID=""
set -e

echo "----" | tee -a "$LOG"
echo "exit=$EC" | tee -a "$LOG"

# False-green evidence, part 2: did the workspace actually change?
GIT_AFTER="$(git -C "$WORKSPACE" rev-parse HEAD 2>/dev/null || echo '')"
COMMITS_MADE=0
if [ -n "$GIT_BEFORE" ] && [ -n "$GIT_AFTER" ] && [ "$GIT_BEFORE" != "$GIT_AFTER" ]; then
  COMMITS_MADE="$(git -C "$WORKSPACE" rev-list --count "$GIT_BEFORE..$GIT_AFTER" 2>/dev/null || echo 0)"
fi
DIRTY_AFTER="$(git -C "$WORKSPACE" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
[ -n "$DIRTY_AFTER" ] || DIRTY_AFTER=0
if [ "$EC" -eq 0 ] && [ "$COMMITS_MADE" -eq 0 ] && [ "$DIRTY_AFTER" -eq 0 ]; then
  echo "WARNING: exit=0 but workspace unchanged (0 commits, 0 dirty files) — likely a false green, do not trust this as a PASS without reading the log" | tee -a "$LOG"
fi

ARGV_JSON="$(python3 -c "import json; print(json.dumps(['$WORKER','--model','$MODEL','--effort','$EFFORT','--speed','$SPEED']))")"
REC_ARGS=(
  --role worker --cli "$WORKER" --model "$MODEL" --mission "$MISSION"
  --action "task-${BASE}" --work-unit "$BASE" --exit "$EC" --log "$LOG_REL" --task "$TASK_REL"
  --tier "$TIER" --argv "$ARGV_JSON" --repo "$WORKSPACE"
  --commits-made "$COMMITS_MADE" --dirty-after "$DIRTY_AFTER"
  --run-id "$RUN_ID" --spec "$SPEC_PATH" --spec-sha256 "$SPEC_SHA256"
)
if [ -n "$FEATURE" ]; then
  REC_ARGS+=(--feature "$FEATURE")
fi
REC="$(bash "$ROOT/scripts/write-receipt.sh" "${REC_ARGS[@]}")"
echo "receipt=$REC"
echo "tail:"; tail -20 "$LOG"
exit "$EC"
