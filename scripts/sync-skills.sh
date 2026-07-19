#!/usr/bin/env bash
# sync-skills.sh — link the canonical .agents/skills/ into every tool's discovery path.
# Canonical source of truth: .agents/skills/  (Agent Skills open standard, agentskills.io)
# Discovery paths: Claude Code .claude/skills, Cursor .cursor/skills,
#                  Gemini CLI .gemini/skills, Codex .codex/skills (also reads .agents/skills)
# Idempotent. Run from repo root after adding/removing a skill.

set -euo pipefail

ROOT="$(pwd)"
CANON="$ROOT/.agents/skills"

if [ ! -d "$CANON" ]; then
  echo "ERROR: $CANON not found. Run from the repo root." >&2
  exit 1
fi

TARGETS=".claude/skills .cursor/skills .gemini/skills .codex/skills"

for target in $TARGETS; do
  mkdir -p "$ROOT/$(dirname "$target")"
  # Link each skill folder individually (tools tolerate this better than a linked parent)
  mkdir -p "$ROOT/$target"
  for skill in "$CANON"/*/; do
    name="$(basename "$skill")"
    dest="$ROOT/$target/$name"
    # remove stale copy/link, then symlink
    if [ -L "$dest" ] || [ -d "$dest" ]; then rm -rf "$dest"; fi
    ln -s "$CANON/$name" "$dest"
  done
  # prune links to skills that no longer exist
  for existing in "$ROOT/$target"/*/; do
    [ -e "$existing" ] || continue
    name="$(basename "$existing")"
    if [ ! -d "$CANON/$name" ]; then rm -rf "$existing"; fi
  done
  echo "synced -> $target"
done

echo "Done. Canonical: .agents/skills/  (edit skills ONLY there)"
echo "Tip: add .claude/skills .cursor/skills .gemini/skills .codex/skills to .gitignore"
echo "     and commit only .agents/skills/ — teammates re-run this script after clone."
