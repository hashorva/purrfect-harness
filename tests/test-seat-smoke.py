#!/usr/bin/env python3
"""Seat smoke scaffold contracts, through the real fleet-doctor.sh --smoke entry point.

Every fixture lives in a temporary directory.  The source repository is a copy of
this harness's scripts, schemas and registry, plus a fixture mission whose fleet is
the frozen v1 fixture (tests/fixtures/fleet/v1-2a-foundation.json, not the live mission
fleet) with only its mission path changed.  The v2 tests rewrite that mission's fleet.
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
import fleet_state  # noqa: E402
from fleet_state import canonical, validate_fleet  # noqa: E402
from verification_record import task_at_base  # noqa: E402

FIXTURE = "docs/missions/fixture"
SMOKE_MISSION = "docs/missions/00000000-seat-smoke"
F007_DIR = "docs/missions/00000000-f007-smoke"
F007_SEATS = ("claude.economy", "codex.economy", "cursor.economy", "cursor.premium")
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


FAKE_CLI = r'''#!/usr/bin/env python3
"""Fake provider CLI: behaviour per seat comes from SMOKE_MODES, probes go to SMOKE_PROBE."""
import json, os, pathlib, re, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
prompt = " ".join(sys.argv[1:])
brain = re.search(r"mission BRAIN for ([^\s]+)\.", prompt)
if brain:
    mission = brain.group(1)
    progress = pathlib.Path(mission) / "PROGRESS.md"
    progress.parent.mkdir(parents=True, exist_ok=True)
    with progress.open("a") as handle:
        handle.write("brain smoke line\n")
    GIT = ["git", "-c", "user.name=fake", "-c", "user.email=fake@invalid"]
    subprocess.run([*GIT, "add", str(progress)], check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "smoke: brain"], check=True)
    if json.loads(os.environ.get("SMOKE_MODES", "{}")).get("brain") == "live-touch":
        pathlib.Path(os.environ["SMOKE_LIVE"], "TRACKED.txt").write_text("live touched by brain\n")
    raise SystemExit(0)
seat = re.search(r"T-SMOKE-([a-z]+-[a-z]+)", prompt).group(1).replace("-", ".", 1)
probe = pathlib.Path(os.environ["SMOKE_PROBE"])
(probe / f"launched.{seat}").write_text(name)
mode = json.loads(os.environ.get("SMOKE_MODES", "{}")).get(seat, "both")
docs = pathlib.Path("docs/smoke") / f"{seat}.txt"
agents = pathlib.Path(".agents/smoke") / f"{seat}.txt"
GIT = ["git", "-c", "user.name=fake", "-c", "user.email=fake@invalid"]


def write(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"seat smoke {seat}\n")


if mode == "push":
    pushed = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/escape"], capture_output=True, text=True)
    (probe / f"push.{seat}").write_text(str(pushed.returncode))
    mode = "both"
if mode == "fail-model":
    print("ERROR: Cannot use this model: x")
    raise SystemExit(1)
if mode == "dirty":
    write(docs)
    write(agents)
    raise SystemExit(0)
write(docs)
if mode == "docs-only":
    try:
        raise PermissionError(13, "Permission denied", str(agents))
    except OSError as exc:
        print(f"ERROR: Cannot write {exc.filename}: {exc.strerror}")
else:
    write(agents)
if mode == "live-touch":
    pathlib.Path(os.environ["SMOKE_LIVE"], "TRACKED.txt").write_text("live touched\n")
if mode == "live-branch":
    subprocess.run(["git", "-C", os.environ["SMOKE_LIVE"], "branch", "x"], check=True)
subprocess.run([*GIT, "add", str(docs), *([] if mode == "docs-only" else [str(agents)])], check=True)
subprocess.run([*GIT, "commit", "-q", "-m", f"smoke: {seat}"], check=True)
raise SystemExit(0)
'''


class SeatSmoke(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp(prefix="seat-smoke-test-"))
        self.source = self.parent / "source"
        self.source.mkdir()
        shutil.copytree(ROOT / "scripts", self.source / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "schemas", self.source / "schemas")
        shutil.copy2(ROOT / "harness-registry.json", self.source / "harness-registry.json")
        live = json.loads((ROOT / "tests/fixtures/fleet/v1-2a-foundation.json").read_text())
        live["mission"] = {"path": FIXTURE}
        # The frozen agy seat encodes high while its effort is medium; contract 8 rejects that mismatch.
        live["seats"]["agy.economy"].update(model="gemini-3.8-flash-medium", effort="medium")
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
        (self.source / "TRACKED.txt").write_text("live\n")
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

    def f007(self, *args, modes=None):
        return subprocess.run(
            ["bash", str(self.source / "scripts/fleet-doctor.sh"), "--smoke", "--f007", *args],
            cwd=self.source, text=True, capture_output=True, env=self.launch_env(modes),
        )

    def launch(self, *args, modes=None):
        return subprocess.run(
            ["bash", str(self.source / "scripts/fleet-doctor.sh"), "--smoke", "--mission", FIXTURE, *args],
            cwd=self.source, text=True, capture_output=True, env=self.launch_env(modes),
        )

    def launch_env(self, modes):
        bin_dir = self.parent / "bin"
        if not bin_dir.exists():
            bin_dir.mkdir()
            for name in ("claude", "codex", "cursor-agent", "agy"):
                path = bin_dir / name
                path.write_text(FAKE_CLI)
                path.chmod(0o755)
        probe = self.parent / "probe"
        probe.mkdir(exist_ok=True)
        return {**ENV, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "SMOKE_PROBE": str(probe),
                "SMOKE_LIVE": str(self.source), "SMOKE_MODES": json.dumps(modes or {})}

    def latest_summary(self):
        files = sorted((self.source / ".tasks/smoke").glob("*.json"))
        self.assertTrue(files, "no summary file written")
        return json.loads(files[-1].read_text())

    def set_seat(self, seat, **fields):
        fleet = json.loads((self.source / FIXTURE / "fleet.json").read_text())
        fleet["seats"][seat].update(fields)
        (self.source / FIXTURE / "fleet.json").write_text(canonical(fleet))
        self.git("commit", "-qam", f"seat {seat} {fields}")

    def non_brain_seats(self):
        return sorted(name for name in self.fleet["seats"] if not name.startswith("brain"))

    def plan(self, *extra):
        result = self.doctor("--dry-run", "--mission", FIXTURE, *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    NOW = "2026-10-16T18:00:00Z"
    V2_MODELS = {"claude": ["opus", "sonnet", "haiku"], "codex": ["gpt-6-luna"], "agent": ["grok-4.7-medium"],
                 "agy": ["gemini-3.8-flash-medium"]}

    def make_v2(self, failed=()):
        """Replace the fixture fleet with a v2 fleet and give the live root its inventory."""
        providers = {}
        for key in fleet_state.PROVIDERS:
            base = {"probed_at": self.NOW, "capabilities": fleet_state.CAPABILITIES[key]}
            if key in failed:
                providers[key] = {**base, "status": "failure", "path": "/bin/" + key, "error": "fixture failure"}
            elif key == "claude":
                providers[key] = {**base, "status": "success", "path": "/bin/claude", "aliases": self.V2_MODELS[key], "observed_models": []}
            else:
                providers[key] = {**base, "status": "success", "path": "/bin/" + key, "aliases": [], "observed_models": self.V2_MODELS[key]}
        inventory = {"schema_version": 1, "probed_at": self.NOW, "providers": providers, "last_good": {},
                     "seats": fleet_state.make_seats(providers, {})}
        fleet_state.validate_inventory(inventory)
        (self.source / ".tasks").mkdir(exist_ok=True)
        self.inventory_bytes = fleet_state.canonical(inventory).encode()
        (self.source / ".tasks/fleet-inventory.json").write_bytes(self.inventory_bytes)

        def seat(family, effort, doors, speed, provider, model):
            return {"family": family, "effort": effort, "speed": speed, "doors": doors,
                    "approved_resolution": {"provider": provider, "model": model, "effort": effort, "speed": speed}}
        fleet = {"schema_version": 2, "mission": {"path": FIXTURE}, "inventory": {"sha256": "0" * 64, "probed_at": self.NOW},
                 "approval": {"status": "approved", "approved_by": "test", "approved_at": self.NOW},
                 "policy": {"billing_classes": ["included"], "fast": False, "no_zdr": "allow"},
                 "seats": {"brain": seat("opus", "high", ["claude"], "unknown", "claude", "opus"),
                           "agy.economy": seat("flash", "medium", ["agy"], "unknown", "agy", "gemini-3.8-flash-medium"),
                           "claude.economy": seat("haiku", "medium", ["claude"], "unknown", "claude", "haiku"),
                           "cursor.premium": seat("grok", "medium", ["cursor-grok"], "standard", "cursor", "grok-4.7-medium")}}
        validate_fleet(fleet)
        (self.source / FIXTURE / "fleet.json").write_text(canonical(fleet))
        self.git("commit", "-qam", "v2 fleet")

    def test_v2_dry_run_plans_resolved_seats_and_clone_has_inventory(self):
        self.make_v2()
        data = self.plan("--dest", str(self.parent / "dest"), "--keep")
        self.assertEqual(sorted(data["seats"]), ["agy.economy", "claude.economy", "cursor.premium"])
        argv = data["seats"]["cursor.premium"]["argv"]
        self.assertEqual((argv[2], argv[argv.index("--effort") + 1], argv[argv.index("--speed") + 1]),
                         ("cursor", "medium", "standard"))
        self.assertEqual(data["seats"]["agy.economy"]["argv"][2], "agy")
        clone = Path(data["clone"])
        self.assertEqual((clone / ".tasks/fleet-inventory.json").read_bytes(), self.inventory_bytes)
        resolved = subprocess.run(
            ["python3", str(clone / "scripts/fleet_state.py"), "resolve", "--fleet", str(clone / SMOKE_MISSION / "fleet.json"),
             "--seat", "cursor.premium", "--inventory", str(clone / ".tasks/fleet-inventory.json"), "--root", str(clone)],
            cwd=clone, text=True, capture_output=True, env=ENV)
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertEqual(json.loads(resolved.stdout)["model"], "grok-4.7-medium")

    def test_v2_seat_launches_with_resolved_provider_and_model(self):
        self.make_v2()
        result = self.launch("--seat", "cursor.premium", "--dest", str(self.parent / "dest"),
                             modes={"cursor.premium": "both"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        entry = json.loads(result.stdout)["seats"]["cursor.premium"]
        self.assertEqual(entry["status"], "usable")
        self.assertEqual((entry["provider"], entry["model"], entry["effort"], entry["speed"]),
                         ("cursor", "grok-4.7-medium", "medium", "standard"))
        self.assertEqual((self.parent / "probe" / "launched.cursor.premium").read_text(), "cursor-agent")

    def test_v2_unavailable_seat_exits_2_before_the_destination_exists(self):
        self.make_v2(failed=("agy",))
        dest = self.parent / "dest"
        for extra in ((), ("--dry-run",)):
            result = self.doctor(*extra, "--mission", FIXTURE, "--seat", "agy.economy", "--dest", str(dest))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("seat agy.economy resolves as unavailable", result.stderr)
            self.assertFalse(dest.exists())

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

    def test_clone_has_no_remote_after_cloning(self):
        data = self.launch("--seat", "claude.economy", "--dest", str(self.parent / "dest"), "--keep",
                           modes={"claude.economy": "both"})
        self.assertIn(data.returncode, (0, 1), data.stdout + data.stderr)
        clone = Path(json.loads(data.stdout)["clone"])
        self.assertEqual(self.git("remote", cwd=clone), "")

    def test_fake_seat_cannot_push_out_of_the_clone(self):
        result = self.launch("--seat", "claude.economy", "--dest", str(self.parent / "dest"), "--keep",
                             modes={"claude.economy": "push"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        probe = (self.parent / "probe/push.claude.economy").read_text()
        self.assertNotEqual(probe, "0", "git push inside the clone must fail")
        self.assertEqual(self.git("branch", "--list", "escape").strip(), "")
        self.assertEqual(self.git("status", "--porcelain").strip(), "")

    def test_live_branch_change_fails_the_smoke(self):
        result = self.launch("--seat", "claude.economy", "--dest", str(self.parent / "dest"),
                             modes={"claude.economy": "live-branch"})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ERROR smoke: live tree changed", result.stderr)
        self.assertEqual(self.git("branch", "--list", "x").strip(), "x")

    def test_live_tracked_file_change_fails_the_smoke(self):
        result = self.launch("--seat", "claude.economy", "--dest", str(self.parent / "dest"),
                             modes={"claude.economy": "live-touch"})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ERROR smoke: live tree changed", result.stderr)
        self.assertEqual((self.source / "TRACKED.txt").read_text(), "live touched\n")

    def test_seat_classifications_from_receipt_and_head(self):
        modes = {"agy.economy": "dirty", "claude.economy": "both", "codex.economy": "docs-only",
                 "cursor.economy": "fail-model"}
        dest = self.parent / "dest"
        result = self.launch("--dest", str(dest), modes=modes)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse(dest.exists(), "clone and transcripts are removed without --keep")
        summary = json.loads(result.stdout)
        self.assertEqual(summary, self.latest_summary())
        self.assertEqual(sorted(summary), sorted(["base_commit", "clone", "finished_at", "kept", "mission",
                                                  "seats", "skipped", "started_at"]))
        seats = summary["seats"]
        self.assertEqual(sorted(seats), self.non_brain_seats())
        self.assertEqual(seats["claude.economy"]["status"], "usable")
        self.assertEqual(seats["claude.economy"]["outcome"], "completed")
        self.assertEqual(seats["claude.economy"]["exit_code"], 0)
        self.assertFalse(seats["claude.economy"]["clone_reset"])
        self.assertEqual(len(seats["claude.economy"]["commit"]), 40)
        self.assertEqual(seats["codex.economy"]["status"], "usable-with-limit")
        self.assertEqual(seats["codex.economy"]["reason"], "cannot write .agents/")
        self.assertEqual(seats["agy.economy"]["status"], "unusable")
        self.assertTrue(seats["agy.economy"]["clone_reset"])
        self.assertEqual(seats["cursor.economy"]["status"], "unusable")
        self.assertEqual(seats["cursor.economy"]["exit_code"], 1)
        self.assertIn("Cannot use this model: x", seats["cursor.economy"]["reason"])
        self.assertLessEqual(len(seats["cursor.economy"]["reason"]), 300)
        for seat, entry in seats.items():
            self.assertEqual(entry["provider"], self.fleet["seats"][seat]["provider"])
            self.assertEqual(entry["model"], self.fleet["seats"][seat]["model"])
        self.assertEqual(self.git("status", "--porcelain").strip(), "")

    def test_fast_seat_never_launches(self):
        self.set_seat("cursor.economy", speed="fast")
        result = self.launch("--seat", "cursor.economy", "--dest", str(self.parent / "dest"),
                             modes={"cursor.economy": "both"})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse((self.parent / "probe/launched.cursor.economy").exists())
        entry = self.latest_summary()["seats"]["cursor.economy"]
        self.assertEqual((entry["status"], entry["reason"], entry["run_id"]),
                         ("unusable", "fast mode is never smoked", None))

    def test_fast_model_suffix_never_launches(self):
        self.set_seat("claude.economy", model="haiku-fast")
        result = self.launch("--seat", "claude.economy", "--dest", str(self.parent / "dest"),
                             modes={"claude.economy": "both"})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse((self.parent / "probe/launched.claude.economy").exists())
        self.assertEqual(self.latest_summary()["seats"]["claude.economy"]["reason"],
                         "fast mode is never smoked")

    def test_fast_seat_is_skipped_while_others_launch(self):
        self.set_seat("cursor.economy", speed="fast")
        result = self.launch("--seat", "cursor.economy", "--seat", "claude.economy",
                             "--dest", str(self.parent / "dest"), modes={"claude.economy": "both"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.parent / "probe/launched.cursor.economy").exists())
        self.assertTrue((self.parent / "probe/launched.claude.economy").exists())

    def test_launch_keeps_live_snapshot_and_summary_in_live_root(self):
        before = snapshot(self.source)
        result = self.launch("--seat", "claude.economy", "--dest", str(self.parent / "dest"), "--keep",
                             modes={"claude.economy": "both"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(self.source), before)
        self.assertTrue(Path(json.loads(result.stdout)["clone"]).is_dir())
        self.assertEqual(json.loads(result.stdout)["kept"], True)

    def test_timeout_must_be_positive(self):
        result = self.launch("--seat", "claude.economy", "--timeout", "0", "--dest", str(self.parent / "dest"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_f007_requires_keep_and_refuses_seat(self):
        dest = self.parent / "f007-refuse"
        no_keep = self.f007("--dest", str(dest))
        self.assertEqual(no_keep.returncode, 2, no_keep.stdout + no_keep.stderr)
        self.assertIn("--f007 requires --keep", no_keep.stderr)
        self.assertFalse(dest.exists())
        with_seat = self.f007("--keep", "--seat", "claude.economy", "--dest", str(self.parent / "f007-seat"))
        self.assertEqual(with_seat.returncode, 2, with_seat.stdout + with_seat.stderr)
        self.assertIn("--f007 cannot be combined with --seat", with_seat.stderr)
        self.assertFalse((self.parent / "f007-seat").exists())

    def test_f007_dry_run_plans_four_seats_in_order_and_one_brain(self):
        dest = self.parent / "f007-plan"
        result = self.f007("--dry-run", "--dest", str(dest), "--keep")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["order"], list(F007_SEATS))
        self.assertEqual(sorted(data["seats"]), sorted(F007_SEATS))
        self.assertEqual(data["brain"]["argv"],
                         ["bash", "scripts/spawn-brain.sh", F007_DIR, "review"])
        clone = Path(data["clone"])
        for seat in F007_SEATS:
            task_id = "T-SMOKE-" + seat.replace(".", "-")
            task = clone / F007_DIR / "tasks" / f"{task_id}.md"
            self.assertTrue(task.is_file(), seat)
            self.assertEqual(data["seats"][seat]["task"], f"{F007_DIR}/tasks/{task_id}.md")

    def test_f007_happy_path_has_full_evidence(self):
        dest = self.parent / "f007-happy"
        modes = {seat: "both" for seat in F007_SEATS}
        result = self.f007("--dest", str(dest), "--keep", modes=modes)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout)
        clone = Path(summary["clone"])
        worker_ids = []
        for seat in F007_SEATS:
            worker_ids.append(summary["seats"][seat]["run_id"])
            self.assertEqual(summary["seats"][seat]["outcome"], "completed")
            self.assertTrue((dest / f"{seat}.out").is_file())
            self.assertTrue((dest / f"verify-{seat}.out").is_file())
            self.assertTrue((clone / F007_DIR / "verification" / f"{summary['seats'][seat]['run_id']}.json").is_file())
            self.assertTrue((clone / ".tasks/ledger" / f"{summary['seats'][seat]['run_id']}.json").is_file())
        self.assertEqual(summary["verify"], {seat: 0 for seat in F007_SEATS})
        self.assertEqual(summary["audit_exit"], 0)
        self.assertEqual(summary["reconstruct_exit"], 0)
        self.assertEqual(summary["brain"]["status"], "completed")
        self.assertTrue((dest / "brain.out").is_file())
        self.assertTrue((dest / "audit.out").is_file())
        self.assertTrue((dest / "reconstruct.out").is_file())
        brain_id = summary["brain"]["run_id"]
        self.assertTrue((clone / ".tasks/receipts" / f"{brain_id}.json").is_file())
        for run_id in worker_ids:
            self.assertTrue((clone / ".tasks/receipts" / f"{run_id}.json").is_file())
            self.assertIn(run_id, (dest / "reconstruct.out").read_text())
        self.assertFalse((self.parent / "probe/launched.agy.economy").exists())
        reconstruct = (dest / "reconstruct.out").read_text()
        for run_id in worker_ids:
            self.assertIn(f"RUN {run_id}", reconstruct)

    def test_f007_live_tree_touched_by_the_brain_fails(self):
        dest = self.parent / "f007-live-brain"
        modes = {seat: "both" for seat in F007_SEATS}
        modes["brain"] = "live-touch"
        result = self.f007("--dest", str(dest), "--keep", modes=modes)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("live tree changed during seat smoke", result.stderr)

    def test_f007_failed_seat_exits_1(self):
        dest = self.parent / "f007-fail"
        modes = {seat: "both" for seat in F007_SEATS}
        modes["cursor.premium"] = "fail-model"
        result = self.f007("--dest", str(dest), "--keep", modes=modes)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        summary = json.loads(result.stdout)
        self.assertNotIn("cursor.premium", summary.get("verify", {}))
        self.assertEqual(summary["reconstruct_exit"], 1)

    def test_f007_missing_ledger_row_fails_reconstruct(self):
        dest = self.parent / "f007-ledger"
        modes = {seat: "both" for seat in F007_SEATS}
        result = self.f007("--dest", str(dest), "--keep", modes=modes)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout)
        clone = Path(summary["clone"])
        worker_ids = [summary["seats"][seat]["run_id"] for seat in F007_SEATS]
        victim = worker_ids[0]
        (clone / ".tasks/ledger" / f"{victim}.json").unlink()
        recon = subprocess.run(
            ["bash", "scripts/reconstruct-run.sh", F007_DIR, *worker_ids],
            cwd=clone, text=True, capture_output=True, env=ENV,
        )
        self.assertEqual(recon.returncode, 1, recon.stdout + recon.stderr)
        self.assertIn(f"MISSING {victim}: ledger row", recon.stdout + recon.stderr)


if __name__ == "__main__":
    unittest.main()
