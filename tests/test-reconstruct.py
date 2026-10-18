#!/usr/bin/env python3
"""Reconstruction reports complete evidence and refuses hostile run ids."""
import contextlib
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import execution_receipt
import execution_spec
import reconstruct_run
import verification_record

_integration_spec = importlib.util.spec_from_file_location(
    "execution_integration", ROOT / "tests/test-execution-integration.py")
integration = importlib.util.module_from_spec(_integration_spec)
_integration_spec.loader.exec_module(integration)

RUN = "01234567-89ab-42cd-8ef0-0123456789ab"
MISSION = "docs/missions/fixture"
OTHER_MISSION = "docs/missions/other"


def tree_snapshot(root):
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            kind = "symlink"
        elif path.is_file():
            kind = "file"
        elif path.is_dir():
            kind = "dir"
        else:
            kind = "other"
        stat = path.lstat()
        entries.append((path.relative_to(root).as_posix(), kind, stat.st_size, stat.st_mtime_ns))
    return entries


class ReconstructFixture(unittest.TestCase):
    def setUp(self):
        self.wrapper = integration.WrapperIntegration("runTest")
        self.wrapper.setUp()
        self.root = self.wrapper.root
        self.cwd = os.getcwd()
        os.chdir(self.root)
        self.wrapper.write_fleet("codex", "reconstruct-model", "medium", "unknown")
        self.wrapper.task.write_text(
            "---\ntask_id: T-001\nfeature: F001\n---\n# Task\n\n"
            "## Files you MAY touch\n- `allowed.txt`\n\n## Verification commands\n\n- `[\"true\"]`\n")
        self.wrapper.commit_fixture("reconstruct task")
        worker = self.wrapper.invoke([
            "bash", "scripts/spawn-worker.sh", "codex", f"{MISSION}/tasks/T-001.md",
            "--model", "reconstruct-model", "--feature", "F001",
        ], env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        self.run_id = max(
            (path for path in (self.root / ".tasks/receipts").glob("*.json")
             if json.loads(path.read_text())["role"] == "worker"),
            key=lambda path: path.stat().st_mtime_ns,
        ).stem
        verified = self.wrapper.invoke(
            ["bash", "scripts/verify-mission.sh", "--run-id", self.run_id, MISSION])
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.wrapper.commit_fixture("verification record")
        self.assertTrue((self.root / ".tasks/ledger" / f"{self.run_id}.json").is_file())

    def tearDown(self):
        os.chdir(self.cwd)
        self.wrapper.tearDown()

    def invoke(self, *argv, stderr=False):
        stdout = io.StringIO()
        stderr_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr_buf):
            code = reconstruct_run.main(list(argv))
        if stderr:
            return code, stdout.getvalue(), stderr_buf.getvalue()
        return code, stdout.getvalue()

    def test_run_ids_with_all_exit_two_and_touch_nothing(self):
        before = tree_snapshot(self.root)
        code, stdout, stderr = self.invoke(MISSION, self.run_id, "--all", stderr=True)
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr.strip(), "ERROR: reconstruct: run ids and --all cannot be combined")
        self.assertEqual(tree_snapshot(self.root), before)

    def test_no_run_ids_and_no_all_exit_two(self):
        code, _, stderr = self.invoke(MISSION, stderr=True)
        self.assertEqual(code, 2)
        self.assertEqual(stderr.strip(), "ERROR: no runs selected")

    def test_parser_builds_under_python312_group_rules(self):
        original = argparse._MutuallyExclusiveGroup._add_action

        def strict(group, action):
            if action.required or not action.option_strings:
                raise ValueError("mutually exclusive arguments must be optional")
            return original(group, action)

        with mock.patch.object(argparse._MutuallyExclusiveGroup, "_add_action", strict):
            code, _ = self.invoke(MISSION, self.run_id)
        self.assertEqual(code, 0)

    def spec_raw(self):
        path = self.root / ".tasks/specs" / f"{self.run_id}.json"
        return path.read_bytes()

    def receipt_doc(self):
        return json.loads((self.root / ".tasks/receipts" / f"{self.run_id}.json").read_text())

    def test_complete_fixture_exits_zero_and_prints_evidence(self):
        code, output = self.invoke(MISSION, self.run_id)
        self.assertEqual(code, 0, output)
        receipt = self.receipt_doc()
        spec, raw = execution_spec.load_persisted(self.root / ".tasks/specs" / f"{self.run_id}.json")
        self.assertIn(f"seat: {spec['provider']} / {spec['model']} / {spec['effort']} / {spec['speed']}", output)
        self.assertIn(f"sha256={hashlib.sha256(raw).hexdigest()}", output)
        self.assertIn(f"receipt: {receipt['outcome']} exit={receipt['exit_code']}", output)
        self.assertIn(f"commits={json.dumps(receipt['commits'])}", output)
        observed = receipt["observation"]["observed_model"]
        self.assertIn(f"observed model: {observed['value']} (source={observed['source']})", output)
        record_path = self.root / MISSION / "verification" / f"{self.run_id}.json"
        record, record_raw = verification_record.load_record(record_path)
        expected_record = (
            f"  VerificationRecord {record_path.name}: {record['result']} "
            f"sha256={hashlib.sha256(record_raw).hexdigest()}"
        )
        self.assertIn(expected_record, output.splitlines())
        ledger_path = self.root / ".tasks/ledger" / f"{self.run_id}.json"
        self.assertIn(f"  ledger: {ledger_path.resolve()} VALID", output.splitlines())

    def test_each_missing_artifact_exits_one_and_names_it(self):
        cases = (
            (self.root / ".tasks/specs" / f"{self.run_id}.json", "spec"),
            (self.root / ".tasks/receipts" / f"{self.run_id}.json", "receipt"),
            (self.root / MISSION / "verification" / f"{self.run_id}.json", "VerificationRecord"),
            (self.root / ".tasks/ledger" / f"{self.run_id}.json", "ledger row"),
        )
        for path, name in cases:
            with self.subTest(name=name):
                backup = path.read_bytes()
                path.unlink()
                code, output = self.invoke(MISSION, self.run_id)
                self.assertEqual(code, 1, output)
                self.assertIn(f"MISSING {self.run_id}: {name}", output)
                path.write_bytes(backup)

    def test_multiple_gaps_list_all_of_them(self):
        (self.root / ".tasks/specs" / f"{self.run_id}.json").unlink()
        (self.root / ".tasks/receipts" / f"{self.run_id}.json").unlink()
        code, output = self.invoke(MISSION, self.run_id)
        self.assertEqual(code, 1, output)
        self.assertIn(f"MISSING {self.run_id}: spec", output)
        self.assertIn(f"MISSING {self.run_id}: receipt", output)

    def test_invalid_receipt_run_id_is_reported_not_crashed(self):
        path = self.root / ".tasks/receipts" / f"{self.run_id}.json"
        receipt = json.loads(path.read_text())
        receipt["run_id"] = RUN
        path.chmod(0o600)
        path.write_bytes(execution_receipt.canonical_bytes(receipt))
        code, output = self.invoke(MISSION, self.run_id)
        self.assertEqual(code, 1, output)
        self.assertIn("receipt: INVALID", output)
        self.assertIn(f"MISSING {self.run_id}: receipt (invalid)", output)

    def test_two_verification_records_are_listed(self):
        second = self.wrapper.invoke(
            ["bash", "scripts/verify-mission.sh", "--run-id", self.run_id, MISSION])
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        code, output = self.invoke(MISSION, self.run_id)
        self.assertEqual(code, 0, output)
        expected = {}
        for name in (f"{self.run_id}.json", f"{self.run_id}.2.json"):
            path = self.root / MISSION / "verification" / name
            record, raw = verification_record.load_record(path)
            expected[name] = (
                f"  VerificationRecord {name}: {record['result']} "
                f"sha256={hashlib.sha256(raw).hexdigest()}"
            )
        self.assertIn(f"VerificationRecord {self.run_id}.json:", output)
        self.assertIn(f"VerificationRecord {self.run_id}.2.json:", output)
        for line in expected.values():
            self.assertIn(line, output.splitlines())

    def test_hostile_run_ids_exit_two_without_echoing_id(self):
        hostile = ("../x", "x/y", RUN.upper(), "", "a" * 300)
        for run_id in hostile:
            with self.subTest(run_id=repr(run_id)):
                before = tree_snapshot(self.root)
                code, _out, err = self.invoke(MISSION, run_id, stderr=True)
                self.assertEqual(code, 2, err)
                self.assertEqual(err.strip(), "ERROR: reconstruct: invalid run id")
                if run_id:
                    self.assertNotIn(run_id, err)
                self.assertEqual(tree_snapshot(self.root), before)

    def test_symlinked_ledger_row_exits_one(self):
        path = self.root / ".tasks/ledger" / f"{self.run_id}.json"
        real = path.read_bytes()
        path.unlink()
        target = self.root / ".tasks/ledger" / "real-row.json"
        target.write_bytes(real)
        path.symlink_to(target.name)
        code, output = self.invoke(MISSION, self.run_id)
        self.assertEqual(code, 1, output)
        self.assertIn(f"MISSING {self.run_id}: ledger row (not a regular file)", output)

    def test_directory_ledger_row_exits_one(self):
        path = self.root / ".tasks/ledger" / f"{self.run_id}.json"
        path.unlink()
        path.mkdir()
        code, output = self.invoke(MISSION, self.run_id)
        self.assertEqual(code, 1, output)
        self.assertIn(f"MISSING {self.run_id}: ledger row (not a regular file)", output)

    def test_read_only_fixture_tree(self):
        before = tree_snapshot(self.root)
        code, output = self.invoke(MISSION, self.run_id)
        self.assertEqual(code, 0, output)
        self.assertEqual(tree_snapshot(self.root), before)

    def test_all_enumerates_mission_receipts_and_skips_other_missions(self):
        other = self.root / OTHER_MISSION
        other.mkdir(parents=True)
        (other / "GOAL.md").write_text("---\nstatus: in-progress\n---\n# Other\n")
        foreign_id = RUN
        foreign = {
            "schema_version": 2,
            "run_id": foreign_id,
            "mission": OTHER_MISSION,
            "role": "worker",
            "outcome": "completed",
        }
        (self.root / ".tasks/receipts" / f"{foreign_id}.json").write_text(
            json.dumps(foreign, sort_keys=True) + "\n")
        self.wrapper.commit_fixture("before second worker")
        second = self.wrapper.invoke([
            "bash", "scripts/spawn-worker.sh", "codex", f"{MISSION}/tasks/T-001.md",
            "--model", "reconstruct-model", "--feature", "F001",
        ], env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        second_id = max(
            (path for path in (self.root / ".tasks/receipts").glob("*.json")
             if json.loads(path.read_text())["role"] == "worker" and path.stem != self.run_id),
            key=lambda path: path.stat().st_mtime_ns,
        ).stem
        verified = self.wrapper.invoke(
            ["bash", "scripts/verify-mission.sh", "--run-id", second_id, MISSION])
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.wrapper.commit_fixture("second verification")
        code, output = self.invoke(MISSION, "--all")
        self.assertEqual(code, 0, output)
        self.assertIn(f"RUN {self.run_id}", output)
        self.assertIn(f"RUN {second_id}", output)
        self.assertNotIn(f"RUN {foreign_id}", output)

    def test_all_exits_one_when_one_run_lacks_an_artifact(self):
        (self.root / ".tasks/ledger" / f"{self.run_id}.json").unlink()
        code, output = self.invoke(MISSION, "--all")
        self.assertEqual(code, 1, output)
        self.assertIn(f"MISSING {self.run_id}: ledger row", output)

    def test_all_rejects_invalid_id_without_echoing_it(self):
        invalid_id = "not-a-canonical-uuid"
        receipt = {
            "mission": MISSION,
            "run_id": RUN,
        }
        (self.root / ".tasks/receipts" / f"{invalid_id}.json").write_text(
            json.dumps(receipt) + "\n"
        )
        code, _out, err = self.invoke(MISSION, "--all", stderr=True)
        self.assertEqual(code, 2, err)
        self.assertEqual(err.strip(), "ERROR: reconstruct: invalid run id")
        self.assertNotIn(invalid_id, err)

    def test_all_skips_symlinked_receipt(self):
        link_id = "89abcdef-0123-4567-89ab-cdef01234567"
        target = self.root / "outside-receipt.json"
        target.write_text(json.dumps({"mission": MISSION, "run_id": link_id}) + "\n")
        link = self.root / ".tasks/receipts" / f"{link_id}.json"
        link.symlink_to(target)
        code, output = self.invoke(MISSION, "--all")
        self.assertEqual(code, 0, output)
        self.assertNotIn(f"RUN {link_id}", output)


if __name__ == "__main__":
    unittest.main()
