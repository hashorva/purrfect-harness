#!/usr/bin/env bash
# drive-cli.sh — drive a CLI inside an isolated tmux session using drive_cli_rules.py (T-066).
# Usage: scripts/drive-cli.sh <workspace> -- <cli argv...>
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
RULES_PY="$ROOT/scripts/drive_cli_rules.py"

usage() {
  echo "Usage: scripts/drive-cli.sh <workspace> -- <cli argv...>" >&2
}

if ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux is required but not installed" >&2
  exit 2
fi

if [ "$#" -lt 1 ]; then
  usage
  exit 2
fi

WORKSPACE_ARG="$1"
shift
if [ "$#" -lt 1 ] || [ "$1" != "--" ]; then
  usage
  exit 2
fi
shift
if [ "$#" -lt 1 ]; then
  usage
  exit 2
fi
CLI_ARGS=("$@")

if [ ! -d "$WORKSPACE_ARG" ]; then
  echo "ERROR: workspace is not an existing directory: $WORKSPACE_ARG" >&2
  exit 2
fi

WORKSPACE="$(cd "$WORKSPACE_ARG" && pwd -P)"

STALL_SECS="${DRIVE_CLI_STALL_SECS:-90}"
if ! [[ "$STALL_SECS" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "ERROR: DRIVE_CLI_STALL_SECS must be a positive number" >&2
  exit 2
fi
if ! awk -v s="$STALL_SECS" 'BEGIN { exit (s > 0) ? 0 : 1 }'; then
  echo "ERROR: DRIVE_CLI_STALL_SECS must be a positive number" >&2
  exit 2
fi

OUT_ROOT="${DRIVE_CLI_OUT_ROOT:-.tasks/drive}"
TRANSCRIPT_DIR="$OUT_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$TRANSCRIPT_DIR"

TMUX_SOCKET="drive-cli-$$-$(date -u +%s)"
SESSION="drive-cli"
ANSWERED_TEXT=""
ANSWERED_DIGEST=""
LAST_PANE=""
LAST_CHANGE_EPOCH="$(date +%s)"

write_command_json() {
  python3 - "$WORKSPACE" "${CLI_ARGS[@]}" <<'PY' >"$TRANSCRIPT_DIR/command.json"
import json, sys
doc = {"workspace": sys.argv[1], "argv": sys.argv[2:]}
print(json.dumps(doc, indent=2))
PY
}

write_pane_log() {
  local pane_text="$1"
  printf '%s' "$pane_text" >"$TRANSCRIPT_DIR/pane.log"
}

write_result_json() {
  local exit_code="$1" reason="$2" rule_id="${3:-null}"
  python3 - "$exit_code" "$reason" "$rule_id" <<'PY' >"$TRANSCRIPT_DIR/result.json"
import json, sys
rule_id = sys.argv[3]
if rule_id == "null":
    rule_id = None
doc = {"exit_code": int(sys.argv[1]), "reason": sys.argv[2], "rule_id": rule_id}
print(json.dumps(doc, indent=2))
PY
}

append_event() {
  local line="$1"
  printf '%s\n' "$line" >>"$TRANSCRIPT_DIR/events.jsonl"
}

# shellcheck disable=SC2317,SC2329
cleanup() {
  local code=$?
  trap - EXIT
  set +e
  tmux -L "$TMUX_SOCKET" kill-server 2>/dev/null || true
  exit "$code"
}
trap cleanup EXIT

write_command_json
touch "$TRANSCRIPT_DIR/events.jsonl"

tmux -L "$TMUX_SOCKET" -f /dev/null new-session -d -x 220 -s "$SESSION" -c "$WORKSPACE" -- "${CLI_ARGS[@]}"
tmux -L "$TMUX_SOCKET" set-option -t "$SESSION" remain-on-exit on 2>/dev/null || \
  tmux -L "$TMUX_SOCKET" set-option -t "$SESSION":0 remain-on-exit on

stop_session() {
  local exit_code="$1" reason="$2" rule_id="${3:-null}" pane_text="$4"
  write_pane_log "$pane_text"
  write_result_json "$exit_code" "$reason" "$rule_id"
  printf '%s' "$pane_text"
  printf '%s' "$pane_text" >&2
  tmux -L "$TMUX_SOCKET" kill-server 2>/dev/null || true
  trap - EXIT
  exit "$exit_code"
}

while true; do
  PANE_FULL="$(tmux -L "$TMUX_SOCKET" capture-pane -p -J -S - -t "$SESSION" 2>/dev/null || true)"
  if [ "$PANE_FULL" != "$LAST_PANE" ]; then
    LAST_PANE="$PANE_FULL"
    LAST_CHANGE_EPOCH="$(date +%s)"
    write_pane_log "$PANE_FULL"
  fi

  NOW="$(date +%s)"
  if awk -v elapsed="$((NOW - LAST_CHANGE_EPOCH))" -v stall="$STALL_SECS" \
    'BEGIN { exit (elapsed >= stall) ? 0 : 1 }'; then
    stop_session 4 stall null "$PANE_FULL"
  fi

  CURRENT_DIGEST="$(PANE_TEXT="$PANE_FULL" python3 -c 'import os,sys; sys.path.insert(0, sys.argv[1]); import drive_cli_rules as R; print(R.pane_digest(os.environ["PANE_TEXT"]))' "$ROOT/scripts")"
  if [ -n "$ANSWERED_DIGEST" ] && [ "$CURRENT_DIGEST" = "$ANSWERED_DIGEST" ]; then
    DECISION_JSON='{"decision":"wait","category":"pane_unchanged","rule_id":null,"answer":null,"exit_code":null}'
  else
    DECISION_JSON="$(PANE_TEXT="$PANE_FULL" ANSWERED_TEXT="$ANSWERED_TEXT" python3 -c 'import os,sys,json; sys.path.insert(0, os.path.dirname(sys.argv[1])); import drive_cli_rules as R; print(json.dumps(R.classify_window(os.environ["PANE_TEXT"], sys.argv[2], os.environ.get("ANSWERED_TEXT") or None, R.load_rules())))' "$RULES_PY" "$WORKSPACE" 2>/dev/null)" || {
    echo "ERROR: drive_cli_rules.py failed" >&2
    stop_session 2 rules_error null "$PANE_FULL"
    }
  fi

  DECISION="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["decision"])' <<<"$DECISION_JSON")"
  CATEGORY="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("category") or "")' <<<"$DECISION_JSON")"
  RULE_ID="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("rule_id") or "")' <<<"$DECISION_JSON")"

  if [ "$DECISION" = "stop" ]; then
    RID="${RULE_ID:-null}"
    stop_session 3 "$CATEGORY" "$RID" "$PANE_FULL"
  fi

  if [ "$DECISION" = "answer" ]; then
    python3 - "$TMUX_SOCKET" "$SESSION" "$DECISION_JSON" <<'PY'
import json
import subprocess
import sys

decision = json.loads(sys.argv[3])
answer = decision["answer"]
socket, session = sys.argv[1], sys.argv[2]
tmux = ["tmux", "-L", socket, "send-keys", "-t", session]
if answer == "y\n":
    subprocess.check_call(tmux + ["y", "Enter"])
else:
    body = answer.rstrip("\n")
    subprocess.check_call(tmux + ["-l", body])
    if answer.endswith("\n"):
        subprocess.check_call(tmux + ["Enter"])
PY
    append_event "$DECISION_JSON"
    ANSWERED_TEXT="$PANE_FULL"
    ANSWERED_DIGEST="$CURRENT_DIGEST"
    LAST_CHANGE_EPOCH="$(date +%s)"
  fi

  PANE_DEAD="$(tmux -L "$TMUX_SOCKET" display-message -p -t "$SESSION" '#{pane_dead}' 2>/dev/null || echo 0)"
  if [ "$PANE_DEAD" = "1" ]; then
    PANE_FULL="$(tmux -L "$TMUX_SOCKET" capture-pane -p -J -S - -t "$SESSION" 2>/dev/null || true)"
    FINAL_JSON="$(PANE_TEXT="$PANE_FULL" ANSWERED_TEXT="$ANSWERED_TEXT" python3 -c 'import os,sys,json; sys.path.insert(0, os.path.dirname(sys.argv[1])); import drive_cli_rules as R; print(json.dumps(R.classify_window(os.environ["PANE_TEXT"], sys.argv[2], os.environ.get("ANSWERED_TEXT") or None, R.load_rules())))' "$RULES_PY" "$WORKSPACE")"
    FINAL_DECISION="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["decision"])' <<<"$FINAL_JSON")"
    if [ "$FINAL_DECISION" = "stop" ]; then
      CATEGORY="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("category") or "")' <<<"$FINAL_JSON")"
      RULE_ID="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("rule_id") or "")' <<<"$FINAL_JSON")"
      RID="${RULE_ID:-null}"
      stop_session 3 "$CATEGORY" "$RID" "$PANE_FULL"
    fi
    DEAD_STATUS="$(tmux -L "$TMUX_SOCKET" display-message -p -t "$SESSION" '#{pane_dead_status}' 2>/dev/null || echo 0)"
    write_pane_log "$PANE_FULL"
    write_result_json "$DEAD_STATUS" completed null
    printf '%s' "$PANE_FULL"
    printf '%s' "$PANE_FULL" >&2
    trap - EXIT
    tmux -L "$TMUX_SOCKET" kill-server 2>/dev/null || true
    exit "$DEAD_STATUS"
  fi

  sleep 0.1
done
