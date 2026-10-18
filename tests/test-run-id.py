import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class RunIdTests(unittest.TestCase):
    def setUp(self):
        self.run_id = importlib.import_module("run_id")

    def test_canonical_run_ids_pass(self):
        values = (str(uuid.uuid1()), str(uuid.uuid4()),
                  "0b6f1c2e-9a4d-7c3b-af2e-1d2c3b4a5f60",
                  "0b6f1c2e-9a4d-8c3b-bf2e-1d2c3b4a5f60")
        for value in values:
            self.assertEqual(self.run_id.validate_run_id(value), value)

    def test_weakest_invalid_values_are_refused_without_echo(self):
        good = "0b6f1c2e-9a4d-4c3b-8f2e-1d2c3b4a5f60"
        values = (None, 7, b"x", [], "", " " + good, good + "\n", good.upper(),
                  "{" + good + "}", "urn:uuid:" + good, good.replace("-", ""),
                  "00000000-0000-0000-0000-000000000000", good[:14] + "9" + good[15:],
                  good[:19] + "c" + good[20:], "../" + good, good[:35], "a" * 300)
        for value in values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError) as caught:
                    self.run_id.validate_run_id(value)
                self.assertEqual(str(caught.exception), "run_id must be a canonical UUID")
                if value is not None and value != [] and value != "":
                    echoed = value.decode() if isinstance(value, bytes) else str(value)
                    self.assertNotIn(echoed, str(caught.exception))

    def test_cli_modules_share_one_rule(self):
        for name in ("execution_spec", "ledger", "reconstruct_run"):
            self.assertIs(importlib.import_module(name).validate_run_id,
                          self.run_id.validate_run_id)
        self.assertIs(importlib.import_module("ledger").UUID_SHAPE, self.run_id.UUID_SHAPE)
        self.assertIs(importlib.import_module("model_id").MODEL_UUID_SHAPE, self.run_id.UUID_SHAPE)

    def test_reconstruct_refuses_nil_and_version_9_without_echo(self):
        script = ROOT / "scripts/reconstruct_run.py"
        ids = ("00000000-0000-0000-0000-000000000000",
               "0b6f1c2e-9a4d-9c3b-bf2e-1d2c3b4a5f60")
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "docs/missions/20990101-x").mkdir(parents=True)
            for value in ids:
                done = subprocess.run([sys.executable, str(script),
                                       "docs/missions/20990101-x", value], cwd=temp,
                                      capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                      env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                self.assertEqual((done.returncode, done.stderr),
                                 (2, "ERROR: reconstruct: invalid run id\n"))
                self.assertNotIn(value, done.stderr)


if __name__ == "__main__":
    unittest.main()
