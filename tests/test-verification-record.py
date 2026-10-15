#!/usr/bin/env python3
"""Mounted entry-point regressions for immutable VerificationRecord acceptance."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("execution_integration", ROOT / "tests/test-execution-integration.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VerificationRecordIntegration(unittest.TestCase):
    def setUp(self):
        self.fixture = module.WrapperIntegration("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.write_fleet("codex", "model", "medium", "unknown", include_brain=True)
        brain = self.fixture.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"])
        self.assertEqual(brain.returncode, 0, brain.stderr + brain.stdout)
        worker = self.fixture.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--model", "model", "--feature", "F001"], env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        self.run_id = next(path.stem for path in (self.fixture.root / ".tasks/receipts").glob("*.json") if json.loads(path.read_text())["role"] == "worker")
        self.mission = "docs/missions/fixture"

    def call(self, *args, env=None):
        return self.fixture.invoke(list(args), env=env)

    def make_run_with_check(self, argv, extra_env=None):
        self.fixture.task.write_text(
            "---\ntask_id: T-001\nfeature: F001\n---\n# Task\n\n"
            "## Files you MAY touch\n- `allowed.txt`\n\n## Verification commands\n"
            f"\n- `{json.dumps(argv)}`\n")
        self.fixture.commit_fixture("verification command fixture")
        worker_env = {"PROVIDER_ACTION": "commit"}
        if extra_env:
            worker_env.update(extra_env)
        worker = self.call("bash", "scripts/spawn-worker.sh", "codex",
                           "docs/missions/fixture/tasks/T-001.md", "--model", "model",
                           "--feature", "F001", env=worker_env)
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        return max((path for path in (self.fixture.root / ".tasks/receipts").glob("*.json")
                    if json.loads(path.read_text())["role"] == "worker"),
                   key=lambda path: path.stat().st_mtime_ns).stem

    def test_verification_uses_receipt_commit_when_live_tree_is_later_and_dirty(self):
        run_id = self.make_run_with_check(["true"])
        receipt = json.loads((self.fixture.root / ".tasks/receipts" / f"{run_id}.json").read_text())
        (self.fixture.root / "later.txt").write_text("committed later state\n")
        self.fixture.commit_fixture("later live commit")
        (self.fixture.root / "untracked-later.txt").write_text("live-only state\n")
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = json.loads((self.fixture.mission / "verification" / f"{run_id}.json").read_text())
        self.assertEqual(record["result"], "pass")
        live_head = subprocess.run(["git", "-C", str(self.fixture.root), "rev-parse", "HEAD"],
                                   check=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(record["verification_git_before"]["head"], receipt["git_after"]["head"])
        self.assertNotEqual(record["verification_git_before"]["head"], live_head)

    def test_check_changing_worktree_fails_and_live_tree_stays_clean_of_check_artifacts(self):
        run_id = self.make_run_with_check(["bash", "-c", "touch check-stray.txt"])
        before_worktrees = self.call("git", "worktree", "list", "--porcelain")
        self.assertEqual(before_worktrees.returncode, 0)
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", run_id, self.mission)
        self.assertNotEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = json.loads((self.fixture.mission / "verification" / f"{run_id}.json").read_text())
        self.assertEqual(record["result"], "fail")
        self.assertFalse((self.fixture.root / "check-stray.txt").exists())
        self.assertFalse((self.fixture.root / "scripts/__pycache__").exists())
        self.assertFalse((self.fixture.root / "tests/__pycache__").exists())
        status = self.call("git", "status", "--porcelain", "--untracked-files=all")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(status.stdout.splitlines(),
                         [f"?? docs/missions/fixture/verification/{run_id}.json"])
        listed = self.call("git", "worktree", "list", "--porcelain")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(sum(line.startswith("worktree ") for line in listed.stdout.splitlines()), 1)

    def test_dirty_receipt_git_after_is_refused(self):
        receipt_path = self.fixture.root / ".tasks/receipts" / f"{self.run_id}.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["git_after"]["status_entry_count"] = 1
        # The provider committed allowed.txt, so retaining it as the recorded dirty
        # path keeps changed_paths and scope internally consistent.
        receipt["git_after"]["dirty_paths"] = ["allowed.txt"]
        receipt_path.chmod(0o600)
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        denied = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertNotEqual(denied.returncode, 0, denied.stderr + denied.stdout)
        self.assertIn("worktree verification needs a clean receipt git_after", denied.stderr + denied.stdout)
        self.assertFalse((self.fixture.mission / "verification" / f"{self.run_id}.json").exists())

    def test_post_checkout_hook_dirtied_worktree_is_refused_before_checks(self):
        hook = self.fixture.root / ".git/hooks/post-checkout"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\nprintf stray > hook-stray.txt\n")
        hook.chmod(0o755)
        denied = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertNotEqual(denied.returncode, 0, denied.stderr + denied.stdout)
        self.assertIn("verification worktree snapshot does not equal receipt git_after before checks",
                      denied.stderr + denied.stdout)
        self.assertFalse((self.fixture.mission / "verification" / f"{self.run_id}.json").exists())
        listed = self.call("git", "worktree", "list", "--porcelain")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(sum(line.startswith("worktree ") for line in listed.stdout.splitlines()), 1)
        self.assertFalse((self.fixture.root / "hook-stray.txt").exists())

    def test_sigterm_during_verify_leaves_no_worktree_or_temp_dir(self):
        with tempfile.TemporaryDirectory(prefix="verification-sigterm-") as temp_dir:
            marker = Path(temp_dir) / "verify-started.marker"
            run_id = self.make_run_with_check(
                ["bash", "-c", 'touch "$MARKER"; exec sleep 60'],
                extra_env={"MARKER": str(marker)},
            )
            proc = subprocess.Popen(
                [sys.executable, "scripts/verification_record.py", "verify", "--run-id", run_id, self.mission],
                cwd=self.fixture.root,
                env={**os.environ, "TMPDIR": temp_dir, "PYTHONDONTWRITEBYTECODE": "1", "MARKER": str(marker)},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if marker.is_file():
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
            self.assertTrue(marker.is_file(), "verifier never reached the sleeping check")
            proc.send_signal(signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 143, (stdout + stderr).decode("utf-8", "replace"))
            self.assertFalse((self.fixture.mission / "verification" / f"{run_id}.json").exists())
            listed = self.call("git", "worktree", "list", "--porcelain")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(sum(line.startswith("worktree ") for line in listed.stdout.splitlines()), 1)
            self.assertEqual(list(Path(temp_dir).glob("purrfect-verify-*")), [])

    def test_live_root_environment_points_outside_check_worktree(self):
        run_id = self.make_run_with_check(["bash", "-c", "test -n \"$PURRFECT_LIVE_ROOT\" && test \"$PURRFECT_LIVE_ROOT\" != \"$(pwd -P)\" && test -d \"$PURRFECT_LIVE_ROOT/.git\""])
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = json.loads((self.fixture.mission / "verification" / f"{run_id}.json").read_text())
        self.assertEqual(record["result"], "pass")

    def test_real_run_verification_is_immutable_and_acceptance_is_separate(self):
        before_features = (self.fixture.mission / "features.json").read_bytes()
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.assertEqual((self.fixture.mission / "features.json").read_bytes(), before_features)
        record = self.fixture.mission / "verification" / f"{self.run_id}.json"
        raw = record.read_bytes(); doc = json.loads(raw)
        self.assertEqual(doc["result"], "pass")
        self.assertNotIn("accepted_by", doc)
        self.assertEqual(oct(record.stat().st_mode & 0o777), "0o400")
        duplicate = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertNotEqual(duplicate.returncode, 0)
        good_hash = hashlib.sha256(raw).hexdigest()
        bad_hash = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id, "--verification-sha256", "0" * 64, "--accepted-by", "reviewer", self.mission)
        self.assertNotEqual(bad_hash.returncode, 0)
        locked = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id, "--verification-sha256", good_hash, "--accepted-by", "reviewer", self.mission, env={"PURRFECT_DISPATCH_LOCK_PATH": "/tmp/active-lock"})
        self.assertNotEqual(locked.returncode, 0)
        # A real lock directory is as authoritative as the dispatch environment.
        lock = self.fixture.root / ".tasks/locks/active.lock"
        lock.mkdir(parents=True)
        locked_dir = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id, "--verification-sha256", good_hash, "--accepted-by", "reviewer", self.mission, env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertNotEqual(locked_dir.returncode, 0)
        lock.rmdir()
        features_path = self.fixture.mission / "features.json"
        features_path.chmod(0o640)
        accepted = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id, "--verification-sha256", good_hash, "--accepted-by", "reviewer", self.mission, env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout + repr(list((self.fixture.root / ".tasks/locks").glob("*"))))
        self.assertEqual(features_path.stat().st_mode & 0o777, 0o640)
        feature = json.loads(features_path.read_text())["features"][0]
        self.assertEqual(feature["accepted_run_id"], self.run_id)
        self.assertEqual(feature["accepted_verification_sha256"], good_hash)
        audited = self.call("bash", "scripts/verify-mission.sh", "--require-workers", self.mission)
        self.assertEqual(audited.returncode, 0, audited.stderr + audited.stdout)

    def test_unrelated_live_git_change_does_not_invalidate_receipt_worktree(self):
        (self.fixture.root / "unrelated.txt").write_text("must invalidate verification\n")
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = json.loads((self.fixture.mission / "verification" / f"{self.run_id}.json").read_text())
        self.assertEqual(record["result"], "pass")

    def test_rehashed_cross_feature_record_fails_real_acceptance_and_audit(self):
        """The supplied hash asserts bytes; it cannot authorize a re-bound identity."""
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record_path = self.fixture.mission / "verification" / f"{self.run_id}.json"
        record_path.chmod(0o600)
        forged = json.loads(record_path.read_text())
        forged["feature"] = "F002"
        forged_raw = (json.dumps(forged, sort_keys=True, separators=(",", ":")) + "\n").encode()
        record_path.write_bytes(forged_raw)
        forged_hash = hashlib.sha256(forged_raw).hexdigest()
        denied = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id,
                           "--verification-sha256", forged_hash, "--accepted-by", "reviewer", self.mission,
                           env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertNotEqual(denied.returncode, 0, denied.stderr + denied.stdout)
        features_path = self.fixture.mission / "features.json"
        features = json.loads(features_path.read_text())
        feature = features["features"][1]
        feature.update({"passes": True, "accepted_run_id": self.run_id,
                        "accepted_verification_sha256": forged_hash,
                        "accepted_at": "2026-09-03T00:00:00Z", "accepted_by": "reviewer"})
        features_path.write_text(json.dumps(features, indent=2) + "\n")
        audited = self.call("bash", "scripts/verify-mission.sh", "--require-workers", self.mission)
        self.assertNotEqual(audited.returncode, 0, audited.stderr + audited.stdout)
        self.assertIn("feature", audited.stderr + audited.stdout)

    def test_real_verifier_rejects_non_markdown_command_bullets_at_receipt_base(self):
        task = self.fixture.task.parent / "T-002.md"
        task.write_text("---\ntask_id: T-002\nfeature: F002\n---\n# Task\n\n## Files you MAY touch\n- `allowed.txt`\n\n## Verification commands\n- [\"git\",\"status\"]\n")
        self.fixture.commit_fixture("malformed verification command fixture")
        worker = self.call("bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-002.md",
                           "--model", "model", "--feature", "F002", env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        run_id = next(path.stem for path in (self.fixture.root / ".tasks/receipts").glob("*.json")
                      if json.loads(path.read_text())["feature"] == "F002")
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", run_id, self.mission)
        self.assertNotEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.assertIn("Markdown JSON code span", verified.stderr + verified.stdout)

    def test_launch_error_persists_a_failed_record(self):
        task = self.fixture.task.parent / "T-002.md"
        task.write_text("---\ntask_id: T-002\nfeature: F002\n---\n# Task\n\n## Files you MAY touch\n- `allowed.txt`\n\n## Verification commands\n\n- `[\"definitely-not-a-command\"]`\n")
        self.fixture.commit_fixture("launch failure verification command fixture")
        worker = self.call("bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-002.md",
                           "--model", "model", "--feature", "F002", env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        run_id = next(path.stem for path in (self.fixture.root / ".tasks/receipts").glob("*.json")
                      if json.loads(path.read_text())["feature"] == "F002")
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", run_id, self.mission)
        self.assertNotEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = json.loads((self.fixture.mission / "verification" / f"{run_id}.json").read_text())
        self.assertEqual(record["result"], "fail")
        self.assertEqual(record["commands"][0]["exit_code"], 127)

    def test_revalidation_rejects_every_bound_identity_state_and_hash(self):
        """Canonical rehashing cannot turn any weaker record value into authority."""
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record_path = self.fixture.mission / "verification" / f"{self.run_id}.json"
        raw = record_path.read_bytes()
        good_hash = hashlib.sha256(raw).hexdigest()
        accepted = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id,
                             "--verification-sha256", good_hash, "--accepted-by", "reviewer", self.mission,
                             env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
        features_path = self.fixture.mission / "features.json"
        feature_doc = json.loads(features_path.read_text())

        def mutate(doc, label):
            if label == "mission": doc["mission"] = "docs/missions/other"
            elif label == "feature": doc["feature"] = "F002"
            elif label == "work_unit": doc["work_unit"] = "T-002"
            elif label == "attempt": doc["attempt"] = 2
            elif label == "spec_hash": doc["execution_spec"]["sha256"] = "0" * 64
            elif label == "receipt_hash": doc["execution_receipt"]["sha256"] = "0" * 64
            elif label == "task_hash": doc["task"]["sha256"] = "0" * 64
            elif label == "task_commit": doc["task"]["git_commit"] = "0" * 40
            elif label == "receipt_snapshot": doc["receipt_git_after"]["head"] = "0" * 40
            elif label == "before_snapshot": doc["verification_git_before"]["head"] = "0" * 40
            elif label == "after_snapshot": doc["verification_git_after"]["head"] = "0" * 40
            elif label == "argv": doc["commands"][0]["argv"] = ["false"]
            elif label == "outcome": doc["commands"][0]["exit_code"] = 1
            elif label == "timestamp": doc["commands"][0]["finished_at"] = "2000-01-01T00:00:00Z"
            else: raise AssertionError(label)

        labels = ("mission", "feature", "work_unit", "attempt", "spec_hash", "receipt_hash", "task_hash",
                  "task_commit", "receipt_snapshot", "before_snapshot", "after_snapshot", "argv", "outcome", "timestamp")
        for label in labels:
            with self.subTest(label=label):
                record_path.chmod(0o600)
                doc = json.loads(raw)
                mutate(doc, label)
                record_path.write_bytes((json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode())
                feature_doc["features"][0]["accepted_verification_sha256"] = hashlib.sha256(record_path.read_bytes()).hexdigest()
                features_path.write_text(json.dumps(feature_doc, indent=2) + "\n")
                audited = self.call("bash", "scripts/verify-mission.sh", "--require-workers", self.mission)
                self.assertNotEqual(audited.returncode, 0, label + ": " + audited.stderr + audited.stdout)
                # Rehashing proves the caller-supplied hash is only an assertion.
                forged_hash = hashlib.sha256(record_path.read_bytes()).hexdigest()
                denied = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id,
                                   "--verification-sha256", forged_hash, "--accepted-by", "reviewer", self.mission,
                                   env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
                self.assertNotEqual(denied.returncode, 0, label + ": " + denied.stderr + denied.stdout)
                record_path.write_bytes(raw)
                record_path.chmod(0o400)
                feature_doc["features"][0]["accepted_verification_sha256"] = good_hash
                features_path.write_text(json.dumps(feature_doc, indent=2) + "\n")

    def test_validator_rejects_weakest_values_and_schema_declares_them(self):
        """Keep the dependency-free executable validator and shipped schema aligned."""
        policy_spec = importlib.util.spec_from_file_location("verification_record", ROOT / "scripts/verification_record.py")
        policy = importlib.util.module_from_spec(policy_spec)
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            policy_spec.loader.exec_module(policy)
        finally:
            sys.path.pop(0)
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        valid = json.loads((self.fixture.mission / "verification" / f"{self.run_id}.json").read_text())
        schema = json.loads((ROOT / "schemas/verification-record.schema.json").read_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), policy.RECORD_FIELDS)
        self.assertEqual(schema["properties"]["commands"]["minItems"], 1)
        self.assertEqual(schema["$defs"]["gitState"]["additionalProperties"], False)
        task_pattern = schema["$defs"]["taskLink"]["properties"]["path"]["pattern"]
        receipt_pattern = schema["$defs"]["receiptLink"]["allOf"][1]["properties"]["path"]["pattern"]
        self.assertTrue(re.fullmatch(task_pattern, valid["task"]["path"]))
        self.assertTrue(re.fullmatch(receipt_pattern, valid["execution_receipt"]["path"]))
        weakest = (
            ("empty argv", lambda d: d["commands"][0].update(argv=[])),
            ("empty command item", lambda d: d["commands"][0].update(argv=[""])),
            ("empty task path", lambda d: d["task"].update(path="")),
            ("absolute task path", lambda d: d["task"].update(path="/tmp/task.md")),
            ("traversing task path", lambda d: d["task"].update(path="docs/../task.md")),
            ("newline task path", lambda d: d["task"].update(path="docs/tasks/one\ntwo.md")),
            ("edge whitespace task path", lambda d: d["task"].update(path=" docs/tasks/T-001.md")),
            ("noncanonical receipt UUID", lambda d: d["execution_receipt"].update(path=".tasks/receipts/not-a-uuid.json")),
            ("negative snapshot count", lambda d: d["receipt_git_after"].update(status_entry_count=-1)),
            ("undeclared property", lambda d: d.update(extra=None)),
        )
        for name, change in weakest:
            with self.subTest(name=name):
                candidate = json.loads(json.dumps(valid))
                change(candidate)
                with self.assertRaises(policy.VerificationError):
                    policy.validate_record(candidate)
        valid_with_internal_space = json.loads(json.dumps(valid))
        valid_with_internal_space["task"]["path"] = "docs/missions/fixture/tasks/T 001.md"
        self.assertEqual(policy.validate_record(valid_with_internal_space), valid_with_internal_space)
        malformed = (
            ("non-string run id", lambda d: d.update(run_id=1)),
            ("non-string result", lambda d: d.update(result=[])),
            ("non-string receipt hash", lambda d: d["execution_receipt"].update(sha256=1)),
            ("non-string task path", lambda d: d["task"].update(path=1)),
            ("non-string task commit", lambda d: d["task"].update(git_commit=1)),
            ("non-object command", lambda d: d.update(commands=[1])),
            ("non-string command timestamp", lambda d: d["commands"][0].update(started_at=1)),
        )
        for name, change in malformed:
            with self.subTest(name=name):
                candidate = json.loads(json.dumps(valid))
                change(candidate)
                with self.assertRaises(policy.VerificationError):
                    policy.validate_record(candidate)

    def test_audit_rejects_invalid_or_stale_acceptance_metadata_before_record_loading(self):
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = self.fixture.mission / "verification" / f"{self.run_id}.json"
        good_hash = hashlib.sha256(record.read_bytes()).hexdigest()
        accepted = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id,
                             "--verification-sha256", good_hash, "--accepted-by", "reviewer", self.mission,
                             env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
        features_path = self.fixture.mission / "features.json"
        accepted_doc = json.loads(features_path.read_text())
        cases = (
            ("nonboolean passes", lambda f: f.update(passes=1)),
            ("stale false acceptance", lambda f: f.update(passes=False)),
            ("bad run UUID", lambda f: f.update(accepted_run_id="bad")),
            ("uppercase hash", lambda f: f.update(accepted_verification_sha256=good_hash.upper())),
            ("non-UTC timestamp", lambda f: f.update(accepted_at="2026-09-03T00:00:00+00:00")),
            ("blank accepted by", lambda f: f.update(accepted_by=" reviewer ")),
            ("non-string run UUID", lambda f: f.update(accepted_run_id=1)),
            ("non-string acceptance hash", lambda f: f.update(accepted_verification_sha256=1)),
            ("non-string timestamp", lambda f: f.update(accepted_at=1)),
            ("non-string accepted by", lambda f: f.update(accepted_by=1)),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                doc = json.loads(json.dumps(accepted_doc))
                mutate(doc["features"][0])
                features_path.write_text(json.dumps(doc, indent=2) + "\n")
                audited = self.call("bash", "scripts/verify-mission.sh", "--require-workers", self.mission)
                self.assertNotEqual(audited.returncode, 0, label + ": " + audited.stderr + audited.stdout)
                self.assertIn("feature F001", audited.stderr + audited.stdout)
        features_path.write_text(json.dumps(accepted_doc, indent=2) + "\n")

    def test_wrong_acceptance_hash_is_rejected_at_the_real_entry_point(self):
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        denied = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id,
                           "--verification-sha256", "0" * 64, "--accepted-by", "reviewer", self.mission,
                           env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertNotEqual(denied.returncode, 0, denied.stderr + denied.stdout)

    def test_required_guard_mutations_break_the_real_focused_entry_and_restore(self):
        """Every named authority guard is mounted: removing it breaks a real test entry."""
        # The focused test below loads its policy from its own repository root.
        # Give it a private copy so guard mutations can never affect this checkout.
        with tempfile.TemporaryDirectory(prefix="verification-guard-mutation-") as temp_dir:
            temp_root = Path(temp_dir)
            for directory in ("scripts", "tests", "schemas", "docs/missions/templates"):
                shutil.copytree(ROOT / directory, temp_root / directory)
            shutil.copy2(ROOT / "harness-registry.json", temp_root / "harness-registry.json")
            self._assert_guard_mutations_break_focused_entries(temp_root)

    def _assert_guard_mutations_break_focused_entries(self, temp_root):
        policy = temp_root / "scripts/verification_record.py"
        original = policy.read_text()
        mutations = (
            ("task-at-base", 'if not line.startswith("- `") or not line.endswith("`") or line.count("`") != 2:\n            fail("verification command must be one Markdown JSON code span bullet")\n        try: argv = json.loads(line[3:-1])',
             'if False:\n            fail("verification command must be one Markdown JSON code span bullet")\n        try: argv = json.loads(line[2:])', "test_real_verifier_rejects_non_markdown_command_bullets_at_receipt_base"),
            ("spec-hash", '"execution_spec": {"path": str(spec_path), "sha256": digest(spec_raw)},',
             '"execution_spec": {"path": str(spec_path), "sha256": record["execution_spec"]["sha256"]},', "test_revalidation_rejects_every_bound_identity_state_and_hash"),
            ("receipt-hash", '"execution_receipt": {"path": receipt_path.relative_to(root).as_posix(), "sha256": digest(receipt_path.read_bytes())},',
             '"execution_receipt": {"path": receipt_path.relative_to(root).as_posix(), "sha256": record["execution_receipt"]["sha256"]},', "test_revalidation_rejects_every_bound_identity_state_and_hash"),
            ("identity-rebind", 'for key, value in expected.items():', 'for key, value in ():', "test_revalidation_rejects_every_bound_identity_state_and_hash"),
            ("snapshot-rebind", 'if record["verification_git_before"] != receipt["git_after"] or record["verification_git_after"] != receipt["git_after"]:',
             'if False:', "test_revalidation_rejects_every_bound_identity_state_and_hash"),
            ("snapshot-pre-post", 'if before != receipt["git_after"]:\n            fail("verification worktree snapshot does not equal receipt git_after before checks")',
             'if False:\n            pass', "test_check_changing_worktree_fails_and_live_tree_stays_clean_of_check_artifacts"),
            ("snapshot-pre", 'if before != receipt["git_after"]:\n            fail("verification worktree snapshot does not equal receipt git_after before checks")',
             'if False:\n            pass', "test_post_checkout_hook_dirtied_worktree_is_refused_before_checks"),
            ("dirty-receipt-refusal", 'if receipt["git_after"]["status_entry_count"] != 0 or receipt["git_after"]["dirty_paths"]:',
             'if False:', "test_dirty_receipt_git_after_is_refused"),
            ("worktree-cwd", "cwd=worktree", "cwd=root", "test_check_changing_worktree_fails_and_live_tree_stays_clean_of_check_artifacts"),
            ("sigterm-cleanup", "prev_sigterm = signal.signal(signal.SIGTERM, on_sigterm)",
             "prev_sigterm = None", "test_sigterm_during_verify_leaves_no_worktree_or_temp_dir"),
            ("lock", 'if os.environ.get("PURRFECT_DISPATCH_LOCK_PATH") or (lock_dir.is_dir() and list(lock_dir.glob("*.lock"))):',
             'if False:', "test_real_run_verification_is_immutable_and_acceptance_is_separate"),
            ("acceptance-hash", 'if digest(raw) != expected_hash or record["result"] != "pass":',
             'if record["result"] != "pass":', "test_wrong_acceptance_hash_is_rejected_at_the_real_entry_point"),
        )
        selected = os.environ.get("GUARD_MUTATION_LABEL")
        for label, old, new, target in mutations:
            if selected and label != selected:
                continue
            with self.subTest(label=label):
                source = original
                if label in {"spec-hash", "receipt-hash"}:
                    start = source.index("def revalidate_record")
                    prefix, revalidation = source[:start], source[start:]
                    self.assertIn(old, revalidation)
                    source = prefix + revalidation.replace(old, new, 1)
                elif label == "snapshot-pre-post":
                    self.assertIn(old, source)
                    self.assertIn('if after != receipt["git_after"]: passed = False', source)
                    source = source.replace(old, new, 1).replace('if after != receipt["git_after"]: passed = False', 'if False: passed = False', 1)
                elif label == "snapshot-pre":
                    self.assertIn(old, source)
                    source = source.replace(old, new, 1)
                else:
                    self.assertIn(old, source)
                    source = source.replace(old, new, 1)
                policy.write_text(source)
                try:
                    result = subprocess.run([sys.executable, "tests/test-verification-record.py",
                                             f"VerificationRecordIntegration.{target}"], cwd=temp_root,
                                            # Run from the temporary copy containing the mutated guard.
                                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                                            text=True, capture_output=True)
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, label + ": guard mutation did not break real entry\n" + output)
                    self.assertIn("AssertionError", output, label + ": mutation failed before its test assertion\n" + output)
                    self.assertNotIn("NameError", output, label + ": mutation produced a construction error\n" + output)
                    self.assertNotIn("SyntaxError", output, label + ": mutation produced a syntax error\n" + output)
                    self.assertNotIn("IndentationError", output, label + ": mutation produced an indentation error\n" + output)
                    self.assertNotIn("TabError", output, label + ": mutation produced a tab error\n" + output)
                    self.assertNotIn("\nERROR", output, label + ": mutation produced a test setup error\n" + output)
                finally:
                    policy.write_text(original)
                self.assertEqual(policy.read_text(), original)


class ShippedWorkerTemplateIntegration(unittest.TestCase):
    """The distributed template must authorize a usable real worker run."""

    def setUp(self):
        self.fixture = module.WrapperIntegration("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.write_fleet("codex", "model", "medium", "unknown", include_brain=True)
        self.mission = "docs/missions/fixture"

    def render_template(self):
        values = {
            "NNN": "001", "F00X": "F001", "F00X from features.json": "F001",
            "WORKER": "codex", "INVOCATION": "codex economy / model / medium / unknown",
            "MISSION": self.mission, "slug": "fixture", "ALLOWED_PATH": "allowed.txt",
            "DENIED_PATH": "outside.txt", "SKILL_PATH": ".agents/skills/guard-verification/SKILL.md",
            "BASELINE_CMD": "git status --porcelain", "OBJECTIVE": "Change allowed.txt only.",
            "VERIFY_ARGV": json.dumps(["python3", "-c", "from pathlib import Path; assert Path('allowed.txt').read_text().startswith('allowed change')"]),
            "COMMIT_MESSAGE": "test: template qualification (T-001)", "2": "2",
            # Keep the regression meaningful against the pre-Phase-1 template too.
            "src/pages/FundDetail.tsx": "allowed.txt",
            "src/components/fund/*": "docs/missions/fixture/PROGRESS.md",
        }
        template = (ROOT / "docs/missions/templates/WORKER_TASK.template.md").read_text()
        return re.sub(r"\{\{(.*?)\}\}", lambda match: values.get(match.group(1), "fixture"), template, flags=re.S)

    def run_template(self, task):
        self.fixture.task.write_text(task)
        self.fixture.commit_fixture("render shipped worker task")
        result = self.fixture.invoke([
            "bash", "scripts/spawn-worker.sh", "codex",
            f"{self.mission}/tasks/T-001.md", "--tier", "economy", "--feature", "F001",
        ], env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        receipt = next((self.fixture.root / ".tasks/receipts").glob("*.json"))
        return receipt.stem

    def test_rendered_shipped_template_verifies_through_real_entry_points(self):
        run_id = self.run_template(self.render_template())
        features = (self.fixture.mission / "features.json").read_bytes()
        verified = self.fixture.invoke(["bash", "scripts/verify-mission.sh", "--run-id", run_id, self.mission])
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = json.loads((self.fixture.mission / "verification" / f"{run_id}.json").read_text())
        self.assertEqual(record["result"], "pass")
        self.assertEqual(record["commands"][0]["exit_code"], 0)
        self.assertEqual((self.fixture.mission / "features.json").read_bytes(), features)

    def test_missing_template_verification_section_is_rejected_without_record(self):
        task = re.sub(r"## Verification commands\n.*?(?=## |\Z)", "", self.render_template(), flags=re.S)
        run_id = self.run_template(task)
        verified = self.fixture.invoke(["bash", "scripts/verify-mission.sh", "--run-id", run_id, self.mission])
        self.assertNotEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.assertIn("no Verification commands section", verified.stderr + verified.stdout)
        self.assertFalse((self.fixture.mission / "verification" / f"{run_id}.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
