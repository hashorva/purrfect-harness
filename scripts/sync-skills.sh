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
MANIFEST="$ROOT/harness-manifest.json"

if [ ! -d "$CANON" ]; then
  echo "ERROR: $CANON not found. Run from the repo root." >&2
  exit 1
fi

[ -f "$MANIFEST" ] || { echo "ERROR: $MANIFEST not found. Run from a harness-managed repo root." >&2; exit 1; }
manifest_values() {
python3 - "$MANIFEST" "$CANON" "$1" <<'PY'
import json, pathlib, sys
try:
    manifest = json.load(open(sys.argv[1]))
    declared = manifest["ownership"]["canonical_skills"]
    actual = sorted(p.name for p in pathlib.Path(sys.argv[2]).iterdir() if p.is_dir())
    if declared != actual:
        raise ValueError("canonical_skills must exactly list every .agents/skills directory")
    print(*manifest["ownership"][sys.argv[3]], sep="\n")
except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
    print(f"ERROR: invalid harness manifest: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
}

# Resolve CANON to a real path for comparison (macOS lacks readlink -f; use pwd -P)
CANON_REAL="$(cd "$CANON" && pwd -P)"

while IFS= read -r target; do
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

  while IFS= read -r name; do
    dest="$dest_dir/$name"
    # remove stale copy/link, then symlink with a RELATIVE path (portable across machines)
    if [ -L "$dest" ] || [ -e "$dest" ]; then rm -rf "$dest"; fi
    # From .claude/skills/foo → ../../.agents/skills/foo (same for .cursor/.gemini/.codex)
    rel_target="../../.agents/skills/$name"
    ln -s "$rel_target" "$dest"
  done < <(manifest_values canonical_skills)

  # Entries outside the manifest are owned by the consuming project/tool.
  # Never prune or replace them during harness discovery sync.

  echo "synced -> $target"
done < <(manifest_values discovery_targets)

echo "Done. Canonical: .agents/skills/  (edit skills ONLY there)"
echo "Tip: add .claude/skills .cursor/skills .gemini/skills .codex/skills to .gitignore"
echo "     and commit only .agents/skills/ — teammates re-run this script after clone."
