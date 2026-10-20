import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import observe_output as O
import replay_seeded_defects as R
class ReplaySeededDefectsTests(unittest.TestCase):
    def test_cases_and_required_set_match_2a(self):
        expected = {"A": ("53fb0f5817aa94c8845e9811d29123afdff85dbb", "scripts/verification_record.py", "T-043"), "B": ("0e3cebacc3123496f524202bd0cf14783012e69e", "scripts/execution_runner.py", "T-042"), "C": ("eb7e8c7e61274c1eab37bff3571e485d9854e17d", "scripts/ledger.py", "T-044")}
        self.assertEqual({c["id"]: (c["commit"], c["file"], c["task"]) for c in R.CASES}, expected)
        fixture = ROOT / R.REQUIRED_2A
        rows = fixture.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(json.loads(row)["type"] == "seeded-calibration" for row in rows))
        self.assertEqual(R.required(fixture), {"argon": ["A", "B", "C"], "grok": ["A", "B", "C"]})
        with tempfile.TemporaryDirectory() as temp:
            for bad in ({"reviewer": "other", "case": "A", "task": "T-043", "commit": "53fb0f5"}, {"reviewer": "grok-4.7-high", "case": "A", "task": "T-043", "commit": "0e3ceba"}, {"reviewer": "grok-4.7-high", "case": "D", "task": "T-043", "commit": "53fb0f5"}):
                path = Path(temp) / "bad.jsonl"
                path.write_text(json.dumps(dict(bad, type="seeded-calibration", caught=True)) + "\n")
                with self.assertRaises(R.ReplayError):
                    R.required(path)
    def test_plant_changes_one_line_of_the_task_commit(self):
        def git(path, *args):
            return subprocess.run(["git", "-C", str(path), *args], check=True,
                                  capture_output=True, text=True).stdout
        with tempfile.TemporaryDirectory() as temp:
            for case in R.CASES:
                dest = Path(temp) / case["id"]
                self.assertEqual(R.plant(ROOT, case, dest), dest)
                self.assertEqual(git(dest, "diff", "--numstat", case["commit"], "HEAD"), f"1\t1\t{case['file']}\n")
                self.assertEqual(git(dest, "rev-parse", "HEAD~1").strip(), git(dest, "rev-parse", case["commit"] + "~1").strip())
                fmt = "--format=%s%n%an%n%ae"
                self.assertEqual(git(dest, "log", "-1", fmt, "HEAD"), git(dest, "log", "-1", fmt, case["commit"]))
                self.assertEqual(git(dest, "remote"), "")
                self.assertEqual(git(dest, "status", "--porcelain"), "")
                text = (dest / case["file"]).read_text(encoding="utf-8")
                self.assertNotIn(case["old"], text)
                self.assertIn(case["new"], text)
            with self.assertRaises(R.ReplayError):
                R.plant(ROOT, dict(R.CASES[0], old="no such text"), Path(temp) / "absent")
    def test_caught_reads_only_a_failing_final_verdict_naming_file_and_defect(self):
        case = R.CASES[0]
        finding = {"id": "F1", "severity": "blocking", "text": "scripts/verification_record.py:33 marker pattern lacks re.M"}
        def verdict(value="FAIL", findings=None):
            return json.dumps({"run_ids": [], "commits": [{"commit": "HEAD", "verdict": value, "evidence": ["git show HEAD"]}], "findings": [finding] if findings is None else findings, "verdict": value})
        def raw(provider, body):
            event = {"claude": {"type": "result", "result": body}, "agent": {"type": "result", "result": body}, "agy": {"event": "result", "result": {"response": body}}, "codex": {"type": "item.completed", "item": {"type": "agent_message", "text": body}}}[provider]
            return (json.dumps({"type": "system"}) + "\n" + json.dumps(event) + "\n").encode()
        for provider in ("claude", "agent", "agy", "codex"):
            self.assertEqual(O.final_answer(provider, raw(provider, "answer")), "answer")
            self.assertTrue(R.caught(provider, raw(provider, verdict()), case), provider)
        negatives = (verdict("PASS"), verdict("FAIL", [dict(finding, severity="non-blocking")]), verdict("FAIL", [dict(finding, text="scripts/ledger.py:2 re.M")]), verdict("FAIL", [dict(finding, text="scripts/verification_record.py:2 wrong defect")]), json.dumps({"verdict": "FAIL"}), "no verdict")
        for body in negatives:
            self.assertFalse(R.caught("claude", raw("claude", body), case), body)
        self.assertFalse(R.caught("claude", verdict().encode(), case))
        earlier = raw("claude", verdict()) + json.dumps({"type": "result", "result": "not final JSON"}).encode() + b"\n"
        self.assertFalse(R.caught("claude", earlier, case))
    def _replay(self, temp, seats, miss, out_name, extra=()):
        bin_dir = Path(temp) / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "claude").write_text(_FAKE_CLAUDE, encoding="utf-8")
        (bin_dir / "claude").chmod(0o755)
        fleet_path = Path(temp) / "fleet.json"
        fleet_path.write_text(json.dumps(_REPLAY_FLEET), encoding="utf-8")
        log = Path(temp) / (out_name + ".log")
        env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "FAKE_LOG": str(log),
               "FAKE_MISS": miss, "PYTHONDONTWRITEBYTECODE": "1"}
        argv = [sys.executable, str(ROOT / "scripts/replay_seeded_defects.py"), "--fleet", str(fleet_path),
                "--out", str(Path(temp) / out_name), "--timeout", "120", *extra]
        argv += sum([["--seat", seat] for seat in seats], [])
        result = subprocess.run(argv, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, cwd=ROOT)
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return result, result.stdout.splitlines(), calls
    def test_replay_passes_when_every_required_case_is_caught(self):
        T = "\t"
        with tempfile.TemporaryDirectory() as temp:
            r, out, calls = self._replay(temp, ["rev_grok", "rev.argon"], "", "pass")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(out[-1], T.join(("result", "pass")))
            for call in calls:
                self.assertNotIn("budget", call["prompt"].lower())
                self.assertIn("explorer subagent", call["prompt"])
            gonly = Path(temp) / "grok-only.jsonl"
            gonly.write_text(json.dumps({"type": "seeded-calibration", "reviewer": "grok-4.7-high", "case": "A",
                                         "task": "T-043", "commit": "53fb0f5", "caught": True}) + "\n")
            r, out, _ = self._replay(temp, ["rev_grok"], "fake-grok:B", "gonly", ("--routing-data", str(gonly)))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(T.join(("rev_grok", "grok", "B", "no", "no")), out)
    def test_replay_fails_on_a_required_miss_or_a_missing_family(self):
        T = "\t"
        with tempfile.TemporaryDirectory() as temp:
            r, out, _ = self._replay(temp, ["rev_grok"], "fake-grok:B", "miss")
            self.assertEqual(r.returncode, 1, out)
            self.assertIn(T.join(("rev_grok", "grok", "B", "yes", "no")), out)
            r, out, _ = self._replay(temp, ["rev.opus"], "", "opus")
            self.assertEqual(r.returncode, 1, out)
            self.assertIn(T.join(("missing", "argon")), out)
            self.assertIn(T.join(("missing", "grok")), out)
    def test_unknown_seat_exits_two_before_any_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            r, out, calls = self._replay(temp, ["nosuch"], "", "bad")
            self.assertEqual((r.returncode, out, calls), (2, [], []))
            self.assertTrue(r.stderr.startswith("replay_seeded_defects: "))
_FAKE_CLAUDE = "#!/usr/bin/env python3\nimport json, os, sys\na = sys.argv\nprompt, model = a[a.index('-p') + 1], a[a.index('--model') + 1]\nwith open(os.environ['FAKE_LOG'], 'a') as h:\n    h.write(json.dumps({'model': model, 'prompt': prompt, 'cwd': os.getcwd()}) + chr(10))\ncases = {'T-043': ('A', 'scripts/verification_record.py:33 marker pattern lacks re.M'), 'T-042': ('B', 'scripts/execution_runner.py:75 git read lacks --no-replace-objects'), 'T-044': ('C', 'scripts/ledger.py:40 SENSITIVE_PATH lost the ~name/ alternative')}\ncid, text = [v for k, v in cases.items() if k in prompt][0]\nmiss = model + ':' + cid in os.environ.get('FAKE_MISS', '').split(',')\nv = 'PASS' if miss else 'FAIL'\nbody = {'run_ids': [], 'commits': [{'commit': 'HEAD', 'verdict': v, 'evidence': ['git show HEAD']}], 'findings': [] if miss else [{'id': 'F1', 'severity': 'blocking', 'text': text}], 'verdict': v}\nprint(json.dumps({'type': 'system'}))\nprint(json.dumps({'type': 'result', 'result': json.dumps(body)}))\n"
_REPLAY_FLEET = {"seats": {n: {"provider": "claude", "model": m, "effort": "medium", "speed": "unknown", "family": f}
                            for n, m, f in (("rev_grok", "fake-grok", "grok"), ("rev.argon", "fake-argon", "argon"),
                                              ("rev.opus", "fake-opus", "opus"))}}
if __name__ == "__main__":
    unittest.main()
