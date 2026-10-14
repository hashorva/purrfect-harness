#!/usr/bin/env python3
"""Seat smoke scaffold contracts, through the real fleet-doctor.sh --smoke entry point.

Every fixture lives in a temporary directory.  The source repository is a copy of
this harness's scripts, schemas and registry, plus a fixture mission whose fleet is
the live canonical fleet with only its mission path changed.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))

from dispatch_policy import worker_write_scope  # noqa: E402
from execution_receipt import snapshot  # noqa: E402
from fleet_state import canonical, validate_fleet  # noqa: E402
from verification_record import task_at_base  # noqa: E402

FIXTURE = "docs/missions/fixture"
SMOKE_MISSION = "docs/missions/00000000-seat-smoke"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


class SeatSmoke(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp(prefix="seat-smoke-test-"))
        self.source = self.parent / "source"
        self.source.mkdir()
        shutil.copytree(ROOT / "scripts", self.source / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "schemas", self.source / "schemas")
        shutil.copy2(ROOT / "harness-registry.json", self.source / "harness-registry.json")
        live = json.loads((ROOT / "docs/missions/20261014-2a-foundation/fleet.json").read_text())
        live["mission"] = {"path": FIXTURE}
        validate_fleet(live)
        self.fleet = live
        mission = self.source / FIXTURE
        (mission / "tasks").mkdir(parents=True)
        (mission / "GOAL.md").write_text("---\nstatus: in-progress\n---\n# Goal\n")
        (mission / "PROGRESS.md").write_text("# Fixture progress\n")
        (mission / "features.json").write_text(json.dumps({"goal": "fixture", "features": [
            {"id": "F001", "description": "one", "bootstrap": False, "steps": [], "passes": False},
        ]}) + "\n")
        (mission / "fleet.json").write_text(canonical(live))
        (self.source / ".gitignore").write_text(".tasks/\n__pycache__/\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def tearDown(self):
        shutil.rmtree(self.parent, ignore_errors=True)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *GIT_ID, *args], cwd=cwd or self.source, text=True,
                              capture_output=True, check=True).stdout

    def doctor(self, *args):
        return subprocess.run(
            ["bash", str(self.source / "scripts/fleet-doctor.sh"), "--smoke", *args],
            cwd=self.source, text=True, capture_output=True, env=ENV,
        )

    def non_brain_seats(self):
        return sorted(name for name in self.fleet["seats"] if not name.startswith("brain"))

    def plan(self, *extra):
        result = self.doctor("--dry-run", "--mission", FIXTURE, *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_dry_run_lists_every_non_brain_seat(self):
        dest = self.parent / "dest"
        data = self.plan("--dest", str(dest), "--keep")
        self.assertEqual(sorted(data["seats"]), self.non_brain_seats())
        self.assertTrue(data["kept"])
        self.assertEqual(sorted(data["skipped"]), ["brain"])
        self.assertIn("not launched", data["skipped"]["brain"])
        for seat, entry in data["seats"].items():
            argv = entry["argv"]
            self.assertEqual(argv[:2], ["bash", "scripts/spawn-worker.sh"])
            self.assertEqual(argv[argv.index("--tier") + 1], seat.split(".", 1)[1])
            self.assertEqual(argv[argv.index("--feature") + 1], "SMOKE")
        self.assertEqual(data["seats"]["cursor.economy"]["argv"][2], "cursor")

    def test_kept_clone_has_one_mission_valid_fleet_and_scoped_tasks(self):
        data = self.plan("--dest", str(self.parent / "dest"), "--keep")
        clone = Path(data["clone"])
        active = subprocess.run(["bash", str(clone / "scripts/active-mission.sh")], cwd=clone,
                                env={**ENV, "REPO": str(clone)}, text=True, capture_output=True)
        self.assertEqual(active.returncode, 0, active.stderr)
        self.assertEqual(active.stdout.strip(), SMOKE_MISSION)
        check = subprocess.run(["python3", str(clone / "scripts/fleet_state.py"), "validate-fleet",
                                str(clone / SMOKE_MISSION / "fleet.json")],
                               cwd=clone, text=True, capture_output=True, env=ENV)
        self.assertEqual(check.returncode, 0, check.stderr)
        smoke_fleet = json.loads((clone / SMOKE_MISSION / "fleet.json").read_text())
        self.assertIn("copied by seat smoke", smoke_fleet["approval"]["approved_by"])
        self.assertEqual(smoke_fleet["seats"], self.fleet["seats"])
        self.assertEqual(data["base_commit"], self.git("rev-parse", "HEAD", cwd=clone).strip())
        for seat in self.non_brain_seats():
            task_id = "T-SMOKE-" + seat.replace(".", "-")
            task = clone / SMOKE_MISSION / "tasks" / f"{task_id}.md"
            self.assertTrue(task.is_file(), seat)
            self.assertEqual(data["seats"][seat]["task"], f"{SMOKE_MISSION}/tasks/{task_id}.md")
            receipt = {"mission": SMOKE_MISSION, "work_unit": task_id, "feature": "SMOKE",
                       "task": data["seats"][seat]["task"], "git_before": {"head": data["base_commit"]}}
            _, _, commands = task_at_base(clone, receipt)
            self.assertEqual(commands, [["test", "-f", f"docs/smoke/{seat}.txt"],
                                        ["test", "-f", f".agents/smoke/{seat}.txt"]])
            scope = worker_write_scope(task)
            self.assertEqual(scope, [f"docs/smoke/{seat}.txt", f".agents/smoke/{seat}.txt",
                                     f"{SMOKE_MISSION}/PROGRESS.md"])
        self.assertEqual(self.git("status", "--porcelain", cwd=clone), "")

    def test_source_tree_is_unchanged(self):
        before = snapshot(self.source)
        self.plan("--dest", str(self.parent / "dest"), "--keep")
        self.assertEqual(snapshot(self.source), before)

    def test_unknown_seat_exits_2(self):
        result = self.doctor("--dry-run", "--mission", FIXTURE, "--seat", "no.such.seat",
                             "--dest", str(self.parent / "dest"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("unknown seat: no.such.seat", result.stderr)

    def test_brain_seat_is_never_smoked(self):
        result = self.doctor("--dry-run", "--mission", FIXTURE, "--seat", "brain",
                             "--dest", str(self.parent / "dest"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_narrowed_seat_is_the_only_plan_entry(self):
        data = self.plan("--seat", "claude.economy", "--dest", str(self.parent / "dest2"), "--keep")
        self.assertEqual(sorted(data["seats"]), ["claude.economy"])

    def test_dirty_source_tree_is_refused(self):
        (self.source / "stray.txt").write_text("dirty\n")
        result = self.doctor("--dry-run", "--mission", FIXTURE, "--dest", str(self.parent / "dest"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ERROR smoke: live tree must be clean", result.stderr)
        self.assertFalse((self.parent / "dest").exists())

    def test_dest_inside_source_is_refused_unless_under_tasks_smoke(self):
        result = self.doctor("--dry-run", "--mission", FIXTURE, "--dest", str(self.source / "inside"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("--dest must be outside the live tree", result.stderr)
        self.assertFalse((self.source / "inside").exists())
        allowed = self.source / ".tasks/smoke/run"
        data = self.plan("--dest", str(allowed), "--keep")
        self.assertTrue(Path(data["clone"]).is_dir())

    def test_clone_is_removed_without_keep(self):
        dest = self.parent / "gone"
        data = self.plan("--dest", str(dest))
        self.assertFalse(data["kept"])
        self.assertFalse(Path(data["clone"]).exists())
        self.assertFalse(dest.exists())

    def test_launch_is_refused_without_dry_run(self):
        result = self.doctor("--mission", FIXTURE, "--dest", str(self.parent / "dest"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("ERROR smoke: launch is implemented in T-008", result.stderr)


if __name__ == "__main__":
    unittest.main()
