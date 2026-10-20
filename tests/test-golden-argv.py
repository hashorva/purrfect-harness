"""Golden argv checks for immutable provider contracts."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import os, shutil, subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "golden-argv"
sys.path.insert(0, str(ROOT / "scripts"))
execute_provider = importlib.import_module("execute_provider")
execution_spec = importlib.import_module("execution_spec")
spec = importlib.util.spec_from_file_location("check_golden_argv", ROOT / "scripts" / "check-golden-argv.py")
checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)


def fixture_paths():
    return sorted(p for p in FIXTURES.glob("*.json") if p.name != "MANIFEST.json")


def read_fixtures():
    return [json.loads(path.read_text()) for path in fixture_paths()]


def mismatches(provider_contract):
    bad = []
    for path in fixture_paths():
        fixture = json.loads(path.read_text())
        if any(provider_contract(case["spec"])[0] != case["argv"] for case in fixture["cases"]):
            bad.append(path.stem)
    return bad


class GoldenArgv(unittest.TestCase):
    def test_every_provider_contract_has_one_golden_file(self):
        fixtures = read_fixtures()
        expected = {(p, n) for p in execution_spec.PROVIDERS
                    for n in (1,) + execution_spec.PROVIDER_CONTRACTS_V3}
        self.assertEqual({(f["provider"], f["contract"]) for f in fixtures}, expected)
        for path in fixture_paths():
            raw = path.read_bytes()
            fixture = json.loads(raw)
            self.assertEqual(path.name, f'{fixture["provider"]}-v{fixture["contract"]}.json')
            self.assertEqual(raw, (json.dumps(fixture, sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=False) + "\n").encode())
            self.assertEqual(len(fixture["cases"]), 2 if fixture["provider"] == "codex" else 1)
        self.assertEqual(execution_spec.CURRENT_PROVIDER_CONTRACT,
                         max(execution_spec.PROVIDER_CONTRACTS_V3))

    def test_adapter_reproduces_every_golden_argv(self):
        self.assertEqual(mismatches(execute_provider.provider_contract), [],
                         "recorded contract argv changed; add a new contract instead (T-115)")

    def test_historical_forms_are_documented(self):
        entries = [(f, h) for f in read_fixtures() for h in f["historical"]]
        self.assertEqual({(f["provider"], f["contract"]) for f, _ in entries},
                         {("claude", 8), ("claude", 9), ("codex", 9)})
        for fixture, entry in entries:
            spec = fixture["cases"][0]["spec"]
            self.assertNotEqual(entry["argv"], fixture["cases"][0]["argv"])
            self.assertEqual(entry["accepted_by_adapter"],
                             execute_provider.argv_sha256(entry["argv"]) in
                             execute_provider.historical_argv_sha256s(spec))

    def test_changing_one_old_contract_flag_fails(self):
        source = (ROOT / "scripts" / "execute_provider.py").read_text()
        old = '"--allowedTools", "Read,Write,Edit,Bash"'
        self.assertEqual(source.count(old), 1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "execute_provider.py"
            path.write_text(source.replace(old, '"--allowedTools", "Read,Write,Edit"'))
            spec = importlib.util.spec_from_file_location("golden_mutant_execute_provider", path)
            mutant = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mutant)
            self.assertEqual(mismatches(mutant.provider_contract),
                             [f"claude-v{n}" for n in range(1, 9)])

    def test_manifest_pins_every_fixture_hash(self):
        self.assertEqual(checker.manifest_errors(FIXTURES), [])
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / "fixtures"; shutil.copytree(FIXTURES, copied)
            path = copied / "agy-v1.json"
            path.write_text(path.read_text().replace('"30m"', '"60m"'))
            self.assertTrue(any("agy-v1.json" in error for error in checker.manifest_errors(copied)))
            (copied / "MANIFEST.json").write_bytes(checker.manifest_bytes(copied))
            # A hash alone cannot stop a coordinated edit; the history check does.
            self.assertEqual(checker.manifest_errors(copied), [])

    def test_history_check_refuses_edits_and_allows_new_contracts(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp); fixtures = repo / "tests/fixtures/golden-argv"
            fixtures.parent.mkdir(parents=True); shutil.copytree(FIXTURES, fixtures)
            def git(*args):
                return subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
                                      check=True, capture_output=True, text=True).stdout.strip()
            git("init", "-q"); git("config", "user.email", "t@example.invalid")
            git("config", "user.name", "t"); git("add", "-A"); git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            def commit(message):
                (fixtures / "MANIFEST.json").write_bytes(checker.manifest_bytes(fixtures))
                git("add", "-A"); git("commit", "-qm", message)
            def run():
                env = {key: value for key, value in os.environ.items() if key != "CI"}
                return subprocess.run([sys.executable, str(ROOT / "scripts/check-golden-argv.py"), "--base", base],
                                      cwd=repo, env=env, capture_output=True, text=True)
            def expect(code, name=""):
                result = run()
                self.assertEqual((result.returncode, name in result.stderr), (code, True),
                                 (result.returncode, result.stdout, result.stderr))
            expect(0)
            for path in fixtures.glob("agy-v*.json"):
                path.write_text(path.read_text().replace('"30m"', '"60m"'))
            commit("mutate recorded fixtures"); expect(1, "agy-v1.json"); git("reset", "-q", "--hard", base)
            (fixtures / "codex-v2.json").unlink()
            commit("delete recorded fixture"); expect(1, "codex-v2.json"); git("reset", "-q", "--hard", base)
            (fixtures / "claude-v3.json").rename(fixtures / "claude-v10.json")
            commit("rename recorded fixture"); expect(1, "claude-v3.json"); git("reset", "-q", "--hard", base)
            for provider in ("agent", "agy", "claude", "codex"):
                data = json.loads((fixtures / f"{provider}-v9.json").read_text())
                data["contract"] = 10; data["historical"] = []
                for case in data["cases"]:
                    case["spec"]["provider_contract_version"] = 10
                (fixtures / f"{provider}-v10.json").write_text(
                    json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
            commit("add contract 10"); expect(0)
    def test_ci_runs_the_history_check(self):
        lines = (ROOT / ".github/workflows/ci.yml").read_text().splitlines()
        for line in ('          fetch-depth: 0', '          CI: "true"', '        run: python3 scripts/check-golden-argv.py'):
            self.assertIn(line, lines)
        checkout = lines.index("      - uses: actions/checkout@v4"); check = lines.index('        run: python3 scripts/check-golden-argv.py')
        suite = lines.index("        run: bash tests/run-tests.sh")
        self.assertLess(checkout, check); self.assertLess(check, suite)


if __name__ == "__main__":
    unittest.main()
