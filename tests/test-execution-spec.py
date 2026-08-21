#!/usr/bin/env python3
"""Deterministic contract tests for immutable ExecutionSpec and provider adapter."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SPEC_TOOL = ROOT / "scripts" / "execution_spec.py"
ADAPTER = ROOT / "scripts" / "execute_provider.py"


class ExecutionSpecContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.command(["git", "init", "-q"], cwd=self.repo)
        self.command(["git", "config", "user.email", "test@example.invalid"], cwd=self.repo)
        self.command(["git", "config", "user.name", "Execution Spec Test"], cwd=self.repo)
        (self.repo / "README.md").write_text("fixture\n")
        self.command(["git", "add", "README.md"], cwd=self.repo)
        self.command(["git", "commit", "-qm", "fixture"], cwd=self.repo)
        self.commit = self.command(["git", "rev-parse", "HEAD"], cwd=self.repo).stdout.strip()
        self.sentinel = self.tmp / "provider-sentinel"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name in ("codex", "claude", "agent", "agy"):
            path = self.bin / name
            path.write_text("#!/usr/bin/env bash\nprintf '%s\\n' invoked >> \"$EXECUTION_SENTINEL\"\n")
            path.chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    @staticmethod
    def command(argv, cwd=None, check=True, env=None):
        return subprocess.run(argv, cwd=cwd, check=check, text=True, capture_output=True, env=env)

    def spec(self, provider="codex", role="brain", **changes):
        value = {
            "schema_version": 1,
            "run_id": str(uuid.uuid4()),
            "mission": "docs/missions/fixture",
            "work_unit": "T-001",
            "role": role,
            "feature": None if role == "brain" else "F001",
            "provider": provider,
            "model": "test-model",
            "effort": "medium",
            "speed": "unknown",
            "repo": str(self.repo),
            "base_commit": self.commit,
            "attempt": 1,
            "prompt": "exact prompt",
        }
        value.update(changes)
        return value

    def persist(self, spec, check=True):
        source = self.tmp / f"input-{uuid.uuid4()}.json"
        source.write_text(json.dumps(spec))
        return self.command([sys.executable, str(SPEC_TOOL), "persist", "--input", str(source)], check=check)

    def persisted(self, spec):
        result = self.persist(spec)
        return Path(json.loads(result.stdout)["path"])

    def adapter(self, spec_path, dry=True, env=None, check=True):
        argv = [sys.executable, str(ADAPTER), "--spec", str(spec_path)]
        if dry:
            argv.append("--dry-run")
        return self.command(argv, check=check, env=env)

    def test_schema_and_validator_reject_weakest_invalid_values(self):
        schema = json.loads((ROOT / "schemas" / "execution-spec.schema.json").read_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(self.spec()))
        cases = [
            ({"schema_version": 2}, "schema_version"),
            ({"run_id": "not-a-uuid"}, "run_id"),
            ({"mission": ""}, "mission"),
            ({"work_unit": " "}, "work_unit"),
            ({"role": "operator"}, "role"),
            ({"provider": "other"}, "provider"),
            ({"model": ""}, "model"),
            ({"effort": ""}, "effort"),
            ({"speed": ""}, "speed"),
            ({"repo": "relative"}, "repo"),
            ({"base_commit": "not-a-commit"}, "base_commit"),
            ({"base_commit": "0" * 40}, "base_commit"),
            ({"attempt": 0}, "attempt"),
            ({"prompt": ""}, "prompt"),
            ({"feature": ""}, "feature"),
        ]
        for changes, label in cases:
            with self.subTest(label=label):
                values = {"role": "worker"}
                values.update(changes)
                value = self.spec(**values)
                result = self.persist(value, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.repo / ".tasks" / "specs" / f"{value['run_id']}.json").exists())
        value = self.spec()
        del value["prompt"]
        self.assertNotEqual(self.persist(value, check=False).returncode, 0)
        value = self.spec(extra="rejected")
        self.assertNotEqual(self.persist(value, check=False).returncode, 0)
        self.assertNotEqual(self.persist(self.spec(feature="wrong"), check=False).returncode, 0)
        alias = self.repo.parent / "repo-alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        unsafe = self.spec(repo=str(alias))
        self.assertNotEqual(self.persist(unsafe, check=False).returncode, 0)

    def test_persistence_is_canonical_hashed_and_no_clobber(self):
        value = self.spec()
        result = self.persist(value)
        outcome = json.loads(result.stdout)
        path = Path(outcome["path"])
        expected = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(outcome["sha256"], hashlib.sha256(expected).hexdigest())
        again = self.persist(value, check=False)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(path.read_bytes(), expected)
        amended = self.spec(run_id=str(uuid.uuid4()), prompt="amended prompt")
        self.assertNotEqual(amended["run_id"], value["run_id"])
        self.assertTrue(self.persist(amended).returncode == 0)

    def test_exact_dry_run_contract_for_every_provider_and_role(self):
        expected = {
            "codex": lambda s: ["codex", "exec", "-C", str(self.repo), "-s", "workspace-write", "-m", "test-model", "-c", 'model_reasoning_effort="medium"', "exact prompt"],
            "claude": lambda s: ["claude", "-p", "exact prompt", "--model", "test-model", "--effort", "medium", "--allowedTools", "Read,Write,Edit,Bash"],
            "agy": lambda s: ["agy", "--dangerously-skip-permissions", "--print-timeout", "30m", "--model", "test-model", "--effort", "medium", "-p", "exact prompt"],
            "agent": lambda s: ["agent", "-p", "--force", "--trust", "--workspace", str(self.repo), "--model", "test-model[effort=medium,fast=false]", "exact prompt"],
        }
        for provider in expected:
            for role in ("brain", "worker"):
                with self.subTest(provider=provider, role=role):
                    changes = {"speed": "standard"} if provider == "agent" else {}
                    path = self.persisted(self.spec(provider=provider, role=role, **changes))
                    result = json.loads(self.adapter(path).stdout)
                    self.assertEqual(result["argv"], expected[provider](None))
                    self.assertEqual(result["env_overrides"], {})
                    self.assertEqual(result["observed"], {"model": "unknown", "effort": "unknown", "speed": "unknown"})
        fast = self.persisted(self.spec(provider="agent", speed="fast"))
        self.assertEqual(json.loads(self.adapter(fast).stdout)["argv"][-2], "test-model[effort=medium,fast=true]")

    def test_negative_adapter_paths_do_not_invoke_provider_sentinel(self):
        env = dict(__import__("os").environ)
        env.update(PATH=f"{self.bin}:{env['PATH']}", EXECUTION_SENTINEL=str(self.sentinel))
        # Missing required field is supplied as a persisted-looking file: the shared adapter
        # must validate it before it can resolve or launch the provider.
        missing = self.spec()
        del missing["prompt"]
        missing_path = self.repo / ".tasks" / "specs" / f"{missing['run_id']}.json"
        missing_path.parent.mkdir(parents=True)
        missing_path.write_text(json.dumps(missing, sort_keys=True, separators=(",", ":")) + "\n")
        self.assertNotEqual(self.adapter(missing_path, dry=False, env=env, check=False).returncode, 0)
        unsupported_effort = self.persisted(self.spec(provider="agy", effort="xhigh"))
        self.assertNotEqual(self.adapter(unsupported_effort, dry=False, env=env, check=False).returncode, 0)
        unsupported_speed = self.persisted(self.spec(provider="codex", speed="fast"))
        self.assertNotEqual(self.adapter(unsupported_speed, dry=False, env=env, check=False).returncode, 0)
        unknown_agent = self.persisted(self.spec(provider="agent", speed="unknown"))
        self.assertNotEqual(self.adapter(unknown_agent, dry=False, env=env, check=False).returncode, 0)
        parameterized_agent = self.persisted(self.spec(provider="agent", speed="fast", model="test-model[x=true]"))
        self.assertNotEqual(self.adapter(parameterized_agent, dry=False, env=env, check=False).returncode, 0)
        collision = self.spec()
        self.persist(collision)
        self.assertNotEqual(self.persist(collision, check=False).returncode, 0)
        self.assertFalse(self.sentinel.exists(), "a rejected request must never launch the provider")


if __name__ == "__main__":
    unittest.main(verbosity=2)
