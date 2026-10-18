import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FX, ENV = ROOT / "tests/fixtures/plan-extract", dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
T = lambda i, b="Body.": "\n".join(["---", f"task_id: {i}", "feature: F001", "---", "", f"# Task {i}", "", b])
class PlanExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.logs = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp); self.addCleanup(shutil.rmtree, self.logs)
        self.mission = self.tmp / "docs/missions/fx"; self.tasks = self.mission / "tasks"
        self.tasks.mkdir(parents=True); (self.mission / "GOAL.md").write_text("# Goal\n")
    def cli(self, arg, out=None):
        return subprocess.run([sys.executable, str(ROOT / "scripts/plan_extract.py"), arg, str(out or self.tasks)],
                              cwd=self.tmp, capture_output=True, text=True, env=ENV)
    def run_text(self, text, header="", out=None):
        p = self.logs / "run.log"; p.write_text(header + json.dumps({"type": "result", "result": text}) + "\n")
        return self.cli(str(p), out)
    def test_both_block_styles_are_extracted_in_text_order(self):
        out = self.run_text((FX / "both-styles.md").read_text())
        self.assertEqual((out.returncode, out.stdout), (0, "T-801\nT-802\n"))
        self.assertEqual((self.tasks / "T-801.md").read_text(), T("T-801", "First fenced task.") + "\n")
        self.assertEqual((self.tasks / "T-802.md").read_text(), T("T-802", "Second file block.") + "\n")
    def test_paths_outside_the_mission_folder_are_refused(self):
        ext = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, ext)
        def refused(text):
            before = sorted(self.tmp.rglob("*")); r = self.run_text(text)
            self.assertEqual((r.returncode, r.stdout), (2, "")); self.assertTrue(r.stderr.startswith("plan_extract: "))
            self.assertEqual(sorted(self.tmp.rglob("*")), before); self.assertEqual(list(ext.iterdir()), [])
        refused((FX / "traversal.md").read_text()); refused(f"=== FILE: {self.tasks / 'T-abs.md'} ===\n{T('T-abs')}\n=== END FILE ===\n")
        (self.tasks / "link").symlink_to(ext); refused(f"=== FILE: docs/missions/fx/tasks/link/T-link.md ===\n{T('T-link')}\n=== END FILE ===\n")
        refused(f"=== FILE: docs/missions/fx/features.json ===\n{T('T-prot')}\n=== END FILE ===\n")
    def test_block_without_task_id_is_refused(self):
        out = self.run_text((FX / "no-task-id.md").read_text()); self.assertEqual((out.returncode, out.stdout), (2, "")); self.assertFalse(any(self.tasks.iterdir()))
    def test_duplicates_and_existing_files_are_refused(self):
        self.assertEqual(self.run_text((FX / "duplicate.md").read_text()).returncode, 2)
        self.assertEqual(self.run_text((FX / "both-styles.md").read_text()).returncode, 0)
        again = self.run_text((FX / "both-styles.md").read_text()); self.assertEqual((again.returncode, again.stdout), (2, ""))
        self.assertEqual(sorted(p.name for p in self.tasks.iterdir()), ["T-801.md", "T-802.md"])
    def test_run_id_reads_its_log_and_ignores_prompt_text(self):
        rid = "550e8400-e29b-41d4-a716-446655440000"; (self.tmp / ".tasks/logs").mkdir(parents=True)
        fence = "````markdown\n" + T("T-820") + "\n````\n"
        (self.tmp / ".tasks/logs" / f"{rid}.log").write_text("spawn-brain: action=plan\nprompt: " + fence + "\n" + json.dumps({"event": "result", "result": {"response": fence}}) + "\n")
        out = self.cli(rid); self.assertEqual((out.returncode, out.stdout), (0, "T-820\n")); self.assertEqual((self.tasks / "T-820.md").read_text(), T("T-820") + "\n")
if __name__ == "__main__": unittest.main()