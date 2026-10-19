import importlib
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
B = importlib.import_module("brain_prompt")
R = importlib.import_module("replay_seeded_defects")
FORBIDDEN = ("delegat", "excerpts you need", "cheap subagent", "log tail", "stream full transcripts", "before you finish", "stay within it by")
PRINCIPLE = "The harness defines goals, budgets, permissions and deterministic checks; the model decides its own method."


def method_hits(texts):
    return sorted((name, phrase) for name, text in texts.items()
                  for phrase in FORBIDDEN if phrase in " ".join(text.split()).lower())


class GoalStyleTests(unittest.TestCase):
    def test_prompts_skills_and_agents_have_no_method_phrases(self):
        texts = {f"brain {action} {provider}": B.render(action, "m", provider, "run.log")
                 for action in B.ROLES for provider in B.PROVIDERS}
        texts.update({f"review {provider}": R.review_prompt({"task": "T-043"}, provider)
                      for provider in B.PROVIDERS})
        worker_lines = [line for line in (ROOT / "scripts/spawn-worker.sh").read_text().splitlines()
                        if line.startswith("PROMPT=")]
        self.assertEqual(len(worker_lines), 1)
        texts["worker"] = worker_lines[0]
        for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")) + sorted((ROOT / ".claude/agents").glob("*.md")):
            texts[str(path.relative_to(ROOT))] = path.read_text(encoding="utf-8")
        self.assertEqual(method_hits(texts), [])

    def test_helper_flags_method_phrases(self):
        hits = method_hits({"sample": "Delegate wide reading and\nsearching to a cheap subagent"})
        self.assertEqual(hits, [("sample", "cheap subagent"), ("sample", "delegat")])

    def test_claude_prompts_list_explorer_and_permissions(self):
        for action in B.ROLES:
            text = B.render(action, "m", "claude")
            self.assertIn("\n## Permissions\n", text)
            resources = text.split("## Resources", 1)[1].split("## Budget", 1)[0]
            self.assertIn(".claude/agents/explorer.md", resources)

    def test_docs_state_principle(self):
        for relative in ("AGENTS.md", "docs/missions/ORCHESTRATION.md"):
            text = " ".join((ROOT / relative).read_text(encoding="utf-8").split())
            self.assertIn(PRINCIPLE, text)


if __name__ == "__main__":
    unittest.main()
