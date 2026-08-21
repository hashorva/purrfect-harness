#!/usr/bin/env bash
# install-harness.sh — first-time install of purrfect-harness into a repo.
# Usage (from the purrfect-harness repo root):
#   bash scripts/install-harness.sh /path/to/target-repo
# Collision rule: NEVER overwrite an existing file — write <file>.harness-new
# beside it and let the human diff. For later updates use update-harness.sh.

set -euo pipefail

HARNESS="$(pwd)"
DEV_MODE=0
if [ "${1:-}" = "--dev" ] || [ "${1:-}" = "--allow-untagged" ]; then
  DEV_MODE=1
  shift
fi
if [ "${1:-}" = "--validate-release" ]; then
  VALIDATE_ONLY=1
  shift
else
  VALIDATE_ONLY=0
fi
TARGET="${1:-}"

manifest() {
  python3 - "$HARNESS" "$DEV_MODE" "${1:-validate}" <<'PY'
import json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
dev = sys.argv[2] == "1"
action = sys.argv[3]
manifest_path = root / "harness-manifest.json"
try:
    m = json.loads(manifest_path.read_text())
    assert m["schema_version"] == 1
    ownership, release = m["ownership"], m["release"]
    declared = ownership["canonical_skills"]
    actual = sorted(p.name for p in (root / ".agents/skills").iterdir() if p.is_dir())
    if declared != actual:
        raise ValueError("canonical_skills must exactly list every .agents/skills directory")
    readme_version = next(line.split(":", 1)[1].strip() for line in (root / "README.md").read_text().splitlines() if line.startswith("version:"))
    changelog_version = next(line[3:].split()[0] for line in (root / "CHANGELOG.md").read_text().splitlines() if line.startswith("## "))
    if {readme_version, changelog_version, release["version"]} != {release["version"]}:
        raise ValueError("README, CHANGELOG, and manifest release versions disagree")
    for path in ownership["install_payload_paths"] + ownership["update_paths"] + [ownership["consumer_agents_template"]]:
        if not (root / path).exists():
            raise ValueError(f"manifest-owned path is missing: {path}")
except (OSError, KeyError, ValueError, AssertionError, StopIteration, json.JSONDecodeError) as exc:
    print(f"ERROR: invalid harness manifest: {exc}", file=sys.stderr)
    raise SystemExit(1)
if action == "validate":
    if not dev:
        tags = subprocess.check_output(["git", "-C", str(root), "tag", "--points-at", "HEAD"], text=True).split()
        if release["required_tag"] not in tags:
            print(f"ERROR: {release['required_tag']} must point at HEAD; use --dev/--allow-untagged only for explicit development work.", file=sys.stderr)
            raise SystemExit(1)
        if subprocess.check_output(["git", "-C", str(root), "cat-file", "-t", f"refs/tags/{release['required_tag']}"], text=True).strip() != "tag":
            print(f"ERROR: {release['required_tag']} must be an annotated tag.", file=sys.stderr)
            raise SystemExit(1)
    print(release["version"])
elif action == "install-payload":
    for skill in ownership["canonical_skills"]:
        for p in sorted((root / ".agents/skills" / skill).rglob("*")):
            if p.is_file(): print(p.relative_to(root))
    for item in ownership["install_payload_roots"]:
        for p in sorted((root / item).rglob("*")):
            if p.is_file(): print(p.relative_to(root))
    print(*ownership["install_payload_paths"], sep="\n")
PY
}

[ -f "$HARNESS/CHANGELOG.md" ] || { echo "Run from the purrfect-harness repo root."; exit 1; }
VERSION="$(manifest validate)"
if [ "$VALIDATE_ONLY" -eq 1 ]; then
  [ "$#" -eq 0 ] || { echo "Usage: install-harness.sh [--dev|--allow-untagged] --validate-release"; exit 1; }
  echo "Release validation passed for $VERSION."
  exit 0
fi
[ -n "$TARGET" ] || { echo "Usage: install-harness.sh [--dev|--allow-untagged] /path/to/target-repo"; exit 1; }

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
PAYLOAD="$(manifest install-payload)"

for f in $PAYLOAD; do copy_one "$f"; done

# ---- AGENTS.md is special: never installed as-is over an existing one ----
if [ -e "$TARGET/AGENTS.md" ]; then
  if [ ! -e "$TARGET/AGENTS.md.template" ]; then
    cp "$HARNESS/docs/templates/AGENTS.md.template" "$TARGET/AGENTS.md.template"
    echo "  NOTE     : existing AGENTS.md kept. Consumer skeleton -> AGENTS.md.template"
  else
    echo "  NOTE     : existing AGENTS.md and AGENTS.md.template kept (project-owned)."
  fi
else
  cp "$HARNESS/docs/templates/AGENTS.md.template" "$TARGET/AGENTS.md"; INSTALLED=$((INSTALLED+1))
  echo "  installed: AGENTS.md (fill consumer placeholders before committing)"
fi

# ---- skill discovery paths: real dirs of per-skill symlinks (never parent symlink) ----
# Parent symlink (.claude/skills -> ../.agents/skills) + naive sync used to corrupt CANON.
( cd "$TARGET" && bash "$HARNESS/scripts/sync-skills.sh" )
echo "  symlinks : per-skill links under .claude/.cursor/.gemini/.codex skills/"

echo "$VERSION" > "$TARGET/.harness-version"
chmod +x "$TARGET/scripts/active-mission.sh" "$TARGET/scripts/spawn-worker.sh" 2>/dev/null || true
chmod +x "$TARGET/scripts/fleet-inventory.sh" "$TARGET/scripts/spawn-brain.sh" 2>/dev/null || true
chmod +x "$TARGET/scripts/verify-mission.sh" "$TARGET/scripts/write-receipt.sh" 2>/dev/null || true
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
