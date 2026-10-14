#!/usr/bin/env python3
import json
import os
import subprocess
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
            env={**os.environ, "PATH": path, "PYTHONDONTWRITEBYTECODE": "1"},
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


if __name__ == "__main__":
    unittest.main()
