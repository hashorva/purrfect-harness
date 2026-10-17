#!/usr/bin/env python3
"""Unit tests for drive-cli rule table and deterministic prompt matcher (T-065)."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import drive_cli_rules as R
from drive_cli_rules import RulesError, load_rules, match_pane


class TestLoadRules(unittest.TestCase):
    """Test schema and integrity validation of rules data."""

    def setUp(self):
        self.rules = load_rules()

    def test_default_rules_valid(self):
        self.assertEqual(self.rules.get("schema_version"), 1)
        never_ids = [r.get("id") for r in self.rules.get("never_rules", [])]
        for req in R.REQUIRED_NEVER_IDS:
            self.assertIn(req, never_ids)
        self.assertIn("folder_trust_rule", self.rules)
        self.assertEqual(self.rules["folder_trust_rule"].get("decision"), "answer")
        self.assertEqual(self.rules["folder_trust_rule"].get("answer"), "y\n")
        self.assertTrue(len(self.rules.get("prompt_patterns", [])) > 0)
        self.assertEqual(self.rules["danger_words"], R.DANGER_WORDS)

    def test_danger_words_must_be_exact(self):
        doc = json.loads(R.DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
        doc["danger_words"].remove("push")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(doc, tf)
            path = tf.name
        try:
            with self.assertRaises(RulesError):
                load_rules(path)
        finally:
            os.unlink(path)

    def test_missing_file_raises_rules_error(self):
        with self.assertRaises(RulesError):
            load_rules("/nonexistent/path/rules.json")

    def test_invalid_json_raises_rules_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write("{ not valid json }")
            tf_path = tf.name
        try:
            with self.assertRaises(RulesError):
                load_rules(tf_path)
        finally:
            os.unlink(tf_path)

    def test_non_dict_root_raises_rules_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(json.dumps(["not", "a", "dict"]))
            tf_path = tf.name
        try:
            with self.assertRaises(RulesError):
                load_rules(tf_path)
        finally:
            os.unlink(tf_path)

    def test_invalid_schema_version_raises_rules_error(self):
        with open(R.DEFAULT_RULES_PATH, "r", encoding="utf-8") as f:
            base_doc = json.load(f)
        for bad_ver in (2, 0, "1", None):
            doc = copy.deepcopy(base_doc)
            doc["schema_version"] = bad_ver
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
                json.dump(doc, tf)
                tf_path = tf.name
            try:
                with self.assertRaises(RulesError):
                    load_rules(tf_path)
            finally:
                os.unlink(tf_path)

    def test_missing_never_rules_category_raises_rules_error(self):
        for drop_id in R.REQUIRED_NEVER_IDS:
            doc = {
                "schema_version": 1,
                "never_rules": [
                    {"id": r["id"], "decision": "stop", "exit_code": 3, "patterns": r["patterns"]}
                    for r in self.rules["never_rules"]
                    if r["id"] != drop_id
                ],
                "allowed_rules": [
                    {"id": "folder_trust", "decision": "answer", "answer": "y\n", "patterns": ["trust"]}
                ],
                "prompt_patterns": ["\\[y/n\\]"],
            }
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
                json.dump(doc, tf)
                tf_path = tf.name
            try:
                with self.assertRaises(RulesError):
                    load_rules(tf_path)
            finally:
                os.unlink(tf_path)

    def test_invalid_never_rule_attributes_raise_rules_error(self):
        base = {
            "schema_version": 1,
            "never_rules": [
                {"id": r, "decision": "stop", "exit_code": 3, "patterns": [r]}
                for r in R.REQUIRED_NEVER_IDS
            ],
            "allowed_rules": [
                {"id": "folder_trust", "decision": "answer", "answer": "y\n", "patterns": ["trust"]}
            ],
            "prompt_patterns": ["\\[y/n\\]"],
        }
        # Bad decision
        doc = copy.deepcopy(base)
        doc["never_rules"][0]["decision"] = "answer"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(doc, tf)
            tf_path = tf.name
        try:
            with self.assertRaises(RulesError):
                load_rules(tf_path)
        finally:
            os.unlink(tf_path)

        # Bad exit code
        doc = copy.deepcopy(base)
        doc["never_rules"][0]["exit_code"] = 1
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(doc, tf)
            tf_path = tf.name
        try:
            with self.assertRaises(RulesError):
                load_rules(tf_path)
        finally:
            os.unlink(tf_path)

    def test_missing_folder_trust_raises_rules_error(self):
        doc = {
            "schema_version": 1,
            "never_rules": [
                {"id": r, "decision": "stop", "exit_code": 3, "patterns": [r]}
                for r in R.REQUIRED_NEVER_IDS
            ],
            "allowed_rules": [],
            "prompt_patterns": ["\\[y/n\\]"],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(doc, tf)
            tf_path = tf.name
        try:
            with self.assertRaises(RulesError):
                load_rules(tf_path)
        finally:
            os.unlink(tf_path)

    def test_invalid_regex_raises_rules_error(self):
        doc = {
            "schema_version": 1,
            "never_rules": [
                {"id": r, "decision": "stop", "exit_code": 3, "patterns": ["(" if r == "credits_payment" else r]}
                for r in R.REQUIRED_NEVER_IDS
            ],
            "allowed_rules": [
                {"id": "folder_trust", "decision": "answer", "answer": "y\n", "patterns": ["trust"]}
            ],
            "prompt_patterns": ["\\[y/n\\]"],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(doc, tf)
            tf_path = tf.name
        try:
            with self.assertRaises(RulesError):
                load_rules(tf_path)
        finally:
            os.unlink(tf_path)


class TestWorkspaceValidation(unittest.TestCase):
    """Test workspace argument safety guards."""

    def setUp(self):
        self.rules = load_rules()

    def test_empty_workspace_rejected(self):
        for bad in ("", "   ", None):
            with self.assertRaises(RulesError):
                match_pane("some text", bad, self.rules)

    def test_relative_workspace_rejected(self):
        for bad in ("relative/path", "./ws", "ws"):
            with self.assertRaises(RulesError):
                match_pane("some text", bad, self.rules)

    def test_dotdot_segments_rejected(self):
        for bad in ("/tmp/../etc", "/tmp/ws/..", "/tmp/ws/../other", "/../tmp"):
            with self.assertRaises(RulesError):
                match_pane("some text", bad, self.rules)

    def test_valid_workspace_accepted(self):
        res = match_pane("Compiling...", "/tmp/ws-exact", self.rules)
        self.assertEqual(res["decision"], "wait")


class TestFolderTrustExactMatching(unittest.TestCase):
    """Test folder-trust prompt matching on exact workspace token boundaries."""

    def setUp(self):
        self.rules = load_rules()
        self.ws = "/tmp/ws-exact"

    def test_multiline_prompt_accepted(self):
        pane = f"Do you trust the files in this folder?\n{self.ws}\n[y/n] "
        res = match_pane(pane, self.ws, self.rules)
        self.assertEqual(res["decision"], "answer")
        self.assertEqual(res["category"], "allowed")
        self.assertEqual(res["rule_id"], "folder_trust")
        self.assertEqual(res["answer"], "y\n")
        self.assertIsNone(res["exit_code"])

    def test_single_line_prompt_accepted(self):
        pane = f"Do you trust the files in this folder? {self.ws} [y/n]"
        res = match_pane(pane, self.ws, self.rules)
        self.assertEqual(res["decision"], "answer")
        self.assertEqual(res["rule_id"], "folder_trust")
        self.assertEqual(res["answer"], "y\n")

    def test_prompt_with_surrounding_quotes_accepted(self):
        pane = f"Do you trust the files in this folder?\n'{self.ws}'\n[y/n] "
        res = match_pane(pane, self.ws, self.rules)
        self.assertEqual(res["decision"], "stop")
        self.assertEqual(res["category"], "unknown_prompt")
        self.assertEqual(res["exit_code"], 3)

    def test_rejection_of_bad_workspace_paths(self):
        bad_paths = (
            f"{self.ws}-2",         # sibling
            f"{self.ws}/sub",       # child
            "/tmp",                 # parent
            f"{self.ws}/../other",  # dot-dot traversal
        )
        for bad in bad_paths:
            pane = f"Do you trust the files in this folder?\n{bad}\n[y/n] "
            res = match_pane(pane, self.ws, self.rules)
            self.assertEqual(res["decision"], "stop", f"Failed on {bad}")
            self.assertEqual(res["category"], "unknown_prompt", f"Failed on {bad}")
            self.assertEqual(res["exit_code"], 3, f"Failed on {bad}")

    def test_missing_path_in_trust_prompt_rejected_as_unknown_prompt(self):
        pane = "Do you trust the files in this folder?\n[y/n] "
        res = match_pane(pane, self.ws, self.rules)
        self.assertEqual(res["decision"], "stop")
        self.assertEqual(res["category"], "unknown_prompt")
        self.assertEqual(res["exit_code"], 3)

    def test_multiple_paths_in_trust_prompt_rejected(self):
        pane = f"Do you trust the files in this folder?\n{self.ws}\n/tmp/other\n[y/n] "
        res = match_pane(pane, self.ws, self.rules)
        self.assertEqual(res["decision"], "stop")
        self.assertEqual(res["category"], "unknown_prompt")
        self.assertEqual(res["exit_code"], 3)

    def test_extra_unapproved_prompt_line_rejects_folder_trust(self):
        pane = f"Do you trust the files in this folder?\n{self.ws}\n[y/n]\nEnable telemetry uploads? [y/n]"
        res = match_pane(pane, self.ws, self.rules)
        self.assertEqual(res["decision"], "stop")
        self.assertEqual(res["category"], "unknown_prompt")
        self.assertEqual(res["exit_code"], 3)
        ordinary_output = f"Do you trust the files in this folder?\n{self.ws}\n[y/n]\nbuild ok"
        res = match_pane(ordinary_output, self.ws, self.rules)
        self.assertEqual((res["decision"], res["category"], res["exit_code"]), ("stop", "unknown_prompt", 3))

    def test_normalization_boundaries_danger_words_and_hashing(self):
        base = "Do you trust the files in this folder?\n/ws\n[y/n]"
        cases = [
            ("/ws:evil", "unknown_prompt"), ("/ws–evil", "unknown_prompt"),
            ("/ws\x1b[0m-evil", "unknown_prompt"), ("/ws：evil", "unknown_prompt"),
            ("'/ws'", "unknown_prompt"),
        ]
        for path, category in cases:
            result = match_pane(f"Do you trust the files in this folder?\n{path}\n[y/n]", "/ws", self.rules)
            self.assertEqual((result["decision"], result["category"], result["exit_code"]), ("stop", category, 3), path)
        for word in self.rules["danger_words"]:
            pane = f"Do you trust this folder /ws and {word} here? [y/n]"
            result = match_pane(pane, "/ws", self.rules)
            expected = "push_network_install" if word in {"curl", "wget", "fetch"} else "credits_payment" if word in {"credit", "payment", "billing", "purchase"} else None
            self.assertEqual(result["decision"], "stop", word)
            self.assertEqual(result["exit_code"], 3, word)
            if expected:
                self.assertEqual((result["category"], result["rule_id"]), ("never", expected), word)
            else:
                self.assertEqual((result["category"], result["rule_id"]), ("unknown_prompt", None), word)
        self.assertEqual(match_pane("Do you trust this folder /ws while pushing files? [y/n]", "/ws", self.rules)["decision"], "answer")
        self.assertEqual(match_pane("Do you trust this folder /ws and " + "a" * 4000 + " push? [y/n]", "/ws", self.rules)["category"], "unknown_prompt")
        self.assertEqual(R.normalize_pane("/ws\x1b[0m-evil"), "/ws-evil")
        self.assertEqual(R.normalize_pane("git\u200bpush"), "git push")
        self.assertEqual(R.normalize_pane("git\u200cpush"), "git push")
        self.assertEqual(R.pane_digest(base), hashlib.sha256(base.encode("utf-8")).hexdigest())
        self.assertNotEqual(R.pane_digest("/ws"), R.pane_digest("/ws\u200b"))
        changed = copy.deepcopy(self.rules)
        changed["danger_words"].remove("push")
        self.assertEqual(match_pane("Do you trust this folder /ws and push here? [y/n]", "/ws", changed)["decision"], "answer")

    def test_answered_window_classification(self):
        old = "Do you trust this folder /ws [y/n]"
        rules = self.rules
        same = R.classify_window(old, "/ws", old, rules)
        self.assertEqual((same["decision"], same["answer"], same["exit_code"]), ("wait", None, None))
        scrolled = R.classify_window("Allow git push origin main? [y/n]\n" + old, "/ws", old, rules)
        self.assertEqual((scrolled["decision"], scrolled["exit_code"], scrolled["answer"]), ("stop", 3, None))
        benign = R.classify_window(old + "\ntrusted and done", "/ws", old, rules)
        self.assertEqual((benign["decision"], benign["exit_code"]), ("wait", None))
        second = R.classify_window(old + "\n" + old, "/ws", old, rules)
        self.assertEqual((second["decision"], second["exit_code"], second["answer"]), ("stop", 3, None))
        self.assertEqual(R.classify_window("", "/ws", rules=rules)["decision"], "wait")


class TestNeverRules(unittest.TestCase):
    """Test all 5 required NEVER categories."""

    def setUp(self):
        self.rules = load_rules()
        self.ws = "/tmp/ws-exact"

    def test_write_outside_workspace(self):
        prompts = [
            "Allow write to /etc/hosts? [y/n]",
            "Writing outside workspace: ../secret.txt [y/n]",
            "Edit ~/.bashrc? [y/n]",
            "Create file in external directory /var/log? [y/n]",
        ]
        for p in prompts:
            res = match_pane(p, self.ws, self.rules)
            self.assertEqual(res["decision"], "stop", f"Failed on {p}")
            self.assertEqual(res["category"], "never", f"Failed on {p}")
            self.assertEqual(res["rule_id"], "write_outside_workspace", f"Failed on {p}")
            self.assertEqual(res["exit_code"], 3, f"Failed on {p}")

    def test_delete_ignored_files(self):
        prompts = [
            "Run git clean -fdX to delete ignored files? [y/n]",
            "Run git clean -fdx? [y/n]",
            "Delete untracked files? [y/n]",
            "Remove ignored files? [y/n]",
        ]
        for p in prompts:
            res = match_pane(p, self.ws, self.rules)
            self.assertEqual(res["decision"], "stop", f"Failed on {p}")
            self.assertEqual(res["category"], "never", f"Failed on {p}")
            self.assertEqual(res["rule_id"], "delete_ignored_files", f"Failed on {p}")
            self.assertEqual(res["exit_code"], 3, f"Failed on {p}")

    def test_push_network_install(self):
        prompts = [
            "Allow git push origin main? [y/n]",
            "Run curl https://example.com/setup.sh? [y/n]",
            "Run wget http://example.com/file? [y/n]",
            "npm install left-pad? [y/n]",
            "pip install requests? [y/n]",
            "cargo install ripgrep? [y/n]",
            "brew install jq? [y/n]",
        ]
        for p in prompts:
            res = match_pane(p, self.ws, self.rules)
            self.assertEqual(res["decision"], "stop", f"Failed on {p}")
            self.assertEqual(res["category"], "never", f"Failed on {p}")
            self.assertEqual(res["rule_id"], "push_network_install", f"Failed on {p}")
            self.assertEqual(res["exit_code"], 3, f"Failed on {p}")

    def test_git_history_changes(self):
        prompts = [
            "Run git reset --hard HEAD~1? [y/n]",
            "Run git rebase -i main? [y/n]",
            "git commit --amend? [y/n]",
            "git push --force origin main? [y/n]",
            "git filter-branch --env-filter ...? [y/n]",
        ]
        for p in prompts:
            res = match_pane(p, self.ws, self.rules)
            self.assertEqual(res["decision"], "stop", f"Failed on {p}")
            self.assertEqual(res["category"], "never", f"Failed on {p}")
            self.assertEqual(res["rule_id"], "git_history_changes", f"Failed on {p}")
            self.assertEqual(res["exit_code"], 3, f"Failed on {p}")

    def test_credits_payment(self):
        prompts = [
            "Purchase $20 API credits now? [y/n]",
            "Charge card for additional credits? [y/n]",
            "Upgrade plan to Pro for $50/mo? [y/n]",
            "Exceeded billing spend limit, increase limit? [y/n]",
        ]
        for p in prompts:
            res = match_pane(p, self.ws, self.rules)
            self.assertEqual(res["decision"], "stop", f"Failed on {p}")
            self.assertEqual(res["category"], "never", f"Failed on {p}")
            self.assertEqual(res["rule_id"], "credits_payment", f"Failed on {p}")
            self.assertEqual(res["exit_code"], 3, f"Failed on {p}")


class TestPrecedenceAndCompoundPrompts(unittest.TestCase):
    """Test that never_rules ALWAYS take precedence over allowed_rules."""

    def setUp(self):
        self.rules = load_rules()
        self.ws = "/tmp/ws-exact"

    def test_never_precedence_over_allowed(self):
        compound_cases = [
            (
                f"Do you trust the files in this folder?\n{self.ws}\n[y/n]\nAllow write to /etc/hosts? [y/n]",
                "write_outside_workspace",
            ),
            (
                f"Do you trust the files in this folder?\n{self.ws}\n[y/n]\nRun git clean -fdX? [y/n]",
                "delete_ignored_files",
            ),
            (
                f"Do you trust the files in this folder?\n{self.ws}\n[y/n]\nAllow git push origin main? [y/n]",
                "push_network_install",
            ),
            (
                f"Do you trust this folder {self.ws} and git push --force? [y/n]",
                "git_history_changes",
            ),
            (
                f"Do you trust the files in this folder?\n{self.ws}\n[y/n]\nPurchase $20 API credits now? [y/n]",
                "credits_payment",
            ),
        ]
        for pane, expected_rule in compound_cases:
            res = match_pane(pane, self.ws, self.rules)
            self.assertEqual(res["decision"], "stop", f"Expected stop on compound prompt: {pane}")
            self.assertEqual(res["category"], "never")
            self.assertEqual(res["rule_id"], expected_rule)
            self.assertEqual(res["exit_code"], 3)


class TestUnknownPromptsAndWaiting(unittest.TestCase):
    """Test unrecognized interactive prompts and normal non-prompt output."""

    def setUp(self):
        self.rules = load_rules()
        self.ws = "/tmp/ws-exact"

    def test_unknown_prompts_stop_with_exit_3(self):
        prompts = [
            "Enable telemetry uploads? [y/n]",
            "Do you want to send crash reports? (y/n)",
            "Approve execution of unknown tool? [y/n]",
            "Confirm deletion of buffer? yes/no",
            "Press enter to continue...",
            "Select an option [1-3]:",
        ]
        for p in prompts:
            res = match_pane(p, self.ws, self.rules)
            self.assertEqual(res["decision"], "stop", f"Failed on {p}")
            self.assertEqual(res["category"], "unknown_prompt", f"Failed on {p}")
            self.assertEqual(res["exit_code"], 3, f"Failed on {p}")

    def test_non_prompt_output_returns_wait(self):
        outputs = [
            "Compiling project... 42%",
            "Finished 12 tests in 0.05s\nOK",
            "Building wheel for package (pyproject.toml)...",
            "",
            "   \n  \n",
        ]
        for out in outputs:
            res = match_pane(out, self.ws, self.rules)
            self.assertEqual(res["decision"], "wait", f"Failed on {out}")
            self.assertEqual(res["category"], "no_prompt", f"Failed on {out}")
            self.assertIsNone(res["exit_code"])


class TestCLIEntrypoint(unittest.TestCase):
    """Test CLI invocation of drive_cli_rules.py."""

    def test_cli_allowed_prompt(self):
        ws = "/tmp/ws-exact"
        pane = f"Do you trust the files in this folder?\n{ws}\n[y/n] "
        p = subprocess.run(
            [sys.executable, str(ROOT / "scripts/drive_cli_rules.py"), "--workspace", ws],
            input=pane,
            text=True,
            capture_output=True,
        )
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertEqual(data["decision"], "answer")
        self.assertEqual(data["rule_id"], "folder_trust")

    def test_cli_never_prompt(self):
        ws = "/tmp/ws-exact"
        pane = "Allow git push origin main? [y/n]"
        p = subprocess.run(
            [sys.executable, str(ROOT / "scripts/drive_cli_rules.py"), "--workspace", ws],
            input=pane,
            text=True,
            capture_output=True,
        )
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertEqual(data["decision"], "stop")
        self.assertEqual(data["category"], "never")
        self.assertEqual(data["rule_id"], "push_network_install")
        self.assertEqual(data["exit_code"], 3)

    def test_cli_bad_workspace_exits_2(self):
        p = subprocess.run(
            [sys.executable, str(ROOT / "scripts/drive_cli_rules.py"), "--workspace", "bad/rel/path"],
            input="some text",
            text=True,
            capture_output=True,
        )
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
