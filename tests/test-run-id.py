import contextlib
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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

    def test_slice_two_modules_share_one_rule(self):
        verification_record = importlib.import_module("verification_record")
        seat_smoke = importlib.import_module("seat_smoke")
        self.assertIs(verification_record.validate_run_id, self.run_id.validate_run_id)
        self.assertIs(seat_smoke.validate_run_id, self.run_id.validate_run_id)
        self.assertFalse(hasattr(verification_record, "UUID"))
        good = "0b6f1c2e-9a4d-4c3b-8f2e-1d2c3b4a5f60"
        nil = "00000000-0000-0000-0000-000000000000"
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "seat.out"
            out.write_text(f"spawn-worker: worker=codex run_id={good} log=x\n")
            self.assertEqual(seat_smoke.run_id_of(out), good)
            out.write_text(f"spawn-worker: worker=codex run_id={nil} log=x\n")
            self.assertIsNone(seat_smoke.run_id_of(out))
            out.write_text(f"spawn-worker: worker=codex run_id={good.upper()} log=x\n")
            self.assertIsNone(seat_smoke.run_id_of(out))
            out.write_text(f"spawn-brain: action=a run_id={good} log=x\n")
            self.assertEqual(seat_smoke.brain_run_id_of(out), good)
            out.write_text(f"spawn-brain: action=a run_id={nil} log=x\n")
            self.assertIsNone(seat_smoke.brain_run_id_of(out))
            out.write_text(f"spawn-brain: action=a run_id={good.upper()} log=x\n")
            self.assertIsNone(seat_smoke.brain_run_id_of(out))

    def test_no_script_parses_run_ids_itself(self):
        tokens = ("uuid.UUID(", "[1-8]", "[89ab]", "{36}", "{8}-")
        allowed = {("observe_output.py", "{8}-"): 1}
        for path in sorted((ROOT / "scripts").iterdir()):
            if path.suffix not in (".py", ".sh") or path.name == "run_id.py":
                continue
            text = path.read_text(encoding="utf-8")
            for token in tokens:
                count = text.count(token)
                expected = allowed.get((path.name, token), 0)
                self.assertEqual(count, expected, (path.name, token))


GOOD = "0b6f1c2e-9a4d-4c3b-8f2e-1d2c3b4a5f60"
OTHER = "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f"
HOSTILE = ("../../../../tmp/x", "*", "a/b", GOOD.upper(), GOOD + "\n", "")
SHA = "0" * 64
RUN_ID_MSG = "run_id must be a canonical RFC UUID"


class RunIdPathRefusalTests(unittest.TestCase):
    def _mission_tree(self, base):
        mission = base / "docs/missions/20990101-x"
        (mission / "verification").mkdir(parents=True)
        for name in (OTHER + ".json", OTHER + ".2.json"):
            (mission / "verification" / name).write_text("{}")
        (base / "tmp").mkdir()
        (base / "tmp/x.json").write_text("{}")
        return mission

    def test_library_refuses_before_any_path_use(self):
        verification_record = importlib.import_module("verification_record")
        seen = []

        def spy(name):
            real = getattr(Path, name)

            def wrapper(self, *a, **k):
                seen.append((name, str(self)))
                return real(self, *a, **k)

            return mock.patch.object(Path, name, wrapper)

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp).resolve()
            mission = self._mission_tree(t)
            patches = [spy(n) for n in ("exists", "is_symlink", "is_dir", "is_file",
                                        "glob", "iterdir", "read_bytes", "read_text")]
            with contextlib.ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                for value in HOSTILE + (None,):
                    for call, args in (
                        (verification_record.verify, (t, mission, value)),
                        (verification_record.accept, (t, mission, value, SHA, "o")),
                        (verification_record.run_records, (mission, value)),
                    ):
                        seen.clear()
                        with self.assertRaises(verification_record.VerificationError) as caught:
                            call(*args)
                        self.assertEqual(str(caught.exception), RUN_ID_MSG,
                                         (call.__name__, repr(value)))
                        self.assertEqual(seen, [], (call.__name__, repr(value), seen[:3]))

    def test_clis_refuse_hostile_run_ids_with_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp).resolve()
            shutil.copytree(ROOT / "scripts", t / "scripts",
                            ignore=shutil.ignore_patterns("__pycache__"))
            mission = self._mission_tree(t)
            subprocess.run(["git", "init", "-q", str(t)], check=True)
            env = {k: v for k, v in os.environ.items() if k != "PURRFECT_DISPATCH_LOCK_PATH"}
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            m = "docs/missions/20990101-x"
            shell_err = "ERROR: run_id must be a canonical UUID\n"
            py_err = "VERIFY FAIL: run_id must be a canonical RFC UUID\n"
            for value in HOSTILE:
                cases = (
                    (["bash", "scripts/verify-mission.sh", "--run-id", value, m], shell_err),
                    (["bash", "scripts/accept-feature.sh", "--run-id", value,
                      "--verification-sha256", SHA, "--accepted-by", "o", m], shell_err),
                    ([sys.executable, "scripts/run_id.py", "check", value], shell_err),
                    ([sys.executable, "scripts/verification_record.py", "verify",
                      "--run-id", value, m], py_err),
                    ([sys.executable, "scripts/verification_record.py", "accept",
                      "--run-id", value, "--verification-sha256", SHA, "--accepted-by", "o", m], py_err),
                )
                for argv, err in cases:
                    done = subprocess.run(argv, cwd=t, env=env, capture_output=True, text=True,
                                          stdin=subprocess.DEVNULL)
                    self.assertEqual((done.returncode, done.stdout, done.stderr), (2, "", err),
                                     (argv[:3], repr(value), done.returncode, done.stderr[-300:]))
            done = subprocess.run([sys.executable, "scripts/run_id.py", "check", GOOD],
                                  cwd=t, env=env, capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
