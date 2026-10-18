"""Golden argv checks for immutable provider contracts."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "golden-argv"
sys.path.insert(0, str(ROOT / "scripts"))
execute_provider = importlib.import_module("execute_provider")
execution_spec = importlib.import_module("execution_spec")


def read_fixtures():
    return [json.loads(path.read_text()) for path in sorted(FIXTURES.glob("*.json"))]


def mismatches(provider_contract):
    bad = []
    for path in sorted(FIXTURES.glob("*.json")):
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
        for path in FIXTURES.glob("*.json"):
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


if __name__ == "__main__":
    unittest.main()
