#!/usr/bin/env python3
"""Mounted real-wrapper contracts for immutable execution specs and receipts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("codex", "claude", "agent", "agy")


class WrapperIntegration(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp())
        self.root = self.parent / "repo"
        self.root.mkdir()
        (self.root / "scripts").mkdir()
        for name in ("execution_spec.py", "execution_receipt.py", "execution_runner.py",
                     "execute_provider.py", "fleet_state.py", "dispatch_policy.py",
                     "spawn-worker.sh", "spawn-brain.sh", "verify-mission.sh", "verification_record.py",
                     "accept-feature.sh", "write-receipt.sh"):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        self.task = self.root / "docs/missions/fixture/tasks/T-001.md"
        self.task.parent.mkdir(parents=True)
        self.mission = self.task.parent.parent
        self.task.write_text("---\ntask_id: T-001\nfeature: F001\n---\n# Task\n\n## Files you MAY touch\n- `allowed.txt`\n- `docs/missions/fixture/PROGRESS.md`\n\n## Verification commands\n- [\"git\",\"status\",\"--porcelain\"]\n")
        (self.task.parent / "T-002.md").write_text("---\ntask_id: T-002\nfeature: F002\n---\n# Task\n\n## Files you MAY touch\n- `allowed.txt`\n- `docs/missions/fixture/PROGRESS.md`\n\n## Verification commands\n- [\"git\",\"status\",\"--porcelain\"]\n")
        (self.mission / "GOAL.md").write_text("---\nstatus: in-progress\n---\n# Goal\n")
        (self.mission / "features.json").write_text(json.dumps({
            "goal": "fixture",
            "features": [
                {"id": "F001", "description": "one", "bootstrap": False, "steps": [], "passes": False, "priority": 1},
                {"id": "F002", "description": "two", "bootstrap": False, "steps": [], "passes": False, "priority": 2},
            ],
        }, indent=2) + "\n")
        (self.root / ".gitignore").write_text(".tasks/\nbin/\nsame.json\n")
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.physical_root = subprocess.run(["bash", "-c", "pwd -P"], cwd=self.root, check=True,
                                            text=True, capture_output=True).stdout.strip()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        stub = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
specs = list(pathlib.Path('.tasks/specs').glob('*.json'))
if not specs:
    raise SystemExit('provider invoked before spec persistence')
pathlib.Path('.tasks/invoked.json').write_text(json.dumps({
    'provider': pathlib.Path(sys.argv[0]).name,
    'argv': sys.argv[1:], 'spec_existed': True,
    'lock_existed': pathlib.Path(os.environ.get('PURRFECT_DISPATCH_LOCK_PATH', '')).is_dir(),
    'pid': os.getpid(),
}))
child_path = os.environ.get('PROVIDER_CHILD_PID_PATH')
if child_path:
    import subprocess
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    pathlib.Path(child_path).write_text(str(child.pid))
wait_for = os.environ.get('PROVIDER_WAIT_FOR')
if wait_for:
    while not pathlib.Path(wait_for).exists():
        time.sleep(0.02)
action = os.environ.get('PROVIDER_ACTION', 'noop')
if action in ('dirty', 'commit', 'mixed'):
    pathlib.Path('allowed.txt').write_text(f'allowed change {time.time_ns()}\\n')
if action == 'outside':
    pathlib.Path('outside.txt').write_text('outside change\\n')
if action in ('commit', 'mixed'):
    import subprocess
    subprocess.run(['git', 'add', 'allowed.txt'], check=True)
    subprocess.run(['git', 'commit', '-qm', 'provider change'], check=True)
if action == 'mixed':
    pathlib.Path('allowed.txt').write_text(f'dirty after commit {time.time_ns()}\\n')
raise SystemExit(int(os.environ.get('PROVIDER_EXIT', '0')))
'''
        for provider in PROVIDERS:
            path = self.bin / provider
            path.write_text(stub)
            path.chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.parent)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True)

    def invoke(self, args, *, env=None):
        launch_env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                          PYTHONDONTWRITEBYTECODE="1", SPAWN_WORKER_TIMEOUT_SECS="0",
                          SPAWN_BRAIN_TIMEOUT_SECS="0",
                          EMPTY_OVERRIDE_SENTINEL="retained")
        if env:
            launch_env.update(env)
        return subprocess.run(args, cwd=self.root, env=launch_env, text=True, capture_output=True)

    def clean_runs(self):
        shutil.rmtree(self.root / ".tasks", ignore_errors=True)

    def commit_fixture(self, message="fixture state"):
        self.git("add", "-A")
        if self.git("status", "--porcelain").stdout:
            self.git("commit", "--amend", "-qm", message)

    def set_status(self, status):
        (self.mission / "GOAL.md").write_text(f"---\nstatus: {status}\n---\n# Goal\n")
        self.commit_fixture(f"status {status}")

    def write_fleet(self, provider, model, effort, speed, *, tier=None, mission_path="docs/missions/fixture", approved=True, seat_name=None, include_brain=False):
        tier = tier or ("premium" if provider == "agent" else "economy")
        seat_name = seat_name or ({"agent": "cursor"}.get(provider, provider) + f".{tier}")
        family = {
            ("agent", "premium"): "grok", ("agent", "economy"): "composer",
            ("codex", "premium"): "terra", ("codex", "economy"): "luna",
            ("agy", "premium"): "pro", ("agy", "economy"): "flash",
            ("claude", "premium"): "sonnet", ("claude", "economy"): "haiku",
        }[(provider, tier)]
        capabilities = {
            "agent": {"efforts": ["low", "medium", "high", "xhigh"], "speeds": ["standard", "fast"]},
            "codex": {"efforts": ["low", "medium", "high", "xhigh"], "speeds": ["unknown"]},
            "agy": {"efforts": ["low", "medium", "high"], "speeds": ["unknown"]},
            "claude": {"efforts": ["low", "medium", "high", "xhigh", "max"], "speeds": ["unknown"]},
        }[provider]
        source = "alias" if provider == "claude" else "observed"
        seat = {"provider": provider, "model": model, "family": family,
                "effort": effort, "speed": speed, "health": "healthy",
                "source": source, "capabilities": capabilities}
        seats = {seat_name: seat}
        if include_brain:
            seats["brain"] = dict(seat)
        doc = {
            "schema_version": 1,
            "mission": {"path": mission_path},
            "inventory": {"sha256": "0" * 64, "probed_at": "2026-08-21T00:00:00Z"},
            "approval": {"status": "approved" if approved else "draft", "approved_by": "human", "approved_at": "2026-08-21T00:00:00Z"},
            "seats": seats,
        }
        fleet = self.mission / "fleet.json"
        if fleet.exists():
            fleet.chmod(0o644)
        fleet.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")
        fleet.chmod(0o444)
        self.commit_fixture("frozen fleet")
        return doc

    def assert_worker_rejected(self, args):
        result = self.invoke(args)
        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse((self.root / ".tasks/invoked.json").exists())
        self.assertFalse(list((self.root / ".tasks/specs").glob("*.json")) if (self.root / ".tasks/specs").exists() else [])
        self.assertFalse(list((self.root / ".tasks/locks").glob("*.lock")) if (self.root / ".tasks/locks").exists() else [])
        self.clean_runs()

    def assert_brain_rejected(self, args):
        result = self.invoke(args)
        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse((self.root / ".tasks/invoked.json").exists())
        self.assertFalse(list((self.root / ".tasks/specs").glob("*.json")) if (self.root / ".tasks/specs").exists() else [])
        self.assertFalse(list((self.root / ".tasks/locks").glob("*.lock")) if (self.root / ".tasks/locks").exists() else [])
        self.clean_runs()

    def assert_no_lock(self):
        locks = self.root / ".tasks/locks"
        self.assertFalse(list(locks.glob("*.lock")) if locks.exists() else [])

    def assert_normal_exit_descendant_cleanup(self, *, provider_exit, outcome):
        self.clean_runs()
        child_pid_path = self.parent / f"normal-exit-child-{provider_exit}"
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                "--model", "normal-exit-model", "--feature", "F001"]
        child_pid = None
        try:
            result = self.invoke(base, env={
                "PROVIDER_CHILD_PID_PATH": str(child_pid_path),
                "PROVIDER_EXIT": str(provider_exit),
            })
            self.assertEqual(result.returncode, provider_exit, result.stderr + result.stdout)
            self.assertTrue(child_pid_path.exists(), result.stderr + result.stdout)
            child_pid = int(child_pid_path.read_text())
            receipts = list((self.root / ".tasks/receipts").glob("*.json"))
            self.assertEqual(len(receipts), 1)
            receipt = json.loads(receipts[0].read_text())
            self.assertEqual(receipt["outcome"], outcome)
            valid = self.invoke([
                sys.executable, "scripts/execution_receipt.py", "validate", "--receipt", str(receipts[0]),
            ])
            self.assertEqual(valid.returncode, 0, valid.stderr)
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @staticmethod
    def prompt_worker():
        return ("Read docs/missions/fixture/tasks/T-001.md and complete it exactly. Follow AGENTS.md and the skills "
                "the task names. Do not touch files outside the allow-list. Append a PROGRESS.md entry in the mission folder.")

    def expected_argv(self, provider, model, effort, speed, prompt):
        repo = self.physical_root
        if provider == "codex":
            return ["exec", "-C", repo, "-s", "workspace-write", "-m", model, "-c", f'model_reasoning_effort="{effort}"', prompt]
        if provider == "claude":
            return ["-p", prompt, "--model", model, "--effort", effort, "--allowedTools", "Read,Write,Edit,Bash"]
        if provider == "agy":
            return ["--dangerously-skip-permissions", "--print-timeout", "30m", "--model", model, "--effort", effort, "-p", prompt]
        return ["-p", "--force", "--trust", "--workspace", repo, "--model", f"{model}[effort={effort},fast={'true' if speed == 'fast' else 'false'}]", prompt]

    def linked(self, *, role, provider, model, effort, speed, work_unit, feature):
        specs = list((self.root / ".tasks/specs").glob("*.json"))
        receipts = [p for p in (self.root / ".tasks/receipts").glob("*.json") if not p.name.startswith("latest-")]
        self.assertEqual(len(specs), 1)
        self.assertEqual(len(receipts), 1)
        raw = specs[0].read_bytes()
        spec, receipt = json.loads(raw), json.loads(receipts[0].read_text())
        self.assertEqual(specs[0].stat().st_mode & 0o777, 0o400)
        self.assertEqual(receipts[0].stat().st_mode & 0o777, 0o400)
        self.assertRegex(spec["run_id"], r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        self.assertEqual(receipt["run_id"], spec["run_id"])
        self.assertEqual(Path(receipt["execution_spec_path"]).resolve(), specs[0].resolve())
        self.assertEqual(receipt["execution_spec_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual({k: spec[k] for k in ("role", "provider", "model", "effort", "speed", "work_unit", "feature")},
                         {"role": role, "provider": provider, "model": model, "effort": effort, "speed": speed,
                          "work_unit": work_unit, "feature": feature})
        self.assertEqual(receipt["requested_configuration"], {k: spec[k] for k in ("provider", "model", "effort", "speed")})
        self.assertEqual(receipt["resolved_configuration"]["env_override_keys"], [])
        self.assertRegex(receipt["resolved_configuration"]["argv_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["observed_configuration"], {"model": "unknown", "effort": "unknown", "speed": "unknown"})
        self.assertEqual(receipt["outcome"], "completed")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertFalse(receipt["workspace_changed"])
        self.assertEqual(receipt["scope"]["result"], "pass")
        self.assertEqual(spec["schema_version"], 2)
        self.assertEqual(receipt["log_path"], f".tasks/logs/{spec['run_id']}.log")
        self.assertNotIn(spec["prompt"], json.dumps(receipt))
        invoked = json.loads((self.root / ".tasks/invoked.json").read_text())
        self.assertTrue(invoked["spec_existed"])
        self.assertTrue(invoked["lock_existed"])
        self.assertEqual(invoked["provider"], provider)
        return spec, specs[0], receipt, invoked

    def test_exact_provider_contracts_through_both_wrappers(self):
        for role in ("worker", "brain"):
            for provider in PROVIDERS:
                with self.subTest(role=role, provider=provider):
                    model = f"{provider}-model"
                    speed = "fast" if provider == "agent" else "unknown"
                    self.write_fleet(provider, model, "high", speed,
                                     seat_name="brain" if role == "brain" else None)
                    args = (["bash", "scripts/spawn-worker.sh", provider, "docs/missions/fixture/tasks/T-001.md", "--provider", provider,
                             "--model", model, "--effort", "high", "--speed", speed, "--attempt", "2", "--feature", "F001"]
                            if role == "worker" else
                            ["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review", "--provider", provider,
                             "--model", model, "--effort", "high", "--speed", speed, "--attempt", "2"])
                    result = self.invoke(args)
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    spec, _, _, invoked = self.linked(role=role, provider=provider, model=model, effort="high", speed=speed,
                                                       work_unit="T-001" if role == "worker" else "review", feature="F001" if role == "worker" else None)
                    self.assertEqual(invoked["argv"], self.expected_argv(provider, model, "high", speed, spec["prompt"]))
                    if provider == "claude":
                        self.assertLess(invoked["argv"].index(spec["prompt"]), invoked["argv"].index("--allowedTools"))
                    if provider == "agy":
                        self.assertEqual(invoked["argv"][-2:], ["-p", spec["prompt"]])
                    self.clean_runs()

    def test_sol_brain_and_unsupported_configs_fail_before_sentinel(self):
        self.write_fleet("codex", "gpt-5.6-sol", "high", "unknown", seat_name="brain")
        result = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review", "--provider", "codex",
                              "--model", "gpt-5.6-sol", "--effort", "high", "--speed", "unknown"])
        self.assertEqual(result.returncode, 0, result.stderr)
        spec, _, _, invoked = self.linked(role="brain", provider="codex", model="gpt-5.6-sol", effort="high", speed="unknown", work_unit="review", feature=None)
        self.assertEqual(invoked["argv"], self.expected_argv("codex", "gpt-5.6-sol", "high", "unknown", spec["prompt"]))
        self.clean_runs()
        for role in ("worker", "brain"):
            for provider in PROVIDERS:
                with self.subTest(role=role, provider=provider):
                    bad = ["--effort", "max"] if provider == "agent" else ["--speed", "fast"]
                    self.write_fleet(provider, "test", "medium", "standard" if provider == "agent" else "unknown",
                                     seat_name="brain" if role == "brain" else None)
                    args = (["bash", "scripts/spawn-worker.sh", provider, "docs/missions/fixture/tasks/T-001.md", "--model", "test", "--feature", "F001", *bad]
                            if role == "worker" else
                            ["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review", "--provider", provider, "--model", "test", *bad])
                    result = self.invoke(args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((self.root / ".tasks/invoked.json").exists())
                    self.clean_runs()

    def test_spec_and_receipt_negatives(self):
        self.write_fleet("codex", "model", "medium", "unknown")
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--model", "model", "--feature", "F001"])
        self.assertEqual(result.returncode, 0, result.stderr)
        spec, path, receipt, _ = self.linked(role="worker", provider="codex", model="model", effort="medium", speed="unknown", work_unit="T-001", feature="F001")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        original = path.read_bytes()
        # Duplicate IDs are no-clobber, while a fresh construct necessarily has a new UUID.
        source = self.root / "same.json"; source.write_bytes(original)
        duplicate = self.invoke([sys.executable, "scripts/execution_spec.py", "persist", "--input", str(source)])
        self.assertNotEqual(duplicate.returncode, 0); self.assertEqual(path.read_bytes(), original)
        fresh = self.invoke([sys.executable, "scripts/execution_spec.py", "construct", "--role", "worker", "--mission", "docs/missions/fixture", "--feature", "F001", "--work-unit", "other", "--attempt", "1", "--provider", "codex", "--model", "model", "--effort", "medium", "--speed", "unknown", "--repo", self.physical_root, "--prompt", "fresh", "--write-scope-json", '["allowed.txt"]'])
        self.assertEqual(fresh.returncode, 0, fresh.stderr); self.assertNotEqual(json.loads(fresh.stdout)["run_id"], spec["run_id"])
        (self.root / ".tasks/invoked.json").unlink()
        os.chmod(path, 0o600)
        malformed = dict(spec); del malformed["prompt"]; path.write_text(json.dumps(malformed))
        launch = self.invoke([sys.executable, "scripts/execute_provider.py", "--spec", str(path), "--sha256", digest])
        self.assertNotEqual(launch.returncode, 0); self.assertFalse((self.root / ".tasks/invoked.json").exists())
        path.write_bytes(original)
        tampered = dict(spec); tampered["prompt"] = "different"; path.write_bytes(json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        launch = self.invoke([sys.executable, "scripts/execute_provider.py", "--spec", str(path), "--sha256", digest])
        self.assertNotEqual(launch.returncode, 0); self.assertFalse((self.root / ".tasks/invoked.json").exists())
        path.write_bytes(original)
        receipt_path = self.root / ".tasks/receipts" / f"{spec['run_id']}.json"
        receipt_raw = receipt_path.read_bytes()
        validate = [sys.executable, "scripts/execution_receipt.py", "validate", "--receipt", str(receipt_path)]
        self.assertEqual(self.invoke(validate).returncode, 0)
        log_path = self.root / receipt["log_path"]
        log_raw = log_path.read_bytes()
        log_path.unlink()
        self.assertNotEqual(self.invoke(validate).returncode, 0)
        log_path.write_bytes(log_raw)
        receipt_path.chmod(0o600)
        wrong_hash = dict(receipt); wrong_hash["execution_spec_sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(wrong_hash, sort_keys=True, separators=(",", ":")) + "\n")
        self.assertNotEqual(self.invoke(validate).returncode, 0)
        receipt_path.write_text("{malformed\n")
        self.assertNotEqual(self.invoke(validate).returncode, 0)
        receipt_path.write_bytes(receipt_raw)

    def test_terminal_outcomes_uuid_identity_and_git_evidence(self):
        self.write_fleet("codex", "model", "medium", "unknown")
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                "--model", "model", "--feature", "F001"]

        for _ in range(2):
            result = self.invoke(base)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        result = self.invoke(base, env={"PROVIDER_EXIT": "7"})
        self.assertEqual(result.returncode, 7, result.stderr + result.stdout)
        result = self.invoke(base, env={"PROVIDER_WAIT_FOR": str(self.parent / "never"),
                                        "SPAWN_WORKER_TIMEOUT_SECS": "0.15"})
        self.assertEqual(result.returncode, 124, result.stderr + result.stdout)

        codex = self.bin / "codex"
        stub = codex.read_bytes()
        codex.unlink()
        result = self.invoke(base, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(result.returncode, 127, result.stderr + result.stdout)
        codex.write_bytes(stub); codex.chmod(0o755)

        result = self.invoke(base, env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        result = self.invoke(base, env={"PROVIDER_ACTION": "dirty"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        head_value = self.git("show", "HEAD:allowed.txt").stdout
        (self.root / "allowed.txt").write_text(head_value)
        result = self.invoke(base, env={"PROVIDER_ACTION": "mixed"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

        paths = sorted((self.root / ".tasks/receipts").glob("*.json"))
        self.assertEqual(len(paths), 8)
        self.assertEqual(len({path.stem for path in paths}), 8)
        docs = [json.loads(path.read_text()) for path in paths]
        outcomes = [doc["outcome"] for doc in docs]
        self.assertEqual(outcomes.count("completed"), 5)
        self.assertEqual(outcomes.count("failed"), 1)
        self.assertEqual(outcomes.count("timed_out"), 1)
        self.assertEqual(outcomes.count("launch_failed"), 1)
        for path, doc in zip(paths, docs):
            self.assertEqual(path.stem, doc["run_id"])
            self.assertTrue((self.root / doc["log_path"]).is_file())
            valid = self.invoke([sys.executable, "scripts/execution_receipt.py", "validate", "--receipt", str(path)])
            self.assertEqual(valid.returncode, 0, valid.stderr)
        noops = [doc for doc in docs if doc["outcome"] == "completed" and not doc["workspace_changed"]]
        self.assertEqual(len(noops), 2)
        committed = [doc for doc in docs if doc["commits"]]
        dirty = [doc for doc in docs if doc["git_after"]["dirty_paths"]]
        mixed = [doc for doc in docs if doc["commits"] and doc["git_after"]["dirty_paths"]]
        self.assertEqual(len(committed), 2)
        self.assertEqual(len(dirty), 2)
        self.assertEqual(len(mixed), 1)
        for doc in committed + dirty:
            self.assertEqual(doc["changed_paths"], ["allowed.txt"])
            self.assertTrue(doc["workspace_changed"])
            self.assertEqual(doc["scope"]["result"], "pass")

    def test_normal_provider_exit_reaps_descendants_before_worker_return(self):
        self.write_fleet("codex", "normal-exit-model", "medium", "unknown")
        self.assert_normal_exit_descendant_cleanup(provider_exit=0, outcome="completed")
        self.assert_normal_exit_descendant_cleanup(provider_exit=7, outcome="failed")

    def test_normal_exit_descendant_regressions_are_non_vacuous(self):
        self.write_fleet("codex", "normal-exit-model", "medium", "unknown")
        runner = self.root / "scripts/execution_runner.py"
        corrected = runner.read_bytes()
        corrected_text = corrected.decode()
        current_guard = "    if process is None:\n        return\n"
        reproduced_guard = "    if process is None or process.poll() is not None:\n        return\n"
        self.assertEqual(corrected_text.count(current_guard), 1)
        runner.write_text(corrected_text.replace(current_guard, reproduced_guard, 1))
        self.commit_fixture("reproduce normal-exit descendant leak")
        try:
            with self.assertRaises(AssertionError):
                self.assert_normal_exit_descendant_cleanup(provider_exit=0, outcome="completed")
            with self.assertRaises(AssertionError):
                self.assert_normal_exit_descendant_cleanup(provider_exit=7, outcome="failed")
        finally:
            runner.write_bytes(corrected)
        self.assertEqual(runner.read_bytes(), corrected)
        self.commit_fixture("restore corrected normal-exit cleanup")

    def test_real_verifier_rejects_out_of_scope_noop_and_corrupt_evidence(self):
        self.write_fleet("codex", "model", "medium", "unknown", include_brain=True)
        legacy_dir = self.root / ".tasks/receipts"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "brain-waiver-20260822T000000Z.json").write_text(json.dumps({
            "mission": "prefix/fixture", "role": "brain", "cli": "waiver", "exit": 0,
        }) + "\n")
        verify = ["bash", "scripts/verify-mission.sh", "docs/missions/fixture"]
        legacy_only = self.invoke(verify)
        self.assertNotEqual(legacy_only.returncode, 0)
        self.assertIn("no completed", legacy_only.stdout + legacy_only.stderr)
        brain = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"])
        self.assertEqual(brain.returncode, 0, brain.stderr + brain.stdout)
        worker_args = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                       "--model", "model", "--feature", "F001"]

        noop = self.invoke(worker_args)
        self.assertEqual(noop.returncode, 0, noop.stderr + noop.stdout)
        features = json.loads((self.mission / "features.json").read_text())
        features["features"][0]["passes"] = True
        (self.mission / "features.json").write_text(json.dumps(features, indent=2) + "\n")
        self.git("add", "docs/missions/fixture/features.json")
        self.git("commit", "-qm", "accept fixture feature")
        result = self.invoke(verify)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing acceptance evidence", result.stdout + result.stderr)

        # Re-open the feature, dispatch an in-scope change, then accept it.
        features["features"][0]["passes"] = False
        (self.mission / "features.json").write_text(json.dumps(features, indent=2) + "\n")
        self.git("add", "docs/missions/fixture/features.json")
        self.git("commit", "-qm", "reopen fixture feature")
        changed = self.invoke(worker_args, env={"PROVIDER_ACTION": "dirty"})
        self.assertEqual(changed.returncode, 0, changed.stderr + changed.stdout)
        run_id = next(path.stem for path in (self.root / ".tasks/receipts").glob("*.json")
                      if json.loads(path.read_text())["role"] == "worker" and json.loads(path.read_text())["workspace_changed"])
        verified = self.invoke(["bash", "scripts/verify-mission.sh", "--run-id", run_id, "docs/missions/fixture"])
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = self.root / "docs/missions/fixture/verification" / f"{run_id}.json"
        record_hash = hashlib.sha256(record.read_bytes()).hexdigest()
        accepted = self.invoke(["bash", "scripts/accept-feature.sh", "--run-id", run_id,
                                "--verification-sha256", record_hash, "--accepted-by", "test", "docs/missions/fixture"],
                               env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
        result = self.invoke(verify)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

        worker_receipts = []
        for path in (self.root / ".tasks/receipts").glob("*.json"):
            doc = json.loads(path.read_text())
            if doc["role"] == "worker" and doc["workspace_changed"]:
                worker_receipts.append((path, doc))
        self.assertEqual(len(worker_receipts), 1)
        receipt_path, receipt = worker_receipts[0]
        receipt_raw = receipt_path.read_bytes()
        log_path = self.root / receipt["log_path"]
        log_raw = log_path.read_bytes()

        for label, mutate, restore in (
            ("wrong hash", lambda: self._rewrite_receipt(receipt_path, receipt, execution_spec_sha256="0" * 64),
             lambda: receipt_path.write_bytes(receipt_raw)),
            ("missing log", lambda: log_path.unlink(), lambda: log_path.write_bytes(log_raw)),
            ("malformed", lambda: receipt_path.write_text("{bad\n"), lambda: receipt_path.write_bytes(receipt_raw)),
            ("null changed", lambda: self._rewrite_receipt(receipt_path, receipt, workspace_changed=None),
             lambda: receipt_path.write_bytes(receipt_raw)),
        ):
            with self.subTest(evidence=label):
                receipt_path.chmod(0o600)
                mutate()
                result = self.invoke(verify)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                restore()

    @staticmethod
    def _rewrite_receipt(path, receipt, **changes):
        changed = dict(receipt)
        changed.update(changes)
        path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n")

    def test_out_of_scope_write_is_terminal_evidence_but_fails_real_verification(self):
        self.write_fleet("codex", "model", "medium", "unknown", include_brain=True)
        brain = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"])
        self.assertEqual(brain.returncode, 0, brain.stderr + brain.stdout)
        worker = self.invoke(
            ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
             "--model", "model", "--feature", "F001"],
            env={"PROVIDER_ACTION": "outside"},
        )
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        worker_receipt = [
            json.loads(path.read_text()) for path in (self.root / ".tasks/receipts").glob("*.json")
            if json.loads(path.read_text())["role"] == "worker"
        ][0]
        self.assertEqual(worker_receipt["scope"]["result"], "fail")
        self.assertEqual(worker_receipt["scope"]["violations"], ["outside.txt"])
        (self.root / "outside.txt").unlink()
        features = json.loads((self.mission / "features.json").read_text())
        features["features"][0]["passes"] = True
        (self.mission / "features.json").write_text(json.dumps(features, indent=2) + "\n")
        self.git("add", "docs/missions/fixture/features.json")
        self.git("commit", "-qm", "accept out-of-scope fixture")
        result = self.invoke(["bash", "scripts/verify-mission.sh", "docs/missions/fixture"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing acceptance evidence", result.stdout + result.stderr)

    def test_mounted_bypass_proofs(self):
        """Real wrapper mounts expose adapter and terminal-receipt bypass mutations."""
        self.write_fleet("codex", "test", "medium", "unknown")
        runner = self.root / "scripts/execution_runner.py"
        original_runner = runner.read_text()
        runner.write_text(original_runner.replace(
            "argv, env_overrides = provider_contract(spec)",
            "argv, env_overrides = ['true'], {}  # mounted adapter bypass",
            1,
        ))
        self.commit_fixture("adapter bypass mutation")
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--model", "test", "--feature", "F001"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse((self.root / ".tasks/invoked.json").exists(), result.stderr + result.stdout)
        runner.write_text(original_runner)
        self.commit_fixture("restore provider adapter")
        self.clean_runs()

        runner.write_text(original_runner.replace(
            "    receipt = write_receipt(\n",
            "    return exit_code  # mounted receipt-finalization bypass\n    receipt = write_receipt(\n",
            1,
        ))
        self.commit_fixture("receipt bypass mutation")
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--model", "test", "--feature", "F001"])
        self.assertEqual(result.returncode, 125, result.stderr + result.stdout)
        self.assertFalse(list((self.root / ".tasks/receipts").glob("*.json")))
        runner.write_text(original_runner)

    def test_worker_dispatch_gate_rejects_lifecycle_location_identity_dirty_and_cross_repo(self):
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                "--model", "test", "--feature", "F001"]
        self.write_fleet("codex", "test", "medium", "unknown")

        for status in ("draft", "approved", "awaiting-gate", "done"):
            with self.subTest(status=status):
                self.set_status(status)
                self.assert_worker_rejected(base)
        self.set_status("in-progress")

        outside = self.root / "outside.md"
        outside.write_text("---\ntask_id: outside\nfeature: F001\n---\n")
        self.commit_fixture("outside task")
        self.assert_worker_rejected(["bash", "scripts/spawn-worker.sh", "codex", "outside.md",
                                     "--model", "test", "--feature", "F001"])
        self.assert_worker_rejected(base[:-1] + ["F002"])
        self.assert_worker_rejected(base[:-2])

        original_task = self.task.read_text()
        self.task.write_text(original_task.replace("task_id: T-001", "task_id: T-999"))
        self.commit_fixture("mismatched task identity")
        self.assert_worker_rejected(base)
        self.task.write_text(original_task)
        self.commit_fixture("restore task identity")

        self.task.write_text(original_task.split("\n## Files you MAY touch", 1)[0] + "\n")
        self.commit_fixture("missing task scope")
        self.assert_worker_rejected(base)
        self.task.write_text(original_task.replace("- `allowed.txt`", "- allowed.txt"))
        self.commit_fixture("malformed task scope")
        self.assert_worker_rejected(base)
        self.task.write_text(original_task)
        self.commit_fixture("restore task scope")

        features = self.mission / "features.json"
        original_features = features.read_text()
        changed = json.loads(original_features)
        changed["features"][0]["passes"] = True
        features.write_text(json.dumps(changed, indent=2) + "\n")
        self.commit_fixture("accepted feature")
        self.assert_worker_rejected(base)
        features.write_text(original_features)
        self.commit_fixture("restore pending feature")

        dirty = self.root / "dirty.txt"
        dirty.write_text("dirty\n")
        self.assert_worker_rejected(base)
        dirty.unlink()

        external = self.parent / "external"
        external.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=external, check=True)
        self.assert_worker_rejected(base + ["--repo", str(external)])

    def test_execution_artifact_directories_cannot_escape_through_symlinks(self):
        self.write_fleet("codex", "test", "medium", "unknown")
        escaped = self.parent / "escaped-artifacts"
        escaped.mkdir()
        (self.root / ".tasks").symlink_to(escaped, target_is_directory=True)
        result = self.invoke([
            "bash", "scripts/spawn-worker.sh", "codex",
            "docs/missions/fixture/tasks/T-001.md", "--model", "test", "--feature", "F001",
        ])
        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse((escaped / "specs").exists())
        self.assertFalse((escaped / "logs").exists())
        self.assertFalse((escaped / "receipts").exists())
        self.assertFalse((self.root / ".tasks/invoked.json").exists())
        (self.root / ".tasks").unlink()

    def test_brain_role_policy_allows_only_draft_intake_and_frozen_review(self):
        self.set_status("draft")
        for action in ("mission-init", "gate0"):
            result = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", action,
                                  "--provider", "codex", "--model", "draft-model",
                                  "--effort", "high", "--speed", "unknown"])
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.linked(role="brain", provider="codex", model="draft-model", effort="high", speed="unknown",
                        work_unit=action, feature=None)
            self.assert_no_lock()
            self.clean_runs()
        self.assert_brain_rejected(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review",
                                    "--provider", "codex", "--model", "review-model",
                                    "--effort", "high", "--speed", "unknown"])

        self.set_status("in-progress")
        self.write_fleet("codex", "review-model", "high", "unknown", seat_name="brain")
        for status in ("in-progress", "awaiting-gate"):
            self.set_status(status)
            result = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"])
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.linked(role="brain", provider="codex", model="review-model", effort="high", speed="unknown",
                        work_unit="review", feature=None)
            self.assert_no_lock()
            self.clean_runs()

        self.assert_brain_rejected(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "gate0",
                                    "--provider", "codex", "--model", "review-model",
                                    "--effort", "high", "--speed", "unknown"])
        self.set_status("done")
        self.assert_brain_rejected(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"])

    def test_workspace_lock_spans_provider_and_receipt_then_releases(self):
        self.write_fleet("codex", "test", "medium", "unknown")
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                "--model", "test", "--feature", "F001"]
        receipt_script = self.root / "scripts/execution_receipt.py"
        original_receipt = receipt_script.read_text()
        mounted_check = '''def write_receipt(**kwargs):
    lock = Path(os.environ.get("PURRFECT_DISPATCH_LOCK_PATH", ""))
    if not lock.is_dir():
        raise ReceiptError("workspace lock missing during receipt finalization")
    Path(kwargs["spec_path"]).parents[1].joinpath("receipt-saw-lock").touch()
'''
        receipt_script.write_text(original_receipt.replace("def write_receipt(**kwargs):\n", mounted_check, 1))
        self.commit_fixture("instrument receipt lock")
        result = self.invoke(base)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue((self.root / ".tasks/receipt-saw-lock").is_file())
        self.assert_no_lock()
        receipt_script.write_text(original_receipt)
        self.commit_fixture("restore receipt writer")
        self.clean_runs()

        result = self.invoke(base, env={"PROVIDER_EXIT": "7"})
        self.assertEqual(result.returncode, 7, result.stderr + result.stdout)
        failed_receipts = list((self.root / ".tasks/receipts").glob("*.json"))
        self.assertEqual(len(failed_receipts), 1)
        self.assertEqual(json.loads(failed_receipts[0].read_text())["outcome"], "failed")
        self.assert_no_lock()
        self.clean_runs()

        release = self.parent / "release-provider"
        launch_env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                          PYTHONDONTWRITEBYTECODE="1", SPAWN_WORKER_TIMEOUT_SECS="0",
                          PROVIDER_WAIT_FOR=str(release))
        first = subprocess.Popen(base, cwd=self.root, env=launch_env, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        invoked = self.root / ".tasks/invoked.json"
        deadline = time.time() + 5
        while not invoked.exists() and time.time() < deadline:
            time.sleep(0.02)
        self.assertTrue(invoked.exists(), "first provider did not start")
        first_invocation = invoked.read_bytes()
        self.assertTrue(list((self.root / ".tasks/locks").glob("*.lock")))
        specs_before = list((self.root / ".tasks/specs").glob("*.json"))
        second = self.invoke(base)
        self.assertNotEqual(second.returncode, 0, second.stderr + second.stdout)
        self.assertEqual(invoked.read_bytes(), first_invocation)
        self.assertEqual(list((self.root / ".tasks/specs").glob("*.json")), specs_before)
        release.touch()
        stdout, stderr = first.communicate(timeout=5)
        self.assertEqual(first.returncode, 0, stderr + stdout)
        self.assert_no_lock()

        self.clean_runs()
        never_release = self.parent / "never-release-provider"
        child_pid_path = self.parent / "provider-child-pid"
        launch_env["PROVIDER_WAIT_FOR"] = str(never_release)
        launch_env["PROVIDER_CHILD_PID_PATH"] = str(child_pid_path)
        interrupted = subprocess.Popen(base, cwd=self.root, env=launch_env, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.time() + 5
        while (not invoked.exists() or not child_pid_path.exists()) and time.time() < deadline:
            time.sleep(0.02)
        self.assertTrue(invoked.exists(), "interrupted provider did not start")
        self.assertTrue(child_pid_path.exists(), "provider child did not start")
        provider_pid = json.loads(invoked.read_text())["pid"]
        child_pid = int(child_pid_path.read_text())
        interrupted.terminate()
        interrupted.communicate(timeout=5)
        self.assertNotEqual(interrupted.returncode, 0)
        interrupted_receipts = list((self.root / ".tasks/receipts").glob("*.json"))
        self.assertEqual(len(interrupted_receipts), 1)
        self.assertEqual(json.loads(interrupted_receipts[0].read_text())["outcome"], "interrupted")
        self.assert_no_lock()
        with self.assertRaises(ProcessLookupError):
            os.kill(provider_pid, 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    def test_both_real_wrappers_mount_the_dispatch_policy(self):
        self.write_fleet("codex", "test", "medium", "unknown")
        self.set_status("draft")
        worker = self.root / "scripts/spawn-worker.sh"
        original_worker = worker.read_text()
        worker_gate = '''POLICY_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" validate-worker \\
  --root "$ROOT" --workspace "$WORKSPACE" --mission "$MISSION" --fleet "$FLEET" \\
  --task "$TASK_ABS" --feature "$FEATURE" --work-unit "$BASE")" || exit $?
'''
        self.assertIn(worker_gate, original_worker)
        worker.write_text(original_worker.replace(worker_gate, "POLICY_JSON='{\"write_scope\":[\"allowed.txt\"]}'\n", 1))
        self.commit_fixture("worker gate bypass mutation")
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                              "--model", "test", "--feature", "F001"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue((self.root / ".tasks/invoked.json").exists())
        worker.write_text(original_worker)
        self.clean_runs()

        self.write_fleet("codex", "brain-model", "high", "unknown", seat_name="brain")
        self.set_status("done")
        brain = self.root / "scripts/spawn-brain.sh"
        original_brain = brain.read_text()
        brain_gate = '''POLICY_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/dispatch_policy.py" validate-brain \\
  --root "$ROOT" --workspace "$WORKSPACE" --mission "$MISSION" --fleet "$FLEET" --action "$ACTION")" || exit $?
'''
        self.assertIn(brain_gate, original_brain)
        brain.write_text(original_brain.replace(brain_gate, "POLICY_JSON='{\"write_scope\":[\"docs/missions/fixture/PROGRESS.md\"]}'\n", 1))
        self.commit_fixture("brain gate bypass mutation")
        result = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue((self.root / ".tasks/invoked.json").exists())
        brain.write_text(original_brain)

    def test_worker_uses_only_the_approved_frozen_fleet(self):
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-002.md", "--feature", "F002"]
        self.assert_worker_rejected(base)  # missing fleet

        fleet = self.mission / "fleet.json"
        fleet.write_text("{bad")
        self.commit_fixture("malformed fleet")
        self.assert_worker_rejected(base)  # malformed fleet

        self.write_fleet("codex", "frozen", "medium", "unknown", approved=False)
        self.assert_worker_rejected(base)
        self.write_fleet("codex", "frozen", "medium", "unknown", mission_path="docs/missions/other")
        self.assert_worker_rejected(base)
        self.write_fleet("claude", "haiku", "medium", "unknown", seat_name="claude.economy")
        self.assert_worker_rejected(base)  # mapped seat missing

        for extra in (["--model", "other"], ["--effort", "high"], ["--speed", "fast"]):
            self.write_fleet("codex", "frozen", "medium", "unknown")
            self.assert_worker_rejected(base + extra)

        self.write_fleet("agent", "composer", "medium", "standard", tier="economy", seat_name="codex.economy")
        self.assert_worker_rejected(base)  # provider assertion

        self.write_fleet("codex", "frozen", "medium", "unknown")
        (self.root / ".tasks").mkdir(exist_ok=True)
        (self.root / ".tasks/fleet-inventory.json").write_text('{"model":"mutable-and-wrong"}\n')
        result = self.invoke(base + ["--model", "frozen"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        spec, _, _, invoked = self.linked(role="worker", provider="codex", model="frozen", effort="medium", speed="unknown", work_unit="T-002", feature="F002")
        self.assertEqual(invoked["argv"], self.expected_argv("codex", "frozen", "medium", "unknown", spec["prompt"]))

    def test_all_worker_provider_tier_mappings_use_frozen_values(self):
        for provider in PROVIDERS:
            for tier in ("economy", "premium"):
                with self.subTest(provider=provider, tier=tier):
                    model = f"{provider}-{tier}-frozen"
                    speed = "fast" if provider == "agent" else "unknown"
                    self.write_fleet(provider, model, "high", speed, tier=tier)
                    result = self.invoke(["bash", "scripts/spawn-worker.sh", provider, "docs/missions/fixture/tasks/T-002.md",
                                          "--tier", tier, "--model", model, "--effort", "high", "--speed", speed, "--feature", "F002"])
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    spec, _, _, invoked = self.linked(role="worker", provider=provider, model=model, effort="high", speed=speed,
                                                       work_unit="T-002", feature="F002")
                    self.assertEqual(invoked["argv"], self.expected_argv(provider, model, "high", speed, spec["prompt"]))
                    self.clean_runs()


if __name__ == "__main__":
    unittest.main()
