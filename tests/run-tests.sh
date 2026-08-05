#!/usr/bin/env bash
# run-tests.sh — end-to-end test of the harness contracts.
# Creates a throwaway git repo, installs the harness into it, asserts the
# collision rules, then exercises the update path. Run from the kit root.

set -euo pipefail

HARNESS="$(pwd)"
[ -f "$HARNESS/CHANGELOG.md" ] || { echo "Run from the kit root."; exit 1; }

FAIL=0
check() { # check <description> <command...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "  ok   : $desc"
  else echo "  FAIL : $desc"; FAIL=1; fi
}

TARGET="$(mktemp -d)"
trap 'rm -rf "$TARGET"' EXIT

# ---- fixture: a target repo with one pre-existing conflicting file ----
git -C "$TARGET" init -q
git -C "$TARGET" config user.email ci@test && git -C "$TARGET" config user.name CI
echo "# my project readme" > "$TARGET/README.md"
echo "my own claude notes" > "$TARGET/CLAUDE.md"   # will conflict with kit CLAUDE.md
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm baseline

# ---- install ----
echo "== install-harness.sh"
bash scripts/install-harness.sh "$TARGET"

VERSION="$(grep -m1 '^## ' CHANGELOG.md | sed 's/## //;s/ .*//' )"
check "records .harness-version = $VERSION" grep -qx "$VERSION" "$TARGET/.harness-version"
check "AGENTS.md installed (was absent)"     test -f "$TARGET/AGENTS.md"
check "conflict -> CLAUDE.md.harness-new"    test -f "$TARGET/CLAUDE.md.harness-new"
check "existing CLAUDE.md untouched"         grep -q "my own claude notes" "$TARGET/CLAUDE.md"
check "skills copied"                        test -f "$TARGET/.agents/skills/dispatch-worker/SKILL.md"
check "missions ORCHESTRATION installed"     test -f "$TARGET/docs/missions/ORCHESTRATION.md"
check "missions MODEL_ROUTING installed"     test -f "$TARGET/docs/missions/MODEL_ROUTING.md"
check "missions templates installed"         test -f "$TARGET/docs/missions/templates/GOAL.template.md"
# 2.2.4: every template feature must ship the bootstrap field, and the rules string must
# explain it. verify-mission requires a worker receipt unless bootstrap is true, so a
# template that stops carrying the field lets orchestrator-only features go green on
# another feature's receipt with only a WARN.
check "template features all carry bootstrap" sh -c "python3 -c \"import json,sys; d=json.load(open('$TARGET/docs/missions/templates/features.template.json')); sys.exit(0 if all('bootstrap' in f for f in d['features']) else 1)\""
check "template rules explain bootstrap"      sh -c "python3 -c \"import json,sys; d=json.load(open('$TARGET/docs/missions/templates/features.template.json')); sys.exit(0 if 'bootstrap' in d['rules'] else 1)\""
# grep for the flag literal, not the word: the skill's own description already contains
# "bootstrap the loop", so a bare word match would pass without any guidance present.
check "mission-init skill documents bootstrap" sh -c "grep -q '\"bootstrap\": true' '$TARGET/.agents/skills/mission-init/SKILL.md'"
check "stub ORCHESTRATION at old path"       test -f "$TARGET/docs/ORCHESTRATION.md"
check "spawn-worker.sh installed +x"         test -x "$TARGET/scripts/spawn-worker.sh"
check "active-mission.sh installed +x"       test -x "$TARGET/scripts/active-mission.sh"
check "fleet-inventory.sh installed +x"      test -x "$TARGET/scripts/fleet-inventory.sh"
check ".claude/skills is a real directory"   sh -c "[ ! -L '$TARGET/.claude/skills' ] && [ -d '$TARGET/.claude/skills' ]"
check "per-skill link under .claude/skills"  test -L "$TARGET/.claude/skills/dispatch-worker"
check "per-skill link under .cursor/skills"  test -L "$TARGET/.cursor/skills/dispatch-worker"
check "canonical skill is a real directory"  sh -c "[ ! -L '$TARGET/.agents/skills/dispatch-worker' ] && [ -f '$TARGET/.agents/skills/dispatch-worker/SKILL.md' ]"
check "install stayed on a branch"           sh -c "git -C '$TARGET' branch --show-current | grep -q chore/harness-install"
check "install did not commit"               sh -c "[ -n \"\$(git -C '$TARGET' status --porcelain)\" ]"

# ---- mission layout helpers ----
echo "== active-mission / spawn dry checks"
mkdir -p "$TARGET/docs/missions/20990101-fixture/tasks"
printf '%s\n' '---' 'status: in-progress' '---' '# Goal' > "$TARGET/docs/missions/20990101-fixture/GOAL.md"
echo '{}' > "$TARGET/docs/missions/20990101-fixture/features.json"
check "active-mission finds fixture" sh -c "cd '$TARGET' && bash scripts/active-mission.sh | grep -q 20990101-fixture"
check "spawn-worker rejects unknown worker" sh -c "cd '$TARGET' && ! bash scripts/spawn-worker.sh nope docs/missions/20990101-fixture/GOAL.md"
check "fleet-inventory writes json" sh -c "cd '$TARGET' && bash scripts/fleet-inventory.sh --json >/dev/null && test -f .tasks/fleet-inventory.json"
check "inventory binds cursor.premium grok-family" sh -c "cd '$TARGET' && python3 -c \"import json; s=json.load(open('.tasks/fleet-inventory.json'))['seats']['cursor.premium']; assert 'grok' in (s.get('family') or '') or 'grok' in (s.get('model') or '').lower()\""
check "inventory binds brain opus" sh -c "cd '$TARGET' && python3 -c \"import json; assert json.load(open('.tasks/fleet-inventory.json'))['seats']['brain']['family']=='opus'\""
check "inventory has agy seats when CLI present" sh -c "cd '$TARGET' && python3 -c \"import json; d=json.load(open('.tasks/fleet-inventory.json'));
import shutil; 
assert 'agy.premium' in d['seats'] and 'agy.economy' in d['seats']\""
check "spawn-brain.sh installed +x" test -x "$TARGET/scripts/spawn-brain.sh"
check "verify-mission.sh installed +x" test -x "$TARGET/scripts/verify-mission.sh"
# receipt greenlight
echo "== verify-mission receipts"
FEAT="$TARGET/docs/missions/20990101-fixture"
printf '%s\n' '{"goal":"t","features":[{"id":"F001","description":"Mission folder active","bootstrap":true,"steps":[],"passes":true,"priority":1},{"id":"F002","description":"Real work mentions mission files in prose only","steps":[],"passes":true,"priority":2}]}' > "$FEAT/features.json"
check "verify fails without receipts" sh -c "cd '$TARGET' && ! bash scripts/verify-mission.sh docs/missions/20990101-fixture"
( cd "$TARGET" && bash scripts/write-receipt.sh --role brain --cli claude --model opus --mission docs/missions/20990101-fixture --action mission-init --exit 0 --log .tasks/logs/x.log --argv '["claude"]' >/dev/null )
( cd "$TARGET" && bash scripts/write-receipt.sh --role worker --cli agent --model composer-2.5 --mission docs/missions/20990101-fixture --action task-T-001 --exit 0 --log .tasks/logs/y.log --feature F002 --tier economy --argv '["agent"]' >/dev/null )
check "verify passes with brain+worker receipts" sh -c "cd '$TARGET' && bash scripts/verify-mission.sh docs/missions/20990101-fixture"
check "spawn-worker --repo rejects missing path" sh -c "cd '$TARGET' && bash scripts/spawn-worker.sh agent docs/missions/20990101-fixture/GOAL.md --repo /nope/does/not/exist; test \$? -eq 1"

# ---- agy prompt-flag regression (2.2.3) ----
# Antigravity's CLI uses a Go flag parser: -p/--print/--prompt takes the PROMPT AS
# ITS VALUE. `agy -p --dangerously-skip-permissions ... "$PROMPT"` set
# print="--dangerously-skip-permissions", dropped the real prompt, and exited 0 — so
# the wrapper reported success having done no work. -p must come last.
echo "== agy prompt-flag order"
STUBBIN="$TARGET/.stubbin"; mkdir -p "$STUBBIN"
STUB_OUT="$TARGET/.agy-args"
# shellcheck disable=SC2016  # printf template: $ must stay literal
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" > "%s"\nexit 0\n' "$STUB_OUT" > "$STUBBIN/agy"
chmod +x "$STUBBIN/agy"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" \
    bash scripts/spawn-worker.sh agy docs/missions/20990101-fixture/GOAL.md --tier premium --effort xhigh ) >/dev/null 2>&1 || true
check "agy receives the real prompt as the value of -p" \
  sh -c "grep -q -- '-p Read ' '$STUB_OUT'"
check "agy -p is not fed the permissions flag" \
  sh -c "! grep -q -- '-p --dangerously-skip-permissions' '$STUB_OUT'"
check "agy gets a print-timeout longer than the 5m default" \
  sh -c "grep -q -- '--print-timeout' '$STUB_OUT'"

# ---- claude prompt-position regression (2.2.5) ----
# claude's --allowedTools is VARIADIC: it keeps consuming following args as tool names,
# so a prompt placed after it is swallowed and claude exits with "Input must be provided
# either through stdin or as a prompt argument". The prompt must precede the flags.
echo "== claude prompt position"
CLAUDE_OUT="$TARGET/.claude-args"
# shellcheck disable=SC2016  # printf template: $ must stay literal
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" > "%s"\nexit 0\n' "$CLAUDE_OUT" > "$STUBBIN/claude"
chmod +x "$STUBBIN/claude"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" \
    bash scripts/spawn-worker.sh claude docs/missions/20990101-fixture/GOAL.md --tier premium --effort xhigh ) >/dev/null 2>&1 || true
check "claude receives the prompt immediately after -p" \
  sh -c "grep -q -- '-p Read ' '$CLAUDE_OUT'"
check "claude prompt is not placed after --allowedTools" \
  sh -c "! grep -qE -- '--allowedTools [^ ]+ Read ' '$CLAUDE_OUT'"

# ---- codex prompt/argument and stdin regressions ----
# Keep this stub's stdin read: codex waits for additional input unless its stdin is
# explicitly closed by spawn-worker.sh. The argument file is one line per argv entry so
# the exact flag/value boundaries and final prompt position are asserted, not just $*.
echo "== codex prompt, effort, and stdin"
CODEX_OUT="$TARGET/.codex-args"
CODEX_EOF_MARK="$TARGET/.codex-eof"
CODEX_STUB_PID="$TARGET/.codex-stub-pid"
# shellcheck disable=SC2016  # printf template: $ must stay literal
printf '#!/usr/bin/env bash\nset -euo pipefail\nprintf "%%s\\n" "$$" > "%s"\nwhile IFS= read -r _codex_stdin_line; do :; done\ntouch "%s"\nprintf "%%s\\n" "$(basename "$0")" "$@" > "%s"\nexit 0\n' "$CODEX_STUB_PID" "$CODEX_EOF_MARK" "$CODEX_OUT" > "$STUBBIN/codex"
chmod +x "$STUBBIN/codex"
CODEX_MODEL="codex-test-model"
CODEX_PROMPT="Read docs/missions/20990101-fixture/GOAL.md and complete it exactly. Follow AGENTS.md and the skills the task names. Do not touch files outside the allow-list. Append a PROGRESS.md entry in the mission folder. "
CODEX_EXPECTED="$TARGET/.codex-expected"
printf '%s\n' codex exec -C "$TARGET" -s workspace-write -m "$CODEX_MODEL" \
  '-c' 'model_reasoning_effort="medium"' "$CODEX_PROMPT" > "$CODEX_EXPECTED"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" \
    bash scripts/spawn-worker.sh codex docs/missions/20990101-fixture/GOAL.md \
      --tier economy --model "$CODEX_MODEL" ) >/dev/null 2>&1 || true
check "codex receives the exact invocation with medium default" \
  cmp -s "$CODEX_EXPECTED" "$CODEX_OUT"

CODEX_EXPECTED_XHIGH="$TARGET/.codex-expected-xhigh"
printf '%s\n' codex exec -C "$TARGET" -s workspace-write -m "$CODEX_MODEL" \
  '-c' 'model_reasoning_effort="xhigh"' "$CODEX_PROMPT" > "$CODEX_EXPECTED_XHIGH"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" \
    bash scripts/spawn-worker.sh codex docs/missions/20990101-fixture/GOAL.md \
      --tier economy --model "$CODEX_MODEL" --effort xhigh ) >/dev/null 2>&1 || true
check "codex receives --effort xhigh" \
  cmp -s "$CODEX_EXPECTED_XHIGH" "$CODEX_OUT"

# Hold the wrapper's stdin open through a FIFO. The fixed codex branch redirects the
# CLI's stdin to /dev/null and exits; the broken branch leaves the EOF-reading stub blocked.
CODEX_FIFO="$TARGET/.codex-stdin"
rm -f "$CODEX_EOF_MARK" "$CODEX_STUB_PID"
mkfifo "$CODEX_FIFO"
exec 9<>"$CODEX_FIFO"
set +e
( cd "$TARGET" && PATH="$STUBBIN:$PATH" \
    bash scripts/spawn-worker.sh codex docs/missions/20990101-fixture/GOAL.md \
      --tier economy --model "$CODEX_MODEL" ) <"$CODEX_FIFO" >/dev/null 2>&1 &
CODEX_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -f "$CODEX_EOF_MARK" ] && break
  sleep 0.1
done
if [ -f "$CODEX_EOF_MARK" ]; then
  wait "$CODEX_PID"
  CODEX_STDIN_EOF=$?
else
  CODEX_STUB_PID_VALUE=""
  if [ -f "$CODEX_STUB_PID" ]; then
    CODEX_STUB_PID_VALUE="$(<"$CODEX_STUB_PID")"
  fi
  if [ -n "$CODEX_STUB_PID_VALUE" ]; then kill "$CODEX_STUB_PID_VALUE" 2>/dev/null || true; fi
  kill "$CODEX_PID" 2>/dev/null || true
  exec 9>&-
  wait "$CODEX_PID" 2>/dev/null || true
  CODEX_STDIN_EOF=1
fi
set -e
exec 9>&-
rm -f "$CODEX_FIFO" "$CODEX_STUB_PID"
check "codex stdin is closed so EOF-reading stub returns" test "$CODEX_STDIN_EOF" -eq 0

# ---- agent prompt/argument regression ----
# Agent's -p is boolean. Assert the full invocation and final prompt, including every
# value-taking option, so a simplified smoke test cannot pass a swallowed prompt.
echo "== agent prompt and argument order"
AGENT_OUT="$TARGET/.agent-args"
# shellcheck disable=SC2016  # printf template: $ must stay literal
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$(basename "$0")" "$@" > "%s"\nexit 0\n' "$AGENT_OUT" > "$STUBBIN/agent"
chmod +x "$STUBBIN/agent"
AGENT_MODEL="agent-test-model"
AGENT_EXPECTED="$TARGET/.agent-expected"
printf '%s\n' agent -p --force --trust --workspace "$TARGET" --model "$AGENT_MODEL" "$CODEX_PROMPT" > "$AGENT_EXPECTED"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" \
    bash scripts/spawn-worker.sh agent docs/missions/20990101-fixture/GOAL.md \
      --tier economy --model "$AGENT_MODEL" --effort xhigh ) >/dev/null 2>&1 || true
check "agent receives the exact invocation with intact final prompt" \
  cmp -s "$AGENT_EXPECTED" "$AGENT_OUT"

# ---- legacy parent-symlink must be migrated safely ----
echo "== sync-skills parent-symlink migration"
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "harness install"
rm -rf "$TARGET/.claude/skills"
ln -s ../.agents/skills "$TARGET/.claude/skills"
( cd "$TARGET" && bash scripts/sync-skills.sh )
check "parent symlink replaced" sh -c "[ ! -L '$TARGET/.claude/skills' ]"
check "canonical intact after sync" test -f "$TARGET/.agents/skills/dispatch-worker/SKILL.md"
check "canonical not a symlink" sh -c "[ ! -L '$TARGET/.agents/skills/dispatch-worker' ]"

# ---- re-install must refuse ----
check "second install refused" sh -c "! bash scripts/install-harness.sh '$TARGET'"

# ---- update path must preserve instance mission folders ----
echo "== update-harness.sh"
echo "keep-me" > "$TARGET/docs/missions/20990101-fixture/KEEP.md"
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "fixture mission marker"
bash scripts/update-harness.sh "$TARGET"
check "update stayed on version branch" sh -c "git -C '$TARGET' branch --show-current | grep -q 'chore/harness-'"
check "kit skill still present after update" test -f "$TARGET/.agents/skills/mission-init/SKILL.md"
check "MODEL_ROUTING under docs/missions" test -f "$TARGET/docs/missions/MODEL_ROUTING.md"
check "instance mission folder preserved" test -f "$TARGET/docs/missions/20990101-fixture/KEEP.md"
check "instance GOAL preserved" test -f "$TARGET/docs/missions/20990101-fixture/GOAL.md"

# ---- dirty-tree refusals ----
echo dirty > "$TARGET/dirty.txt"
check "update refuses dirty tree" sh -c "! bash scripts/update-harness.sh '$TARGET'"

echo ""
if [ "$FAIL" -eq 1 ]; then echo "TESTS FAILED"; exit 1; else echo "ALL TESTS PASSED"; fi
