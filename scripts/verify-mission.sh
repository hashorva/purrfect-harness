#!/usr/bin/env bash
# verify-mission.sh — refuse to greenlight a mission without CLI receipts.
# Usage:
#   bash scripts/verify-mission.sh                 # active mission
#   bash scripts/verify-mission.sh <mission-dir>   # explicit
#   bash scripts/verify-mission.sh --require-workers <mission>
#
# Exit 0 = greenlight OK. Exit 1 = missing/invalid receipts (do not flip done / GATE).
set -euo pipefail

REQUIRE_WORKERS=0
MISSION_IN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --require-workers) REQUIRE_WORKERS=1; shift ;;
    -h|--help)
      echo "Usage: verify-mission.sh [--require-workers] [mission-dir]"; exit 0 ;;
    *) MISSION_IN="$1"; shift ;;
  esac
done

ROOT="$(pwd)"
if [ -n "$MISSION_IN" ]; then
  if [ -d "$MISSION_IN" ]; then MISSION="$MISSION_IN"
  elif [ -d "docs/missions/$MISSION_IN" ]; then MISSION="docs/missions/$MISSION_IN"
  else echo "ERROR: mission not found: $MISSION_IN" >&2; exit 1
  fi
else
  MISSION="$(bash "$ROOT/scripts/active-mission.sh")"
fi
MISSION="${MISSION%/}"

export VERIFY_MISSION="$MISSION"
export VERIFY_REQUIRE_WORKERS="$REQUIRE_WORKERS"
export VERIFY_ROOT="$ROOT"

python3 - <<'PY'
import json, os, sys
from pathlib import Path

root = Path(os.environ["VERIFY_ROOT"])
mission = Path(os.environ["VERIFY_MISSION"])
require_workers = os.environ.get("VERIFY_REQUIRE_WORKERS") == "1"
rec_dir = root / ".tasks" / "receipts"
fail = []

def load_receipts():
    if not rec_dir.is_dir():
        return []
    out = []
    for p in sorted(rec_dir.glob("*.json")):
        if p.name.startswith("latest-"):
            continue
        try:
            doc = json.loads(p.read_text())
        except Exception as e:
            fail.append(f"unreadable receipt {p.name}: {e}")
            continue
        if doc.get("mission") in (str(mission), mission.as_posix()):
            out.append((p, doc))
        # also accept if mission path endswith
        elif str(doc.get("mission") or "").rstrip("/").endswith(mission.name):
            out.append((p, doc))
    return out

receipts = load_receipts()
brains = [(p, d) for p, d in receipts if d.get("role") == "brain"]
workers = [(p, d) for p, d in receipts if d.get("role") == "worker"]

ok_brains = [
    (p, d) for p, d in brains
    if int(d.get("exit", 1)) == 0 and d.get("cli") in ("claude", "codex", "waiver")
]
if not ok_brains:
    fail.append(
        f"no successful brain receipt for {mission} under .tasks/receipts/ "
        f"(need spawn-brain.sh … with exit=0). Found {[p.name for p,_ in brains] or 'none'}."
    )
else:
    # Prefer real CLI over waiver when both exist
    real = [x for x in ok_brains if x[1].get("cli") != "waiver"]
    chosen = real[-1] if real else ok_brains[-1]
    p, d = chosen
    print(f"OK brain: {p.name} cli={d.get('cli')} model={d.get('model')} action={d.get('action')}")
    if d.get("cli") == "waiver":
        print(f"  WARNING: brain is a waiver — not a Claude CLI run")

feat_path = mission / "features.json"
if feat_path.is_file():
    features = json.loads(feat_path.read_text()).get("features") or []
else:
    features = []
    fail.append(f"missing {feat_path}")

passed = [f for f in features if f.get("passes") is True]
# Features that are allowed with brain-only proof (bootstrap)
def is_bootstrap(f):
    desc = (f.get("description") or "").lower()
    return f.get("id") == "F001" or "mission folder" in desc or "mission files" in desc

need_worker = [f for f in passed if not is_bootstrap(f)]
if require_workers or need_worker:
    ok_workers = [(p, d) for p, d in workers if int(d.get("exit", 1)) == 0]
    if not ok_workers and need_worker:
        fail.append(
            f"{len(need_worker)} feature(s) passes:true need worker receipts "
            f"({[f.get('id') for f in need_worker]}). Run spawn-worker.sh."
        )
    # Per-feature: if feature id set on receipt, enforce match; else any worker ok for now
    for f in need_worker:
        fid = f.get("id")
        matched = [
            (p, d) for p, d in ok_workers
            if d.get("feature") in (fid, None, "")
        ]
        # Prefer explicit feature match
        explicit = [(p, d) for p, d in ok_workers if d.get("feature") == fid]
        if explicit:
            print(f"OK worker for {fid}: {explicit[-1][0].name} cli={explicit[-1][1].get('cli')}")
        elif ok_workers:
            # soft: warn if no explicit feature tag
            print(f"WARN {fid}: no receipt with feature={fid}; accepting any worker receipt (tag --feature next time)")
        else:
            fail.append(f"feature {fid} passes:true but no worker receipt with exit=0")

# PROGRESS honesty: if it claims Claude/Cursor CLI without receipts, warn (non-fatal if receipts exist)
prog = mission / "PROGRESS.md"
if prog.is_file() and not ok_brains:
    text = prog.read_text()
    if "Claude" in text or "spawn-brain" in text:
        fail.append("PROGRESS mentions brain/Claude but no brain receipt exists")

if fail:
    print("VERIFY FAIL:")
    for line in fail:
        print(f"  - {line}")
    sys.exit(1)

print(f"VERIFY OK: {mission}")
sys.exit(0)
PY
