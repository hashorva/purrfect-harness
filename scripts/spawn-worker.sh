#!/usr/bin/env bash
# spawn-worker.sh — run a WORKER_TASK via a real local CLI agent (Mac Mini / studio).
# Usage (from the consuming repo root):
#   bash scripts/spawn-worker.sh <codex|agent|agy|claude> <path-to-task.md> \
#        [--tier economy|premium] [--model <id>] [--feature F00X] [--repo <path>] \
#        [extra prompt...]
#
# Model resolution order:
#   1. --model
#   2. seat from .tasks/fleet-inventory.json (run fleet-inventory.sh if missing)
#   3. family fallbacks from MODEL_ROUTING.md
#
# Cursor: premium=Grok (fallback Composer), economy=Composer.
# --repo sets the worker CLI workspace only; logs/receipts/mission stay in this repo.
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
# Delete only the snapshot copy — never the real scripts/spawn-worker.sh.
if [ "$0" = "$SPAWN_WORKER_SNAPSHOT" ]; then
  trap 'rm -f "$SPAWN_WORKER_SNAPSHOT"' EXIT
fi

set -euo pipefail

usage() {
  echo "Usage: spawn-worker.sh <codex|agent|agy|claude> <task.md> [--tier economy|premium] [--model <id>] [--feature ID] [--repo <path>]" >&2
  exit 2
}

[ $# -ge 2 ] || usage
WORKER="$1"
TASK="$2"
shift 2

TIER=""
MODEL_OVERRIDE=""
FEATURE=""
REPO_IN=""
EXTRA_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --tier) TIER="${2:?}"; shift 2 ;;
    --model) MODEL_OVERRIDE="${2:?}"; shift 2 ;;
    --feature) FEATURE="${2:?}"; shift 2 ;;
    --repo) REPO_IN="${2:?}"; shift 2 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done
EXTRA="${EXTRA_ARGS[*]:-}"

ROOT="$(pwd)"
[ -f "$TASK" ] || { echo "ERROR: task file not found: $TASK" >&2; exit 1; }
TASK_ABS="$(cd "$(dirname "$TASK")" && pwd)/$(basename "$TASK")"
TASK_REL="${TASK_ABS#"$ROOT"/}"
BASE="$(basename "$TASK" .md)"

# Worker workspace: optional --repo; default is this repo (ROOT).
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

# Infer mission from task path when under docs/missions/<slug>/tasks/
MISSION=""
if [[ "$TASK_REL" == docs/missions/*/tasks/* ]]; then
  MISSION="$(echo "$TASK_REL" | awk -F/ '{print $1"/"$2"/"$3}')"
fi
if [ -z "$MISSION" ] && [ -x "$ROOT/scripts/active-mission.sh" ]; then
  MISSION="$(bash "$ROOT/scripts/active-mission.sh" 2>/dev/null || true)"
fi
[ -n "$MISSION" ] || MISSION="docs/missions/unknown"

mkdir -p "$ROOT/.tasks/logs" "$ROOT/.tasks/receipts"
# Timestamped logs: nested/stub runs of the same task basename must not clobber
# the real dispatch transcript (that happened on T-001 / F007).
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_REL=".tasks/logs/${BASE}-${STAMP}.log"
LOG="$ROOT/$LOG_REL"
INV="$ROOT/.tasks/fleet-inventory.json"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: CLI '$1' not on PATH. Install/login on this machine before dispatch." >&2
    exit 127
  }
}

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

# Ensure inventory exists (best-effort)
if [ ! -f "$INV" ] && [ -x "$ROOT/scripts/fleet-inventory.sh" ]; then
  bash "$ROOT/scripts/fleet-inventory.sh" --json >/dev/null 2>&1 || true
fi

resolve_model() {
  local worker="$1" tier="$2" override="$3"
  if [ -n "$override" ]; then
    echo "$override"
    return
  fi
  python3 - "$worker" "$tier" "$INV" <<'PY'
import json, sys
from pathlib import Path
worker, tier, inv_path = sys.argv[1], sys.argv[2], sys.argv[3]
seat_key = {
    ("agent", "premium"): "cursor.premium",
    ("agent", "economy"): "cursor.economy",
    ("codex", "premium"): "codex.premium",
    ("codex", "economy"): "codex.economy",
    ("agy", "premium"): "agy.premium",
    ("agy", "economy"): "agy.economy",
    ("claude", "premium"): "claude.premium",
    ("claude", "economy"): "claude.economy",
}.get((worker, tier))

fallbacks = {
    ("agent", "premium"): "cursor-grok-4.5-high",
    ("agent", "economy"): "composer-2.5",
    ("codex", "premium"): "gpt-5.6-terra",
    ("codex", "economy"): "gpt-5.6-luna",
    ("agy", "premium"): "gemini-3.1-pro-high",
    ("agy", "economy"): "gemini-3.6-flash-high",
    ("claude", "premium"): "sonnet",
    ("claude", "economy"): "haiku",
}

model = None
fb = None
if seat_key and Path(inv_path).exists():
    doc = json.loads(Path(inv_path).read_text())
    seat = (doc.get("seats") or {}).get(seat_key) or {}
    model = seat.get("model")
    fb = seat.get("fallback")
    # Grok premium → Composer if marked unavailable
    if seat.get("unavailable") and fb:
        model = fb

if not model:
    model = fallbacks.get((worker, tier))

# agent premium: if grok missing from inventory models list, use fallback composer
if worker == "agent" and tier == "premium" and Path(inv_path).exists():
    doc = json.loads(Path(inv_path).read_text())
    models = (doc.get("clis") or {}).get("agent", {}).get("models") or []
    seat = (doc.get("seats") or {}).get("cursor.premium") or {}
    if models and model and "grok" in model.lower():
        if not any("grok" in m.lower() for m in models):
            model = seat.get("fallback") or fallbacks[("agent", "economy")]

print(model or "")
PY
}

MODEL="$(resolve_model "$WORKER" "$TIER" "$MODEL_OVERRIDE")"
[ -n "$MODEL" ] || { echo "ERROR: could not resolve model for $WORKER/$TIER" >&2; exit 1; }

# Cross-repo workers cannot resolve TASK_REL against their workspace — use absolute path.
if [ "$WORKSPACE" = "$ROOT" ]; then
  PROMPT_TASK="$TASK_REL"
else
  PROMPT_TASK="$TASK_ABS"
fi
PROMPT="Read ${PROMPT_TASK} and complete it exactly. Follow AGENTS.md and the skills the task names. Do not touch files outside the allow-list. Append a PROGRESS.md entry in the mission folder. ${EXTRA}"

{
  echo "spawn-worker: worker=$WORKER tier=$TIER model=$MODEL task=$TASK_REL feature=${FEATURE:-} mission=$MISSION log=$LOG_REL repo=$WORKSPACE"
  echo "prompt: $PROMPT"
  echo "----"
} | tee "$LOG"

case "$WORKER" in
  codex)
    need codex
    set +e
    codex exec -C "$WORKSPACE" -s workspace-write -m "$MODEL" \
      -c 'model_reasoning_effort="medium"' \
      "$PROMPT" >>"$LOG" 2>&1
    EC=$?
    set -e
    ;;
  agent)
    need agent
    set +e
    # Cursor Agent CLI: -p print; --force auto-approves; --trust workspace.
    agent -p --force --trust --workspace "$WORKSPACE" --model "$MODEL" "$PROMPT" >>"$LOG" 2>&1
    EC=$?
    set -e
    ;;
  agy)
    need agy
    set +e
    # Antigravity CLI uses a Go flag parser: -p / --print / --prompt TAKES THE PROMPT
    # AS ITS VALUE. The old order
    #     agy -p --dangerously-skip-permissions --model M "$PROMPT"
    # therefore set print="--dangerously-skip-permissions" and DROPPED the real
    # prompt: agy answered a question about the flag, exited 0, and the wrapper
    # reported success having done no work. -p MUST come last, with the prompt as
    # its value. --print-timeout defaults to 5m, too short for multi-file UI tasks.
    AGY_ARGS=(--dangerously-skip-permissions --print-timeout 30m)
    [ -n "$MODEL" ] && AGY_ARGS+=(--model "$MODEL")
    if [ "$WORKSPACE" = "$ROOT" ]; then
      agy "${AGY_ARGS[@]}" -p "$PROMPT" >>"$LOG" 2>&1
      EC=$?
    else
      ( cd "$WORKSPACE" && agy "${AGY_ARGS[@]}" -p "$PROMPT" ) >>"$LOG" 2>&1
      EC=$?
    fi
    set -e
    ;;
  claude)
    need claude
    set +e
    if [ "$WORKSPACE" = "$ROOT" ]; then
      claude -p --model "$MODEL" \
        --allowedTools "Read,Write,Edit,Bash" \
        "$PROMPT" >>"$LOG" 2>&1
      EC=$?
    else
      ( cd "$WORKSPACE" && claude -p --model "$MODEL" \
        --allowedTools "Read,Write,Edit,Bash" \
        "$PROMPT" ) >>"$LOG" 2>&1
      EC=$?
    fi
    set -e
    ;;
  *)
    echo "ERROR: unknown worker '$WORKER' (codex|agent|agy|claude)" >&2
    exit 2
    ;;
esac

echo "----" | tee -a "$LOG"
echo "exit=$EC" | tee -a "$LOG"

ARGV_JSON="$(python3 -c "import json; print(json.dumps(['$WORKER','--tier','$TIER','--model','$MODEL']))")"
REC_ARGS=(
  --role worker --cli "$WORKER" --model "$MODEL" --mission "$MISSION"
  --action "task-${BASE}" --exit "$EC" --log "$LOG_REL" --task "$TASK_REL"
  --tier "$TIER" --argv "$ARGV_JSON" --repo "$WORKSPACE"
)
if [ -n "$FEATURE" ]; then
  REC_ARGS+=(--feature "$FEATURE")
fi
REC="$(bash "$ROOT/scripts/write-receipt.sh" "${REC_ARGS[@]}")"
echo "receipt=$REC"
echo "tail:"; tail -20 "$LOG"
exit "$EC"
