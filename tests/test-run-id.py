import ast
import contextlib
import importlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SAMPLE = "0b6f1c2e-9a4d-4c3b-8f2e-1d2c3b4a5f60"
EXEMPT_NAMES = {("observe_output.py", "CODEX_THREAD_ID_RE")}  # Codex thread id: a provider id, not a run id

def uuid_shaped(pattern):
    """True when pattern finds a UUID's hex-and-dash shape but not the same shape in non-hex letters."""
    attempts = [pattern]
    if "\\" in pattern:
        attempts.append(pattern.replace("\\-", "-"))

    def finds(rx, sample):
        return any(sample[:13] in m.group(0) for text in (sample, f"x {sample} x") for m in rx.finditer(text))

    for attempt in attempts:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                rx = re.compile(attempt)
            except (re.error, RecursionError, OverflowError, ValueError):
                continue
        if any(finds(rx, s) and not finds(rx, re.sub("[0-9A-Fa-f]", g, s))
               for s, g in ((SAMPLE, "g"), (SAMPLE.upper(), "G"))):
            return True
    return False


def fold(node, env):
    """The string value of a constant, a known name, a + concatenation or an f-string; else None."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = fold(node.left, env), fold(node.right, env)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        parts = [fold(v.value if isinstance(v, ast.FormattedValue) else v, env) for v in node.values]
        return None if None in parts else "".join(parts)
    return None


def python_findings(rel, text):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    found, env, modules, skip = [], {}, set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = fold(node.value, env)
            if value is not None:
                env[node.targets[0].id] = value
            if (rel, node.targets[0].id) in EXEMPT_NAMES:
                skip.update(id(n) for n in ast.walk(node.value))
        elif isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names if a.name.split(".")[0] == "uuid")
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "uuid":
            found += [(rel, "imports uuid." + a.name) for a in node.names if a.name != "uuid4"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in modules and node.attr != "uuid4":
            found.append((rel, "uses uuid." + node.attr))
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            if name == "UUID":
                found.append((rel, "calls UUID("))
            elif name in ("__import__", "import_module") and node.args and fold(node.args[0], env) == "uuid":
                found.append((rel, "imports uuid dynamically"))
        elif isinstance(node, (ast.Constant, ast.BinOp, ast.JoinedStr)) and id(node) not in skip:
            value = fold(node, env)
            if value == "UUID":
                found.append((rel, "names UUID"))
            elif value and uuid_shaped(value):
                found.append((rel, "UUID-shaped pattern"))
    return found


def shell_findings(rel, text):
    found = []
    if re.search(r"uuid\.(?!uuid4\b)|UUID\(|from uuid import|\{8\}\\?-", text):
        found.append((rel, "uuid parser text"))
    quoted = re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"", text)
    candidates = {a or b for a, b in quoted} | {w.strip("'\"") for w in text.split()}
    if any(uuid_shaped(c) for c in candidates if c):
        found.append((rel, "UUID-shaped pattern"))
    return found


def private_run_id_parsers(scripts):
    """(path relative to scripts/, reason) for every private run-id parser; never file content."""
    found = []
    for path in sorted(p for p in scripts.rglob("*") if p.suffix in (".py", ".sh") and "__pycache__" not in p.parts):
        rel = path.relative_to(scripts).as_posix()
        if rel != "run_id.py":
            text = path.read_text(encoding="utf-8")
            found += python_findings(rel, text) if path.suffix == ".py" else shell_findings(rel, text)
    return found


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
        self.assertEqual(private_run_id_parsers(ROOT / "scripts"), [])

    def test_scanner_catches_known_bypasses(self):
        n = "\n"
        h = "[0-9a-f]"
        dashed = h + "{8}-" + h + "{4}-" + h + "{4}-" + h + "{4}-" + h + "{12}"
        bypass = {
            "bypass_import.py": "from uuid import UUID" + n + "def ok(value):" + n + "    return UUID(value).version in range(1, 9)" + n,
            "bypass_alias.py": "import uuid as u" + n + "def ok(value):" + n + "    return u.UUID(value).int != 0" + n,
            "bypass_getattr.py": "import uuid" + n + 'PARSE = getattr(uuid, "UUID")' + n,
            "bypass_escaped.py": "import re" + n + "RID = re.compile(" + repr(dashed.replace("-", "\\-")) + ")" + n,
            "bypass_concat.py": "import re" + n + "HEXC = " + repr(h) + n + "RID = re.compile(HEXC + " + repr("{8}-") + " + HEXC + " + repr("{4}-") + " + HEXC + " + repr("{4}") + ")" + n,
            "bypass_fstring.py": "import re" + n + "HEXC = " + repr(h) + n + "RID = re.compile(f" + repr("{HEXC}{{8}}-{HEXC}{{4}}-{HEXC}{{4}}") + ")" + n,
            "lib/ids.py": "import re" + n + "RID = re.compile(" + repr("^" + "[0-9A-F]{8}-[0-9A-F]{4}-[1-8][0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$") + ")" + n,
            "lib/run_id.py": "import re" + n + "RID = re.compile(" + repr(dashed) + ")" + n,
            "observe_output.py": (ROOT / "scripts/observe_output.py").read_text().replace("CODEX_THREAD_ID_RE", "THREAD_RE"),
            "bypass.sh": "#!/usr/bin/env bash" + n + "grep -Eq '^" + dashed.replace("-", "\\-") + "' <<<\"$1\"" + n,
            "bypass_xdigit.sh": "#!/usr/bin/env bash" + n + "grep -Eq '[[:xdigit:]]{8}-[[:xdigit:]]{4}' <<<x" + n,
        }
        allowed = {
            "gen_ok.py": "import re, uuid" + n + "TOKEN = str(uuid.uuid4())" + n + "LOC = re.compile(" + repr("run_id=(\\S+)") + ")" + n + "SHA = re.compile(" + repr(h + "{64}") + ")" + n,
            "gen_ok.sh": "#!/usr/bin/env bash" + n + "RUN_ID=\"$(python3 -c 'import uuid; print(uuid.uuid4())')\"" + n,
            "observe_output.py": (ROOT / "scripts/observe_output.py").read_text(),
        }
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            for rel, text in allowed.items():
                p = scripts / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
                self.assertEqual(private_run_id_parsers(scripts), [], rel)
            for rel, text in bypass.items():
                with tempfile.TemporaryDirectory() as case_tmp:
                    case_scripts = Path(case_tmp) / "scripts"
                    case_scripts.mkdir()
                    p = case_scripts / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(text)
                    findings = private_run_id_parsers(case_scripts)
                    self.assertTrue(findings, rel)
                    self.assertEqual(findings[0][0], rel, (rel, findings))


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
