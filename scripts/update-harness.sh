#!/usr/bin/env bash
# update-harness.sh — propagate purrfect-harness updates into a consuming repo
# Usage (from the purrfect-harness repo root):
#   bash scripts/update-harness.sh /path/to/target-repo
# Safety: refuses dirty targets, works on a branch, overwrites ONLY kit-owned
# paths, never deletes project files, never overwrites settings.json.

set -euo pipefail

TARGET="${1:?Usage: update-harness.sh /path/to/target-repo}"
HARNESS="$(pwd)"
VERSION="$(grep -m1 '^## ' CHANGELOG.md | sed 's/## //;s/ .*//')"

# ---- kit-owned manifest (the ONLY paths this script may overwrite) ----
KIT_SKILLS="supabase-migration shadcn-luma react-conventions mcp-hygiene \
cloudflare-deploy dispatch-worker mission-init skillify"
# Kit-owned mission *protocol* paths only. Never list docs/missions as a whole —
# instance folders (YYYYMMDD-*) are project-owned and must survive updates.
KIT_PATHS="docs/missions/ORCHESTRATION.md docs/missions/MODEL_ROUTING.md \
docs/missions/README.md docs/missions/templates \
docs/ORCHESTRATION.md docs/MODEL_ROUTING.md docs/templates \
.claude/rules .claude/agents \
scripts/sync-skills.sh scripts/update-harness.sh \
scripts/active-mission.sh scripts/spawn-worker.sh scripts/fleet-inventory.sh \
scripts/spawn-brain.sh scripts/verify-mission.sh scripts/write-receipt.sh"

# ---- preflight ----
[ -f "$HARNESS/CHANGELOG.md" ] || { echo "Run from the purrfect-harness repo root."; exit 1; }
[ -d "$TARGET/.git" ] || { echo "ERROR: $TARGET is not a git repo."; exit 1; }
if [ -n "$(git -C "$TARGET" status --porcelain)" ]; then
  echo "ERROR: target has uncommitted changes. Commit or stash first."; exit 1
fi

OLD_VERSION="none"
[ -f "$TARGET/.harness-version" ] && OLD_VERSION="$(cat "$TARGET/.harness-version")"
echo "Updating $TARGET : harness $OLD_VERSION -> $VERSION"

BRANCH="chore/harness-$VERSION"
git -C "$TARGET" checkout -b "$BRANCH" 2>/dev/null || git -C "$TARGET" checkout "$BRANCH"

# ---- copy kit-owned skills (other skill folders in target are untouched) ----
mkdir -p "$TARGET/.agents/skills"
for s in $KIT_SKILLS; do
  if [ -d "$HARNESS/.agents/skills/$s" ]; then
    rm -rf "$TARGET/.agents/skills/$s"
    cp -R "$HARNESS/.agents/skills/$s" "$TARGET/.agents/skills/$s"
    echo "  updated skill: $s"
  fi
done

# ---- copy other kit-owned paths ----
for p in $KIT_PATHS; do
  if [ -e "$HARNESS/$p" ]; then
    mkdir -p "$TARGET/$(dirname "$p")"
    rm -rf "${TARGET:?}/$p"
    cp -R "$HARNESS/$p" "$TARGET/$p"
    echo "  updated: $p"
  fi
done

# ---- settings.json: merged file, never overwrite ----
if [ -f "$HARNESS/.claude/settings.json" ]; then
  if [ -f "$TARGET/.claude/settings.json" ]; then
    if ! diff -q "$HARNESS/.claude/settings.json" "$TARGET/.claude/settings.json" >/dev/null 2>&1; then
      cp "$HARNESS/.claude/settings.json" "$TARGET/.claude/settings.json.new"
      echo "  ATTENTION: kit settings baseline changed -> wrote .claude/settings.json.new"
      echo "             diff it against your settings.json and merge by hand."
    fi
  else
    mkdir -p "$TARGET/.claude"
    cp "$HARNESS/.claude/settings.json" "$TARGET/.claude/settings.json"
    echo "  installed: .claude/settings.json (baseline)"
  fi
fi

echo "$VERSION" > "$TARGET/.harness-version"

# Ensure mission helper scripts are executable
chmod +x "$TARGET/scripts/active-mission.sh" "$TARGET/scripts/spawn-worker.sh" 2>/dev/null || true
chmod +x "$TARGET/scripts/fleet-inventory.sh" "$TARGET/scripts/spawn-brain.sh" 2>/dev/null || true
chmod +x "$TARGET/scripts/verify-mission.sh" "$TARGET/scripts/write-receipt.sh" 2>/dev/null || true
chmod +x "$TARGET/scripts/sync-skills.sh" "$TARGET/scripts/update-harness.sh" 2>/dev/null || true

# Refresh discovery symlinks safely (handles legacy parent-symlink layout)
( cd "$TARGET" && bash scripts/sync-skills.sh )

echo ""
echo "Done. NOT auto-committed. Next steps in $TARGET:"
echo "  1. git diff                      # review everything"
echo "  2. diff .claude/settings.json .claude/settings.json.new   # if it exists"
echo "  3. Check CHANGELOG ($OLD_VERSION -> $VERSION) for AGENTS.md skeleton"
echo "     changes to port manually (AGENTS.md is project-owned, never touched)."
echo "  4. Port AGENTS.md 'Orchestrated missions' section to docs/missions/ layout if upgrading from <2.0.0"
echo "  5. git add -A && git commit -m 'chore: harness $VERSION' && merge to dev"
