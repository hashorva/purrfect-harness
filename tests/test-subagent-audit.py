import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M = "docs/missions/20261018-2b-autonomy"
A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"

class AuditTest(unittest.TestCase):
    def test_saved_logs_and_manual_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            for d in ("receipts", "specs", "logs"): (t / d).mkdir()
            def put(folder, rid, role="brain", mission=M, provider="claude"):
                (t / folder / f"{rid}.json").write_text(json.dumps(dict(run_id=rid, role=role, mission=mission, provider=provider, work_unit="plan")))
            put("receipts", A)
            shutil.copy(ROOT / "tests/fixtures/observe/claude-subagent.jsonl", t / "logs" / f"{A}.log")
            put("specs", B, mission=M + "/")
            put("receipts", "33333333-3333-4333-8333-333333333333", "worker")
            put("specs", "44444444-4444-4444-8444-444444444444", mission="other")
            rows = [dict(type="architect-run", plan="T|1", seat="claude.brain", subagent_stats={"spawned": 2}, outcome="done"),
                    dict(type="architect-run", run_id=A, plan="T-2", seat="claude.brain", subagent_stats={"spawned": 2}, outcome="done"),
                    dict(type="architect-run", run_id=A, plan="T-6", seat="claude.brain", subagent_stats={"spawned": 1}, outcome="done"),
                    dict(type="architect-run", run_id=B, plan="T-3", seat="codex.brain", subagent_stats={"spawned": 1}),
                    dict(run_id=A, task="T-4", seat="claude.worker"),
                    dict(type="architect-run", run_id="55555555-5555-4555-8555-555555555555", plan="T-5", seat="agy.brain", subagent_stats={"spawned": 0})]
            before = [json.dumps(x, separators=(",", ":")) for x in rows]
            routing = t / "routing.jsonl"; routing.write_text("".join(x + "\n" for x in before))
            cmd = [sys.executable, str(ROOT / "scripts/subagent_audit.py"), "--mission", M, "--tasks-dir", str(t), "--routing", str(routing)]
            dry = subprocess.run(cmd, capture_output=True, text=True); self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertEqual(routing.read_text(), "".join(x + "\n" for x in before))
            out = subprocess.run(cmd + ["--mark-manual"], capture_output=True, text=True); self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout, dry.stdout); self.assertIn("| T\\|1 | no | claude | unknown | unknown | no run id recorded (ad hoc) |", out.stdout)
            self.assertIn(f"| {A} | plan | yes | claude | 2 | 1234 | receipt |", out.stdout)
            self.assertIn(f"| {B} | plan | no | claude | unknown | unknown | spec only |", out.stdout)
            self.assertIn("routing row only", out.stdout); self.assertNotIn("44444444", out.stdout)
            self.assertIn("Unconfirmed routing rows: 4", out.stdout)
            after = routing.read_text().splitlines(); self.assertEqual(after[1], before[1]); self.assertEqual(after[4], before[4])
            for i in (0, 2, 3, 5):
                expected = dict(rows[i]); expected["source"] = "manual"
                self.assertEqual(after[i], json.dumps(expected, separators=(",", ":")))
            again = subprocess.run(cmd + ["--mark-manual"], capture_output=True, text=True)
            self.assertEqual(again.returncode, 0); self.assertEqual(routing.read_text().splitlines(), after)
            routing.write_text(routing.read_text() + "{broken\n"); snapshot = routing.read_text()
            bad = subprocess.run(cmd + ["--mark-manual"], capture_output=True, text=True)
            self.assertEqual((bad.returncode, bad.stdout), (2, "")); self.assertTrue(bad.stderr.startswith("subagent_audit: "))
            self.assertEqual(routing.read_text(), snapshot)

if __name__ == "__main__": unittest.main()
