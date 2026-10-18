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
import unittest.mock
import uuid

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import execution_spec  # noqa: E402
import execution_receipt  # noqa: E402
import execute_provider  # noqa: E402
from execute_provider import CLAUDE_DISALLOWED_TOOLS, CODEX_CONFIG_OVERRIDES, SpecError, provider_contract  # noqa: E402

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
        (self.repo / ".gitignore").write_text(".tasks/\n")
        (self.repo / "README.md").write_text("fixture\n")
        self.command(["git", "add", ".gitignore", "README.md"], cwd=self.repo)
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
        self.assertEqual(self.persist(self.spec_v3(provider_contract_version=7), check=False).returncode, 0)
        self.assertEqual(self.persist(self.spec_v3(provider_contract_version=8), check=False).returncode, 0)
        self.assertEqual(self.persist(self.spec_v3(provider_contract_version=9), check=False).returncode, 0)
        self.assertNotEqual(self.persist(self.spec_v3(provider_contract_version=10), check=False).returncode, 0)
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
            "codex": lambda s: ["codex", "exec", "-C", str(self.repo), "-s", "workspace-write", "-m", "test-model",
                                "-c", 'model_reasoning_effort="medium"', *CODEX_CONFIG_OVERRIDES, "exact prompt"],
            "claude": lambda s: ["claude", "-p", "exact prompt", "--model", "test-model", "--effort", "medium",
                                 "--allowedTools", "Read,Write,Edit,Bash"],
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
                                        "-m", "test-model", "-c", 'model_reasoning_effort="medium"',
                                        *CODEX_CONFIG_OVERRIDES, "exact prompt"])

    def test_codex_config_overrides_unlock_network_and_disable_repl_servers(self):
        expected_overrides = (
            "-c", "sandbox_workspace_write.network_access=true",
            "-c", 'web_search="live"',
            "-c", 'mcp_servers.cua_repl={command="true",enabled=false}',
            "-c", 'mcp_servers.node_repl={command="true",enabled=false}',
        )
        self.assertEqual(CODEX_CONFIG_OVERRIDES, expected_overrides)
        for contract in (1, 2, 5, 6, 8, 9):
            with self.subTest(contract=contract):
                argv, _ = provider_contract(self.spec_v3(provider="codex", provider_contract_version=contract))
                s_idx = argv.index("-s")
                self.assertEqual(argv[s_idx + 1], "workspace-write")
                self.assertEqual(argv[-1], "exact prompt")
                overrides_slice = tuple(argv[-1 - len(expected_overrides):-1])
                self.assertEqual(overrides_slice, expected_overrides)

        original = execute_provider.CODEX_CONFIG_OVERRIDES
        try:
            execute_provider.CODEX_CONFIG_OVERRIDES = ("-c", "mutated=true")
            argv, _ = provider_contract(self.spec_v3(provider="codex", provider_contract_version=9))
            with self.assertRaises(AssertionError):
                overrides_slice = tuple(argv[-1 - len(expected_overrides):-1])
                self.assertEqual(overrides_slice, expected_overrides)
        finally:
            execute_provider.CODEX_CONFIG_OVERRIDES = original

    def test_contract_nine_codex_pre_t071_argv_reproduces_historical_receipts(self):
        fixtures = [
            ({'schema_version': 3, 'provider': 'codex', 'model': 'gpt-6-luna', 'effort': 'medium', 'speed': 'unknown', 'repo': '/Users/zamirhashorva/dev/purrfect-harness', 'prompt': 'Read docs/missions/20261014-2a-foundation/tasks/T-070-R2.md and complete it exactly. Follow AGENTS.md and the skills the task names. Do not touch files outside the allow-list. Do not write PROGRESS.md; the Front Desk records your run from its receipt. End with a short plain-text report: what you changed and the exit code of each check you ran.', 'write_scope': ['tests/run-tests.sh'], 'provider_contract_version': 9},
             'c67f41f8c3545466ee447d3df797c51ea9b2f234a56196e9496fbd0fa6a81357'),
            ({'schema_version': 3, 'provider': 'codex', 'model': 'gpt-6-luna', 'effort': 'medium', 'speed': 'unknown', 'repo': '/Users/zamirhashorva/dev/purrfect-harness', 'prompt': 'Read docs/missions/20261014-2a-foundation/tasks/T-070-R4.md and complete it exactly. Follow AGENTS.md and the skills the task names. Do not touch files outside the allow-list. Do not write PROGRESS.md; the Front Desk records your run from its receipt. End with a short plain-text report: what you changed and the exit code of each check you ran.', 'write_scope': ['scripts/execution_receipt.py', 'tests/test-execution-receipt.py'], 'provider_contract_version': 9},
             '632ad969bcb2902fbabca9324322d7b8956591e06242c038ec357ddb03d0bfbe'),
        ]
        self.assertEqual(execute_provider.CODEX_PRE_T071_CONFIG_OVERRIDES, ())
        self.assertEqual(execute_provider.CODEX_PRE_T071_CONTRACTS, frozenset({9}))
        for spec, expected in fixtures:
            with self.subTest(expected=expected):
                argv = provider_contract(spec, codex_overrides=execute_provider.CODEX_PRE_T071_CONFIG_OVERRIDES)[0]
                self.assertEqual(execute_provider.argv_sha256(argv), expected)
                self.assertEqual(execute_provider.historical_argv_sha256s(spec), {expected})
                current = execute_provider.argv_sha256(provider_contract(spec)[0])
                self.assertNotEqual(current, expected)
                arbitrary = execute_provider.argv_sha256(argv[:-1] + ["-c", 'web_search="live"', argv[-1]])
                self.assertNotIn(arbitrary, execute_provider.historical_argv_sha256s(spec) | {current})
        for negative in (
            dict(spec, provider_contract_version=8),
            dict(spec, provider_contract_version=True),
            dict(spec, schema_version=2),
            self.spec_v3(provider="claude", provider_contract_version=9),
        ):
            with self.subTest(negative=negative):
                self.assertEqual(execute_provider.historical_argv_sha256s(negative), frozenset())

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

    def test_construct_emits_contract_8(self):
        spec, path, _ = execution_spec.construct(
            role="worker", mission="docs/missions/fixture", feature="F001", work_unit="T-001", attempt=1,
            provider="codex", model="test-model", effort="medium", speed="unknown", repo=str(self.repo),
            prompt="exact prompt", write_scope=["allowed.txt"],
        )
        self.assertEqual(spec["schema_version"], 3)
        self.assertEqual(spec["provider_contract_version"], 9)
        self.assertEqual(json.loads(path.read_text()), spec)

    def test_contract_seven_claude_streams_with_no_mcp_servers_for_every_role(self):
        tail = ["--model", "test-model", "--effort", "medium", "--allowedTools", "Read,Write,Edit,Bash"]
        for role in ("worker", "brain"):
            with self.subTest(role=role):
                path, digest = self.persisted(self.spec_v3(provider="claude", role=role, provider_contract_version=7))
                argv = json.loads(self.adapter(path, digest).stdout)["argv"]
                self.assertEqual(argv, ["claude", "-p", "exact prompt", "--output-format", "stream-json",
                                        "--verbose", "--strict-mcp-config", *tail])
                self.assertNotIn("--permission-mode", argv)
                self.assertNotIn("--disallowedTools", argv)
        for provider, extra in (("codex", {}), ("claude", {}), ("agent", {"speed": "standard"})):
            with self.subTest(provider=provider):
                argvs = []
                for contract in (7, 8):
                    path, digest = self.persisted(self.spec_v3(provider=provider, provider_contract_version=contract, **extra))
                    argvs.append(json.loads(self.adapter(path, digest).stdout)["argv"])
                self.assertEqual(argvs[0], argvs[1])

    def test_claude_mcp_config_is_per_run_and_rejects_weak_values(self):
        for config, emitted in (("/tmp/mcp.json", ["/tmp/mcp.json"]),
                                (["--a", "--b"], ["--a", "--b"])):
            with self.subTest(config=config):
                argv, _ = provider_contract(self.spec_v3(provider="claude", provider_contract_version=9,
                                                         mcp_config=config))
                strict = argv.index("--strict-mcp-config")
                self.assertEqual(argv[strict + 1:strict + 2 + len(emitted)], ["--mcp-config", *emitted])
        for config in ("", [], [""], 123):
            with self.subTest(config=config):
                with self.assertRaisesRegex(SpecError,
                                            "claude mcp_config must be a non-empty string or list of strings"):
                    provider_contract(self.spec_v3(provider="claude", provider_contract_version=9,
                                                   mcp_config=config))

    def test_contract_nine_claude_unlocks_tools_pins_denylist_and_guards_protected_paths(self):
        expected_patterns = (
            "Bash(*rm -rf *)",
        "Bash(*rm -fr *)",
        "Bash(*rm -Rf *)",
        "Bash(*rm -fR *)",
        "Bash(*rm -r -f *)",
        "Bash(*rm -f -r *)",
        "Bash(*rm -r*)",
        "Bash(*rm -R*)",
        "Bash(*rm -fr*)",
        "Bash(*rm -fR*)",
        "Bash(*rm --recursive*)",
        "Bash(*rm --force*)",
        "Bash(*find*-delete*)",
        "Bash(*rmtree*)",
        "Bash(*-exec rm*)",
        "Bash(*git*push*)",
        "Bash(*git*reset*--hard*)",
        "Bash(*git*checkout*-- *)",
        "Bash(*git*checkout*-f*)",
        "Bash(*git*checkout*--force*)",
        "Bash(*git*clean*-f*)",
        "Bash(*git*clean*-d*)",
        "Bash(*git*clean*-x*)",
        "Bash(*git*clean*--force*)",
        "Bash(*git*branch*-D*)",
        "Bash(*git*stash*clear*)",
        "Bash(*git*stash*drop*)",
        "Bash(*git*config*alias.*)",
        "Bash(*git*config*--global*)",
        "Bash(*git*update-index*--skip-worktree*)",
        "Bash(*git*update-index*--assume-unchanged*)",
        "Bash(*chmod*-R*)",
        "Bash(*chmod*--recursive*)",
        "Bash(sudo *)",
        "Bash(* sudo *)",
        "Bash(*curl*|*sh*)",
        "Bash(*wget*|*sh*)",
        "Edit(../*)",
        "Write(../*)",
        "Edit(../**)",
        "Write(../**)",
        "Edit(../../**)",
        "Write(../../**)",
        "Edit(../../../**)",
        "Write(../../../**)",
        "Edit(~/.claude/**)",
        "Write(~/.claude/**)",
        "Edit(~/.claude.json)",
        "Write(~/.claude.json)",
        "Edit(~/.zshrc)",
        "Write(~/.zshrc)",
        "Edit(~/.zshenv)",
        "Write(~/.zshenv)",
        "Edit(~/.zprofile)",
        "Write(~/.zprofile)",
        "Edit(~/.bash_profile)",
        "Write(~/.bash_profile)",
        "Edit(~/.bashrc)",
        "Write(~/.bashrc)",
        "Edit(~/.gitconfig)",
        "Write(~/.gitconfig)",
        "Edit(~/.config/git/**)",
        "Write(~/.config/git/**)",
        "Edit(~/Library/LaunchAgents/**)",
        "Write(~/Library/LaunchAgents/**)",
        "Edit(~/.ssh/**)",
        "Write(~/.ssh/**)",
        "Edit(.git/hooks/**)",
        "Write(.git/hooks/**)",
        "Edit(.git/info/**)",
        "Write(.git/info/**)",
        "Edit(.git/config)",
        "Write(.git/config)",
    )
        for role in ("worker", "brain"):
            with self.subTest(role=role):
                argv, _ = provider_contract(self.spec_v3(provider="claude", role=role, provider_contract_version=9))
                self.assertIn("--strict-mcp-config", argv)
                self.assertEqual(argv[argv.index("--add-dir") + 1], str(self.repo))
                self.assertEqual(argv[argv.index("--disallowedTools") + 1].split(","), list(expected_patterns))
        original = execute_provider.CLAUDE_DISALLOWED_TOOLS
        try:
            execute_provider.CLAUDE_DISALLOWED_TOOLS = "Bash(*rm -rf *)"
            argv, _ = provider_contract(self.spec_v3(provider="claude", provider_contract_version=9))
            with self.assertRaises(AssertionError):
                self.assertEqual(argv[argv.index("--disallowedTools") + 1].split(","), list(expected_patterns))
        finally:
            execute_provider.CLAUDE_DISALLOWED_TOOLS = original

        home = self.tmp / "home"
        home.mkdir()
        (home / ".claude").mkdir()
        (home / ".ssh").mkdir()
        (home / ".zshrc").write_text("# zshrc\n", encoding="utf-8")
        def write_home(rel, value):
            path = home / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")

        cases = [
            (lambda: (self.repo / ".git" / "config").write_text(
                (self.repo / ".git" / "config").read_text() + "\n# touched\n", encoding="utf-8"),
             "<protected:.git/config>"),
            (lambda: (self.repo / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8"),
             "<protected:.git/hooks/pre-commit>"),
            (lambda: (home / ".claude" / "settings.json").write_text("{}", encoding="utf-8"),
             "<protected:~/.claude/settings.json>"),
            (lambda: write_home(".claude/projects/proj/memory/notes.md", "note\n"),
             "<protected:~/.claude/projects/proj/memory/notes.md>"),
            (lambda: write_home(".claude.json", "{}\n"), "<protected:~/.claude.json>"),
            (lambda: write_home(".gitconfig", "[user]\nname = evil\n"), "<protected:~/.gitconfig>"),
            (lambda: write_home(".config/git/config", "[alias]\npwn = status\n"), "<protected:~/.config/git/config>"),
            (lambda: (home / ".zshrc").write_text("# changed\n", encoding="utf-8"),
             "<protected:~/.zshrc>"),
            (lambda: write_home(".zshenv", "evil\n"), "<protected:~/.zshenv>"),
            (lambda: write_home(".zprofile", "evil\n"), "<protected:~/.zprofile>"),
            (lambda: write_home(".bash_profile", "evil\n"), "<protected:~/.bash_profile>"),
            (lambda: write_home(".bashrc", "evil\n"), "<protected:~/.bashrc>"),
            (lambda: write_home("Library/LaunchAgents/com.evil.plist", "evil\n"),
             "<protected:~/Library/LaunchAgents/com.evil.plist>"),
            (lambda: (home / ".ssh" / "authorized_keys").write_text("key\n", encoding="utf-8"),
             "<protected:~/.ssh/authorized_keys>"),
            (lambda: subprocess.run(["git", "-C", str(self.repo), "update-index", "--skip-worktree", "README.md"], check=True),
             "<protected:.git/index-flags/README.md>"),
        ]
        for mutate, violation in cases:
            with self.subTest(violation=violation):
                path, digest = self.persisted(self.spec_v3(provider="claude", provider_contract_version=9))
                spec = json.loads(path.read_text())
                with unittest.mock.patch.dict(os.environ, {"HOME": str(home)}):
                    before = execution_receipt.capture_before(str(path), digest)
                    mutate()
                    log_dir = self.repo / ".tasks" / "logs"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    log_path = log_dir / f"{spec['run_id']}.log"
                    log_path.write_text("log\n", encoding="utf-8")
                    receipt = execution_receipt.build_receipt(
                        spec_path=str(path), digest=digest, before=before,
                        started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:01:00Z",
                        outcome="completed", exit_code=0, log_path=str(log_path),
                    )
                self.assertEqual(receipt["scope"]["result"], "fail")
                self.assertIn(violation, receipt["scope"]["violations"])
                subprocess.run(["git", "-C", str(self.repo), "update-index", "--no-skip-worktree", "README.md"], check=True)

    def test_contract_eight_providers_use_full_native_toolsets(self):
        limiting = ("--allowedTools", "--tools", "--restricted", "--sandbox", "--disable-slash-commands", "--plan", "--mode")
        agy_model = "gemini-3.8-flash-medium"
        repo = str(self.repo)
        for role in ("worker", "brain"):
            for provider, extra, expected in (
                    ("agent", {"speed": "standard"},
                     ["cursor-agent", "-p", "--force", "--trust", "--output-format", "stream-json",
                      "--workspace", repo, "--model", "test-model", "exact prompt"]),
                    ("agy", {"model": agy_model, "effort": "medium"},
                     ["agy", "--dangerously-skip-permissions", "--print-timeout", "30m", "--model", agy_model,
                      "--output-format", "stream-json", "-p", "exact prompt"]),
            ):
                with self.subTest(provider=provider, role=role):
                    path, digest = self.persisted(self.spec_v3(provider=provider, role=role,
                                                               provider_contract_version=8, **extra))
                    argv = json.loads(self.adapter(path, digest).stdout)["argv"]
                    for flag in limiting:
                        self.assertNotIn(flag, argv)
                    self.assertEqual(argv, expected)
        launch = ADAPTER.read_text()
        self.assertIn("stdin=subprocess.DEVNULL", launch)
        self.assertRegex(launch, r"return subprocess\.run\(argv, check=False, stdin=subprocess\.DEVNULL\)")

    def test_contract_eight_agy_streams_and_validates_effort_before_launch(self):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", EXECUTION_SENTINEL=str(self.sentinel))
        for role in ("worker", "brain"):
            for effort in ("low", "medium", "high"):
                with self.subTest(role=role, effort=effort):
                    model = f"gemini-3.8-flash-{effort}"
                    path, digest = self.persisted(self.spec_v3(provider="agy", role=role, model=model, effort=effort,
                                                               provider_contract_version=8))
                    argv = json.loads(self.adapter(path, digest).stdout)["argv"]
                    self.assertEqual(argv, ["agy", "--dangerously-skip-permissions", "--print-timeout", "30m",
                                            "--model", model, "--output-format", "stream-json", "-p", "exact prompt"])
        path, digest = self.persisted(self.spec_v3(provider="agy", model="test-model", provider_contract_version=7))
        self.assertEqual(json.loads(self.adapter(path, digest).stdout)["argv"], ["agy", "--dangerously-skip-permissions",
                         "--print-timeout", "30m", "--model", "test-model", "--effort", "medium", "-p", "exact prompt"])
        for model, effort, message in (
            ("gemini-3.8-flash-high", "medium", "agy model name encodes effort high; spec effort is medium"),
            ("gemini-3.8-flash-low", "high", "agy model name encodes effort low; spec effort is high"),
            ("test-model", "medium", "agy model name must end in an effort token (-low, -medium or -high)"),
        ):
            with self.subTest(model=model, effort=effort):
                path, digest = self.persisted(self.spec_v3(provider="agy", model=model, effort=effort,
                                                           provider_contract_version=8))
                result = self.adapter(path, digest, dry=False, env=env, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, f"ERROR: {message}\n")
                self.assertFalse(self.sentinel.exists())

    def test_contract_six_requests_json_cli_output(self):
        repo = str(self.repo)
        git_dir = str(self.repo / ".git")
        cases = [
            ("codex", {}, ["codex", "exec", "--json", "-C", repo, "-s", "workspace-write", "--add-dir", git_dir,
                           "-m", "test-model", "-c", 'model_reasoning_effort="medium"',
                           *CODEX_CONFIG_OVERRIDES, "exact prompt"]),
            ("claude", {}, ["claude", "-p", "exact prompt", "--output-format", "json",
                            "--model", "test-model", "--effort", "medium", "--allowedTools", "Read,Write,Edit,Bash"]),
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
