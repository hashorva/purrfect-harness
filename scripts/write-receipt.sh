#!/usr/bin/env bash
# write-receipt.sh — strict ExecutionReceipt v1 entry point.
#
# Usage (normally execution_runner.py owns this lifecycle):
#   bash scripts/write-receipt.sh write --spec PATH --spec-sha256 SHA \
#     --before-json JSON --started-at RFC3339 --finished-at RFC3339 \
#     --outcome OUTCOME --exit-code N --log-path PATH [--task PATH] [--tier TIER]
set -euo pipefail

ROOT="$(pwd -P)"
exec env PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/execution_receipt.py" "$@"
