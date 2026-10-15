#!/usr/bin/env python3
"""Deterministic contract tests for immutable ExecutionSpec and provider adapter."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import execution_spec  # noqa: E402

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

    def spec_v2(self, provider="codex", role="brain", **changes):
        value = self.spec(provider=provider, role=role)
        value["schema_version"] = 2
        value["write_scope"] = ["docs/missions/fixture/**"] if role == "brain" else ["allowed.txt"]
        value.update(changes)
        return value

    def spec_v3(self, provider="codex", role="brain", **changes):
        value = self.spec_v2(provider=provider, role=role)
        value["schema_version"] = 3
        value["provider_contract_version"] = 2
        value.update(changes)
        return value

    def persist(self, spec, check=True):
        source = self.tmp / f"input-{uuid.uuid4()}.json"
        source.write_text(json.dumps(spec))
        return self.command([sys.executable, str(SPEC_TOOL), "persist", "--input", str(source)], check=check)

    def persisted(self, spec):
        result = self.persist(spec)
        outcome = json.loads(result.stdout)
        return Path(outcome["path"]), outcome["sha256"]

    def adapter(self, spec_path, digest, dry=True, env=None, check=True):
        argv = [sys.executable, str(ADAPTER), "--spec", str(spec_path), "--sha256", digest]
        if dry:
            argv.append("--dry-run")
        return self.command(argv, check=check, env=env)

    def test_schema_and_validator_reject_weakest_invalid_values(self):
        schema = json.loads((ROOT / "schemas" / "execution-spec.schema.json").read_text())
        self.assertEqual(len(schema["oneOf"]), 3)
        self.assertFalse(schema["oneOf"][0]["additionalProperties"])
        self.assertEqual(set(schema["oneOf"][0]["required"]), set(self.spec()))
        self.assertFalse(schema["oneOf"][1]["additionalProperties"])
        self.assertEqual(set(schema["oneOf"][1]["required"]), set(self.spec_v2()))
        self.assertFalse(schema["oneOf"][2]["additionalProperties"])
        self.assertEqual(set(schema["oneOf"][2]["required"]), set(self.spec_v3()))
        cases = [
            ({"schema_version": 3}, "schema_version"),
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

        for candidate in ([], [""], ["/absolute"], ["../escape"], ["a/../b"],
                          [".git/config"], [".tasks/**"], ["a\\b"], ["same", "same"]):
            with self.subTest(write_scope=candidate):
                self.assertNotEqual(self.persist(self.spec_v2(write_scope=candidate), check=False).returncode, 0)
        self.assertEqual(self.persist(self.spec_v2()).returncode, 0)
        self.assertEqual(self.persist(self.spec_v3()).returncode, 0)
        self.assertEqual(self.persist(self.spec_v3(provider_contract_version=3)).returncode, 0)
        self.assertNotEqual(self.persist(self.spec_v3(provider_contract_version=1), check=False).returncode, 0)
        self.assertEqual(self.persist(self.spec_v3(provider_contract_version=4), check=False).returncode, 0)
        self.assertEqual(self.persist(self.spec_v3(provider_contract_version=5), check=False).returncode, 0)
        self.assertEqual(self.persist(self.spec_v3(provider_contract_version=6), check=False).returncode, 0)
        self.assertNotEqual(self.persist(self.spec_v3(provider_contract_version=7), check=False).returncode, 0)
        self.assertNotEqual(self.persist(self.spec_v3(provider_contract_version=True), check=False).returncode, 0)

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

    def test_versioned_exact_dry_run_contract_for_every_provider_and_role(self):
        contract_one = {
            "codex": lambda s: ["codex", "exec", "-C", str(self.repo), "-s", "workspace-write", "-m", "test-model", "-c", 'model_reasoning_effort="medium"', "exact prompt"],
            "claude": lambda s: ["claude", "-p", "exact prompt", "--model", "test-model", "--effort", "medium", "--allowedTools", "Read,Write,Edit,Bash"],
            "agy": lambda s: ["agy", "--dangerously-skip-permissions", "--print-timeout", "30m", "--model", "test-model", "--effort", "medium", "-p", "exact prompt"],
            "agent": lambda s: ["agent", "-p", "--force", "--trust", "--workspace", str(self.repo), "--model", "test-model[effort=medium,fast=false]", "exact prompt"],
        }
        for provider in contract_one:
            for role in ("brain", "worker"):
                with self.subTest(provider=provider, role=role):
                    changes = {"speed": "standard"} if provider == "agent" else {}
                    for legacy in (self.spec(provider=provider, role=role, **changes), self.spec_v2(provider=provider, role=role, **changes)):
                        path, digest = self.persisted(legacy)
                        result = json.loads(self.adapter(path, digest).stdout)
                        self.assertEqual(result["argv"], contract_one[provider](None))
                        self.assertEqual(result["env_overrides"], {})
                        self.assertEqual(result["observed"], {"model": "unknown", "effort": "unknown", "speed": "unknown"})
                    for contract in (2, 3):
                        path, digest = self.persisted(self.spec_v3(provider=provider, role=role,
                                                                   provider_contract_version=contract, **changes))
                        result = json.loads(self.adapter(path, digest).stdout)
                        expected = contract_one[provider](None)
                        if provider == "codex":
                            expected = expected[:6] + ["--add-dir", str(self.repo / ".git")] + expected[6:]
                        if provider == "agent" and contract == 3:
                            # Grok Build also installs a bare `agent`; contract 3 names Cursor's CLI.
                            expected = ["cursor-agent"] + expected[1:]
                        self.assertEqual(result["argv"], expected)
        fast, fast_digest = self.persisted(self.spec_v3(provider="agent", speed="fast"))
        self.assertEqual(json.loads(self.adapter(fast, fast_digest).stdout)["argv"][-2], "test-model[effort=medium,fast=true]")

    def test_codex_contract_five_mounts_agents_only_when_write_scope_names_it(self):
        git_dir = str(self.repo / ".git")
        agents_dir = str(self.repo / ".agents")
        cases = [
            (5, [".agents/skills/x/SKILL.md"], ["--add-dir", git_dir, "--add-dir", agents_dir]),
            (5, ["docs/x.md", ".agents/skills/x/SKILL.md"], ["--add-dir", git_dir, "--add-dir", agents_dir]),
            (5, ["docs/x.md"], ["--add-dir", git_dir]),
            (4, [".agents/skills/x/SKILL.md"], ["--add-dir", git_dir]),
            (3, [".agents/skills/x/SKILL.md"], ["--add-dir", git_dir]),
        ]
        for contract, write_scope, expected_dirs in cases:
            with self.subTest(contract=contract, write_scope=write_scope):
                path, digest = self.persisted(self.spec_v3(provider="codex", provider_contract_version=contract,
                                                           write_scope=write_scope))
                argv = json.loads(self.adapter(path, digest).stdout)["argv"]
                self.assertEqual(argv, ["codex", "exec", "-C", str(self.repo), "-s", "workspace-write", *expected_dirs,
                                        "-m", "test-model", "-c", 'model_reasoning_effort="medium"', "exact prompt"])

    def test_cursor_contract_four_plain_models_and_prelaunch_rejections(self):
        cases = [
            ("composer-2.5", "medium", "standard", "composer-2.5"),
            ("grok-4.7-medium", "medium", "standard", "grok-4.7-medium"),
        ]
        for model, effort, speed, expected_model in cases:
            path, digest = self.persisted(self.spec_v3(provider="agent", model=model, effort=effort, speed=speed,
                                                       provider_contract_version=4))
            argv = json.loads(self.adapter(path, digest).stdout)["argv"]
            self.assertEqual(argv[argv.index("--model") + 1], expected_model)
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", EXECUTION_SENTINEL=str(self.sentinel))
        rejected = [
            ("grok-4.7-xhigh", "medium", "standard"),
            ("composer-2.5-fast", "medium", "standard"),
            ("composer-2.5", "medium", "fast"),
        ]
        for model, effort, speed in rejected:
            with self.subTest(model=model, effort=effort, speed=speed):
                path, digest = self.persisted(self.spec_v3(provider="agent", model=model, effort=effort, speed=speed,
                                                           provider_contract_version=4))
                result = self.adapter(path, digest, dry=False, env=env, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.sentinel.exists())

    def test_cursor_real_rejection_fixture_contract_three_fails_contract_four_succeeds(self):
        fixture = ROOT / "tests/fixtures/cursor-model-rejection.txt"
        message = fixture.read_text().strip()
        available = message.split("Available models: ", 1)[1]
        fake_bin = self.tmp / "cursor-bin"
        fake_bin.mkdir()
        fake = fake_bin / "cursor-agent"
        fake.write_text("#!/usr/bin/env python3\nimport sys\nmodel = sys.argv[sys.argv.index('--model') + 1]\navailable = " + repr(available) + "\nif model not in available.split(', '):\n    print(" + repr(message.split('. Available models:', 1)[0] + '. Available models: ') + " + available)\n    raise SystemExit(1)\nprint('OK')\n")
        fake.chmod(0o755)
        env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}")
        for contract, expected in ((3, 1), (4, 0)):
            path, digest = self.persisted(self.spec_v3(provider="agent", model="composer-2.5", effort="medium", speed="standard",
                                                       provider_contract_version=contract))
            result = self.adapter(path, digest, dry=False, env=env, check=False)
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            if contract == 3:
                self.assertTrue(result.stdout.startswith(message.split('. Available models:', 1)[0] + '. Available models:'))
            else:
                self.assertEqual(result.stdout.strip(), "OK")

    def test_construct_emits_contract_6(self):
        spec, path, _ = execution_spec.construct(
            role="worker", mission="docs/missions/fixture", feature="F001", work_unit="T-001", attempt=1,
            provider="codex", model="test-model", effort="medium", speed="unknown", repo=str(self.repo),
            prompt="exact prompt", write_scope=["allowed.txt"],
        )
        self.assertEqual(spec["schema_version"], 3)
        self.assertEqual(spec["provider_contract_version"], 6)
        self.assertEqual(json.loads(path.read_text()), spec)

    def test_contract_six_requests_json_cli_output(self):
        repo = str(self.repo)
        git_dir = str(self.repo / ".git")
        cases = [
            ("codex", {}, ["codex", "exec", "--json", "-C", repo, "-s", "workspace-write", "--add-dir", git_dir,
                           "-m", "test-model", "-c", 'model_reasoning_effort="medium"', "exact prompt"]),
            ("claude", {}, ["claude", "-p", "exact prompt", "--output-format", "json", "--model", "test-model",
                            "--effort", "medium", "--allowedTools", "Read,Write,Edit,Bash"]),
            ("agy", {}, ["agy", "--dangerously-skip-permissions", "--print-timeout", "30m", "--model", "test-model",
                         "--effort", "medium", "-p", "exact prompt"]),
            ("agent", {"speed": "standard"}, ["cursor-agent", "-p", "--force", "--trust", "--output-format", "stream-json",
                                              "--workspace", repo, "--model", "test-model", "exact prompt"]),
        ]
        for provider, extra, expected in cases:
            with self.subTest(provider=provider):
                path, digest = self.persisted(self.spec_v3(provider=provider, provider_contract_version=6, **extra))
                argv = json.loads(self.adapter(path, digest).stdout)["argv"]
                self.assertEqual(argv, expected)
        path, digest = self.persisted(self.spec_v3(provider="codex", provider_contract_version=5))
        argv = json.loads(self.adapter(path, digest).stdout)["argv"]
        self.assertNotIn("--json", argv)

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
        self.assertNotEqual(self.adapter(missing_path, "0" * 64, dry=False, env=env, check=False).returncode, 0)
        unsupported_effort, unsupported_effort_digest = self.persisted(self.spec(provider="agy", effort="xhigh"))
        self.assertNotEqual(self.adapter(unsupported_effort, unsupported_effort_digest, dry=False, env=env, check=False).returncode, 0)
        unsupported_speed, unsupported_speed_digest = self.persisted(self.spec(provider="codex", speed="fast"))
        self.assertNotEqual(self.adapter(unsupported_speed, unsupported_speed_digest, dry=False, env=env, check=False).returncode, 0)
        unknown_agent, unknown_agent_digest = self.persisted(self.spec(provider="agent", speed="unknown"))
        self.assertNotEqual(self.adapter(unknown_agent, unknown_agent_digest, dry=False, env=env, check=False).returncode, 0)
        parameterized_agent, parameterized_agent_digest = self.persisted(self.spec(provider="agent", speed="fast", model="test-model[x=true]"))
        self.assertNotEqual(self.adapter(parameterized_agent, parameterized_agent_digest, dry=False, env=env, check=False).returncode, 0)
        collision = self.spec()
        self.persist(collision)
        self.assertNotEqual(self.persist(collision, check=False).returncode, 0)
        self.assertFalse(self.sentinel.exists(), "a rejected request must never launch the provider")

    def test_atomic_publish_boundary_and_hash_bound_launch(self):
        value = self.spec()
        final = self.repo / ".tasks" / "specs" / f"{value['run_id']}.json"
        with self.assertRaisesRegex(RuntimeError, "fault"):
            execution_spec.persist(value, before_publish=lambda: (_ for _ in ()).throw(RuntimeError("fault")))
        self.assertFalse(final.exists(), "a pre-publish fault must leave no final authorization")
        self.assertFalse(list(final.parent.glob(f".{value['run_id']}.*.tmp")))

        path, digest = self.persisted(value)
        rewritten = dict(value)
        rewritten["prompt"] = "different but still valid"
        path.chmod(0o600)
        path.write_bytes(execution_spec.canonical_bytes(rewritten))
        env = dict(__import__("os").environ)
        env.update(PATH=f"{self.bin}:{env['PATH']}", EXECUTION_SENTINEL=str(self.sentinel))
        self.assertNotEqual(self.adapter(path, digest, dry=False, env=env, check=False).returncode, 0)
        self.assertFalse(self.sentinel.exists(), "hash mismatch must reject before provider launch")

    def test_closed_stdin_prevents_provider_read_hang(self):
        reader = self.bin / "codex"
        reader.write_text("#!/usr/bin/env bash\nIFS= read -r ignored\nprintf '%s\\n' invoked >> \"$EXECUTION_SENTINEL\"\n")
        reader.chmod(0o755)
        path, digest = self.persisted(self.spec())
        env = dict(__import__("os").environ)
        env.update(PATH=f"{self.bin}:{env['PATH']}", EXECUTION_SENTINEL=str(self.sentinel))
        read_fd, write_fd = __import__("os").pipe()
        try:
            process = subprocess.Popen(
                [sys.executable, str(ADAPTER), "--spec", str(path), "--sha256", digest],
                stdin=read_fd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
            )
            __import__("os").close(read_fd)
            read_fd = None
            process.communicate(timeout=2)
            self.assertEqual(process.returncode, 0)
            self.assertTrue(self.sentinel.exists())
        finally:
            if read_fd is not None:
                __import__("os").close(read_fd)
            __import__("os").close(write_fd)

    def test_schema_and_validator_agree_on_static_edge_domains(self):
        schema = json.loads((ROOT / "schemas" / "execution-spec.schema.json").read_text())
        properties = schema["oneOf"][0]["properties"]
        cases = [
            ("run_id", "00000000-0000-0000-0000-000000000000", False),
            ("run_id", "12345678-1234-9234-8234-123456789abc", False),
            ("run_id", "12345678-1234-4234-8234-123456789ABC", False),
            ("repo", str(self.repo.parent / " repo"), True),
            ("repo", str(self.repo) + "\nunsafe", False),
            ("prompt", "first line\nsecond line", True),
        ]
        spaced_repo = self.repo.parent / " repo"
        spaced_repo.mkdir()
        self.command(["git", "init", "-q"], cwd=spaced_repo)
        self.command(["git", "config", "user.email", "test@example.invalid"], cwd=spaced_repo)
        self.command(["git", "config", "user.name", "Execution Spec Test"], cwd=spaced_repo)
        (spaced_repo / "README.md").write_text("fixture\n")
        self.command(["git", "add", "README.md"], cwd=spaced_repo)
        self.command(["git", "commit", "-qm", "fixture"], cwd=spaced_repo)
        spaced_commit = self.command(["git", "rev-parse", "HEAD"], cwd=spaced_repo).stdout.strip()
        for field, candidate, expected in cases:
            with self.subTest(field=field, candidate=candidate):
                definition = schema["$defs"]["commonProperties"][field]
                schema_valid = bool(__import__("re").fullmatch(definition["pattern"], candidate))
                self.assertEqual(schema_valid, expected)
                value = self.spec(**{field: candidate})
                if field == "repo" and expected:
                    value["base_commit"] = spaced_commit
                result = self.persist(value, check=False)
                self.assertEqual(result.returncode == 0, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
