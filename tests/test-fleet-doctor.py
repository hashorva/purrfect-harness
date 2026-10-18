#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "harness-registry.json").read_text())
DOCTOR = ROOT / "scripts/fleet-doctor.sh"
OUTPUTS = {
    "claude": "2.1.299 (Claude Code)",
    "codex": "codex-cli 0.162.0",
    "cursor": "2026.10.14-0f9edde",
    "agy": "1.3.5",
}
WRONG = "grok 1.0.52 (0920c8169e27) [stable]"


class FleetDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fleet-doctor-")
        self.root = Path(self.temp.name)
        self.first = self.root / "one"
        self.first.mkdir()
        self.second = self.root / "two"
        self.second.mkdir()
        self.brew = self.root / "homebrew-bin"
        self.brew.mkdir()
        self.usr_local = self.root / "usr-local-bin"
        self.usr_local.mkdir()
        for tool in ("git", "jq", "tmux", "shellcheck"):
            self.write_cli(self.brew, tool, "stub")
        (self.brew / "python3").symlink_to(sys.executable)
        for provider, data in REGISTRY["providers"].items():
            self.write_cli(self.first, data["binary"], OUTPUTS[provider])

    def tearDown(self):
        self.temp.cleanup()

    def write_cli(self, directory, binary, version, login_exit=0, login_output=""):
        path = directory / binary
        path.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            f"  --version) printf '%s\\n' {json.dumps(version)} ;;\n"
            f"  *) printf '%s' {json.dumps(login_output)}; exit {login_exit} ;;\n"
            "esac\n"
        )
        path.chmod(0o755)
        return path

    def run_doctor(self, *directories):
        path = ":".join([*(str(item) for item in directories), "/usr/bin", "/bin"])
        return subprocess.run(
            ["bash", str(DOCTOR)], text=True, capture_output=True,
            env={**os.environ, "PATH": path, "HARNESS_PATH_DIRS": f"{self.brew}:{self.usr_local}", "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_all_providers_healthy(self):
        result = self.run_doctor(self.first)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("ERROR", result.stdout)

    def test_different_codex_binaries_are_error(self):
        self.write_cli(self.second, "codex", OUTPUTS["codex"])
        result = self.run_doctor(self.first, self.second)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR codex:", result.stdout)

    def test_wrong_identity_is_error(self):
        self.write_cli(self.first, "cursor-agent", WRONG)
        result = self.run_doctor(self.first)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR cursor:", result.stdout)

    def test_login_failure_is_error(self):
        self.write_cli(self.first, "claude", OUTPUTS["claude"], login_exit=1)
        result = self.run_doctor(self.first)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR claude:", result.stdout)

    def test_repeated_directory_warns(self):
        result = self.run_doctor(self.first, self.first)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARN claude: duplicate PATH", result.stdout)

    def test_symlink_to_same_binary_warns(self):
        (self.second / "codex").symlink_to(self.first / "codex")
        result = self.run_doctor(self.first, self.second)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARN codex: duplicate PATH", result.stdout)

    def test_login_output_is_never_printed(self):
        self.write_cli(self.first, "cursor-agent", OUTPUTS["cursor"], login_output="private-marker")
        result = self.run_doctor(self.first)
        self.assertNotIn("private-marker", result.stdout + result.stderr)

    def test_identity_patterns_are_distinct_and_match_recorded_lines(self):
        identities = {**OUTPUTS, "grok": WRONG}
        for provider, data in REGISTRY["providers"].items():
            pattern = data["identity_pattern"]
            self.assertRegex(OUTPUTS[provider], pattern)
            for other, output in identities.items():
                if other != provider:
                    self.assertNotRegex(output, pattern, f"{provider} matched {other}")

    def test_harness_path_prepends_once_without_duplicates_and_under_set_u(self):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("HARNESS_PATH_DIRS", None)
        once = subprocess.check_output(
            ["bash", "-c", "set -euo pipefail; PATH=/usr/bin:/bin; . scripts/harness-path.sh; . scripts/harness-path.sh; printf '%s' \"$PATH\""],
            cwd=ROOT, env=env, text=True,
        ).split(":")
        expected = [item for item in ("/opt/homebrew/bin", "/usr/local/bin") if Path(item).is_dir()]
        self.assertEqual(once[:len(expected)], expected)
        self.assertTrue(all(once.count(item) == 1 for item in expected), once)
        duplicate = subprocess.check_output(
            ["bash", "-c", "set -euo pipefail; PATH=/opt/homebrew/bin:/x:/opt/homebrew/bin:/usr/local/bin:/y:/usr/local/bin; . scripts/harness-path.sh; printf '%s' \"$PATH\""],
            cwd=ROOT, env=env, text=True,
        )
        self.assertEqual(duplicate, "/opt/homebrew/bin:/x:/usr/local/bin:/y")
        unset = subprocess.check_output(
            ["bash", "-c", "set -euo pipefail; unset PATH; . scripts/harness-path.sh; printf '%s' \"$PATH\""],
            cwd=ROOT, env=env, text=True,
        )
        self.assertTrue(unset)
        missing_env = {**env, "HARNESS_PATH_DIRS": "/missing/path"}
        missing = subprocess.check_output(
            ["bash", "-c", "set -euo pipefail; PATH=/usr/bin:/bin; . scripts/harness-path.sh; printf '%s' \"$PATH\""],
            cwd=ROOT, env=missing_env, text=True,
        )
        self.assertEqual(missing, "/usr/bin:/bin")
        for relative in (
            "scripts/spawn-worker.sh", "scripts/spawn-brain.sh", "scripts/fleet-doctor.sh",
            "tests/test-drive-cli.sh", "tests/run-tests.sh",
        ):
            self.assertIn("harness-path.sh", (ROOT / relative).read_text())

    def test_gate0_requires_git_python3_tmux_jq_and_shellcheck(self):
        env = {
            "PATH": str(self.brew), "HARNESS_PATH_DIRS": f"{self.brew}:{self.usr_local}",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        passed = subprocess.run(["/bin/bash", str(DOCTOR)], cwd=ROOT, env=env, text=True, capture_output=True)
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        for tool in ("git", "python3", "tmux", "jq", "shellcheck"):
            target = self.brew / tool
            content = target.read_bytes() if not target.is_symlink() else None
            target.unlink()
            failed = subprocess.run(["/bin/bash", str(DOCTOR)], cwd=ROOT, env=env, text=True, capture_output=True)
            if content is None:
                target.symlink_to(sys.executable)
            else:
                target.write_bytes(content)
                target.chmod(0o755)
            self.assertNotEqual(failed.returncode, 0, tool)
            self.assertIn(f"ERROR {tool}:", failed.stdout + failed.stderr)
            for present in (set(("git", "python3", "tmux", "jq", "shellcheck")) - {tool}):
                self.assertNotIn(f"ERROR {present}:", failed.stdout + failed.stderr)


if __name__ == "__main__":
    unittest.main()
