#!/usr/bin/env python3
"""Tests for CI workflow matrix and test suite Python header."""
import platform, re, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_YML = ROOT / ".github/workflows/ci.yml"
RUN_TESTS = ROOT / "tests/run-tests.sh"


class CiWorkflow(unittest.TestCase):
    def test_matrix_is_ubuntu_312_314_and_macos_314(self):
        lines = CI_YML.read_text(encoding="utf-8").splitlines()
        self.assertNotIn("        os: [ubuntu-latest, macos-latest]", lines)
        self.assertIn("        include:", lines)
        i = lines.index("        include:")
        rows, cur = [], None
        for line in lines[i + 1 :]:
            m = re.fullmatch(r"          - os: ([^ ]+)", line)
            if m:
                cur = {"os": m.group(1)}
                rows.append(cur)
                continue
            m = re.fullmatch(r'            python: "([^"]+)"', line)
            if m and cur is not None and "python" not in cur:
                cur["python"] = m.group(1)
                continue
            break
        self.assertEqual(
            sorted((r["os"], r.get("python")) for r in rows),
            [("macos-latest", "3.14"), ("ubuntu-latest", "3.12"), ("ubuntu-latest", "3.14")],
        )
        self.assertEqual(len(rows), 3)

    def test_setup_python_precedes_installs_and_pins_are_kept(self):
        lines = CI_YML.read_text(encoding="utf-8").splitlines()
        text = "\n".join(lines)

        def at(s):
            return min(k for k, l in enumerate(lines) if s in l)

        checkout_idx = at("actions/checkout@v4")
        setup_python_idx = at("actions/setup-python@v5")
        jsonschema_idx = at("pip install jsonschema")
        tmux_linux_idx = at("apt-get install -y tmux jq")
        tmux_macos_idx = at("brew install tmux jq")
        evidence_idx = at("python3 tests/test-evidence-2a.py")
        suite_idx = at("bash tests/run-tests.sh")

        self.assertLess(checkout_idx, setup_python_idx)
        self.assertLess(setup_python_idx, jsonschema_idx)
        self.assertLess(setup_python_idx, tmux_linux_idx)
        self.assertLess(setup_python_idx, tmux_macos_idx)
        self.assertLess(setup_python_idx, evidence_idx)
        self.assertLess(setup_python_idx, suite_idx)

        self.assertIn("          python-version: ${{ matrix.python }}", lines)
        self.assertIn("          fetch-depth: 0", lines)
        self.assertIn('  SHELLCHECK_VERSION: "0.11.0"', lines)
        self.assertIn("shellcheck-v${SHELLCHECK_VERSION}.linux.x86_64.tar.xz", text)
        self.assertIn("brew install shellcheck", text)
        self.assertIn("      - name: Suite runs the matrix Python", lines)
        self.assertIn(". scripts/harness-path.sh", text)
        self.assertIn("sys.version_info[:2]", text)
        self.assertIn('${{ matrix.python }}"', text)

    def test_suite_header_prints_python_version(self):
        lines = RUN_TESTS.read_text(encoding="utf-8").splitlines()
        first_20 = lines[:20]
        hdr = [l for l in first_20 if l.startswith('echo "== python ')]
        expected = "echo \"== python $(python3 -c 'import platform; print(platform.python_version())')\""
        self.assertEqual(hdr, [expected])
        res = subprocess.run(["bash", "-c", hdr[0]], capture_output=True, text=True, check=True)
        self.assertEqual(res.stdout, f"== python {platform.python_version()}\n")


if __name__ == "__main__":
    unittest.main()
