import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
P = importlib.import_module("planning_stats")
L = importlib.import_module("ledger")
FIXTURE = ROOT / "tests/fixtures/planning-stats/routing-data.jsonl"
BASELINE = ROOT / "tests/fixtures/planning-stats/2a-baseline-routing-data.jsonl"
NEW = b"ghp-/github-pat-"
OLD = NEW.replace(b"-", b"_")

class PlanningStatsTests(unittest.TestCase):
    def test_medians_per_seat_and_model(self):
        got = P.summarize(FIXTURE)
        self.assertEqual(got["groups"], [
            {"seat": "s.one", "model": "m1", "runs": 3, "median_total": 2220},
            {"seat": "s.two", "model": "m2", "runs": 1, "median_total": 555},
        ])
        self.assertEqual(got["all"], {"runs": 4, "median_total": 1665})

    def test_duplicates_and_unmeasured_rows_are_left_out(self):
        got = P.summarize(FIXTURE)
        self.assertEqual((got["duplicates"], got["unmeasured"]), (1, 2))
        self.assertIsNone(P.median([]))
        self.assertEqual(P.median([3, 1, 2]), 2)
        self.assertEqual(P.median([1, 2]), 1)

    def test_cli_prints_the_table(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts/planning_stats.py"), str(FIXTURE)], capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout, out.stderr), (0, "seat\tmodel\truns\tmedian_total\ns.one\tm1\t3\t2220\ns.two\tm2\t1\t555\nall\tall\t4\t1665\nduplicates\t1\nunmeasured\t2\n", ""))

    def test_bad_input_exits_two(self):
        cases = ["{\n", json.dumps({"type": "architect-run", "input_tokens": "1", "output_tokens": 1, "cache_read_tokens": 1}) + "\n", json.dumps({"type": "architect-run", "input_tokens": True, "output_tokens": 1, "cache_read_tokens": 1}) + "\n", json.dumps({"type": "architect-run", "input_tokens": -1, "output_tokens": 1, "cache_read_tokens": 1}) + "\n"]
        with tempfile.TemporaryDirectory() as temp:
            for index, content in enumerate(cases):
                path = Path(temp) / f"bad-{index}.jsonl"
                path.write_text(content, encoding="utf-8")
                out = subprocess.run([sys.executable, str(ROOT / "scripts/planning_stats.py"), str(path)], capture_output=True, text=True)
                self.assertEqual((out.returncode, out.stdout), (2, ""))
                self.assertTrue(out.stderr.startswith("planning_stats: "))
            out = subprocess.run([sys.executable, str(ROOT / "scripts/planning_stats.py"), str(Path(temp) / "missing")], capture_output=True, text=True)
            self.assertEqual((out.returncode, out.stdout), (2, ""))

    def test_frozen_2a_baseline(self):
        data = BASELINE.read_bytes()
        lines = data.decode("utf-8").splitlines()
        self.assertEqual((len(data), len(lines), data.count(NEW), data.count(OLD)), (66755, 247, 1, 0))
        self.assertEqual(next(i for i, line in enumerate(lines, 1) if NEW.decode() in line), 38)
        restored = data.replace(NEW, OLD)
        self.assertEqual(hashlib.sha1(b"blob %d\0" % len(restored) + restored).hexdigest(), "745971d1075b267725f94f8365e258caa2751058")
        self.assertFalse(any(L.EMAIL.search(line) or L.ABSOLUTE_PATH.search(line) or any(p.search(line) for p in L.SECRET_PATTERNS) for line in lines))
        self.assertEqual(P.summarize(BASELINE), {
            "groups": [
                {"seat": "agy.brain", "model": "claude-opus-5-5-high", "runs": 1, "median_total": 1585010},
                {"seat": "agy.premium", "model": "gemini-4-argon-high", "runs": 24, "median_total": 1139698},
                {"seat": "claude.brain-planning", "model": "claude opus (high)", "runs": 11, "median_total": 2033553},
            ],
            "all": {"runs": 36, "median_total": 1250599}, "duplicates": 3, "unmeasured": 2,
        })

if __name__ == "__main__":
    unittest.main()
