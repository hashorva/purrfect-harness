#!/usr/bin/env python3
"""Mounted real-wrapper contracts for immutable execution specs and receipts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("codex", "claude", "agent", "agy")


class WrapperIntegration(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp())
        self.root = self.parent / "repo"
        self.root.mkdir()
        (self.root / "scripts").mkdir()
        for name in ("execution_spec.py", "execute_provider.py", "fleet_state.py", "spawn-worker.sh", "spawn-brain.sh", "write-receipt.sh"):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        self.task = self.root / "docs/missions/fixture/tasks/T-001.md"
        self.task.parent.mkdir(parents=True)
        self.task.write_text("task\n")
        self.mission = self.task.parent.parent
        (self.mission / "GOAL.md").write_text("goal\n")
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
import json, pathlib, sys
specs = list(pathlib.Path('.tasks/specs').glob('*.json'))
if not specs:
    raise SystemExit('provider invoked before spec persistence')
pathlib.Path('.tasks/invoked.json').write_text(json.dumps({
    'provider': pathlib.Path(sys.argv[0]).name,
    'argv': sys.argv[1:], 'spec_existed': True,
}))
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
                          EMPTY_OVERRIDE_SENTINEL="retained")
        if env:
            launch_env.update(env)
        return subprocess.run(args, cwd=self.root, env=launch_env, text=True, capture_output=True)

    def clean_runs(self):
        shutil.rmtree(self.root / ".tasks", ignore_errors=True)

    def write_fleet(self, provider, model, effort, speed, *, tier=None, mission_path="docs/missions/fixture", approved=True, seat_name=None):
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
        doc = {
            "schema_version": 1,
            "mission": {"path": mission_path},
            "inventory": {"sha256": "0" * 64, "probed_at": "2026-08-21T00:00:00Z"},
            "approval": {"status": "approved" if approved else "draft", "approved_by": "human", "approved_at": "2026-08-21T00:00:00Z"},
            "seats": {seat_name: {"provider": provider, "model": model, "family": family,
                                   "effort": effort, "speed": speed, "health": "healthy",
                                   "source": source, "capabilities": capabilities}},
        }
        fleet = self.mission / "fleet.json"
        if fleet.exists():
            fleet.chmod(0o644)
        fleet.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")
        fleet.chmod(0o444)
        return doc

    def assert_worker_rejected(self, args):
        result = self.invoke(args)
        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse((self.root / ".tasks/invoked.json").exists())
        self.assertFalse(list((self.root / ".tasks/specs").glob("*.json")) if (self.root / ".tasks/specs").exists() else [])
        self.clean_runs()

    @staticmethod
    def prompt_worker():
        return ("Read docs/missions/fixture/tasks/T-001.md and complete it exactly. Follow AGENTS.md and the skills "
                "the task names. Do not touch files outside the allow-list. Append a PROGRESS.md entry in the mission folder.")

    def prompt_brain(self, action="review"):
        return f'''You are the mission BRAIN for docs/missions/fixture.
Action: {action}
Follow docs/missions/ORCHESTRATION.md, docs/missions/MODEL_ROUTING.md, and the matching skill (mission-init or dispatch-worker review).
Read AGENTS.md. Work in the mission folder (GOAL.md, features.json, PROGRESS.md, tasks/).
mission-init: ensure GOAL/features/PROGRESS/tasks/T-001 exist from docs/missions/templates/; status stays draft until GATE 0.
gate0: present feature list + fleet-inventory map; do not dispatch workers.
review: judge git diff by effects only; do not re-implement worker scope.
Append PROGRESS.md pointing at brain log .tasks/logs/brain-{action}-{{timestamp}}.log.
Never claim a worker CLI ran unless .tasks/receipts/ proves it.'''.replace(
            f".tasks/logs/brain-{action}-{{timestamp}}.log", "")

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
        self.assertRegex(spec["run_id"], r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        self.assertEqual(receipt["run_id"], spec["run_id"])
        self.assertEqual(Path(receipt["execution_spec_path"]).resolve(), specs[0].resolve())
        self.assertEqual(receipt["execution_spec_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual({k: spec[k] for k in ("role", "provider", "model", "effort", "speed", "work_unit", "feature")},
                         {"role": role, "provider": provider, "model": model, "effort": effort, "speed": speed,
                          "work_unit": work_unit, "feature": feature})
        self.assertEqual(receipt["requested_configuration"], {k: spec[k] for k in ("provider", "model", "effort", "speed")})
        self.assertEqual(receipt["resolved_configuration"]["env_overrides"], {})
        self.assertEqual(receipt["observed_configuration"], {"model": "unknown", "effort": "unknown", "speed": "unknown"})
        invoked = json.loads((self.root / ".tasks/invoked.json").read_text())
        self.assertTrue(invoked["spec_existed"])
        self.assertEqual(invoked["provider"], provider)
        return spec, specs[0], receipt, invoked

    def test_exact_provider_contracts_through_both_wrappers(self):
        for role in ("worker", "brain"):
            for provider in PROVIDERS:
                with self.subTest(role=role, provider=provider):
                    model = f"{provider}-model"
                    speed = "fast" if provider == "agent" else "unknown"
                    if role == "worker":
                        self.write_fleet(provider, model, "high", speed)
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
                    if role == "worker":
                        self.write_fleet(provider, "test", "medium", "standard" if provider == "agent" else "unknown")
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
        spec, path, _, _ = self.linked(role="worker", provider="codex", model="model", effort="medium", speed="unknown", work_unit="T-001", feature="F001")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        original = path.read_bytes()
        # Duplicate IDs are no-clobber, while a fresh construct necessarily has a new UUID.
        source = self.root / "same.json"; source.write_bytes(original)
        duplicate = self.invoke([sys.executable, "scripts/execution_spec.py", "persist", "--input", str(source)])
        self.assertNotEqual(duplicate.returncode, 0); self.assertEqual(path.read_bytes(), original)
        fresh = self.invoke([sys.executable, "scripts/execution_spec.py", "construct", "--role", "worker", "--mission", "docs/missions/fixture", "--feature", "F001", "--work-unit", "other", "--attempt", "1", "--provider", "codex", "--model", "model", "--effort", "medium", "--speed", "unknown", "--repo", self.physical_root, "--prompt", "fresh"])
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
        base = ["bash", "scripts/write-receipt.sh", "--role", "worker", "--cli", "codex", "--model", "model", "--mission", "docs/missions/fixture", "--action", "task-T-001", "--work-unit", "T-001", "--exit", "0", "--log", ".tasks/logs/x.log"]
        trio = ["--run-id", spec["run_id"], "--spec", str(path), "--spec-sha256", digest]
        for label, extra in {
            "partial": ["--run-id", spec["run_id"]], "run_id": ["--run-id", "00000000-0000-4000-8000-000000000001", "--spec", str(path), "--spec-sha256", digest],
            "path": ["--run-id", spec["run_id"], "--spec", str(path.parent / "wrong.json"), "--spec-sha256", digest],
            "hash": ["--run-id", spec["run_id"], "--spec", str(path), "--spec-sha256", "0" * 64],
            "role": ["--run-id", spec["run_id"], "--spec", str(path), "--spec-sha256", digest, "--role", "brain"],
            "mission": ["--run-id", spec["run_id"], "--spec", str(path), "--spec-sha256", digest, "--mission", "wrong"],
            "work": ["--run-id", spec["run_id"], "--spec", str(path), "--spec-sha256", digest, "--work-unit", "wrong"],
            "provider": ["--run-id", spec["run_id"], "--spec", str(path), "--spec-sha256", digest, "--cli", "claude"],
            "model": ["--run-id", spec["run_id"], "--spec", str(path), "--spec-sha256", digest, "--model", "wrong"],
        }.items():
            command = base + extra if label == "partial" else base + trio + extra
            with self.subTest(receipt=label): self.assertNotEqual(self.invoke(command).returncode, 0)
        path.write_text(json.dumps(spec, indent=2) + "\n")
        self.assertNotEqual(self.invoke(base + trio).returncode, 0)

    def test_mounted_bypass_proofs(self):
        """The test's real wrapper mount detects either integration guard being removed."""
        self.write_fleet("codex", "test", "medium", "unknown")
        worker = self.root / "scripts/spawn-worker.sh"
        original_worker = worker.read_text()
        worker.write_text(original_worker.replace('python3 "$ROOT/scripts/execute_provider.py"', 'true # adapter bypass', 1))
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--model", "test", "--feature", "F001"])
        self.assertFalse((self.root / ".tasks/invoked.json").exists(), result.stderr + result.stdout)
        worker.write_text(original_worker)
        self.clean_runs()
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--model", "test", "--feature", "F001"])
        self.assertEqual(result.returncode, 0); _, path, _, _ = self.linked(role="worker", provider="codex", model="test", effort="medium", speed="unknown", work_unit="T-001", feature="F001")
        policy = self.root / "scripts/execution_spec.py"; original_policy = policy.read_text()
        policy.write_text(original_policy.replace('if spec_sha256(raw) != digest:', 'if False:', 1))
        bad = self.invoke(["bash", "scripts/write-receipt.sh", "--role", "worker", "--cli", "codex", "--model", "test", "--mission", "docs/missions/fixture", "--action", "task-T-001", "--work-unit", "T-001", "--exit", "0", "--log", ".tasks/logs/x.log", "--run-id", json.loads(path.read_text())["run_id"], "--spec", str(path), "--spec-sha256", "0" * 64])
        self.assertEqual(bad.returncode, 0, bad.stderr)
        policy.write_text(original_policy)

    def test_worker_uses_only_the_approved_frozen_fleet(self):
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--feature", "F002"]
        self.assert_worker_rejected(base)  # missing fleet

        fleet = self.mission / "fleet.json"
        fleet.write_text("{bad")
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
        spec, _, _, invoked = self.linked(role="worker", provider="codex", model="frozen", effort="medium", speed="unknown", work_unit="T-001", feature="F002")
        self.assertEqual(invoked["argv"], self.expected_argv("codex", "frozen", "medium", "unknown", spec["prompt"]))

    def test_all_worker_provider_tier_mappings_use_frozen_values(self):
        for provider in PROVIDERS:
            for tier in ("economy", "premium"):
                with self.subTest(provider=provider, tier=tier):
                    model = f"{provider}-{tier}-frozen"
                    speed = "fast" if provider == "agent" else "unknown"
                    self.write_fleet(provider, model, "high", speed, tier=tier)
                    result = self.invoke(["bash", "scripts/spawn-worker.sh", provider, "docs/missions/fixture/tasks/T-001.md",
                                          "--tier", tier, "--model", model, "--effort", "high", "--speed", speed, "--feature", "F002"])
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    spec, _, _, invoked = self.linked(role="worker", provider=provider, model=model, effort="high", speed=speed,
                                                       work_unit="T-001", feature="F002")
                    self.assertEqual(invoked["argv"], self.expected_argv(provider, model, "high", speed, spec["prompt"]))
                    self.clean_runs()


if __name__ == "__main__":
    unittest.main()
