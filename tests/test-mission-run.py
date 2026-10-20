#!/usr/bin/env python3
"""Dry run of scripts/mission-run.sh: stub steps, no model CLI."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = (
    "scripts/mission-run.sh",
    "scripts/validate_verdict.py",
    "scripts/observe_output.py",
    "scripts/model_id.py",
    "scripts/run_id.py",
    "scripts/plan_extract.py",
    "schemas/review-verdict.schema.json",
)
STUB = r'''
import json, pathlib, subprocess, sys, uuid
step, args = sys.argv[1], sys.argv[2:]
queue = pathlib.Path(step + ".queue")
items = queue.read_text().split()
queue.write_text((" ".join(items[1:]) + "\n") if len(items) > 1 else "")
result = items[0]
if step == "probe":
    base = args[0]
elif step == "plan":
    base = pathlib.Path(args[args.index("--request") + 1]).name
elif step == "worker":
    base = pathlib.Path(args[0]).name
else:
    base = pathlib.Path(args[-1]).name
open("calls.txt", "a").write(step + " " + base + "\n")
def emit(obj):
    path = pathlib.Path(".tasks/events.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a").write(json.dumps(obj) + "\n")
def brain(text, directory):
    rid = str(uuid.uuid4())
    log = pathlib.Path(directory, rid + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"type": "result", "result": text}) + "\n")
    receipt = pathlib.Path(".tasks", rid + ".json")
    receipt.write_text(json.dumps({"provider": "claude", "log_path": str(log.resolve())}))
    emit({"event": "run_exit", "role": "brain", "run_id": rid, "receipt": str(receipt)})
if step == "worker":
    if result != "none":
        prov = args[args.index("--provider") + 1]
        tier = args[args.index("--tier") + 1]
        outcome = "launch_failed" if result == "launch_failed" else "completed"
        emit({"event": "run_exit", "role": "worker", "run_id": str(uuid.uuid4()), "seat": prov + "." + tier, "outcome": outcome})
elif step == "verify":
    run = args[args.index("--run-id") + 1]
    dest = pathlib.Path(args[-1], "verification", run + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"work_unit": "x", "result": result}))
    sys.exit(0 if result == "pass" else 1)
elif step == "probe":
    sys.exit(0 if result == "ok" else 1)
elif step == "plan":
    fence = "`" * 4
    text = "".join("%s\n---\ntask_id: %s\nfeature: F002\n---\n# Task\n%s\n" % (fence, tid, fence) for tid in result.split(","))
    brain(text, ".tasks/logs")
else:
    if subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout:
        sys.exit(1)
    pathlib.Path(args[0], "PROGRESS.md").write_text("reviewed\n")
    body = {"run_ids": ["r"], "commits": [{"commit": "c", "verdict": result, "evidence": ["e"]}], "findings": [], "verdict": result}
    brain(json.dumps(body), ".tasks")
'''


class MissionRunTests(unittest.TestCase):
    def repo(self, f001=True):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for rel in COPY:
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dest)
        mission = root / "docs/missions/m"
        (mission / "tasks").mkdir(parents=True)
        (mission / "GOAL.md").write_text("- **GATE 1 — Fixture.** Held after F001 and F002. Text.\n")
        (mission / "features.json").write_text(json.dumps({
            "run_order": ["F001", "F002"],
            "features": [
                {"id": "F001", "passes": f001},
                {"id": "F002", "passes": False},
                {"id": "F012", "passes": False},
            ],
        }))
        (mission / "fleet.json").write_text(json.dumps({"seats": {seat: {} for seat in (
            "agy.economy", "claude.economy", "codex.economy", "codex.premium", "cursor.economy",
        )}}))
        for tid, feature in (
            ("T-001", "F002"), ("T-002", "F002"), ("T-003", "F002"),
            ("T-003-R1", "F002"), ("T-004", "F001"),
        ):
            (mission / "tasks" / f"{tid}.md").write_text(
                f"---\ntask_id: {tid}\nfeature: {feature}\n---\n\nfeature: F002\n"
            )
        verification = mission / "verification"
        verification.mkdir()
        (verification / "t1.json").write_text(json.dumps({"work_unit": "T-001", "result": "pass"}))
        (verification / "t2.json").write_text(json.dumps({"work_unit": "T-002", "result": "fail"}))
        (root / "stub.py").write_text(STUB)
        (root / ".gitignore").write_text(".tasks/\ncalls.txt\n*.queue\nstub.py\n")
        def git(*args):
            subprocess.run(("git", *args), cwd=root, check=True, capture_output=True, text=True)
        git("init", "-q")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "t")
        git("config", "commit.gpgsign", "false")
        git("add", "-A")
        git("commit", "-q", "-m", "init")
        return root

    def launch(self, root, **queues):
        for step, items in queues.items():
            (root / f"{step}.queue").write_text(" ".join(items) + "\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PURRFECT_", "MISSION_RUN_"))}
        stub = root / "stub.py"
        for step in ("worker", "verify", "review", "plan", "probe"):
            env[f"MISSION_RUN_{step.upper()}"] = f"{sys.executable} {stub} {step}"
        return subprocess.run(
            ["nohup", "bash", str(root / "scripts/mission-run.sh"), "docs/missions/m", "--provider", "codex"],
            cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        )

    def shown(self, root):
        out = []
        for line in (root / ".tasks/events.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["event"] == "run_exit":
                continue
            if row["event"] in ("verify", "review"):
                out.append(f"{row['event']} {row['task']} {row['round']} {row.get('result', row.get('verdict'))}")
            elif row["event"] == "probe":
                out.append(f"probe {row['task']} {row['seat']} {row['result']}")
            elif row["event"] == "reroute":
                out.append(f"reroute {row['task']} {row['from']} {row['to']}")
            elif row["event"] == "decomposition_miss":
                out.append(f"decomposition_miss {row['task']} {row['tasks']}")
            else:
                out.append(f"{row['event']} {row['detail']}")
        return out

    def calls(self, root):
        return (root / "calls.txt").read_text().splitlines()

    def test_rounds_skip_done_families_and_stop_at_the_gate(self):
        root = self.repo()
        proc = self.launch(root, worker=["w", "w", "w"], verify=["fail", "pass", "pass"], review=["PASS", "PASS"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.shown(root), [
            "verify T-002 1 fail", "verify T-002 2 pass", "review T-002 2 PASS",
            "verify T-003-R1 1 pass", "review T-003-R1 1 PASS", "gate_reached GATE 1",
        ])
        self.assertEqual(self.calls(root), [
            "worker T-002.md", "verify m", "worker T-002.md", "verify m", "review review",
            "worker T-003-R1.md", "verify m", "review review",
        ])
        clean = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True)
        self.assertEqual(clean.stdout, "")

    def test_failed_rounds_missing_runs_and_a_feature_end_without_gate_stop_the_loop(self):
        root = self.repo()
        proc = self.launch(root, worker=["none"])
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertEqual(self.shown(root), ["blocker T-002: no worker run started"])
        self.assertEqual(self.calls(root), ["worker T-002.md"])

        root = self.repo(f001=False)
        proc = self.launch(root, worker=["w"], verify=["pass"], review=["PASS"])
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("decision_needed F001: every task passed; accept it", self.shown(root))
        self.assertEqual(self.calls(root)[0], "worker T-004.md")

    def plans(self, root):
        return [line for line in self.calls(root) if line.startswith("plan ") or line.startswith("probe ")]

    def test_a_first_round_pass_runs_no_probe_and_no_plan(self):
        root = self.repo()
        proc = self.launch(root, worker=["w", "w"], verify=["pass", "pass"], review=["PASS", "PASS"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.shown(root), [
            "verify T-002 1 pass", "review T-002 1 PASS",
            "verify T-003-R1 1 pass", "review T-003-R1 1 PASS", "gate_reached GATE 1",
        ])
        self.assertEqual(self.plans(root), [])

    def test_two_failed_rounds_go_to_the_planner_and_the_split_runs(self):
        root = self.repo()
        proc = self.launch(
            root, worker=["w", "w", "w", "w"], verify=["pass", "pass", "pass", "pass"],
            review=["FAIL", "FAIL", "PASS", "PASS"], plan=["T-005"],
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.shown(root), [
            "verify T-002 1 pass", "review T-002 1 FAIL", "verify T-002 2 pass", "review T-002 2 FAIL",
            "decomposition_miss T-002 T-005",
            "verify T-003-R1 1 pass", "review T-003-R1 1 PASS",
            "verify T-005 1 pass", "review T-005 1 PASS", "gate_reached GATE 1",
        ])
        self.assertEqual(self.plans(root), ["plan T-002-split.md"])
        req = (root / ".tasks/requests/T-002-split.md").read_text()
        self.assertIn("docs/missions/m/tasks/T-002.md", req)
        self.assertIn("round 2", req)
        self.assertIn('"verdict": "FAIL"', req)
        show = subprocess.run(
            ["git", "show", "HEAD:docs/missions/m/tasks/T-005.md"],
            cwd=root, capture_output=True, text=True, check=True,
        )
        self.assertEqual(show.stdout.splitlines()[1], "split_from: T-002")
        clean = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True)
        self.assertEqual(clean.stdout, "")

    def test_a_split_task_that_fails_two_rounds_needs_a_decision(self):
        root = self.repo()
        proc = self.launch(
            root, worker=["w"] * 5, verify=["fail", "fail", "pass", "fail", "fail"],
            review=["PASS"], plan=["T-005"],
        )
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertEqual(self.shown(root), [
            "verify T-002 1 fail", "verify T-002 2 fail", "decomposition_miss T-002 T-005",
            "verify T-003-R1 1 pass", "review T-003-R1 1 PASS",
            "verify T-005 1 fail", "verify T-005 2 fail",
            "decision_needed T-005: split from T-002, 2 rounds without a pass",
        ])
        self.assertEqual(self.plans(root), ["plan T-002-split.md"])

    def worker_seats(self, root):
        calls = [line.split()[1] for line in self.calls(root) if line.startswith("worker ")]
        seats = [
            json.loads(line)["seat"]
            for line in (root / ".tasks/events.jsonl").read_text().splitlines()
            if '"role": "worker"' in line or '"role":"worker"' in line
        ]
        return list(zip(calls, seats))

    def test_a_broken_seat_is_probed_and_rerouted_within_its_tier(self):
        root = self.repo()
        proc = self.launch(
            root, worker=["launch_failed", "launch_failed", "w", "w"], probe=["broken", "broken"],
            verify=["pass", "pass"], review=["PASS", "PASS"],
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.shown(root)[:5], [
            "probe T-002 codex.economy broken", "reroute T-002 codex.economy agy.economy",
            "probe T-002 agy.economy broken", "reroute T-002 agy.economy cursor.economy",
            "verify T-002 1 pass",
        ])
        self.assertEqual(dict(self.worker_seats(root))["T-003-R1.md"], "cursor.economy")

        root = self.repo()
        proc = self.launch(
            root, worker=["launch_failed", "w", "w"], probe=["ok"],
            verify=["fail", "pass", "pass"], review=["PASS", "PASS"],
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.shown(root)[:3], [
            "probe T-002 codex.economy ok", "verify T-002 1 fail", "verify T-002 2 pass",
        ])
        self.assertTrue(all(seat == "codex.economy" for _, seat in self.worker_seats(root)))

        root = self.repo()
        proc = self.launch(root, worker=["launch_failed"] * 3, probe=["broken"] * 3)
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        shown = self.shown(root)
        self.assertEqual(sum(line.startswith("probe ") for line in shown), 3)
        self.assertEqual(shown[-1], "blocker T-002: no usable economy seat left")


if __name__ == "__main__":
    unittest.main()
