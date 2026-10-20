#!/usr/bin/env python3
"""Rebuild a concise, validated evidence view for one or more execution runs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import execution_receipt
import execution_spec
import ledger
import verification_record
from run_id import validate_run_id


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def mission_root(root, value):
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_dir() or path.parent != (root / "docs/missions").resolve():
        raise ValueError("mission must be one direct directory under docs/missions")
    return path


def discover_ids(root, mission, all_runs):
    if not all_runs:
        return all_runs
    directory = root / ".tasks/receipts"
    return sorted(path.stem for path in directory.glob("*.json")
                  if path.is_file() and not path.is_symlink()
                  and receipt_mission(path) == mission.relative_to(root).as_posix())


def receipt_mission(path):
    try:
        return json.loads(path.read_bytes()).get("mission")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return None


def reconstruct(root, mission, run_id):
    missing = []
    spec_path = root / ".tasks/specs" / f"{run_id}.json"
    receipt_path = root / ".tasks/receipts" / f"{run_id}.json"
    ledger_path = root / ".tasks/ledger" / f"{run_id}.json"
    print(f"RUN {run_id}")

    spec = None
    if not spec_path.exists():
        missing.append("spec")
        print("  spec: MISSING")
    else:
        try:
            spec, raw = execution_spec.load_persisted(spec_path)
            if spec["run_id"] != run_id or spec["mission"] != mission.relative_to(root).as_posix():
                raise ValueError("spec identity does not match requested run and mission")
            print("  seat: {provider} / {model} / {effort} / {speed}".format(**spec))
            print(f"  spec: {spec_path} sha256={sha256(raw)}")
        except (execution_spec.SpecError, ValueError, OSError) as exc:
            missing.append("spec (invalid)")
            print(f"  spec: INVALID ({exc})")

    receipt = None
    if not receipt_path.exists():
        missing.append("receipt")
        print("  receipt: MISSING")
    else:
        try:
            receipt = execution_receipt.load_receipt(receipt_path)
            if receipt["run_id"] != run_id or receipt["mission"] != mission.relative_to(root).as_posix():
                raise ValueError("receipt identity does not match requested run and mission")
            observed = receipt.get("observation", {}).get("observed_model", {})
            observed_model = observed.get("value", "unknown")
            observed_source = observed.get("source", "unknown")
            print(f"  receipt: {receipt['outcome']} exit={receipt['exit_code']} commits={json.dumps(receipt['commits'])}")
            print(f"  observed model: {observed_model} (source={observed_source})")
        except (execution_receipt.ReceiptError, execution_spec.SpecError, ValueError, OSError) as exc:
            missing.append("receipt (invalid)")
            print(f"  receipt: INVALID ({exc})")

    try:
        paths = verification_record.run_records(mission, run_id)
        if not paths:
            missing.append("VerificationRecord")
            print("  VerificationRecords: MISSING")
        else:
            for number, path in sorted(paths.items()):
                try:
                    record, raw = verification_record.load_record(path)
                    if record["run_id"] != run_id:
                        raise ValueError("record run_id does not match")
                    print(f"  VerificationRecord {path.name}: {record['result']} sha256={sha256(raw)}")
                except (verification_record.VerificationError, ValueError, OSError) as exc:
                    missing.append(f"VerificationRecord {path.name} (invalid)")
                    print(f"  VerificationRecord {path.name}: INVALID ({exc})")
    except verification_record.VerificationError as exc:
        missing.append("VerificationRecord (invalid)")
        print(f"  VerificationRecords: INVALID ({exc})")

    if ledger_path.is_symlink() or (ledger_path.exists() and not ledger_path.is_file()):
        missing.append("ledger row (not a regular file)")
        print("  ledger: MISSING")
    elif not ledger_path.is_file():
        missing.append("ledger row")
        print("  ledger: MISSING")
    else:
        try:
            row = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger.validate_row(row)
            if row["run_id"] != run_id:
                raise ValueError("ledger run_id does not match")
            print(f"  ledger: {ledger_path} VALID")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ledger.LedgerError, ValueError) as exc:
            missing.append("ledger row (invalid)")
            print(f"  ledger: {ledger_path} INVALID ({exc})")
    return missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mission")
    # Python 3.12 rejects a nargs="*" positional in a mutually exclusive group,
    # so run ids and --all are kept exclusive by hand below.
    parser.add_argument("run_ids", nargs="*", default=[])
    parser.add_argument("--all", action="store_true", dest="all_runs")
    args = parser.parse_args(argv)
    if args.all_runs and args.run_ids:
        print("ERROR: reconstruct: run ids and --all cannot be combined", file=sys.stderr)
        return 2
    root = Path.cwd().resolve()
    try:
        mission = mission_root(root, args.mission)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    run_ids = discover_ids(root, mission, args.all_runs) if args.all_runs else args.run_ids
    if not run_ids:
        print("ERROR: no runs selected", file=sys.stderr)
        return 2
    for run_id in run_ids:
        try:
            validate_run_id(run_id)
        except ValueError:
            print("ERROR: reconstruct: invalid run id", file=sys.stderr)
            return 2
    failures = []
    for run_id in run_ids:
        missing = reconstruct(root, mission, run_id)
        failures.extend((run_id, item) for item in missing)
    for run_id, item in failures:
        print(f"MISSING {run_id}: {item}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
