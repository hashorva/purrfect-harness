#!/usr/bin/env bash
# spawn-worker.sh — run a WORKER_TASK via a real local CLI agent (Mac Mini / studio).
# Usage (from the consuming repo root):
#   bash scripts/spawn-worker.sh <codex|agent|agy|claude> <path-to-task.md> [extra prompt...]
#
# Logs to .tasks/logs/<task-basename>.log and exits with the worker's exit code.
# Never streams the full transcript to the caller — orchestrators read exit + tail.
set -euo pipefail

WORKER="${1:?Usage: spawn-worker.sh <codex|agent|agy|claude> <task.md>}"
TASK="${2:?Usage: spawn-worker.sh <codex|agent|agy|claude> <task.md>}"
shift 2 || true
EXTRA="${*:-}"

ROOT="$(pwd)"
[ -f "$TASK" ] || { echo "ERROR: task file not found: $TASK" >&2; exit 1; }
TASK_ABS="$(cd "$(dirname "$TASK")" && pwd)/$(basename "$TASK")"
TASK_REL="${TASK_ABS#"$ROOT"/}"
BASE="$(basename "$TASK" .md)"

mkdir -p "$ROOT/.tasks/logs"
LOG="$ROOT/.tasks/logs/${BASE}.log"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: CLI '$1' not on PATH. Install/login on this machine before dispatch." >&2
    exit 127
  }
}

PROMPT="Read ${TASK_REL} and complete it exactly. Follow AGENTS.md and the skills the task names. Do not touch files outside the allow-list. Append a PROGRESS.md entry in the mission folder. ${EXTRA}"

echo "spawn-worker: worker=$WORKER task=$TASK_REL log=$LOG" | tee "$LOG"
echo "prompt: $PROMPT" >>"$LOG"
echo "----" >>"$LOG"

case "$WORKER" in
  codex)
    need codex
    # Prefer --profile worker when ~/.codex/config.toml defines it; else inline economy pins.
    if codex exec --help 2>&1 | grep -q -- '--profile'; then
      set +e
      if grep -q '\[profiles\.worker\]' "${CODEX_HOME:-$HOME/.codex}/config.toml" 2>/dev/null \
        || [ -f "${CODEX_HOME:-$HOME/.codex}/worker.config.toml" ]; then
        codex exec --profile worker -C "$ROOT" -s workspace-write "$PROMPT" >>"$LOG" 2>&1
        EC=$?
      else
        codex exec -C "$ROOT" -s workspace-write \
          -c 'model_reasoning_effort="medium"' \
          "$PROMPT" >>"$LOG" 2>&1
        EC=$?
      fi
      set -e
    else
      echo "ERROR: unexpected codex CLI (no exec --profile). Re-run: codex exec --help" >&2
      exit 127
    fi
    ;;
  agent)
    need agent
    set +e
    # Cursor Agent CLI: -p print mode; --force/--yolo auto-approves tools; --trust workspace.
    agent -p --force --trust --workspace "$ROOT" --model composer "$PROMPT" >>"$LOG" 2>&1
    EC=$?
    set -e
    ;;
  agy)
    need agy
    set +e
    # Antigravity: -p print; auto-approve for unattended workers.
    agy -p --dangerously-skip-permissions "$PROMPT" >>"$LOG" 2>&1
    EC=$?
    set -e
    ;;
  claude)
    need claude
    set +e
    claude -p --model haiku \
      --allowedTools "Read,Write,Edit,Bash" \
      "$PROMPT" >>"$LOG" 2>&1
    EC=$?
    set -e
    ;;
  *)
    echo "ERROR: unknown worker '$WORKER' (codex|agent|agy|claude)" >&2
    exit 2
    ;;
esac

echo "----" | tee -a "$LOG"
echo "exit=$EC" | tee -a "$LOG"
echo "tail:"; tail -20 "$LOG"
exit "$EC"
