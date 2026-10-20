#!/usr/bin/env python3
"""git_safe is the only git argv prefix, so gc, maintenance and hooks stay off."""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import git_safe

# T-078 converts these. Until then the scanner skips them.
NOT_YET = {
    "check-golden-argv.py",
    "dispatch_policy.py",
    "execution_receipt.py",
    "execution_runner.py",
    "ledger.py",
    "harness-manifest.py",
    "execution_spec.py",
}


def raw_git_lines(path):
    """Line numbers of list or tuple literals whose first element is the string git."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.List, ast.Tuple))
        and node.elts
        and isinstance(node.elts[0], ast.Constant)
        and node.elts[0].value == "git"
    ]


class GitSafe(unittest.TestCase):
    def test_helper_prefix(self):
        """The helper argv starts with gc, maintenance and hooks disabled."""
        self.assertEqual(
            git_safe.GIT,
            ("git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "core.hooksPath=/dev/null"),
        )
        self.assertEqual(git_safe.argv("-C", "x", "status"), [*git_safe.GIT, "-C", "x", "status"])

    def test_no_raw_git_argv_in_scripts(self):
        """A scripts/*.py list or tuple that starts with git bypasses the helper."""
        bad = {}
        for path in sorted((ROOT / "scripts").glob("*.py")):
            if path.name == "git_safe.py" or path.name in NOT_YET:
                continue
            lines = raw_git_lines(path)
            if lines:
                bad[path.name] = lines
        self.assertEqual(bad, {})


if __name__ == "__main__":
    unittest.main()
