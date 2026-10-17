#!/usr/bin/env bash
# Integration tests for scripts/drive-cli.sh against a fake shell-script CLI (T-066).
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
unset DRIVE_CLI_STALL_SECS

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DRIVE_CLI="$ROOT/scripts/drive-cli.sh"

echo "== drive-cli match_pane sanity (pure Python)"
python3 - <<'PY'
import sys
sys.path.insert(0, "scripts")
import drive_cli_rules as R

ws = "/tmp/ws-exact"
rules = R.load_rules()
ok = R.match_pane(f"Do you trust the files in this folder?\n{ws}\n[y/n] ", ws, rules)
assert ok["decision"] == "answer" and ok["rule_id"] == "folder_trust", ok
hostile = R.match_pane(f"Do you trust the files in this folder?\n{ws}\u200b-evil\n[y/n] ", ws, rules)
assert hostile["decision"] == "stop" and hostile["category"] == "unknown_prompt" and hostile["answer"] is None, hostile
telemetry = R.match_pane(f"Do you trust the files in this folder? {ws}\nEnable telemetry uploads? [y/n]", ws, rules)
assert telemetry["decision"] == "stop" and telemetry["category"] == "unknown_prompt" and telemetry["answer"] is None, telemetry
unk = R.match_pane("Enable telemetry uploads? [y/n]", ws, rules)
assert unk["decision"] == "stop" and unk["exit_code"] == 3, unk
answered = "Do you trust this folder /tmp/ws-exact [y/n]"
scrolled = R.classify_window("Allow git push origin main? [y/n]\n" + answered, ws, answered, rules)
assert scrolled["decision"] == "stop" and scrolled["exit_code"] == 3 and scrolled["answer"] is None, scrolled
print("ok")
PY

if ! command -v tmux >/dev/null 2>&1; then
  echo "SKIP: tmux not installed; skipping tmux integration tests"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/workspace"
WS="$(cd "$TMP/workspace" && pwd -P)"
OUT_ROOT="$TMP/drive-out"
mkdir -p "$OUT_ROOT"
export DRIVE_CLI_OUT_ROOT="$OUT_ROOT"

assert_transcript() {
  local count
  count="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$count" -lt 1 ]; then
    echo "FAIL: expected transcript directory under $OUT_ROOT" >&2
    exit 1
  fi
  local dir
  dir="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  for f in command.json pane.log events.jsonl result.json; do
    if [ ! -f "$dir/$f" ]; then
      echo "FAIL: missing transcript file $dir/$f" >&2
      exit 1
    fi
  done
}

run_drive() {
  # run_drive <expected_status> <grep_pattern> -- <fake-cli-path> [args...]
  local expected_status="$1"
  local pattern="$2"
  shift 2
  if [ "$1" != "--" ]; then
    echo "FAIL: run_drive internal usage" >&2
    exit 1
  fi
  shift
  local fake="$1"
  shift
  set +e
  local combined
  combined="$(bash "$DRIVE_CLI" "$WS" -- "$fake" "$@" 2>&1)"
  local status=$?
  set -e
  if [ "$status" -ne "$expected_status" ]; then
    echo "FAIL: expected exit $expected_status got $status; output:" >&2
    echo "$combined" >&2
    exit 1
  fi
  if [ -n "$pattern" ] && ! printf '%s' "$combined" | grep -Fq "$pattern"; then
    echo "FAIL: expected output to contain: $pattern" >&2
    echo "$combined" >&2
    exit 1
  fi
  printf '%s' "$combined"
}

echo "== folder trust for exact workspace (answer y, exit 0)"
cat >"$TMP/fake-trust-ok.sh" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
ws="$1"
printf 'Do you trust the files in this folder?\n%s\n[y/n] ' "$ws"
read -r _
echo "trusted and done"
exit 0
FAKE
chmod +x "$TMP/fake-trust-ok.sh"
find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
run_drive 0 "trusted and done" -- "$TMP/fake-trust-ok.sh" "$WS"
assert_transcript
events="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/events.jsonl"
if [ ! -s "$events" ]; then
  echo "FAIL: expected answer event in events.jsonl" >&2
  exit 1
fi

echo "== folder trust for different path (stop, exit 3)"
cat >"$TMP/fake-trust-bad.sh" <<'FAKE'
#!/usr/bin/env bash
bad="$1"
printf 'Do you trust the files in this folder?\n%s\n[y/n] ' "$bad"
read -r _
exit 0
FAKE
chmod +x "$TMP/fake-trust-bad.sh"
find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
run_drive 3 "$WS-other" -- "$TMP/fake-trust-bad.sh" "${WS}-other"

echo "== multi-step: answered trust in scrollback must not re-fire"
cat >"$TMP/fake-trust-then-done.sh" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
ws="$1"
printf 'Do you trust the files in this folder?\n%s\n[y/n] ' "$ws"
read -r _
echo "phase-two-output"
sleep 0.2
echo "all-finished"
exit 0
FAKE
chmod +x "$TMP/fake-trust-then-done.sh"
find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
run_drive 0 "all-finished" -- "$TMP/fake-trust-then-done.sh" "$WS"

echo "== NEVER categories (stop, exit 3, no y sent)"
declare -a NEVER_CASES=(
  "write_outside_workspace|Allow write to /etc/hosts? [y/n]"
  "delete_ignored_files|Run git clean -fdX to delete ignored files? [y/n]"
  "push_network_install|Allow git push origin main? [y/n]"
  "git_history_changes|Run git reset --hard HEAD~1? [y/n]"
  "credits_payment|Purchase \$20 API credits now? [y/n]"
)
cat >"$TMP/fake-never.sh" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$1"
read -r _
exit 0
FAKE
chmod +x "$TMP/fake-never.sh"
for entry in "${NEVER_CASES[@]}"; do
  rid="${entry%%|*}"
  prompt="${entry#*|}"
  find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  out="$(run_drive 3 "$prompt" -- "$TMP/fake-never.sh" "$prompt")"
  if printf '%s' "$out" | grep -q '^y$'; then
    echo "FAIL: drive-cli sent y for never rule $rid" >&2
    exit 1
  fi
  result="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/result.json"
  python3 - "$result" "$rid" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
rid = sys.argv[2]
if doc.get("rule_id") != rid:
    raise SystemExit(f"expected rule_id {rid}, got {doc.get('rule_id')}")
PY
done

echo "== unknown prompt (stop, exit 3)"
cat >"$TMP/fake-unknown.sh" <<'FAKE'
#!/usr/bin/env bash
printf 'Enable telemetry uploads? [y/n]\n'
read -r _
exit 0
FAKE
chmod +x "$TMP/fake-unknown.sh"
find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
run_drive 3 "Enable telemetry uploads?" -- "$TMP/fake-unknown.sh"

sentinel="$TMP/read-sentinel"

assert_no_y_answer_event() {
  local events_file="$1"
  if grep -Fq '"answer": "y\n"' "$events_file" 2>/dev/null; then
    echo "FAIL: events.jsonl contains answer y for a never/unknown prompt" >&2
    exit 1
  fi
}

run_sentinel_never_case() {
  local expected_rid="$1"
  local prompt="$2"
  rm -f "$sentinel"
  find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cat >"$TMP/fake-sentinel-never.sh" <<FAKE
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "\$1"
if read -t 2 -r _; then
  echo touched > "\$2"
fi
exit 0
FAKE
  chmod +x "$TMP/fake-sentinel-never.sh"
  run_drive 3 "$prompt" -- "$TMP/fake-sentinel-never.sh" "$prompt" "$sentinel"
  if [ -e "$sentinel" ]; then
    echo "FAIL: sentinel exists for never case $expected_rid" >&2
    exit 1
  fi
  local result
  result="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/result.json"
  python3 - "$result" "$expected_rid" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
rid = sys.argv[2]
if doc.get("rule_id") != rid:
    raise SystemExit(f"expected rule_id {rid}, got {doc.get('rule_id')}")
PY
  local events
  events="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/events.jsonl"
  assert_no_y_answer_event "$events"
}

echo "== never prompts must not receive y (sentinel)"
run_sentinel_never_case push_network_install "Allow git push origin main? [y/n]"
run_sentinel_never_case delete_ignored_files "Run git clean -fdX to delete ignored files? [y/n]"
run_sentinel_never_case push_network_install "Allow npm install the package from the network? [y/n]"
run_sentinel_never_case credits_payment "Purchase \$20 API credits now? [y/n]"

echo "== post-answer push must stop before second read"
rm -f "$sentinel"
find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cat >"$TMP/fake-trust-then-push.sh" <<FAKE
#!/usr/bin/env bash
set -euo pipefail
ws="\$1"
sentinel="\$2"
printf 'Do you trust the files in this folder?\n%s\n[y/n] ' "\$ws"
read -r _
printf 'Allow git push origin main? [y/n]\n'
if read -t 2 -r _; then
  echo touched > "\$sentinel"
fi
exit 0
FAKE
chmod +x "$TMP/fake-trust-then-push.sh"
run_drive 3 "Allow git push origin main? [y/n]" -- "$TMP/fake-trust-then-push.sh" "$WS" "$sentinel"
if [ -e "$sentinel" ]; then
  echo "FAIL: sentinel exists after post-answer push" >&2
  exit 1
fi
result="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/result.json"
python3 - "$result" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
if doc.get("rule_id") != "push_network_install":
    raise SystemExit(f"expected push_network_install, got {doc.get('rule_id')}")
PY
events="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/events.jsonl"
if ! grep -Fq '"rule_id": "folder_trust"' "$events"; then
  echo "FAIL: expected folder_trust answer event" >&2
  exit 1
fi
if ! grep -Fq '"answer": "y\n"' "$events"; then
  echo "FAIL: expected trust y answer event" >&2
  exit 1
fi

echo "== hostile zero-width workspace path must not receive y"
rm -f "$sentinel"
find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
echo "hostile-zwsp-path"
cat >"$TMP/fake-hostile-zwsp.py" <<'PY'
#!/usr/bin/env bash
set -euo pipefail
ws="$1"
sentinel="$2"
python3 - "$ws" <<'PYTHON'
import sys
ws = sys.argv[1]
print("Do you trust the files in this folder?")
print("%s\u200b-evil" % ws)
print("[y/n] ", end="", flush=True)
PYTHON
if read -t 2 -r _; then
  echo touched > "$sentinel"
fi
PY
chmod +x "$TMP/fake-hostile-zwsp.py"
run_drive 3 "[y/n]" -- "$TMP/fake-hostile-zwsp.py" "$WS" "$sentinel"
if [ -e "$sentinel" ]; then
  echo "FAIL: sentinel exists for hostile zero-width path" >&2
  exit 1
fi
result="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/result.json"
events="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/events.jsonl"
python3 - "$result" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
assert doc.get("reason") == "unknown_prompt", doc
PY
assert_no_y_answer_event "$events"

echo "== hostile telemetry question must not receive y"
rm -f "$sentinel"
find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
echo "hostile-telemetry"
cat >"$TMP/fake-hostile-telemetry.py" <<'PY'
#!/usr/bin/env bash
set -euo pipefail
ws="$1"
sentinel="$2"
python3 - "$ws" <<'PYTHON'
import sys
ws = sys.argv[1]
print("Do you trust the files in this folder? %s" % ws)
print("Enable telemetry uploads? [y/n]", flush=True)
PYTHON
if read -t 2 -r _; then
  echo touched > "$sentinel"
fi
PY
chmod +x "$TMP/fake-hostile-telemetry.py"
run_drive 3 "Enable telemetry uploads?" -- "$TMP/fake-hostile-telemetry.py" "$WS" "$sentinel"
if [ -e "$sentinel" ]; then
  echo "FAIL: sentinel exists for hostile telemetry prompt" >&2
  exit 1
fi
result="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/result.json"
events="$(find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | head -n 1)/events.jsonl"
python3 - "$result" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
assert doc.get("reason") == "unknown_prompt", doc
PY
assert_no_y_answer_event "$events"

echo "== stall with no pane change (exit 4)"
cat >"$TMP/fake-stall.sh" <<'FAKE'
#!/usr/bin/env bash
printf 'frozen pane line\n'
sleep 120
FAKE
chmod +x "$TMP/fake-stall.sh"
find "$OUT_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
export DRIVE_CLI_STALL_SECS=1
run_drive 4 "frozen pane line" -- "$TMP/fake-stall.sh"
unset DRIVE_CLI_STALL_SECS

echo "ALL drive-cli tmux tests passed"
