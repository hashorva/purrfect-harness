#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRATCH="$(mktemp -d -t purrfect-f007-evidence.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

cp -R "$ROOT" "$SCRATCH/evidence"
FRESH_PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

env -i PATH="$FRESH_PATH" python3 "$SCRATCH/evidence/reconstruct.py" >"$SCRATCH/valid.out"
grep -q '"result": "PASS"' "$SCRATCH/valid.out"

printf 'tamper\n' >>"$SCRATCH/evidence/consumer/nonce.txt"
if env -i PATH="$FRESH_PATH" python3 "$SCRATCH/evidence/reconstruct.py" >"$SCRATCH/hash.out" 2>&1; then
  echo "ERROR: evidence hash tamper passed reconstruction" >&2
  exit 1
fi
grep -q 'archived input hash mismatch: consumer/nonce.txt' "$SCRATCH/hash.out"
cp "$ROOT/consumer/nonce.txt" "$SCRATCH/evidence/consumer/nonce.txt"

python3 - "$SCRATCH/evidence" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
features_path = root / "consumer/features.json"
features = json.loads(features_path.read_text())
features["features"][0]["accepted_run_id"] = "00000000-0000-4000-8000-000000000000"
features_path.write_text(json.dumps(features, indent=2) + "\n")
manifest_path = root / "manifest.json"
manifest = json.loads(manifest_path.read_text())
manifest["sha256"]["consumer/features.json"] = hashlib.sha256(features_path.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
PY

if env -i PATH="$FRESH_PATH" python3 "$SCRATCH/evidence/reconstruct.py" >"$SCRATCH/semantic.out" 2>&1; then
  echo "ERROR: re-bound acceptance passed reconstruction" >&2
  exit 1
fi
grep -q 'acceptance points to another run' "$SCRATCH/semantic.out"

echo "RECONSTRUCTION TESTS PASSED"

