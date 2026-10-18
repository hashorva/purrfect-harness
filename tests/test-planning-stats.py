import hashlib
import importlib
import json
import os
import shutil
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

def _batch_fixture(case):
    O, U = (lambda v: {"value": v, "source": "observed"}), {"value": None, "source": "unknown"}
    led = lambda i, **x: {"schema_version": 2, "run_id": f"r{i}", "tokens_input": O(100 * (i + 1)), "tokens_output": O(10), "tokens_cache": O(1000), "tokens_reasoning": O(99999), "subagents": {"calls": O(1), "tokens": O(50 * (i + 1))}, "outcome": "completed", "failure_class": None, **x}
    plan = {"type": "architect-run", "plan": "P", "seat": "s", "model": "m", "input_tokens": 5000, "output_tokens": 0, "cache_read_tokens": 0, "thinking_tokens": 777, "subagent_stats": {"spawned": 0}, "outcome": "blocked"}
    rows = [led(i) for i in range(9)] + [led(0), plan, {"type": "review", "run_id": "r1", "input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 1}, led(20, outcome="failed"), led(21, failure_class="environment"), led(22, tokens_cache=U), led(23, subagents={"calls": U, "tokens": U}), {"type": "architect-run", "plan": "spawned", "seat": "s", "model": "m", "input_tokens": 100, "output_tokens": 0, "cache_read_tokens": 0, "subagent_stats": {"spawned": 2}, "outcome": "done"}]
    tmp = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, tmp)
    data = tmp / "d.jsonl"
    data.write_text("\n".join(map(json.dumps, rows)) + "\n[1, 2]\n", encoding="utf-8")
    batch = lambda name, ids: (p := tmp / f"{name}.json", p.write_text(json.dumps({"name": name, "run_ids": ids}), encoding="utf-8"), p)[2]
    ten = [f"r{i}" for i in range(9)] + ["plan:P"]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cli = lambda *a: subprocess.run([sys.executable, str(ROOT / "scripts/planning_stats.py"), *a], capture_output=True, text=True, env=env)
    return data, batch, ten, cli, led, O
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

    def test_batch_reports_medians_and_done_rate(self):
        data, batch, ten, *_ = _batch_fixture(self)
        self.assertEqual(P.batch_summary(batch("before", ten), data), {"batch": "before", "runs": 10, "median_parent_total": 1560, "median_parent_plus_subagent_total": 1835, "median_subagent_calls": 1, "done": 9})

    def test_batch_keeps_unknown_subagent_counts_unknown(self):
        data, batch, ten, *_ = _batch_fixture(self)
        unk = P.batch_summary(batch("unk", ten[:8] + ["r23", "plan:P"]), data)
        self.assertEqual((unk["median_parent_total"], unk["median_parent_plus_subagent_total"], unk["median_subagent_calls"], P.batch_summary(batch("spawned", ten[:8] + ["plan:spawned", "r8"]), data)["median_parent_plus_subagent_total"]), (1560, None, None, None))

    def test_batch_refuses_small_duplicate_and_unclean_batches(self):
        data, batch, ten, cli, led, O = _batch_fixture(self)
        for name, ids in (("nine", ten[:9]), ("dup", ten[:9] + ["r0"]), ("missing", ten[:9] + ["nope"]), ("failed", ten[:9] + ["r20"]), ("env", ten[:9] + ["r21"]), ("unmeasured", ten[:9] + ["r22"])):
            out = cli("batch", str(batch(name, ids)), str(data))
            self.assertEqual((out.returncode, out.stdout, out.stderr.startswith("planning_stats: ")), (2, "", True), name)
        conflict = data.parent / "c.jsonl"
        conflict.write_text(data.read_text(encoding="utf-8") + json.dumps(led(1, tokens_input=O(999))) + "\n", encoding="utf-8")
        out = cli("batch", str(batch("tworows", [f"r{i}" for i in range(9) if i != 1] + ["plan:P", "r1"])), str(conflict))
        self.assertEqual((out.returncode, out.stdout, "different rows" in out.stderr), (2, "", True))
        bad = batch("bad", ten)
        bad.write_text("[]", encoding="utf-8")
        out = cli("batch", str(bad), str(data))
        self.assertEqual((out.returncode, out.stdout, out.stderr.startswith("planning_stats: ")), (2, "", True))

    def test_batch_cli_prints_the_summary(self):
        data, batch, ten, cli, *_ = _batch_fixture(self)
        out = cli("batch", str(batch("before", ten)), str(data))
        table = "batch\tbefore\nruns\t10\nmedian_parent_total\t1560\nmedian_parent_plus_subagent_total\t1835\nmedian_subagent_calls\t1\ndone_rate\t9/10\n"
        self.assertEqual((out.returncode, out.stdout, out.stderr), (0, table, ""))

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
