#!/usr/bin/env python3
"""Rebuild committed 2A evidence and run the real require-workers mission audit."""
import hashlib, json, os, re, shutil, subprocess, tempfile, unittest
from pathlib import Path

ROOT, FIXTURE = Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[1] / "tests/fixtures/evidence-2a"
P = "@PURRFECT_ROOT@"
DENY = re.compile(r"/Users/|/home/|/private/var/|/var/folders/|@gmail[.]com|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16}|ghp_[A-Za-z0-9]{20}|github_pat_|AKIA[0-9A-Z]{16}|xox[abp]-|-----BEGIN")
ACC = {"35ecb39a-5c22-4108-acef-41f7fc694ad6", "fdf5dd38-1433-45eb-972b-823493f9e671", "02e9c769-5c85-4204-9d8e-9933f8c3f819"}


def cbytes(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sub(raw, root):
    return raw.replace(P.encode(), root.encode())


class Evidence2A(unittest.TestCase):
    def materialise(self, mutation=None):
        if subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True).stdout.strip() == "true":
            self.fail("full Git history required; CI checkout needs fetch-depth: 0")
        tmp = Path(tempfile.mkdtemp()).resolve(); self.addCleanup(shutil.rmtree, tmp)
        repo = tmp / "repo"
        subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(repo)], check=True)
        shutil.copytree(ROOT / "scripts", repo / "scripts", ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
        if mutation:
            src = (repo / "scripts/execute_provider.py").read_text(encoding="utf-8")
            self.assertEqual(src.count(mutation[0]), 1)
            (repo / "scripts/execute_provider.py").write_text(src.replace(*mutation), encoding="utf-8")
        manifest = json.loads((FIXTURE / "MANIFEST.json").read_text(encoding="utf-8"))
        mission, root_s = repo / manifest["mission"], str(repo.resolve())
        mission.mkdir(parents=True, exist_ok=True)
        for run in manifest["runs"]:
            rid = run["run_id"]
            spec_raw = sub((FIXTURE / "specs" / f"{rid}.json").read_bytes(), root_s)
            receipt = json.loads(sub((FIXTURE / "receipts" / f"{rid}.json").read_bytes(), root_s))
            argv = json.loads(sub((FIXTURE / "argv" / f"{rid}.json").read_bytes(), root_s))
            (repo / ".tasks/specs").mkdir(parents=True, exist_ok=True)
            (repo / ".tasks/specs" / f"{rid}.json").write_bytes(spec_raw)
            receipt["execution_spec_sha256"] = hashlib.sha256(spec_raw).hexdigest()
            receipt["resolved_configuration"]["argv_sha256"] = hashlib.sha256((json.dumps(argv, ensure_ascii=False, separators=(",", ":")) + "\n").encode()).hexdigest()
            rbytes = cbytes(receipt)
            (repo / ".tasks/receipts").mkdir(parents=True, exist_ok=True)
            (repo / ".tasks/receipts" / f"{rid}.json").write_bytes(rbytes)
            (repo / ".tasks/logs").mkdir(parents=True, exist_ok=True)
            (repo / f".tasks/logs/{rid}.log").write_bytes(b"")
            prot = FIXTURE / "protected" / f"{rid}.protected"
            if prot.is_file():
                (repo / f".tasks/specs/{rid}.protected").write_bytes(sub(prot.read_bytes(), root_s))
            if run["accepted_record"]:
                record = json.loads(sub((FIXTURE / "verification" / run["accepted_record"]).read_bytes(), root_s))
                record["execution_spec"]["sha256"] = hashlib.sha256(spec_raw).hexdigest()
                record["execution_receipt"]["sha256"] = hashlib.sha256(rbytes).hexdigest()
                (mission / "verification").mkdir(parents=True, exist_ok=True)
                (mission / "verification" / run["accepted_record"]).write_bytes(cbytes(record))
        features = json.loads((FIXTURE / "features.json").read_text(encoding="utf-8"))
        for feat in features["features"]:
            rec = mission / "verification" / next(r["accepted_record"] for r in manifest["runs"] if r["run_id"] == feat["accepted_run_id"])
            feat["accepted_verification_sha256"] = hashlib.sha256(rec.read_bytes()).hexdigest()
        (mission / "features.json").write_bytes(cbytes(features))
        return repo

    def audit(self, root):
        return subprocess.run(["bash", "scripts/verify-mission.sh", "--require-workers", "docs/missions/20261014-2a-foundation"],
                              cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)

    def test_committed_2a_evidence_passes_require_workers_audit(self):
        done = self.audit(self.materialise())
        self.assertEqual(done.returncode, 0, f"stdout:\n{done.stdout}\nstderr:\n{done.stderr}")

    def test_adapter_argv_change_breaks_old_receipts(self):
        done = self.audit(self.materialise(mutation=('"-s", "workspace-write"', '"-s", "read-only"')))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("does not match shared adapter evidence", done.stderr + done.stdout)

    def test_fixture_is_scrubbed_and_covers_providers_and_contracts(self):
        runs = json.loads((FIXTURE / "MANIFEST.json").read_text(encoding="utf-8"))["runs"]
        ids = {r["run_id"] for r in runs}
        self.assertEqual(ids & ACC, ACC)
        self.assertIn("f87755da-6925-41a0-80e8-bf7ee4d78002", ids)
        self.assertTrue(any(r["role"] == "brain" for r in runs))
        prov, contracts = {r["provider"] for r in runs}, {r["contract"] for r in runs}
        self.assertTrue({"codex", "claude", "agent"} <= prov and 9 in contracts and len(contracts) >= 3)
        self.assertTrue(any(r["argv_form"] == "historical-pre-T-071" for r in runs))
        for path in FIXTURE.rglob("*"):
            if path.is_file():
                self.assertNotIn(".tasks", path.parts); self.assertNotEqual(path.suffix, ".log")
                self.assertIsNone(DENY.search(path.read_text(encoding="utf-8")), path)
        for run in runs:
            rid = run["run_id"]
            spec, rcpt = json.loads((FIXTURE / f"specs/{rid}.json").read_text()), json.loads((FIXTURE / f"receipts/{rid}.json").read_text())
            self.assertEqual(spec["repo"], rcpt["repo"], P)
            self.assertEqual(rcpt["execution_spec_path"], f"{P}/.tasks/specs/{rid}.json")

    def test_ledger_rows_validate_and_match_receipts(self):
        lines = [ln for ln in (FIXTURE / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 2)
        live = set((ROOT / "docs/missions/ledger.jsonl").read_text(encoding="utf-8").splitlines())
        manifest = {r["run_id"]: r for r in json.loads((FIXTURE / "MANIFEST.json").read_text())["runs"]}
        for line in lines:
            self.assertIn(line, live)
            with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
                handle.write(line + "\n"); handle.flush()
                ok = subprocess.run(["python3", "scripts/ledger.py", "validate", handle.name], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(ok.returncode, 0, ok.stderr + ok.stdout)
        for row in map(json.loads, lines):
            self.assertIn(row["run_id"], manifest)
            rcpt = json.loads((FIXTURE / f"receipts/{row['run_id']}.json").read_text(encoding="utf-8"))
            if manifest[row["run_id"]]["role"] == "brain":
                self.assertEqual(row["task"], "review")
            else:
                self.assertEqual((row["feature"], row["task"]), (rcpt["feature"], rcpt["work_unit"]))


if __name__ == "__main__":
    unittest.main()
