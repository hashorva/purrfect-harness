#!/usr/bin/env python3
"""Reconstruct the F007 smoke chain using only this archived directory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
CONSUMER = ROOT / "consumer"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def load(name: str) -> dict:
    return json.loads((CONSUMER / name).read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"RECONSTRUCT FAIL: {message}")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    require(manifest.get("schema_version") == 1, "unsupported archive manifest")
    for relative, expected in manifest["sha256"].items():
        path = ROOT / relative
        require(path.is_file(), f"missing archived input: {relative}")
        require(sha256(path) == expected, f"archived input hash mismatch: {relative}")

    fleet = load("fleet.json")
    spec = load("execution-spec.json")
    receipt = load("execution-receipt.json")
    verification = load("verification-record.json")
    features = load("features.json")
    commits = load("commit-evidence.json")
    task_path = CONSUMER / "T-001.md"
    nonce_path = CONSUMER / "nonce.txt"
    log_text = (CONSUMER / "worker.log.sanitized").read_text()

    run_id = spec["run_id"]
    seat = fleet["seats"]["codex.economy"]
    require(fleet["approval"]["status"] == "approved", "fleet was not approved")
    require(
        (seat["provider"], seat["model"], seat["effort"], seat["speed"], seat["health"], seat["source"])
        == ("codex", "gpt-5.6-luna", "medium", "unknown", "healthy", "observed"),
        "frozen economy seat does not match the authorized healthy Luna binding",
    )
    require(spec["schema_version"] == 3, "smoke did not use ExecutionSpec v3")
    require(spec["provider_contract_version"] == 2, "smoke did not authorize provider contract 2")
    require(spec["role"] == "worker" and spec["feature"] == "F001", "wrong authorized role or feature")
    require(spec["work_unit"] == "T-001" and spec["attempt"] == 1, "wrong authorized work unit or attempt")
    require(spec["write_scope"] == ["smoke/nonce.txt"], "authorization was not one-file scoped")
    require(
        (spec["provider"], spec["model"], spec["effort"], spec["speed"])
        == (seat["provider"], seat["model"], seat["effort"], seat["speed"]),
        "ExecutionSpec does not match the frozen fleet",
    )

    smoke = commits["smoke_commit"]
    acceptance_commit = commits["acceptance_commit"]
    require(spec["base_commit"] == smoke["parent"] == commits["harness_baseline_commit"], "base commit chain mismatch")
    require(sha256(task_path) == verification["task"]["sha256"], "archived task bytes do not match verification")
    require(verification["task"]["git_commit"] == spec["base_commit"], "verification did not use the authorized task commit")
    require(sha256(CONSUMER / "execution-spec.json") == receipt["execution_spec_sha256"], "receipt does not bind archived spec")
    require(verification["execution_spec"]["sha256"] == receipt["execution_spec_sha256"], "verification does not bind authorized spec")

    require(receipt["run_id"] == run_id == verification["run_id"], "run identity diverges")
    require(receipt["outcome"] == "completed" and receipt["exit_code"] == 0, "execution did not complete successfully")
    require(receipt["workspace_changed"] is True, "execution did not record a real workspace change")
    require(receipt["changed_paths"] == ["smoke/nonce.txt"], "receipt changed-path set is not exact")
    require(receipt["commits"] == [smoke["commit"]], "receipt does not bind exactly the smoke commit")
    require(receipt["scope"]["result"] == "pass" and receipt["scope"]["violations"] == [], "write scope did not pass")
    require(receipt["scope"]["allowed"] == spec["write_scope"], "receipt scope differs from authorization")
    require(receipt["git_before"]["head"] == spec["base_commit"], "execution started from the wrong commit")
    require(receipt["git_after"]["head"] == smoke["commit"], "execution ended at the wrong commit")
    require(receipt["git_before"]["status_entry_count"] == 0, "execution started dirty")
    require(receipt["git_after"]["status_entry_count"] == 0, "execution ended dirty")
    require(receipt["git_before"]["status_porcelain_v1_z_sha256"] == EMPTY_SHA256, "before snapshot was not clean")
    require(receipt["git_after"]["status_porcelain_v1_z_sha256"] == EMPTY_SHA256, "after snapshot was not clean")

    require(verification["result"] == "pass", "VerificationRecord did not pass")
    require(len(verification["commands"]) == 3, "unexpected verification command count")
    require(all(item["exit_code"] == 0 for item in verification["commands"]), "a committed verification command failed")
    require(verification["receipt_git_after"] == receipt["git_after"], "verification receipt snapshot mismatch")
    require(verification["verification_git_before"] == receipt["git_after"], "verification started from different run state")
    require(verification["verification_git_after"] == receipt["git_after"], "verification ended in different run state")
    require(sha256(CONSUMER / "execution-receipt.json") == verification["execution_receipt"]["sha256"], "verification does not bind archived receipt")
    require(not any(key.startswith("accepted") for key in verification), "VerificationRecord improperly contains acceptance")

    feature = next(item for item in features["features"] if item["id"] == "F001")
    verification_sha = sha256(CONSUMER / "verification-record.json")
    require(feature["passes"] is True, "feature was not accepted")
    require(feature["accepted_run_id"] == run_id, "acceptance points to another run")
    require(feature["accepted_verification_sha256"] == verification_sha, "acceptance points to another VerificationRecord")
    require(bool(feature["accepted_by"]) and bool(feature["accepted_at"]), "acceptance authority or time is empty")

    expected_nonce = b"PURRFECT_PHASE1_NONCE=5818a92a-4798-4c29-832f-81e71012bece\n"
    require(nonce_path.read_bytes() == expected_nonce, "archived nonce bytes are wrong")
    require(sha256(nonce_path) == smoke["nonce_sha256"], "nonce hash differs from commit evidence")
    require("$CONSUMER_REPO" in log_text and str(spec["repo"]) not in log_text, "worker log was not path-sanitized")
    require("session id: [redacted]" in log_text, "worker session id was not redacted")
    require(run_id in log_text and "model: gpt-5.6-luna" in log_text, "sanitized log does not identify the run and model")
    require("/.git]" in log_text and "sandbox: workspace-write" in log_text, "sanitized log does not show scoped Git access")
    require(smoke["commit"][:7] in log_text and "exit=0" in log_text, "sanitized log lacks terminal commit/exit evidence")

    bundle = CONSUMER / "consumer-history.bundle"
    with tempfile.TemporaryDirectory(prefix="purrfect-f007-") as temporary:
        checkout = Path(temporary) / "consumer"
        subprocess.run(
            ["git", "clone", "-q", "--branch", "chore/harness-2.3.1", str(bundle), str(checkout)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        require(git(checkout, "rev-parse", acceptance_commit["commit"]) == acceptance_commit["commit"], "acceptance commit missing from bundle")
        require(git(checkout, "rev-parse", f"{smoke['commit']}^") == smoke["parent"], "smoke parent mismatch in bundle")
        require(git(checkout, "show", "-s", "--format=%s", smoke["commit"]) == smoke["subject"], "smoke subject mismatch in bundle")
        require(git(checkout, "diff-tree", "--no-commit-id", "--name-only", "-r", smoke["commit"]) == "smoke/nonce.txt", "smoke commit contains another path")
        require(git(checkout, "rev-parse", f"{smoke['commit']}:smoke/nonce.txt") == smoke["nonce_blob_oid"], "nonce blob mismatch in bundle")
        require((checkout / "smoke/nonce.txt").read_bytes() == expected_nonce, "checked-out bundle nonce is wrong")
        require(git(checkout, "rev-parse", f"{acceptance_commit['commit']}^") == smoke["commit"], "acceptance is not separate from execution commit")

    report = {
        "result": "PASS",
        "authorization": {
            "run_id": run_id,
            "provider": spec["provider"],
            "model": spec["model"],
            "effort": spec["effort"],
            "provider_contract_version": spec["provider_contract_version"],
            "base_commit": spec["base_commit"],
            "write_scope": spec["write_scope"],
        },
        "execution": {
            "outcome": receipt["outcome"],
            "exit_code": receipt["exit_code"],
            "commit": smoke["commit"],
            "changed_paths": receipt["changed_paths"],
            "clean_before": True,
            "clean_after": True,
        },
        "verification": {
            "result": verification["result"],
            "command_count": len(verification["commands"]),
            "all_exit_zero": True,
            "record_sha256": verification_sha,
        },
        "acceptance": {
            "passes": feature["passes"],
            "accepted_run_id": feature["accepted_run_id"],
            "accepted_verification_sha256": feature["accepted_verification_sha256"],
            "accepted_by": feature["accepted_by"],
            "acceptance_commit": acceptance_commit["commit"],
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
