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

VERSION="$(grep -m1 '^## ' CHANGELOG.md | sed 's/## //;s/ .*//')"
check "records .harness-version = $VERSION" grep -qx "$VERSION" "$TARGET/.harness-version"
check "AGENTS.md installed (was absent)"     test -f "$TARGET/AGENTS.md"
check "conflict -> CLAUDE.md.harness-new"    test -f "$TARGET/CLAUDE.md.harness-new"
check "existing CLAUDE.md untouched"         grep -q "my own claude notes" "$TARGET/CLAUDE.md"
check "skills copied"                        test -f "$TARGET/.agents/skills/dispatch-worker/SKILL.md"
check "MODEL_ROUTING.md installed"           test -f "$TARGET/docs/MODEL_ROUTING.md"
check ".claude/skills symlink"               test -L "$TARGET/.claude/skills"
check ".cursor/skills symlink"               test -L "$TARGET/.cursor/skills"
check "install stayed on a branch"           sh -c "git -C '$TARGET' branch --show-current | grep -q chore/harness-install"
check "install did not commit"               sh -c "[ -n \"\$(git -C '$TARGET' status --porcelain)\" ]"

# ---- re-install must refuse ----
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "harness install"
check "second install refused" sh -c "! bash scripts/install-harness.sh '$TARGET'"

# ---- update path ----
echo "== update-harness.sh"
bash scripts/update-harness.sh "$TARGET"
check "update stayed on version branch" sh -c "git -C '$TARGET' branch --show-current | grep -q 'chore/harness-'"
check "kit skill still present after update" test -f "$TARGET/.agents/skills/mission-init/SKILL.md"
check "MODEL_ROUTING.md propagated on update" test -f "$TARGET/docs/MODEL_ROUTING.md"

# ---- dirty-tree refusals ----
echo dirty > "$TARGET/dirty.txt"
check "update refuses dirty tree" sh -c "! bash scripts/update-harness.sh '$TARGET'"

echo ""
if [ "$FAIL" -eq 1 ]; then echo "TESTS FAILED"; exit 1; else echo "ALL TESTS PASSED"; fi
