#!/usr/bin/env python3
"""Mounted entry-point regressions for immutable VerificationRecord acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
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
        worker = self.fixture.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--model", "model", "--feature", "F001"], env={"PROVIDER_ACTION": "dirty"})
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        self.run_id = next(path.stem for path in (self.fixture.root / ".tasks/receipts").glob("*.json") if json.loads(path.read_text())["role"] == "worker")
        self.mission = "docs/missions/fixture"

    def call(self, *args, env=None):
        return self.fixture.invoke(list(args), env=env)

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
        accepted = self.call("bash", "scripts/accept-feature.sh", "--run-id", self.run_id, "--verification-sha256", good_hash, "--accepted-by", "reviewer", self.mission, env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout + repr(list((self.fixture.root / ".tasks/locks").glob("*"))))
        feature = json.loads((self.fixture.mission / "features.json").read_text())["features"][0]
        self.assertEqual(feature["accepted_run_id"], self.run_id)
        self.assertEqual(feature["accepted_verification_sha256"], good_hash)
        audited = self.call("bash", "scripts/verify-mission.sh", "--require-workers", self.mission)
        self.assertEqual(audited.returncode, 0, audited.stderr + audited.stdout)

    def test_mount_fails_when_snapshot_binding_is_removed(self):
        policy = self.fixture.root / "scripts/verification_record.py"
        original = policy.read_text()
        self.assertIn('if before != receipt["git_after"]: fail(', original)
        policy.write_text(original.replace('if before != receipt["git_after"]: fail("current Git snapshot does not equal receipt git_after before checks")', '# snapshot guard bypass', 1).replace('if after != receipt["git_after"]: passed = False', '# snapshot guard bypass', 1))
        self.fixture.commit_fixture("snapshot guard bypass")
        (self.fixture.root / "unrelated.txt").write_text("must invalidate verification\n")
        bypassed = self.call("bash", "scripts/verify-mission.sh", "--run-id", self.run_id, self.mission)
        self.assertEqual(bypassed.returncode, 0, bypassed.stderr + bypassed.stdout)
        policy.write_text(original)
        (self.fixture.root / "unrelated.txt").unlink()
        self.fixture.commit_fixture("restore snapshot guard")

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
                           "--model", "model", "--feature", "F002", env={"PROVIDER_ACTION": "dirty"})
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
                           "--model", "model", "--feature", "F002", env={"PROVIDER_ACTION": "dirty"})
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        run_id = next(path.stem for path in (self.fixture.root / ".tasks/receipts").glob("*.json")
                      if json.loads(path.read_text())["feature"] == "F002")
        verified = self.call("bash", "scripts/verify-mission.sh", "--run-id", run_id, self.mission)
        self.assertNotEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = json.loads((self.fixture.mission / "verification" / f"{run_id}.json").read_text())
        self.assertEqual(record["result"], "fail")
        self.assertEqual(record["commands"][0]["exit_code"], 127)


if __name__ == "__main__":
    unittest.main(verbosity=2)
