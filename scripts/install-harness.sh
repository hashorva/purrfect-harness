#!/usr/bin/env bash
# install-harness.sh — first-time install of purrfect-harness into a repo.
# Usage (from the purrfect-harness repo root):
#   bash scripts/install-harness.sh /path/to/target-repo
# Collision rule: NEVER overwrite an existing file — write <file>.harness-new
# beside it and let the human diff. For later updates use update-harness.sh.

set -euo pipefail

TARGET="${1:?Usage: install-harness.sh /path/to/target-repo}"
HARNESS="$(pwd)"
VERSION="$(grep -m1 '^## ' CHANGELOG.md | sed 's/## //;s/ .*//')"

[ -f "$HARNESS/CHANGELOG.md" ] || { echo "Run from the purrfect-harness repo root."; exit 1; }
[ -d "$TARGET/.git" ] || { echo "ERROR: $TARGET is not a git repo. git init + baseline commit first."; exit 1; }
[ -z "$(git -C "$TARGET" status --porcelain)" ] || { echo "ERROR: target tree not clean."; exit 1; }
[ -f "$TARGET/.harness-version" ] && { echo "ERROR: harness already installed ($(cat "$TARGET/.harness-version")). Use update-harness.sh."; exit 1; }

git -C "$TARGET" checkout -b "chore/harness-install" 2>/dev/null || git -C "$TARGET" checkout "chore/harness-install"

INSTALLED=0; SKIPPED=0; CONFLICTS=0

# copy_one <relative-path> : absent→copy, identical→skip, different→.harness-new
copy_one() {
  local rel="$1" src="$HARNESS/$1" dst="$TARGET/$1"
  mkdir -p "$(dirname "$dst")"
  if [ ! -e "$dst" ]; then
    cp "$src" "$dst"; INSTALLED=$((INSTALLED+1)); echo "  installed: $rel"
  elif diff -q "$src" "$dst" >/dev/null 2>&1; then
    SKIPPED=$((SKIPPED+1))
  else
    cp "$src" "$dst.harness-new"; CONFLICTS=$((CONFLICTS+1))
    echo "  CONFLICT : $rel  -> wrote $rel.harness-new (diff and merge by hand)"
  fi
}

# ---- kit payload (README/CHANGELOG/RELEASING stay in the harness repo only) ----
PAYLOAD=$(cd "$HARNESS" && find .agents/skills docs/missions/templates .claude/rules .claude/agents -type f; \
          echo "docs/missions/ORCHESTRATION.md"; echo "docs/missions/MODEL_ROUTING.md"; \
          echo "docs/missions/README.md"; \
          echo "docs/ORCHESTRATION.md"; echo "docs/MODEL_ROUTING.md"; echo "docs/templates/README.md"; \
          echo ".claude/settings.json"; \
          echo "scripts/sync-skills.sh"; echo "scripts/active-mission.sh"; echo "scripts/spawn-worker.sh"; \
          echo "scripts/fleet-inventory.sh"; \
          echo "CLAUDE.md"; echo "GEMINI.md")

for f in $PAYLOAD; do copy_one "$f"; done

# ---- AGENTS.md is special: never installed as-is over an existing one ----
if [ -e "$TARGET/AGENTS.md" ]; then
  cp "$HARNESS/AGENTS.md" "$TARGET/AGENTS.md.template"
  echo "  NOTE     : existing AGENTS.md kept. Kit skeleton -> AGENTS.md.template"
  echo "             Re-shape your content into the skeleton, then delete the template."
else
  cp "$HARNESS/AGENTS.md" "$TARGET/AGENTS.md"; INSTALLED=$((INSTALLED+1))
  echo "  installed: AGENTS.md (FILL every {{placeholder}} before committing)"
fi

# ---- skill discovery paths: real dirs of per-skill symlinks (never parent symlink) ----
# Parent symlink (.claude/skills -> ../.agents/skills) + naive sync used to corrupt CANON.
( cd "$TARGET" && bash "$HARNESS/scripts/sync-skills.sh" )
echo "  symlinks : per-skill links under .claude/.cursor/.gemini/.codex skills/"

echo "$VERSION" > "$TARGET/.harness-version"
chmod +x "$TARGET/scripts/active-mission.sh" "$TARGET/scripts/spawn-worker.sh" 2>/dev/null || true
chmod +x "$TARGET/scripts/fleet-inventory.sh" 2>/dev/null || true
chmod +x "$TARGET/scripts/sync-skills.sh" 2>/dev/null || true

echo ""
echo "Install of $VERSION staged on branch chore/harness-install."
echo "  installed=$INSTALLED  identical-skipped=$SKIPPED  conflicts=$CONFLICTS"
echo "NOT committed. Your manual TODOs:"
echo "  1. Fill AGENTS.md placeholders (or merge AGENTS.md.template into yours)"
echo "  2. Resolve every *.harness-new (diff, merge, delete the .harness-new)"
echo "  3. Delete kit skills that don't apply to this repo"
echo "  4. Adapt .claude/settings.json allow/deny to this repo's commands"
echo "  5. git diff --stat  -> only harness paths should appear"
echo "  6. Build/tests still green, then commit and merge"
