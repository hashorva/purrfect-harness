import importlib
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
B = importlib.import_module("brain_prompt")
MISSIONS = ("mission-init", "planning", "gate0", "gate", "review")
ROLES = {"mission-init": "planning", "planning": "planning", "gate0": "gate", "gate": "gate", "review": "review"}
PROVIDERS = ("claude", "codex", "agent", "agy")
HEADINGS = ("## Goal", "## Resources", "## Permissions", "## Acceptance checks")


class BrainPromptTests(unittest.TestCase):
    def test_every_role_has_the_four_headings_in_order(self):
        for action in MISSIONS:
            for provider in PROVIDERS:
                with self.subTest(action=action, provider=provider):
                    lines = B.render(action, "docs/missions/x", provider).splitlines()
                    self.assertEqual(lines[0], f"You are the mission BRAIN for docs/missions/x. Role: {ROLES[action]}.")
                    self.assertEqual([lines.count(h) for h in HEADINGS], [1, 1, 1, 1])
                    self.assertEqual([lines.index(h) for h in HEADINGS], sorted(lines.index(h) for h in HEADINGS))

    def test_prompts_state_no_token_budget_and_name_the_log_under_resources(self):
        for action in MISSIONS:
            for provider in PROVIDERS:
                prompt = B.render(action, "m", provider, "run.log")
                low = prompt.lower()
                self.assertNotIn("budget", low)
                self.assertNotIn("tokens", low)
                resources = prompt.split("## Resources\n", 1)[1].split("\n## Permissions", 1)[0]
                self.assertTrue(resources.endswith(" Your log: run.log."), resources)
        self.assertNotIn("Your log", B.render("review", "m", "claude"))

    def test_only_claude_prompts_name_subagents(self):
        for action in MISSIONS:
            prompt = B.render(action, "m", "claude")
            self.assertIn(".claude/agents/explorer.md", prompt)
            self.assertIn("model haiku", prompt)
            self.assertIn("Subagents available: the explorer subagent", prompt)
            for provider in ("codex", "agent", "agy"):
                low = B.render(action, "m", provider).lower()
                for word in ("explorer", "luna", "composer", "flash", "haiku", ".claude/agents", "code-reviewer"):
                    self.assertNotIn(word, low)

    def test_permissions_state_the_role_limits(self):
        for role in ("planning", "gate"):
            section = B.render(role, "m", "claude").split("## Permissions\n", 1)[1].split("\n## Acceptance checks", 1)[0]
            self.assertIn("Write only inside the mission folder", section)
        review = B.render("review", "m", "claude").split("## Permissions\n", 1)[1].split("\n## Acceptance checks", 1)[0]
        self.assertIn("Read-only", review)

    def test_cli_prints_the_prompt_and_refuses_unknown_names(self):
        env = dict(__import__("os").environ, PYTHONDONTWRITEBYTECODE="1")
        cli = [sys.executable, str(ROOT / "scripts/brain_prompt.py")]
        good = subprocess.run(cli + ["review", "m", "--provider", "claude"], capture_output=True, text=True, env=env)
        self.assertEqual((good.returncode, good.stdout, good.stderr), (0, B.render("review", "m", "claude") + "\n", ""))
        for args in (("bogus", "m", "--provider", "claude"), ("review", "m", "--provider", "cursor")):
            bad = subprocess.run(cli + list(args), capture_output=True, text=True, env=env)
            self.assertEqual((bad.returncode, bad.stdout), (2, ""))
            self.assertTrue(bad.stderr.startswith("brain_prompt: "))

    def test_request_is_appended_under_its_own_heading(self):
        prompt = B.render("planning", "m", "claude", request="  Do X.\n")
        self.assertTrue(prompt.endswith("\n## Request\nDo X."))
        self.assertNotIn("## Request", B.render("planning", "m", "claude"))
        with tempfile.TemporaryDirectory() as directory:
            (request := Path(directory) / "request.md").write_text("  Do X.\n", encoding="utf-8")
            cli = [sys.executable, str(ROOT / "scripts/brain_prompt.py"), "planning", "m", "--provider", "claude", "--request", str(request)]
            good = subprocess.run(cli, capture_output=True, text=True)
            self.assertEqual((good.returncode, good.stdout, good.stderr), (0, prompt + "\n", ""))
            for contents in ("", None):
                request.write_text(contents) if contents is not None else request.unlink()
                bad = subprocess.run(cli, capture_output=True, text=True)
                self.assertEqual((bad.returncode, bad.stdout), (2, ""))
                self.assertTrue(bad.stderr.startswith("brain_prompt: "))

    def test_spawn_brain_renders_through_brain_prompt(self):
        source = (ROOT / "scripts/spawn-brain.sh").read_text(encoding="utf-8")
        self.assertIn('PROMPT="$(PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/brain_prompt.py" "$ACTION" "$MISSION" --provider "$PROVIDER" --log "$LOG_REL")" || exit $?', source)
        self.assertNotIn("Goal for mission-init", source)


if __name__ == "__main__":
    unittest.main()
