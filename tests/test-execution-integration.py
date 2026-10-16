#!/usr/bin/env python3
"""Mounted real-wrapper contracts for immutable execution specs and receipts."""
import hashlib
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
import uuid

ROOT = Path(__file__).resolve().parents[1]
OBSERVE_FIXTURES = ROOT / "tests/fixtures/observe"
PROVIDERS = ("codex", "claude", "agent", "agy")
sys.path.insert(0, str(ROOT / "scripts"))
from observe_output import observe  # noqa: E402
import fleet_state  # noqa: E402


class WrapperIntegration(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp())
        self.root = self.parent / "repo"
        self.root.mkdir()
        (self.root / "scripts").mkdir()
        for name in ("execution_spec.py", "execution_receipt.py", "execution_runner.py",
                     "execute_provider.py", "observe_output.py", "fleet_state.py", "dispatch_policy.py",
                     "harness_registry.py", "ledger.py",
                     "spawn-worker.sh", "spawn-brain.sh", "verify-mission.sh", "verification_record.py",
                     "accept-feature.sh", "write-receipt.sh"):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        shutil.copy2(ROOT / "harness-registry.json", self.root / "harness-registry.json")
        self.task = self.root / "docs/missions/fixture/tasks/T-001.md"
        self.task.parent.mkdir(parents=True)
        self.mission = self.task.parent.parent
        self.task.write_text("---\ntask_id: T-001\nfeature: F001\n---\n# Task\n\n## Files you MAY touch\n- `allowed.txt`\n- `docs/missions/fixture/PROGRESS.md`\n\n## Verification commands\n\n- `[\"git\",\"status\",\"--porcelain\"]`\n")
        (self.task.parent / "T-002.md").write_text("---\ntask_id: T-002\nfeature: F002\n---\n# Task\n\n## Files you MAY touch\n- `allowed.txt`\n- `docs/missions/fixture/PROGRESS.md`\n\n## Verification commands\n\n- `[\"git\",\"status\",\"--porcelain\"]`\n")
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
    'python_dont_write_bytecode': os.environ.get('PYTHONDONTWRITEBYTECODE'),
}))
child_path = os.environ.get('PROVIDER_CHILD_PID_PATH')
if child_path:
    import subprocess
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    pathlib.Path(child_path).write_text(str(child.pid))
if os.environ.get('PROVIDER_PRINT'):
    print(os.environ['PROVIDER_PRINT'], flush=True)
for _ in range(int(os.environ.get('PROVIDER_TICKS', '0'))):
    print('tick', flush=True)
    time.sleep(0.1)
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
        for provider in PROVIDERS + ("cursor-agent",):
            path = self.bin / provider
            path.write_text(stub)
            path.chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.parent)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True)

    def invoke(self, args, *, env=None, inherit_pydontwritebytecode=True):
        launch_env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                          SPAWN_WORKER_TIMEOUT_SECS="0",
                          SPAWN_BRAIN_TIMEOUT_SECS="0",
                          EMPTY_OVERRIDE_SENTINEL="retained")
        if inherit_pydontwritebytecode:
            launch_env["PYTHONDONTWRITEBYTECODE"] = "1"
        else:
            launch_env.pop("PYTHONDONTWRITEBYTECODE", None)
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
            ("agy", "premium"): "argon", ("agy", "economy"): "flash",
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

    def write_v2_fleet_and_inventory(self, model):
        (self.root / ".tasks").mkdir(exist_ok=True)
        providers = {}
        for name in fleet_state.PROVIDERS:
            base = {"probed_at": "2026-08-21T00:00:00Z", "capabilities": fleet_state.CAPABILITIES[name]}
            if name == "codex":
                providers[name] = {**base, "status": "success", "path": "/bin/codex", "aliases": [], "observed_models": [model]}
            elif name == "claude":
                providers[name] = {**base, "status": "success", "path": "/bin/claude", "aliases": ["opus", "sonnet", "haiku"], "observed_models": []}
            else:
                providers[name] = {**base, "status": "success", "path": f"/bin/{name}", "aliases": [], "observed_models": ["fixture-1.0-low"]}
        inventory = {"schema_version": 1, "probed_at": "2026-08-21T00:00:00Z", "providers": providers,
                     "last_good": {}, "seats": fleet_state.make_seats(providers, {})}
        fleet_state.validate_inventory(inventory)
        (self.root / ".tasks/fleet-inventory.json").write_text(fleet_state.canonical(inventory))
        fleet = {
            "schema_version": 2, "mission": {"path": "docs/missions/fixture"},
            "inventory": {"sha256": "0" * 64, "probed_at": "2026-08-21T00:00:00Z"},
            "approval": {"status": "approved", "approved_by": "human", "approved_at": "2026-08-21T00:00:00Z"},
            "policy": {"billing_classes": ["included"], "fast": False, "no_zdr": "allow"},
            "seats": {"codex.economy": {"family": "luna", "effort": "medium", "speed": "unknown", "doors": ["codex"],
                                             "approved_resolution": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "medium", "speed": "unknown"}}},
        }
        path = self.mission / "fleet.json"
        if path.exists():
            path.chmod(0o644)
        path.write_text(fleet_state.canonical(fleet))
        path.chmod(0o444)
        self.commit_fixture("frozen v2 fleet")

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
                "the task names. Do not touch files outside the allow-list. Do not write PROGRESS.md; the Front Desk records your run from its receipt. End with a short plain-text report: what you changed and the exit code of each check you ran.")

    def expected_argv(self, provider, model, effort, speed, prompt):
        repo = self.physical_root
        if provider == "codex":
            return ["exec", "--json", "-C", repo, "-s", "workspace-write", "--add-dir", str(Path(repo) / ".git"), "-m", model, "-c", f'model_reasoning_effort="{effort}"', prompt]
        if provider == "claude":
            return ["-p", prompt, "--output-format", "stream-json", "--verbose", "--strict-mcp-config", "--model", model, "--effort", effort, "--allowedTools", "Read,Write,Edit,Bash"]
        if provider == "agy":
            return ["--dangerously-skip-permissions", "--print-timeout", "30m", "--model", model,
                    "--output-format", "stream-json", "-p", prompt]
        return ["-p", "--force", "--trust", "--output-format", "stream-json", "--workspace", repo, "--model", model, prompt]

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
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["observation"], {
            "observed_model": {"value": None, "source": "unknown"},
            "usage": {
                "input": {"value": None, "source": "unknown"},
                "output": {"value": None, "source": "unknown"},
                "cache": {"value": None, "source": "unknown"},
                "reasoning": {"value": None, "source": "unknown"},
            },
            "fast_state": {"value": None, "source": "unknown"},
        })
        self.assertEqual(receipt["outcome"], "completed")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertFalse(receipt["workspace_changed"])
        self.assertEqual(receipt["scope"]["result"], "pass")
        self.assertEqual(spec["schema_version"], 3)
        self.assertEqual(spec["provider_contract_version"], 8)
        self.assertEqual(receipt["log_path"], f".tasks/logs/{spec['run_id']}.log")
        self.assertNotIn(spec["prompt"], json.dumps(receipt))
        invoked = json.loads((self.root / ".tasks/invoked.json").read_text())
        self.assertTrue(invoked["spec_existed"])
        self.assertTrue(invoked["lock_existed"])
        self.assertEqual(invoked["provider"], {"agent": "cursor-agent"}.get(provider, provider))
        return spec, specs[0], receipt, invoked

    def test_launchers_export_python_dont_write_bytecode_to_provider(self):
        """Provider inherits PYTHONDONTWRITEBYTECODE=1 from the wrapper, not the test harness."""
        self.write_fleet("codex", "bytecode-model", "medium", "unknown")
        worker = self.invoke(
            ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
             "--model", "bytecode-model", "--feature", "F001"],
            inherit_pydontwritebytecode=False,
        )
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        invoked = json.loads((self.root / ".tasks/invoked.json").read_text())
        self.assertEqual(invoked["python_dont_write_bytecode"], "1")
        self.clean_runs()

        self.write_fleet("codex", "bytecode-brain", "high", "unknown", seat_name="brain")
        brain = self.invoke(
            ["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"],
            inherit_pydontwritebytecode=False,
        )
        self.assertEqual(brain.returncode, 0, brain.stderr + brain.stdout)
        invoked = json.loads((self.root / ".tasks/invoked.json").read_text())
        self.assertEqual(invoked["python_dont_write_bytecode"], "1")
        self.clean_runs()

    def test_exact_provider_contracts_through_both_wrappers(self):
        for role in ("worker", "brain"):
            for provider in PROVIDERS:
                with self.subTest(role=role, provider=provider):
                    speed = "fast" if provider == "agent" else "unknown"
                    model = (f"{provider}-model-fast" if provider == "agent" else
                             f"{provider}-model-high" if provider == "agy" else f"{provider}-model")
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

    def test_cursor_alias_persists_agent_contract_through_wrappers(self):
        model, speed = "cursor-model-fast", "fast"
        self.write_fleet("agent", model, "high", speed)
        outcomes = []
        runs = (
            ["cursor", "docs/missions/fixture/tasks/T-001.md"],
            ["docs/missions/fixture/tasks/T-001.md", "--provider", "cursor"],
            ["agent", "docs/missions/fixture/tasks/T-001.md"],
        )
        for provider_args in runs:
            result = self.invoke([
                "bash", "scripts/spawn-worker.sh", *provider_args,
                "--model", model, "--effort", "high", "--speed", speed, "--feature", "F001",
            ])
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            spec, _, _, invoked = self.linked(
                role="worker", provider="agent", model=model, effort="high", speed=speed,
                work_unit="T-001", feature="F001",
            )
            self.assertEqual(invoked["argv"], self.expected_argv("agent", model, "high", speed, spec["prompt"]))
            outcomes.append((spec["provider"], invoked["provider"], invoked["argv"]))
            self.clean_runs()
        self.assertEqual(outcomes[0], outcomes[1])

        self.write_fleet("agent", model, "high", speed, seat_name="brain", include_brain=True)
        result = self.invoke([
            "bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review",
            "--provider", "cursor", "--model", model, "--effort", "high", "--speed", speed,
        ])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        spec, _, _, invoked = self.linked(
            role="brain", provider="agent", model=model, effort="high", speed=speed,
            work_unit="review", feature=None,
        )
        self.assertEqual(invoked["argv"], self.expected_argv("agent", model, "high", speed, spec["prompt"]))

    def test_cursor_provider_flags_compare_after_persisted_name_conversion(self):
        model, speed = "cursor-model-fast", "fast"
        self.write_fleet("agent", model, "high", speed)
        task = "docs/missions/fixture/tasks/T-001.md"
        common = ["--model", model, "--effort", "high", "--speed", speed, "--feature", "F001"]
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "cursor", task, "--provider", "agent", *common])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        spec, _, _, invoked = self.linked(
            role="worker", provider="agent", model=model, effort="high", speed=speed,
            work_unit="T-001", feature="F001",
        )
        self.assertEqual(spec["provider"], "agent")
        self.assertEqual(invoked["argv"], self.expected_argv("agent", model, "high", speed, spec["prompt"]))
        self.clean_runs()

        result = self.invoke(["bash", "scripts/spawn-worker.sh", "cursor", task, "--provider", "codex", *common])
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertIn("disagree", result.stderr)
        tasks = self.root / ".tasks"
        self.assertFalse(list(tasks.glob("specs/*.json")) if tasks.exists() else [])
        self.assertFalse(list(tasks.glob("logs/*.log")) if tasks.exists() else [])
        self.assertFalse(list(tasks.glob("receipts/*.json")) if tasks.exists() else [])
        self.assertFalse(list(tasks.glob("locks/*.lock")) if (tasks / "locks").exists() else [])
        self.clean_runs()

        result = self.invoke(["bash", "scripts/spawn-worker.sh", "cursor", task, "--provider", "grok", *common])
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertIn("ERROR: registry:", result.stderr)
        tasks = self.root / ".tasks"
        self.assertFalse(list(tasks.glob("specs/*.json")) if tasks.exists() else [])
        self.assertFalse(list(tasks.glob("logs/*.log")) if tasks.exists() else [])
        self.assertFalse(list(tasks.glob("receipts/*.json")) if tasks.exists() else [])
        self.assertFalse(list(tasks.glob("locks/*.lock")) if (tasks / "locks").exists() else [])

    def test_unknown_provider_stops_before_persisting_run_artifacts(self):
        result = self.invoke([
            "bash", "scripts/spawn-worker.sh", "docs/missions/fixture/tasks/T-001.md",
            "--provider", "grok",
        ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR:", result.stderr)
        tasks = self.root / ".tasks"
        self.assertFalse(list(tasks.glob("specs/*.json")) if tasks.exists() else [])
        self.assertFalse(list(tasks.glob("logs/*.log")) if tasks.exists() else [])
        self.assertFalse(list(tasks.glob("receipts/*.json")) if tasks.exists() else [])

    def test_historical_contract_one_evidence_survives_contract_two_and_mutation_is_mounted(self):
        """A v2 receipt remains auditable by the real mission entry point after v3 exists."""
        self.write_fleet("codex", "legacy-model", "medium", "unknown", include_brain=True)
        brain = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"])
        self.assertEqual(brain.returncode, 0, brain.stderr + brain.stdout)
        run_id = str(uuid.uuid4())
        legacy = {
            "schema_version": 2, "run_id": run_id, "mission": "docs/missions/fixture", "work_unit": "T-001",
            "role": "worker", "feature": "F001", "provider": "codex", "model": "legacy-model",
            "effort": "medium", "speed": "unknown", "repo": self.physical_root,
            "base_commit": self.git("rev-parse", "HEAD").stdout.strip(), "attempt": 1,
            "prompt": self.prompt_worker(), "write_scope": ["allowed.txt"],
        }
        source = self.parent / "legacy-v2.json"
        source.write_text(json.dumps(legacy, sort_keys=True, separators=(",", ":")) + "\n")
        persisted = self.invoke([sys.executable, "scripts/execution_spec.py", "persist", "--input", str(source)])
        self.assertEqual(persisted.returncode, 0, persisted.stderr)
        details = json.loads(persisted.stdout)
        launched = self.invoke([
            sys.executable, "scripts/execution_runner.py", "--spec", details["path"], "--spec-sha256", details["sha256"],
            "--log", f".tasks/logs/{run_id}.log", "--timeout", "0", "--task", "docs/missions/fixture/tasks/T-001.md", "--tier", "economy",
        ], env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(launched.returncode, 0, launched.stderr + launched.stdout)
        receipt_path = self.root / ".tasks/receipts" / f"{run_id}.json"
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["resolved_configuration"]["argv_sha256"], hashlib.sha256(
            (json.dumps(["codex", "exec", "-C", self.physical_root, "-s", "workspace-write", "-m", "legacy-model", "-c", 'model_reasoning_effort="medium"', self.prompt_worker()], separators=(",", ":")) + "\n").encode()
        ).hexdigest())
        verified = self.invoke(["bash", "scripts/verify-mission.sh", "--run-id", run_id, "docs/missions/fixture"])
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        record = self.mission / "verification" / f"{run_id}.json"
        accepted = self.invoke(["bash", "scripts/accept-feature.sh", "--run-id", run_id,
                                "--verification-sha256", hashlib.sha256(record.read_bytes()).hexdigest(),
                                "--accepted-by", "test", "docs/missions/fixture"], env={"PURRFECT_DISPATCH_LOCK_PATH": ""})
        self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
        audit = ["bash", "scripts/verify-mission.sh", "--require-workers", "docs/missions/fixture"]
        self.assertEqual(self.invoke(audit).returncode, 0)

        adapter = self.root / "scripts/execute_provider.py"
        original = adapter.read_text()
        self.assertIn('contract_version = spec.get("provider_contract_version", 1)', original)
        adapter.write_text(original.replace('contract_version = spec.get("provider_contract_version", 1)',
                                            'contract_version = spec.get("provider_contract_version", 2)', 1))
        self.commit_fixture("mutate legacy provider contract")
        try:
            rejected = self.invoke(audit)
            self.assertNotEqual(rejected.returncode, 0, rejected.stderr + rejected.stdout)
            self.assertIn("resolved_configuration does not match shared adapter evidence", rejected.stderr + rejected.stdout)
        finally:
            adapter.write_text(original)
        self.assertEqual(adapter.read_text(), original)

    def test_removing_contract_two_git_mount_fails_real_new_wrapper_argv_assertion(self):
        self.write_fleet("codex", "new-model", "medium", "unknown")
        adapter = self.root / "scripts/execute_provider.py"
        original = adapter.read_text()
        old = 'codex_git_dir = (["--add-dir", str(Path(repo) / ".git")]\n                         if contract_version >= 2 else [])'
        self.assertIn(old, original)
        adapter.write_text(original.replace(old, "codex_git_dir = []", 1))
        self.commit_fixture("remove contract two Git mount")
        try:
            result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                                  "--model", "new-model", "--feature", "F001"])
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            spec, _, _, invoked = self.linked(role="worker", provider="codex", model="new-model", effort="medium",
                                               speed="unknown", work_unit="T-001", feature="F001")
            with self.assertRaises(AssertionError):
                self.assertEqual(invoked["argv"], self.expected_argv("codex", "new-model", "medium", "unknown", spec["prompt"]))
        finally:
            adapter.write_text(original)
        self.assertEqual(adapter.read_text(), original)

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
        changed = self.invoke(worker_args, env={"PROVIDER_ACTION": "commit"})
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

    def test_real_uncommitted_worker_run_is_refused_by_worktree_verifier(self):
        self.write_fleet("codex", "model", "medium", "unknown", include_brain=True)
        brain = self.invoke(["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"])
        self.assertEqual(brain.returncode, 0, brain.stderr + brain.stdout)
        worker = self.invoke(
            ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
             "--model", "model", "--feature", "F001"],
            env={"PROVIDER_ACTION": "dirty"},
        )
        self.assertEqual(worker.returncode, 0, worker.stderr + worker.stdout)
        run_id = next(path.stem for path in (self.root / ".tasks/receipts").glob("*.json")
                      if json.loads(path.read_text())["role"] == "worker"
                      and json.loads(path.read_text())["workspace_changed"])
        verified = self.invoke(["bash", "scripts/verify-mission.sh", "--run-id", run_id, "docs/missions/fixture"])
        self.assertNotEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.assertIn("worktree verification needs a clean receipt git_after", verified.stderr + verified.stdout)
        self.assertFalse((self.mission / "verification" / f"{run_id}.json").exists())

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
  --task "$TASK_ABS" --feature "$FEATURE" --work-unit "$BASE" --provider "$WORKER")" || exit $?
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

    def write_allow_list_task(self, task_id, patterns):
        lines = [
            "---",
            f"task_id: {task_id}",
            "feature: F001",
            "---",
            "# Task",
            "",
            "## Files you MAY touch",
        ]
        for pattern in patterns:
            lines.append(f"- `{pattern}`")
        lines.extend(["", "## Verification commands", "", '- `["true"]`', ""])
        path = self.task.parent / f"{task_id}.md"
        path.write_text("\n".join(lines))
        self.commit_fixture(f"task {task_id}")
        return f"docs/missions/fixture/tasks/{task_id}.md"

    def fixture_registry_codex_agents_write_denied(self):
        self.fixture_registry_write_denied("codex", [".agents/"])

    def fixture_registry_write_denied(self, provider, prefixes):
        registry_path = self.root / "harness-registry.json"
        data = json.loads(registry_path.read_text())
        data["providers"][provider]["sandbox_limits"]["write_denied_prefixes"] = prefixes
        registry_path.write_text(json.dumps(data, indent=2) + "\n")
        self.commit_fixture("fixture codex .agents/ write_denied_prefixes")

    def assert_prelaunch_refused(self, result, *, provider, prefix, pattern):
        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn(
            f"ERROR: seat limit: {provider} cannot write {prefix} (allow-list: {pattern}); "
            "route this task to another seat",
            result.stderr,
        )
        self.assert_no_run_artifacts()
        self.clean_runs()

    def test_v2_worker_records_exactly_one_drift_event_for_changed_inventory(self):
        self.set_status("in-progress")
        self.write_v2_fleet_and_inventory("gpt-5.6-luna")
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--feature", "F001", "--effort", "medium", "--speed", "unknown"]
        first = self.invoke(base)
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.write_v2_fleet_and_inventory("gpt-5.7-luna")
        second = self.invoke(base)
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        drift_path = self.root / ".tasks/drift/fixture.jsonl"
        events = [json.loads(line) for line in drift_path.read_text().splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["from"]["model"], "gpt-5.6-luna")
        self.assertEqual(events[0]["to"]["model"], "gpt-5.7-luna")

        folded = self.invoke([sys.executable, "scripts/ledger.py", "fold", "docs/missions/fixture"])
        self.assertEqual(folded.returncode, 0, folded.stderr + folded.stdout)
        self.assertEqual(folded.stdout.strip(), "folded rows=2 drift=1")
        again = self.invoke([sys.executable, "scripts/ledger.py", "fold", "docs/missions/fixture"])
        self.assertEqual(again.returncode, 0, again.stderr + again.stdout)
        self.assertEqual(again.stdout.strip(), "folded rows=0 drift=0")
        self.git("add", "docs/missions")
        self.git("commit", "-qm", "fold drift fixture")

        third = self.invoke(base)
        self.assertEqual(third.returncode, 0, third.stderr + third.stdout)
        self.assertEqual(len(drift_path.read_text().splitlines()), 1)

    def test_v2_worker_fails_before_artifacts_when_drift_directory_is_unwritable(self):
        self.set_status("in-progress")
        self.write_v2_fleet_and_inventory("gpt-5.6-luna")
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--feature", "F001", "--effort", "medium", "--speed", "unknown"]
        initial = self.invoke(base)
        self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)
        self.write_v2_fleet_and_inventory("gpt-5.7-luna")
        for dirname in ("locks", "specs", "logs", "receipts"):
            shutil.rmtree(self.root / ".tasks" / dirname, ignore_errors=True)
        drift_dir = self.root / ".tasks/drift"
        drift_dir.mkdir(parents=True)
        drift_dir.chmod(0o500)
        rejected = self.invoke(base)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("ERROR: drift event could not be written", rejected.stderr)
        tasks = self.root / ".tasks"
        for dirname in ("locks", "specs", "logs", "receipts"):
            self.assertFalse(list((tasks / dirname).glob("*")) if (tasks / dirname).exists() else [])
        drift_dir.chmod(0o700)
        self.clean_runs()

    def test_v2_worker_refuses_model_effort_and_speed_flags_that_differ_from_the_seat(self):
        self.set_status("in-progress")
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--feature", "F001"]
        mismatches = (
            (["--model", "gpt-5.7-luna", "--effort", "medium", "--speed", "unknown"], "ERROR: fleet model assertion failed"),
            (["--model", "gpt-5.6-luna", "--effort", "high", "--speed", "unknown"], "ERROR: fleet effort assertion failed"),
            (["--model", "gpt-5.6-luna", "--effort", "medium", "--speed", "fast"], "ERROR: fleet speed assertion failed"),
        )
        for flags, message in mismatches:
            with self.subTest(flags=flags):
                # clean_runs() removes .tasks, which holds the inventory, so each case rebuilds the fixture.
                self.write_v2_fleet_and_inventory("gpt-5.6-luna")
                result = self.invoke(base + flags)
                self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn(message, result.stderr)
                self.assert_no_run_artifacts()
                self.clean_runs()

    def test_v2_worker_refuses_a_seat_whose_family_has_no_available_model(self):
        self.set_status("in-progress")
        # codex observes only a sol model, so the seat's luna family is absent and must not be guessed.
        self.write_v2_fleet_and_inventory("gpt-5.6-sol")
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md", "--feature", "F001", "--effort", "medium", "--speed", "unknown"]
        result = self.invoke(base)
        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("ERROR: fleet seat resolved as unavailable", result.stderr)
        self.assert_no_run_artifacts()
        self.assertFalse((self.root / ".tasks/drift/fixture.jsonl").exists())
        self.clean_runs()

    def assert_no_run_artifacts(self):
        tasks = self.root / ".tasks"
        self.assertFalse((tasks / "invoked.json").exists())
        self.assertFalse(list((tasks / "specs").glob("*.json")) if (tasks / "specs").is_dir() else [])
        self.assertFalse(list((tasks / "logs").glob("*.log")) if (tasks / "logs").is_dir() else [])
        self.assertFalse(list((tasks / "receipts").glob("*.json")) if (tasks / "receipts").is_dir() else [])
        self.assertFalse(list((tasks / "locks").glob("*.lock")) if (tasks / "locks").is_dir() else [])

    def test_worker_refuses_allow_lists_that_hit_provider_write_limits(self):
        self.fixture_registry_codex_agents_write_denied()
        self.write_fleet("codex", "test", "medium", "unknown")
        opts = ["--model", "test", "--feature", "F001", "--effort", "medium"]
        refused = [".agents/skills/x/SKILL.md", "**", ".agents/**", ".agents/*",
                   "*/skills/x/SKILL.md", "**/SKILL.md", "?agents/x.md", ".age*/x.md",
                   ".*/skills/**"]
        for index, pattern in enumerate(refused):
            with self.subTest(refused_pattern=pattern):
                task = self.write_allow_list_task(f"T-refuse-{index}", [pattern])
                result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", task, *opts])
                self.assert_prelaunch_refused(result, provider="codex", prefix=".agents/", pattern=pattern)

        for index, pattern in enumerate(["docs/x.md", "docs/**", ".agentsx/y.md", ".agents"]):
            with self.subTest(passing_pattern=pattern):
                task = self.write_allow_list_task(f"T-pass-{index}", [pattern])
                result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", task, *opts])
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                spec, _, _, _ = self.linked(role="worker", provider="codex", model="test", effort="medium",
                                            speed="unknown", work_unit=f"T-pass-{index}", feature="F001")
                if pattern == "docs/x.md":
                    self.assertEqual(spec["write_scope"], ["docs/x.md"])
                self.clean_runs()

        for index, pattern in enumerate(["./docs/x.md", "./.agents/skills/x/SKILL.md"]):
            for provider in ("codex", "claude"):
                with self.subTest(dot_pattern=pattern, provider=provider):
                    task = self.write_allow_list_task(f"T-dot-{index}-{provider}", [pattern])
                    self.write_fleet(provider, "test" if provider == "codex" else "haiku", "medium", "unknown",
                                     seat_name=f"{provider}.economy")
                    result = self.invoke(["bash", "scripts/spawn-worker.sh", provider, task,
                                          "--model", "test" if provider == "codex" else "haiku",
                                          "--feature", "F001", "--effort", "medium"])
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("write_scope entries must not contain empty, dot, or parent segments", result.stderr)
                    self.assert_no_run_artifacts()
                    self.clean_runs()

        self.fixture_registry_write_denied("codex", ["./.agents/"])
        task = self.write_allow_list_task("T-prefix-dot", [".agents/skills/x/SKILL.md"])
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", task, *opts])
        self.assert_prelaunch_refused(result, provider="codex", prefix="./.agents/", pattern=".agents/skills/x/SKILL.md")

        self.fixture_registry_write_denied("codex", ["./"])
        task = self.write_allow_list_task("T-prefix-empty", ["docs/x.md"])
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "codex", task, *opts])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("normalizes to empty and would refuse every task", result.stderr)
        self.assert_no_run_artifacts()
        self.clean_runs()

        self.fixture_registry_write_denied("codex", [])
        self.write_fleet("claude", "haiku", "medium", "unknown", seat_name="claude.economy")
        agents_task = self.write_allow_list_task("T-claude", [".agents/skills/x/SKILL.md"])
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "claude", agents_task,
                             "--model", "haiku", "--feature", "F001", "--effort", "medium"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.clean_runs()

        self.fixture_registry_write_denied("cursor", [".agents/"])
        self.write_fleet("agent", "cursor-test", "medium", "fast", tier="economy", seat_name="cursor.economy")
        cursor_task = self.write_allow_list_task("T-cursor-limit", [".agents/skills/x/SKILL.md"])
        result = self.invoke(["bash", "scripts/spawn-worker.sh", "cursor", cursor_task,
                             "--model", "cursor-test", "--feature", "F001", "--effort", "medium", "--speed", "fast"])
        self.assert_prelaunch_refused(result, provider="cursor", prefix=".agents/", pattern=".agents/skills/x/SKILL.md")

    def install_fixture_emitting_provider(self, provider, fixture_name):
        binary = "cursor-agent" if provider == "agent" else provider
        fixture = OBSERVE_FIXTURES / fixture_name
        path = self.bin / binary
        path.write_text(
            f"""#!/usr/bin/env python3
import json, os, pathlib, sys
specs = list(pathlib.Path('.tasks/specs').glob('*.json'))
pathlib.Path('.tasks/invoked.json').write_text(json.dumps({{
    'provider': pathlib.Path(sys.argv[0]).name,
    'argv': sys.argv[1:],
    'spec_existed': bool(specs),
    'lock_existed': pathlib.Path(os.environ.get('PURRFECT_DISPATCH_LOCK_PATH', '')).is_dir(),
    'python_dont_write_bytecode': os.environ.get('PYTHONDONTWRITEBYTECODE'),
}}))
sys.stdout.buffer.write(pathlib.Path({json.dumps(str(fixture))}).read_bytes())
sys.stdout.buffer.flush()
raise SystemExit(int(os.environ.get('PROVIDER_EXIT', '0')))
"""
        )
        path.chmod(0o755)

    def test_receipt_observation_matches_cli_fixture_output(self):
        cases = [
            ("codex", "codex.jsonl", "codex-model", "medium", "unknown"),
            ("claude", "claude.json", "claude-model", "medium", "unknown"),
            ("agent", "cursor.jsonl", "composer-2.5", "medium", "standard"),
            ("agent", "cursor-no-init-model.jsonl", "composer-2.5", "medium", "standard"),
        ]
        for provider, fixture_name, model, effort, speed in cases:
            with self.subTest(provider=provider, fixture=fixture_name):
                self.install_fixture_emitting_provider(provider, fixture_name)
                self.write_fleet(provider, model, effort, speed)
                result = self.invoke([
                    "bash", "scripts/spawn-worker.sh", provider, "docs/missions/fixture/tasks/T-001.md",
                    "--model", model, "--effort", effort, "--speed", speed, "--feature", "F001",
                ])
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                observe_name = "cursor" if provider == "agent" else provider
                expected = observe(observe_name, (OBSERVE_FIXTURES / fixture_name).read_bytes())
                receipt = json.loads(next((self.root / ".tasks/receipts").glob("*.json")).read_text())
                self.assertEqual(receipt["observation"], expected)
                if fixture_name == "cursor.jsonl":
                    self.assertEqual(receipt["observation"]["observed_model"]["value"], "Composer 2.5")
                    self.assertNotEqual(receipt["model"], "Composer 2.5")
                if fixture_name == "codex.jsonl":
                    self.assertEqual(receipt["observation"]["observed_model"]["source"], "unknown")
                self.clean_runs()

    def test_stall_watchdog_stops_silent_providers_for_worker_and_brain(self):
        self.write_fleet("codex", "stall-model", "medium", "unknown", include_brain=True)
        self.set_status("in-progress")
        worker = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                  "--model", "stall-model", "--feature", "F001"]
        brain = ["bash", "scripts/spawn-brain.sh", "docs/missions/fixture", "review"]
        silent = {"PROVIDER_WAIT_FOR": str(self.parent / "never")}
        cases = [
            ("worker silent since launch", worker, {**silent, "SPAWN_WORKER_STALL_SECS": "0.3",
                                                     "SPAWN_WORKER_TIMEOUT_SECS": "5"},
             "STALL: no provider output for 0.3 s since launch; run stopped"),
            ("worker silent after one line", worker, {**silent, "PROVIDER_PRINT": "hello",
                                                       "SPAWN_WORKER_IDLE_SECS": "0.3",
                                                       "SPAWN_WORKER_TIMEOUT_SECS": "5"},
             "STALL: no provider output for 0.3 s after its last output; run stopped"),
            ("silent brain", brain, {**silent, "SPAWN_BRAIN_STALL_SECS": "0.3",
                                     "SPAWN_BRAIN_TIMEOUT_SECS": "5"},
             "STALL: no provider output for 0.3 s since launch; run stopped"),
        ]
        for label, command, env, line in cases:
            with self.subTest(case=label):
                result = self.invoke(command, env=env)
                self.assertEqual(result.returncode, 123, result.stderr + result.stdout)
                receipt_path = next((self.root / ".tasks/receipts").glob("*.json"))
                receipt = json.loads(receipt_path.read_text())
                self.assertEqual(receipt["outcome"], "stalled")
                valid = self.invoke([sys.executable, "scripts/execution_receipt.py", "validate",
                                     "--receipt", str(receipt_path)])
                self.assertEqual(valid.returncode, 0, valid.stderr)
                self.assertIn(line + "\n", self.log_text(receipt["run_id"]))
                row = json.loads((self.root / ".tasks/ledger" / f"{receipt['run_id']}.json").read_text())
                self.assertEqual(row["outcome"], "stalled")
                self.clean_runs()
        with self.subTest(case="ticking worker completes"):
            result = self.invoke(worker, env={"PROVIDER_TICKS": "8", "SPAWN_WORKER_STALL_SECS": "0.3",
                                              "SPAWN_WORKER_IDLE_SECS": "0.3",
                                              "SPAWN_WORKER_TIMEOUT_SECS": "5"})
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(self.latest_receipt()["outcome"], "completed")

    def test_zero_turn_output_turns_a_completed_run_into_a_failure(self):
        cases = [
            ("claude", "claude-zero-turns.json"),
            ("codex", "codex-no-turn.jsonl"),
            ("agent", "cursor-zero-tokens.jsonl"),
        ]
        for provider, fixture_name in cases:
            with self.subTest(provider=provider):
                self.install_fixture_emitting_provider(provider, fixture_name)
                speed = "standard" if provider == "agent" else "unknown"
                self.write_fleet(provider, "zero-model", "medium", speed)
                result = self.invoke([
                    "bash", "scripts/spawn-worker.sh", provider, "docs/missions/fixture/tasks/T-001.md",
                    "--model", "zero-model", "--effort", "medium", "--speed", speed, "--feature", "F001",
                ])
                self.assertEqual(result.returncode, 122, result.stderr + result.stdout)
                receipt = self.latest_receipt()
                self.assertEqual(receipt["outcome"], "failed")
                self.assertIn("NO-TURN: provider output shows 0 turns; completed run recorded as failed\n",
                              self.log_text(receipt["run_id"]))
                self.clean_runs()

    def test_failed_run_still_writes_receipt_observation(self):
        self.install_fixture_emitting_provider("codex", "codex.jsonl")
        self.write_fleet("codex", "codex-model", "medium", "unknown")
        result = self.invoke([
            "bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
            "--model", "codex-model", "--feature", "F001",
        ], env={"PROVIDER_EXIT": "7"})
        self.assertEqual(result.returncode, 7, result.stderr + result.stdout)
        receipt = json.loads(next((self.root / ".tasks/receipts").glob("*.json")).read_text())
        self.assertEqual(receipt["outcome"], "failed")
        self.assertEqual(receipt["observation"], observe("codex", (OBSERVE_FIXTURES / "codex.jsonl").read_bytes()))

    def test_closed_stdin_finishes_eof_reading_provider(self):
        (self.bin / "codex").write_text("#!/usr/bin/env bash\nwhile IFS= read -r _; do :; done\nexit 0\n")
        (self.bin / "codex").chmod(0o755)
        self.write_fleet("codex", "stdin-model", "medium", "unknown")
        result = self.invoke([
            "bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
            "--model", "stdin-model", "--feature", "F001",
        ], env={"SPAWN_WORKER_TIMEOUT_SECS": "2"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotEqual(result.returncode, 124, result.stderr + result.stdout)

    def assert_ledger_row_hygiene(self, run_id):
        ledger_path = self.root / ".tasks/ledger" / f"{run_id}.json"
        self.assertTrue(ledger_path.is_file(), f"missing ledger row for {run_id}")
        valid = self.invoke([sys.executable, "scripts/ledger.py", "validate", str(ledger_path)])
        self.assertEqual(valid.returncode, 0, valid.stderr + valid.stdout)
        self.assertEqual(self.git("status", "--porcelain").stdout, "")
        for rel in (f".tasks/logs/{run_id}.log", f".tasks/ledger/{run_id}.json"):
            ignored = self.invoke(["bash", "-c", f"git check-ignore -q {rel}"])
            self.assertEqual(ignored.returncode, 0, rel)
        dry = self.invoke(["bash", "-c", "git add -A --dry-run"])
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertNotIn(".tasks/", dry.stdout)

    def ledger_worker_base(self):
        return ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                "--model", "ledger-model", "--feature", "F001"]

    def latest_receipt(self):
        return json.loads(next((self.root / ".tasks/receipts").glob("*.json")).read_text())

    def log_text(self, run_id):
        return (self.root / ".tasks/logs" / f"{run_id}.log").read_text()

    def assert_terminal_run_hygiene(self, result, *, expected_exit):
        self.assertEqual(result.returncode, expected_exit, result.stderr + result.stdout)
        self.assertIn("receipt=", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def mutate_runner_once(self, old, new):
        runner = self.root / "scripts/execution_runner.py"
        original = runner.read_text()
        mutant = original.replace(old, new, 1)
        self.assertNotEqual(mutant, original, f"mutation pattern not found: {old[:40]!r}")
        runner.write_text(mutant)
        self.commit_fixture("ledger runner mutation")
        return original

    def restore_runner(self, original):
        (self.root / "scripts/execution_runner.py").write_text(original)
        self.commit_fixture("restore ledger runner")

    def commit_codex_hostile_pool_registry(self, pool_value):
        registry_path = self.root / "harness-registry.json"
        registry = json.loads(registry_path.read_text())
        registry["doors"]["codex"]["pool"] = pool_value
        registry_path.write_text(json.dumps(registry))
        self.commit_fixture("hostile committed registry")

    def prove_runner_mutation_fails(self, old, new=None, check=None):
        if check is None and callable(new):
            replacements = old
            check = new
        else:
            replacements = [(old, new)]
        runner = self.root / "scripts/execution_runner.py"
        original = runner.read_text()
        mutant = original
        for pattern, replacement in replacements:
            mutant = mutant.replace(pattern, replacement, 1)
            self.assertNotEqual(mutant, original, f"mutation pattern not found: {pattern[:40]!r}")
        runner.write_text(mutant)
        self.commit_fixture("ledger runner mutation")
        try:
            with self.assertRaises(AssertionError):
                check()
        finally:
            self.restore_runner(original)

    def run_id_from_output(self, result):
        combined = result.stdout + result.stderr
        match = re.search(r"run_id=([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})", combined)
        self.assertIsNotNone(match, combined)
        return match.group(1)

    def assert_ledger_warn_without_row(self, result, run_id, *, hostile=None):
        self.assert_terminal_run_hygiene(result, expected_exit=0)
        log = self.log_text(run_id)
        self.assertIn("WARN: ledger row not written:", log)
        self.assertFalse((self.root / ".tasks/ledger" / f"{run_id}.json").is_file())
        combined = result.stdout + result.stderr + log
        if hostile is not None:
            self.assertNotIn(hostile, combined)

    def test_ledger_readonly_directory_warns_without_changing_outcome(self):
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        ledger_dir = self.root / ".tasks" / "ledger"
        ledger_dir.mkdir(parents=True)
        os.chmod(ledger_dir, 0o555)
        result = self.invoke(self.ledger_worker_base())
        run_id = self.latest_receipt()["run_id"]
        self.assert_ledger_warn_without_row(result, run_id)

        def check():
            self.clean_runs()
            ledger_dir = self.root / ".tasks" / "ledger"
            ledger_dir.mkdir(parents=True)
            os.chmod(ledger_dir, 0o555)
            retry = self.invoke(self.ledger_worker_base())
            self.assert_ledger_warn_without_row(retry, self.latest_receipt()["run_id"])

        self.prove_runner_mutation_fails(
            "    except OSError:\n        warn_ledger(log, \"ledger: write failed\")\n"
            "    except Exception:\n        warn_ledger(log, \"ledger: row build failed\")\n",
            "    except OSError:\n        raise\n",
            check,
        )
        self.clean_runs()

    def test_ledger_validator_refusal_warns_without_leaking_value(self):
        hostile = "/" + "tmp" + "/" + "h" + "ostile-pool"
        self.commit_codex_hostile_pool_registry(hostile)
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        result = self.invoke(self.ledger_worker_base())
        run_id = self.latest_receipt()["run_id"]
        self.assert_ledger_warn_without_row(result, run_id, hostile=hostile)
        self.assertIn("pool: privacy", self.log_text(run_id))

        def check():
            self.clean_runs()
            self.commit_codex_hostile_pool_registry(hostile)
            retry = self.invoke(self.ledger_worker_base())
            self.assert_ledger_warn_without_row(retry, self.latest_receipt()["run_id"], hostile=hostile)

        self.prove_runner_mutation_fails("        validate_row(row, door_names=frozenset(base_registry_doors(spec[\"repo\"], spec[\"base_commit\"])))\n", "", check)
        self.clean_runs()

    def test_ledger_registry_edited_during_run_does_not_change_row(self):
        hostile = "/" + "tmp" + "/worker-pool-secret"
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        starting_commit = self.git("rev-parse", "HEAD").stdout.strip()
        for edit in ("pool", "malformed", "commit"):
            self.clean_runs()
            self.git("reset", "--hard", starting_commit)
            self.install_fixture_emitting_provider("codex", "codex.jsonl")
            provider = self.bin / "codex"
            source = provider.read_text()
            if edit == "pool":
                inject = ("registry = json.loads(pathlib.Path('harness-registry.json').read_text())\n"
                          f"registry['doors']['codex']['pool'] = {json.dumps(hostile)}\n"
                          "pathlib.Path('harness-registry.json').write_text(json.dumps(registry))\n")
            elif edit == "malformed":
                inject = "pathlib.Path('harness-registry.json').write_text('[1, 2, 3]\\n')\n"
            else:
                inject = ("registry = json.loads(pathlib.Path('harness-registry.json').read_text())\n"
                          f"registry['doors']['codex']['pool'] = {json.dumps(hostile)}\n"
                          "pathlib.Path('harness-registry.json').write_text(json.dumps(registry))\n"
                          "subprocess.run(['git', 'add', 'harness-registry.json'], check=True)\n"
                          "subprocess.run(['git', 'commit', '-qm', 'provider registry edit'], check=True)\n")
            source = source.replace("sys.stdout.buffer.write", "import subprocess\n" + inject + "sys.stdout.buffer.write", 1)
            provider.write_text(source)
            result = self.invoke(self.ledger_worker_base())
            run_id = self.latest_receipt()["run_id"]
            self.assertIn("receipt=", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            log = self.log_text(run_id)
            self.assertNotIn("WARN", log)
            row_path = self.root / ".tasks/ledger" / f"{run_id}.json"
            self.assertTrue(row_path.is_file(), edit)
            row = json.loads(row_path.read_text())
            self.assertEqual((row["door"], row["pool"], row["billing_class"]), ("codex", "openai", "included"))
            self.assertNotIn(hostile, json.dumps(row) + log)
        self.clean_runs()

        self.git("reset", "--hard", starting_commit)

        def malformed_worktree_check():
            self.clean_runs()
            self.install_fixture_emitting_provider("codex", "codex.jsonl")
            provider = self.bin / "codex"
            source = provider.read_text().replace(
                "sys.stdout.buffer.write",
                "pathlib.Path('harness-registry.json').write_text('[1, 2, 3]\\n')\nsys.stdout.buffer.write", 1,
            )
            provider.write_text(source)
            result = self.invoke(self.ledger_worker_base())
            self.assertIn("receipt=", result.stdout, result.stderr + result.stdout)
            run_id = self.latest_receipt()["run_id"]
            self.assertIn("receipt=", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("WARN", self.log_text(run_id))
            row_path = self.root / ".tasks/ledger" / f"{run_id}.json"
            self.assertTrue(row_path.is_file())
            row = json.loads(row_path.read_text())
            self.assertEqual((row["door"], row["pool"], row["billing_class"]), ("codex", "openai", "included"))

        self.prove_runner_mutation_fails(
            '    doors = base_registry_doors(spec["repo"], spec["base_commit"])\n',
            '    doors = json.loads((Path(spec["repo"]) / "harness-registry.json").read_text()).get("doors", {})\n',
            malformed_worktree_check,
        )
        self.prove_runner_mutation_fails(
            '        validate_row(row, door_names=frozenset(base_registry_doors(spec["repo"], spec["base_commit"])))\n',
            '        validate_row(row)\n',
            malformed_worktree_check,
        )
        self.clean_runs()

    def test_ledger_registry_missing_at_base_gives_unknown_door(self):
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        with (self.root / ".gitignore").open("a") as handle:
            handle.write("\nharness-registry.json\n")
        self.invoke(["git", "rm", "--cached", "harness-registry.json"])
        self.commit_fixture("untrack registry")
        result = self.invoke(self.ledger_worker_base())
        run_id = self.latest_receipt()["run_id"]
        self.assert_terminal_run_hygiene(result, expected_exit=0)
        self.assertNotIn("WARN", self.log_text(run_id))
        row = json.loads((self.root / ".tasks/ledger" / f"{run_id}.json").read_text())
        self.assertEqual((row["door"], row["pool"], row["billing_class"]), ("unknown", "unknown", "unknown"))

        def check():
            self.clean_runs()
            self.invoke(["git", "rm", "--cached", "harness-registry.json"])
            broken = self.invoke(self.ledger_worker_base())
            run_id = self.latest_receipt()["run_id"]
            self.assert_terminal_run_hygiene(broken, expected_exit=0)
            row_path = self.root / ".tasks/ledger" / f"{run_id}.json"
            self.assertTrue(row_path.is_file(), "expected a ledger row when the base registry is absent")
            self.assertEqual(json.loads(row_path.read_text())["door"], "unknown")

        self.prove_runner_mutation_fails(
            "    if result.returncode != 0:\n        return {}\n",
            "    if result.returncode != 0:\n        raise OSError()\n",
            check,
        )
        self.clean_runs()

    def test_ledger_unwritable_path_warns_without_changing_outcome(self):
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        tasks = self.root / ".tasks"
        tasks.mkdir(parents=True, exist_ok=True)
        (tasks / "ledger").write_text("not a directory\n")
        result = self.invoke(self.ledger_worker_base())
        run_id = self.latest_receipt()["run_id"]
        self.assert_ledger_warn_without_row(result, run_id)

        def check():
            self.clean_runs()
            tasks = self.root / ".tasks"
            tasks.mkdir(parents=True, exist_ok=True)
            (tasks / "ledger").write_text("not a directory\n")
            retry = self.invoke(self.ledger_worker_base())
            self.assert_ledger_warn_without_row(retry, self.latest_receipt()["run_id"])

        self.prove_runner_mutation_fails(
            "    except Exception:\n        warn_ledger(log, \"ledger: row build failed\")\n",
            "",
            check,
        )
        self.clean_runs()

    def test_ledger_row_observed_model_matches_receipt_not_spec(self):
        self.install_fixture_emitting_provider("agent", "cursor.jsonl")
        spec_model = "spec-only-model-name"
        self.write_fleet("agent", spec_model, "medium", "standard")
        result = self.invoke([
            "bash", "scripts/spawn-worker.sh", "agent", "docs/missions/fixture/tasks/T-001.md",
            "--model", spec_model, "--effort", "medium", "--speed", "standard", "--feature", "F001",
        ])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        receipt = self.latest_receipt()
        row = json.loads((self.root / ".tasks/ledger" / f"{receipt['run_id']}.json").read_text())
        self.assertEqual(row["observed_model"], receipt["observation"]["observed_model"])
        self.assertNotEqual(spec_model, receipt["observation"]["observed_model"]["value"])

        def check():
            self.clean_runs()
            self.install_fixture_emitting_provider("agent", "cursor.jsonl")
            self.write_fleet("agent", spec_model, "medium", "standard")
            self.invoke([
                "bash", "scripts/spawn-worker.sh", "agent", "docs/missions/fixture/tasks/T-001.md",
                "--model", spec_model, "--effort", "medium", "--speed", "standard", "--feature", "F001",
            ])
            doc = self.latest_receipt()
            row = json.loads((self.root / ".tasks/ledger" / f"{doc['run_id']}.json").read_text())
            self.assertEqual(row["observed_model"], doc["observation"]["observed_model"])

        self.prove_runner_mutation_fails(
            '"value": observation["observed_model"]["value"],',
            '"value": spec["model"],',
            check,
        )
        self.clean_runs()

    def test_ledger_row_diff_file_count_matches_receipt(self):
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        result = self.invoke(self.ledger_worker_base(), env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        receipt = self.latest_receipt()
        row = json.loads((self.root / ".tasks/ledger" / f"{receipt['run_id']}.json").read_text())
        self.assertEqual(row["diff_size"]["files"]["value"], len(receipt["changed_paths"]))

        def check():
            self.clean_runs()
            self.write_fleet("codex", "ledger-model", "medium", "unknown")
            self.invoke(self.ledger_worker_base(), env={"PROVIDER_ACTION": "commit"})
            doc = self.latest_receipt()
            row = json.loads((self.root / ".tasks/ledger" / f"{doc['run_id']}.json").read_text())
            self.assertEqual(row["diff_size"]["files"]["value"], len(doc["changed_paths"]))

        self.prove_runner_mutation_fails(
            '"files": observed_number(len(receipt["changed_paths"])),',
            '"files": observed_number(0),',
            check,
        )
        self.clean_runs()

    def test_ledger_row_token_counts_not_swapped(self):
        self.install_fixture_emitting_provider("codex", "codex.jsonl")
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        result = self.invoke(self.ledger_worker_base())
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        receipt = self.latest_receipt()
        usage = receipt["observation"]["usage"]
        row = json.loads((self.root / ".tasks/ledger" / f"{receipt['run_id']}.json").read_text())
        self.assertEqual(row["tokens_input"]["value"], usage["input"]["value"])
        self.assertEqual(row["tokens_output"]["value"], usage["output"]["value"])
        self.assertNotEqual(usage["input"]["value"], usage["output"]["value"])

        def check():
            self.clean_runs()
            self.install_fixture_emitting_provider("codex", "codex.jsonl")
            self.write_fleet("codex", "ledger-model", "medium", "unknown")
            self.invoke(self.ledger_worker_base())
            doc = self.latest_receipt()
            usage = doc["observation"]["usage"]
            row = json.loads((self.root / ".tasks/ledger" / f"{doc['run_id']}.json").read_text())
            self.assertEqual(row["tokens_input"]["value"], usage["input"]["value"])
            self.assertEqual(row["tokens_output"]["value"], usage["output"]["value"])

        self.prove_runner_mutation_fails(
            '"value": usage["input"]["value"],',
            '"value": usage["output"]["value"],',
            check,
        )
        self.clean_runs()

    def test_ledger_second_write_same_run_id_does_not_replace_row(self):
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        result = self.invoke(self.ledger_worker_base())
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        receipt = self.latest_receipt()
        row_path = self.root / ".tasks/ledger" / f"{receipt['run_id']}.json"
        first_bytes = row_path.read_bytes()
        retry = self.invoke([
            sys.executable, "-c",
            "import json, pathlib, sys; sys.path.insert(0, 'scripts'); "
            "from execution_runner import write_ledger_row; "
            f"spec = json.loads(pathlib.Path('.tasks/specs/{receipt['run_id']}.json').read_text()); "
            f"receipt = json.loads(pathlib.Path('.tasks/receipts/{receipt['run_id']}.json').read_text()); "
            "receipt['feature'] = 'F002'; "
            f"write_ledger_row(spec, receipt, tier='economy', log=pathlib.Path('.tasks/logs/{receipt['run_id']}.log'))",
        ])
        self.assertEqual(retry.returncode, 0, retry.stderr + retry.stdout)
        self.assertEqual(row_path.read_bytes(), first_bytes)

        def check():
            self.clean_runs()
            self.write_fleet("codex", "ledger-model", "medium", "unknown")
            self.invoke(self.ledger_worker_base())
            doc = self.latest_receipt()
            path = self.root / ".tasks/ledger" / f"{doc['run_id']}.json"
            run_id = doc["run_id"]
            retry = self.invoke([
                sys.executable, "-c",
                "import json, pathlib, sys; sys.path.insert(0, 'scripts'); "
                "from execution_runner import write_ledger_row; "
                f"spec = json.loads(pathlib.Path('.tasks/specs/{run_id}.json').read_text()); "
                f"receipt = json.loads(pathlib.Path('.tasks/receipts/{run_id}.json').read_text()); "
                "receipt['feature'] = 'F002'; "
                f"write_ledger_row(spec, receipt, tier='economy', log=pathlib.Path('.tasks/logs/{run_id}.log'))",
            ])
            self.assertEqual(retry.returncode, 0, retry.stderr + retry.stdout)
            row = json.loads(path.read_text())
            self.assertEqual(row["feature"], "F001")

        check()
        self.prove_runner_mutation_fails(
            "        try:\n            os.link(temp, path)\n        except FileExistsError as exc:\n"
            "            raise OSError(f\"ledger row already exists for run_id {path.stem}\") from exc\n",
            "        os.replace(temp, path)\n",
            check,
        )
        self.clean_runs()

    def install_codex_ledger_editing_provider(self, source):
        self.install_fixture_emitting_provider("codex", "codex.jsonl")
        path = self.bin / "codex"
        inject = f"pathlib.Path('scripts/ledger.py').write_text({source!r})\n"
        path.write_text(path.read_text().replace("raise SystemExit", inject + "raise SystemExit", 1))

    def restore_ledger_module(self):
        shutil.copy2(ROOT / "scripts/ledger.py", self.root / "scripts/ledger.py")
        self.commit_fixture("restore ledger module")

    def run_with_broken_ledger_module(self, source):
        (self.root / "scripts/ledger.py").write_text(source)
        self.commit_fixture("broken ledger module")
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        result = self.invoke(self.ledger_worker_base())
        self.assert_terminal_run_hygiene(result, expected_exit=0)
        run_id = self.latest_receipt()["run_id"]
        self.assert_ledger_warn_without_row(result, run_id)
        self.assertIn("ledger: module unavailable", self.log_text(run_id))
        self.restore_ledger_module()

    def test_ledger_module_edited_during_run_is_not_executed(self):
        breakages = {"syntax": "def broken(:\n", "runtime": "raise RuntimeError('ledger import boom')\n"}
        for label, source in breakages.items():
            with self.subTest(breakage=label):
                self.clean_runs()
                self.install_codex_ledger_editing_provider(source)
                self.write_fleet("codex", "ledger-model", "medium", "unknown")
                result = self.invoke(self.ledger_worker_base())
                self.assert_terminal_run_hygiene(result, expected_exit=0)
                run_id = self.latest_receipt()["run_id"]
                self.assertNotIn("WARN", self.log_text(run_id))
                row = json.loads((self.root / ".tasks/ledger" / f"{run_id}.json").read_text())
                self.assertEqual(row["run_id"], run_id)
                self.restore_ledger_module()
        self.clean_runs()

    def test_ledger_module_broken_before_run_skips_only_the_ledger_step(self):
        breakages = {"syntax": "def broken(:\n", "runtime": "raise RuntimeError('ledger import boom')\n"}
        for label, source in breakages.items():
            with self.subTest(breakage=label):
                self.clean_runs()
                self.run_with_broken_ledger_module(source)
        self.clean_runs()
        # Restoring `except ImportError` alone lets a SyntaxError escape the runner's start-up import.
        self.prove_runner_mutation_fails(
            "except Exception:\n    LedgerError = None\n",
            "except ImportError:\n    LedgerError = None\n",
            lambda: self.run_with_broken_ledger_module("def broken(:\n"),
        )
        self.clean_runs()

    def test_ledger_generic_failure_warn_never_prints_exception_text(self):
        secret = "ledger-" + "secret-" + "probe"
        faulty = (ROOT / "scripts/ledger.py").read_text() + f"\n\ndef validate_row(row, door_names=None):\n    raise RuntimeError({secret!r})\n"

        def check():
            self.clean_runs()
            (self.root / "scripts/ledger.py").write_text(faulty)
            self.commit_fixture("faulty ledger validator")
            self.write_fleet("codex", "ledger-model", "medium", "unknown")
            result = self.invoke(self.ledger_worker_base())
            self.assert_terminal_run_hygiene(result, expected_exit=0)
            run_id = self.latest_receipt()["run_id"]
            log = self.log_text(run_id)
            self.assertIn("WARN: ledger row not written: ledger: row build failed", log)
            self.assertNotIn(secret, result.stdout + result.stderr + log)
            self.assertFalse((self.root / ".tasks/ledger" / f"{run_id}.json").is_file())
            self.restore_ledger_module()

        check()
        self.prove_runner_mutation_fails(
            "    except Exception:\n        warn_ledger(log, \"ledger: row build failed\")\n",
            "    except Exception as exc:\n        warn_ledger(log, f\"ledger: row build failed: {exc!r}\")\n",
            check,
        )
        self.clean_runs()

    def test_runner_writes_one_valid_ledger_row_per_outcome(self):
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        base = ["bash", "scripts/spawn-worker.sh", "codex", "docs/missions/fixture/tasks/T-001.md",
                "--model", "ledger-model", "--feature", "F001"]
        ok = self.invoke(base)
        self.assertEqual(ok.returncode, 0, ok.stderr + ok.stdout)
        completed_id = json.loads(next((self.root / ".tasks/receipts").glob("*.json")).read_text())["run_id"]
        self.assert_ledger_row_hygiene(completed_id)
        self.clean_runs()

        fail = self.invoke(base, env={"PROVIDER_EXIT": "7"})
        self.assertEqual(fail.returncode, 7, fail.stderr + fail.stdout)
        failed_id = json.loads(next((self.root / ".tasks/receipts").glob("*.json")).read_text())["run_id"]
        failed_row = json.loads((self.root / ".tasks/ledger" / f"{failed_id}.json").read_text())
        self.assertEqual(failed_row["outcome"], "failed")
        self.assert_ledger_row_hygiene(failed_id)
        self.clean_runs()

        timeout = self.invoke(base, env={"PROVIDER_WAIT_FOR": str(self.parent / "never"),
                                         "SPAWN_WORKER_TIMEOUT_SECS": "0.15"})
        self.assertEqual(timeout.returncode, 124, timeout.stderr + timeout.stdout)
        timed_id = self.latest_receipt()["run_id"]
        timed_row = json.loads((self.root / ".tasks/ledger" / f"{timed_id}.json").read_text())
        self.assertEqual(timed_row["outcome"], "timed_out")
        self.assert_ledger_row_hygiene(timed_id)
        self.clean_runs()

        codex = self.bin / "codex"
        stub = codex.read_bytes()
        codex.unlink()
        launch = self.invoke(base, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(launch.returncode, 127, launch.stderr + launch.stdout)
        codex.write_bytes(stub)
        codex.chmod(0o755)
        launch_id = self.latest_receipt()["run_id"]
        launch_row = json.loads((self.root / ".tasks/ledger" / f"{launch_id}.json").read_text())
        self.assertEqual(launch_row["outcome"], "launch_failed")
        self.assert_ledger_row_hygiene(launch_id)

        def check():
            self.clean_runs()
            self.write_fleet("codex", "ledger-model", "medium", "unknown")
            fail = self.invoke(base, env={"PROVIDER_EXIT": "7"})
            self.assertEqual(fail.returncode, 7, fail.stderr + fail.stdout)
            failed_id = self.latest_receipt()["run_id"]
            self.assert_ledger_row_hygiene(failed_id)

        self.prove_runner_mutation_fails(
            "    try:\n        row = build_ledger_row(spec, receipt, tier=tier)",
            "    if receipt.get('outcome') != 'completed':\n        return\n    try:\n        row = build_ledger_row(spec, receipt, tier=tier)",
            check,
        )
        self.clean_runs()

    def test_verification_command_short_label_passes_ledger_privacy(self):
        long_argv = [
            "bash", "-c",
            "! grep -nE '(ghp_|github_pat_|AKIA|xox[abpr]-|-----BEGIN)[A-Za-z0-9_-]{4,}' tests/test-ledger.py",
        ]
        task_path = self.task.parent / "T-ledger-label.md"
        task_path.write_text(
            "---\n"
            "task_id: T-ledger-label\n"
            "feature: F001\n"
            "---\n"
            "# Task\n\n"
            "## Files you MAY touch\n"
            "- `allowed.txt`\n\n"
            "## Verification commands\n\n"
            f"- `{json.dumps(long_argv)}`\n"
        )
        self.commit_fixture("ledger label task")
        sys.path.insert(0, str(self.root / "scripts"))
        from execution_runner import check_command_label  # noqa: E402
        label = check_command_label(long_argv, 0, [long_argv])
        self.assertLess(len(label), 80)
        self.assertNotIn("grep", label)
        self.assertEqual(label, "bash#1")
        second = ["bash", "-c", "true"]
        label_two = check_command_label(second, 1, [long_argv, second])
        self.assertEqual(label_two, "bash#2")

        def check():
            probe = self.invoke([
                sys.executable, "-c",
                "import json, sys; sys.path.insert(0, 'scripts'); "
                "from execution_runner import check_command_label; "
                f"cmds = {json.dumps([long_argv, second])}; "
                "print(check_command_label(cmds[1], 1, cmds))",
            ])
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(probe.stdout.strip(), "bash#2")

        self.prove_runner_mutation_fails('return f"{base}#{occurrence}"', "return base", check)
        good = json.loads((ROOT / "tests/fixtures/ledger/good-completed.json").read_text())
        good["checks"] = [{"name": label, "exit_code": 0}]
        probe = self.parent / "ledger-label-probe.json"
        probe.write_text(json.dumps(good, indent=2) + "\n")
        valid = self.invoke([sys.executable, "scripts/ledger.py", "validate", str(probe)])
        self.assertEqual(valid.returncode, 0, valid.stderr + valid.stdout)

    def test_ledger_fold_lands_in_acceptance_commit_exactly_once(self):
        self.set_status("in-progress")
        self.write_fleet("codex", "ledger-model", "medium", "unknown")
        first = self.invoke(self.ledger_worker_base(), env={"PROVIDER_ACTION": "commit"})
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        run_id = self.latest_receipt()["run_id"]
        self.assert_ledger_row_hygiene(run_id)
        self.assertEqual(self.git("status", "--porcelain").stdout.strip(), "")
        preflight = self.invoke([
            sys.executable, "-c",
            "import sys; from pathlib import Path; sys.path.insert(0, 'scripts'); "
            "from dispatch_policy import clean_workspace; clean_workspace(Path('.').resolve()); print('ok')",
        ])
        self.assertEqual(preflight.returncode, 0, preflight.stderr + preflight.stdout)

        verified = self.invoke(["bash", "scripts/verify-mission.sh", "--run-id", run_id, "docs/missions/fixture"])
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)

        folded = self.invoke([sys.executable, "scripts/ledger.py", "fold", "docs/missions/fixture"])
        self.assertEqual(folded.returncode, 0, folded.stderr + folded.stdout)
        self.assertIn("folded rows=1", folded.stdout)
        self.git("add", "docs/missions")
        self.git("commit", "-qm", "acceptance")

        again = self.invoke([sys.executable, "scripts/ledger.py", "fold", "docs/missions/fixture"])
        self.assertEqual(again.returncode, 0, again.stderr + again.stdout)
        self.assertEqual(again.stdout.strip(), "folded rows=0 drift=0")
        self.assertEqual(self.git("status", "--porcelain").stdout.strip(), "")

    def test_all_worker_provider_tier_mappings_use_frozen_values(self):
        for provider in PROVIDERS:
            for tier in ("economy", "premium"):
                with self.subTest(provider=provider, tier=tier):
                    speed = "fast" if provider == "agent" else "unknown"
                    model = (f"{provider}-{tier}-frozen-fast" if provider == "agent" else
                             f"{provider}-{tier}-frozen-high" if provider == "agy" else f"{provider}-{tier}-frozen")
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
