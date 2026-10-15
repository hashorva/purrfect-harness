#!/usr/bin/env python3
"""Reconstruction reports complete evidence and names every missing artifact."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import reconstruct_run

RUN = "01234567-89ab-42cd-8ef0-0123456789ab"


class ReconstructTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.mission = self.root / "docs/missions/example"
        self.mission.mkdir(parents=True)
        for directory in (".tasks/specs", ".tasks/receipts", ".tasks/ledger", "docs/missions/example/verification"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        for path in (self.root / ".tasks/specs" / f"{RUN}.json",
                     self.root / ".tasks/receipts" / f"{RUN}.json",
                     self.mission / "verification" / f"{RUN}.json"):
            path.write_text("{}\n", encoding="utf-8")
        (self.root / ".tasks/ledger" / f"{RUN}.json").write_text(
            json.dumps({"run_id": RUN}), encoding="utf-8")
        self.cwd = os.getcwd()
        os.chdir(self.root)
        self.patches = [
            patch.object(reconstruct_run.execution_spec, "load_persisted", return_value=({
                "run_id": RUN, "mission": "docs/missions/example", "provider": "codex",
                "model": "gpt-fixture", "effort": "medium", "speed": "standard"}, b"spec")),
            patch.object(reconstruct_run.execution_receipt, "load_receipt", return_value={
                "run_id": RUN, "mission": "docs/missions/example", "outcome": "completed",
                "exit_code": 0, "commits": [], "observation": {"observed_model": {"value": "gpt-fixture", "source": "observed"}}}),
            patch.object(reconstruct_run.verification_record, "load_record", return_value=({"run_id": RUN, "result": "pass"}, b"record")),
            patch.object(reconstruct_run.ledger, "validate_row", return_value=None),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        os.chdir(self.cwd)
        self.temp.cleanup()

    def invoke(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = reconstruct_run.main(["docs/missions/example", RUN])
        return result, output.getvalue()

    def test_complete_fixture_exits_zero(self):
        code, output = self.invoke()
        self.assertEqual(code, 0, output)
        for item in ("seat: codex / gpt-fixture", "receipt: completed", "VerificationRecord", "ledger:"):
            self.assertIn(item, output)

    def test_each_missing_artifact_exits_one_and_names_it(self):
        cases = ((".tasks/specs", "spec"), (".tasks/receipts", "receipt"),
                 ("docs/missions/example/verification", "VerificationRecord"),
                 (".tasks/ledger", "ledger row"))
        for directory, name in cases:
            with self.subTest(name=name):
                path = self.root / directory / f"{RUN}.json"
                path.unlink()
                code, output = self.invoke()
                self.assertEqual(code, 1, output)
                self.assertIn(f"MISSING {RUN}: {name}", output)
                path.write_text(json.dumps({"run_id": RUN}) if directory == ".tasks/ledger" else "{}\n",
                                encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
