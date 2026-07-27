#!/usr/bin/env bash
# sync-skills.sh — link the canonical .agents/skills/ into every tool's discovery path.
# Canonical source of truth: .agents/skills/  (Agent Skills open standard, agentskills.io)
# Discovery paths: Claude Code .claude/skills, Cursor .cursor/skills,
#                  Gemini CLI .gemini/skills, Codex .codex/skills (also reads .agents/skills)
# Idempotent. Run from repo root after adding/removing a skill.
#
# CRITICAL: discovery paths must be REAL directories of per-skill symlinks.
# Never leave .claude/skills as a symlink to ../.agents/skills — writing into that
# target deletes/replaces the canonical skill folders (self-symlink loops).

set -euo pipefail

ROOT="$(pwd)"
CANON="$ROOT/.agents/skills"

if [ ! -d "$CANON" ]; then
  echo "ERROR: $CANON not found. Run from the repo root." >&2
  exit 1
fi

# Resolve CANON to a real path for comparison (macOS lacks readlink -f; use pwd -P)
CANON_REAL="$(cd "$CANON" && pwd -P)"

TARGETS=".claude/skills .cursor/skills .gemini/skills .codex/skills"

for target in $TARGETS; do
  dest_dir="$ROOT/$target"
  mkdir -p "$ROOT/$(dirname "$target")"

  # If discovery path is a symlink (legacy: -> ../.agents/skills), replace with a real dir.
  # Writing per-skill links *through* that symlink would mutate CANON.
  if [ -L "$dest_dir" ]; then
    link_target="$(readlink "$dest_dir")"
    echo "  replacing symlink $target -> $link_target with a real directory"
    rm -f "$dest_dir"
  fi
  mkdir -p "$dest_dir"

  # Safety: dest_dir must not resolve to CANON
  DEST_REAL="$(cd "$dest_dir" && pwd -P)"
  if [ "$DEST_REAL" = "$CANON_REAL" ]; then
    echo "ERROR: $target resolves to .agents/skills — refusing to write (would corrupt canonical skills)." >&2
    exit 1
  fi

  for skill in "$CANON"/*/; do
    [ -d "$skill" ] || continue
    name="$(basename "$skill")"
    dest="$dest_dir/$name"
    # remove stale copy/link, then symlink to absolute canonical path
    if [ -L "$dest" ] || [ -e "$dest" ]; then rm -rf "$dest"; fi
    ln -s "$CANON_REAL/$name" "$dest"
  done

  # prune links to skills that no longer exist
  shopt -s nullglob
  for existing in "$dest_dir"/*; do
    [ -e "$existing" ] || [ -L "$existing" ] || continue
    name="$(basename "$existing")"
    if [ ! -d "$CANON/$name" ]; then rm -rf "$existing"; fi
  done
  shopt -u nullglob

  echo "synced -> $target"
done

echo "Done. Canonical: .agents/skills/  (edit skills ONLY there)"
echo "Tip: add .claude/skills .cursor/skills .gemini/skills .codex/skills to .gitignore"
echo "     and commit only .agents/skills/ — teammates re-run this script after clone."
