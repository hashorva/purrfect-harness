#!/usr/bin/env bash
# verify-mission.sh — validate exact Phase 1 execution evidence for one mission.
# Usage: verify-mission.sh [--require-workers] [mission-dir]
set -euo pipefail

REQUIRE_WORKERS=0
MISSION_IN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --require-workers) REQUIRE_WORKERS=1; shift ;;
    -h|--help) echo "Usage: verify-mission.sh [--require-workers] [mission-dir]"; exit 0 ;;
    *) [ -z "$MISSION_IN" ] || { echo "ERROR: only one mission may be supplied" >&2; exit 2; }; MISSION_IN="$1"; shift ;;
  esac
done

ROOT="$(pwd -P)"
if [ -z "$MISSION_IN" ]; then
  MISSION_IN="$(bash "$ROOT/scripts/active-mission.sh")"
fi
export VERIFY_ROOT="$ROOT"
export VERIFY_MISSION="$MISSION_IN"
export VERIFY_REQUIRE_WORKERS="$REQUIRE_WORKERS"

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import json
import os
from pathlib import Path
import re
import sys

root = Path(os.environ["VERIFY_ROOT"]).resolve()
scripts = root / "scripts"
sys.path.insert(0, str(scripts))
from execution_receipt import ReceiptError, load_receipt  # noqa: E402

supplied = Path(os.environ["VERIFY_MISSION"])
mission = (supplied if supplied.is_absolute() else root / supplied).resolve()
missions_root = (root / "docs/missions").resolve()
if not mission.is_dir() or mission.parent != missions_root:
    print(f"VERIFY FAIL:\n  - mission must be one direct directory under {missions_root}")
    raise SystemExit(1)
mission_rel = mission.relative_to(root).as_posix()
require_workers = os.environ["VERIFY_REQUIRE_WORKERS"] == "1"
receipt_dir = root / ".tasks/receipts"
uuid_json = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.json$")
failures = []
receipts = []

if receipt_dir.is_dir():
    for path in sorted(receipt_dir.glob("*.json")):
        if not uuid_json.fullmatch(path.name):
            continue
        try:
            receipt = load_receipt(path)
        except ReceiptError as exc:
            failures.append(f"invalid execution receipt {path.name}: {exc}")
            continue
        if receipt["mission"] == mission_rel:
            receipts.append((path, receipt))

brains = [(path, receipt) for path, receipt in receipts if receipt["role"] == "brain"]
workers = [(path, receipt) for path, receipt in receipts if receipt["role"] == "worker"]

def terminal_success(item):
    return item[1]["outcome"] == "completed" and item[1]["exit_code"] == 0 and item[1]["scope"]["result"] == "pass"

latest_brain = sorted(brains, key=lambda item: (item[1]["finished_at"], item[1]["attempt"]))[-1] if brains else None
if latest_brain is None or not terminal_success(latest_brain):
    failures.append(f"no completed, in-scope brain ExecutionReceipt for exact mission {mission_rel}")
else:
    path, receipt = latest_brain
    print(
        f"OK brain: {path.name} provider={receipt['provider']} model={receipt['model']} "
        f"action={receipt['work_unit']}"
    )

feature_path = mission / "features.json"
try:
    feature_doc = json.loads(feature_path.read_text())
    features = feature_doc["features"]
    if not isinstance(features, list):
        raise ValueError("features is not an array")
except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
    failures.append(f"missing or malformed {feature_path}: {exc}")
    features = []

need_worker = [
    feature for feature in features
    if isinstance(feature, dict) and feature.get("passes") is True and feature.get("bootstrap") is not True
]
successful_workers = [item for item in workers if terminal_success(item)]

if require_workers and not successful_workers:
    failures.append("--require-workers needs at least one completed, in-scope worker ExecutionReceipt")

for feature in need_worker:
    feature_id = feature.get("id")
    exact = [item for item in workers if item[1]["feature"] == feature_id]
    if not exact:
        failures.append(f"feature {feature_id}: no exact-feature worker ExecutionReceipt")
        continue
    path, receipt = sorted(exact, key=lambda item: (item[1]["finished_at"], item[1]["attempt"]))[-1]
    if not terminal_success((path, receipt)):
        failures.append(
            f"feature {feature_id}: latest exact receipt {path.name} is "
            f"{receipt['outcome']} with scope={receipt['scope']['result']}"
        )
        continue
    expected_task = f"{mission_rel}/tasks/{receipt['work_unit']}.md"
    if receipt["task"] != expected_task:
        failures.append(f"feature {feature_id}: receipt {path.name} task does not match its work unit")
        continue
    if receipt["workspace_changed"] is not True:
        failures.append(f"feature {feature_id}: receipt {path.name} is a no-op (workspace_changed=false)")
        continue
    print(
        f"OK worker for {feature_id}: {path.name} provider={receipt['provider']} "
        f"changed_paths={len(receipt['changed_paths'])}"
    )

if failures:
    print("VERIFY FAIL:")
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)

print(f"VERIFY OK: {mission_rel}")
PY
