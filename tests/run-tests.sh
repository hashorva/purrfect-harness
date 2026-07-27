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
check "stub ORCHESTRATION at old path"       test -f "$TARGET/docs/ORCHESTRATION.md"
check "spawn-worker.sh installed +x"         test -x "$TARGET/scripts/spawn-worker.sh"
check "active-mission.sh installed +x"       test -x "$TARGET/scripts/active-mission.sh"
check ".claude/skills symlink"               test -L "$TARGET/.claude/skills"
check ".cursor/skills symlink"               test -L "$TARGET/.cursor/skills"
check "install stayed on a branch"           sh -c "git -C '$TARGET' branch --show-current | grep -q chore/harness-install"
check "install did not commit"               sh -c "[ -n \"\$(git -C '$TARGET' status --porcelain)\" ]"

# ---- mission layout helpers ----
echo "== active-mission / spawn dry checks"
mkdir -p "$TARGET/docs/missions/20990101-fixture/tasks"
printf '%s\n' '---' 'status: in-progress' '---' '# Goal' > "$TARGET/docs/missions/20990101-fixture/GOAL.md"
echo '{}' > "$TARGET/docs/missions/20990101-fixture/features.json"
check "active-mission finds fixture" sh -c "cd '$TARGET' && bash scripts/active-mission.sh | grep -q 20990101-fixture"
# spawn should fail fast on missing CLI name, not on missing script
check "spawn-worker rejects unknown worker" sh -c "cd '$TARGET' && ! bash scripts/spawn-worker.sh nope docs/missions/20990101-fixture/GOAL.md"

# ---- re-install must refuse ----
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "harness install"
check "second install refused" sh -c "! bash scripts/install-harness.sh '$TARGET'"

# ---- update path must preserve instance mission folders ----
echo "== update-harness.sh"
# leave a project-owned mission marker the updater must not delete
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
