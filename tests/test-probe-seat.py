#!/usr/bin/env python3
"""End-to-end fixtures for the one-seat probe; no real provider is invoked."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from execute_provider import provider_contract
from execution_spec import CURRENT_PROVIDER_CONTRACT


FAKE = r'''#!__PYTHON__
import json, os, sys, time
name = os.path.basename(sys.argv[0])
if sys.argv[1:] == ["mcp", "list"]:
    print("Checking MCP server health...")
    print("alpha: https://private.example/?token=S1 - Connected")
    print("beta: npx private --key S2 - Failed")
    raise SystemExit(0)
mode = os.environ.get("PROBE_MODE", "ok")
if mode == "hang": time.sleep(10)
if mode == "mcp-init-wait": print("MCP server alpha: starting...", file=sys.stderr); time.sleep(10)
if mode == "permission-wait": print("Allow this command to run? [y/n]", file=sys.stderr); time.sleep(10)
if mode == "input-wait": print("waiting for input on stdin", file=sys.stderr); time.sleep(10)
if mode == "auth": print("Error: not logged in", file=sys.stderr); raise SystemExit(1)
if mode == "limit": print("You have hit your usage limit.", file=sys.stderr); raise SystemExit(1)
if name == "claude":
    event = {"type":"result", "num_turns": 0 if mode == "no-turn" else 1, "result":"OK", "usage":{"input_tokens":3,"output_tokens":1}}
    print(json.dumps(event))
elif name == "codex":
    if mode == "no-turn": print(json.dumps({"type":"thread.started"}))
    else: print(json.dumps({"type":"turn.completed", "usage":{"input_tokens":3,"output_tokens":1,"cached_input_tokens":0,"reasoning_output_tokens":0}})); print("OK")
elif name == "cursor-agent":
    if mode == "no-turn": print(json.dumps({"type":"result", "result":"OK", "usage":{"inputTokens":0,"outputTokens":0}}))
    else: print(json.dumps({"type":"system", "subtype":"init", "model":"grok"})); print(json.dumps({"type":"result", "result":"OK", "usage":{"inputTokens":3,"outputTokens":1}})); print("OK")
else: print("OK")
'''


class ProbeSeatTest(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="probe-seat-test-"))
        self.bin = self.temp / "bin"
        self.bin.mkdir()
        for name in ("claude", "codex", "cursor-agent", "agy"):
            path = self.bin / name
            path.write_text(FAKE.replace("__PYTHON__", sys.executable))
            path.chmod(0o755)
        self.out = self.temp / "out"
        seats = {
            "claude.test": ["claude", "sonnet", "medium", "unknown"],
            "codex.test": ["codex", "gpt-6", "medium", "unknown"],
            "cursor.test": ["cursor", "grok-high", "high", "standard"],
            "agy.test": ["agy", "gemini-medium", "medium", "unknown"],
        }
        self.fleet = self.temp / "fleet.json"
        self.fleet.write_text(json.dumps({"seats": {key: {"provider": value[0], "model": value[1],
            "effort": value[2], "speed": value[3]} for key, value in seats.items()}}))

    def tearDown(self):
        shutil.rmtree(self.temp)

    def run_probe(self, seat, mode="ok", timeout=2, wrapper=False):
        env = dict(os.environ, PATH=f"{self.bin}:/usr/bin:/bin", PROBE_MODE=mode, PYTHONDONTWRITEBYTECODE="1")
        executable = ["bash", str(SCRIPTS / "probe-seat.sh")] if wrapper else [sys.executable, str(SCRIPTS / "probe_seat.py")]
        return subprocess.run(executable + [seat, "--fleet", str(self.fleet), "--out-root", str(self.out), "--timeout", str(timeout)],
                              text=True, capture_output=True, env=env, check=False)

    def one(self, seat, mode, expected, timeout=2):
        original_out = self.out
        self.out = original_out / f"{seat}-{mode}"
        result = self.run_probe(seat, mode, timeout)
        self.assertEqual(result.returncode, 0 if expected == "ok" else 1, result.stderr)
        folder = next(self.out.glob(f"*-{seat}"))
        for name in ("command.json", "stdout.txt", "stderr.txt", "events.jsonl", "mcp.json", "result.json"):
            self.assertTrue((folder / name).is_file(), name)
        saved = "\n".join(path.read_text() for path in folder.iterdir())
        self.assertNotIn("S1", saved)
        self.assertNotIn("private.example", saved)
        self.assertNotIn("npx private", saved)
        self.assertEqual(json.loads((folder / "mcp.json").read_text())["names"], ["alpha", "beta"])
        self.assertEqual(json.loads((folder / "result.json").read_text())["class"], expected)
        self.assertEqual("search the CLI's GitHub issues for the exact symptom first" in result.stderr, expected != "ok")
        command = json.loads((folder / "command.json").read_text())
        self.assertNotEqual(Path(command["folder"]).resolve(), ROOT.resolve())
        self.assertTrue((Path(command["folder"]) / ".git").is_dir())
        expected, _ = provider_contract({"provider": {"cursor": "agent"}.get(seat.split(".")[0], seat.split(".")[0]),
            "model": {"claude": "sonnet", "codex": "gpt-6", "cursor": "grok-high", "agy": "gemini-medium"}[seat.split(".")[0]],
            "effort": {"claude": "medium", "codex": "medium", "cursor": "high", "agy": "medium"}[seat.split(".")[0]],
            "speed": {"claude": "unknown", "codex": "unknown", "cursor": "standard", "agy": "unknown"}[seat.split(".")[0]],
            "repo": command["folder"], "prompt": "Reply with OK only.", "write_scope": [], "role": "worker",
            "provider_contract_version": CURRENT_PROVIDER_CONTRACT})
        self.assertEqual(command["argv"], expected)
        self.out = original_out

    def test_ok_all_clis(self):
        for seat in ("claude.test", "codex.test", "cursor.test", "agy.test"):
            with self.subTest(seat=seat): self.one(seat, "ok", "ok")

    def test_no_turn(self):
        for seat in ("claude.test", "codex.test", "cursor.test"):
            with self.subTest(seat=seat): self.one(seat, "no-turn", "no-turn")

    def test_waits_auth_and_limit(self):
        for mode, expected in (("mcp-init-wait", "mcp-init-wait"), ("permission-wait", "permission-wait"),
                               ("input-wait", "input-wait"), ("hang", "unknown"), ("auth", "auth"), ("limit", "limit")):
            with self.subTest(mode=mode): self.one("claude.test", mode, expected, 1 if "wait" in mode or mode == "hang" else 2)

    def test_mcp_names_rejects_hostile_mcp_list(self):
        hostile = "MCP_URL=https://user:password@evil.example/mcp?token=S1"
        mcp_lines = "\n".join(
            [
                "Checking MCP server health...",
                "claude.ai Claude Docs: https://api.example/v1/pages/mcp - Connected",
                "supabase: https://mcp.example/mcp (HTTP) - Pending approval",
                "Name          Command   Args   Env   Cwd   Status   Auth",
                "node_repl     /Applications/x/bin/node_repl   -   TOKEN=abc   -   enabled   Unsupported",
                hostile,
                "no MCP servers configured",
                "https://user:password@evil.example/x",
            ]
        )
        fake = FAKE.replace(
            '    print("Checking MCP server health...")\n'
            '    print("alpha: https://private.example/?token=S1 - Connected")\n'
            '    print("beta: npx private --key S2 - Failed")',
            "    print(" + repr(mcp_lines) + ")",
        )
        path = self.bin / "claude"
        path.write_text(fake.replace("__PYTHON__", sys.executable))
        path.chmod(0o755)
        result = self.run_probe("claude.test", "ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = next(self.out.glob("*-claude.test"))
        expected = ["claude.ai Claude Docs", "supabase", "node_repl"]
        self.assertEqual(json.loads((folder / "mcp.json").read_text())["names"], expected)
        blobs = [result.stdout, result.stderr]
        blobs.extend(path.read_text() for path in folder.iterdir())
        joined = "\n".join(blobs)
        for bad in ("password", "token=", "S1", "://"):
            self.assertNotIn(bad, joined, bad)

    def test_dry_run_and_bad_seats(self):
        result = self.run_probe("claude.test", wrapper=True)
        self.assertEqual(result.returncode, 0)
        shutil.rmtree(self.out)
        env = dict(os.environ, PATH=f"{self.bin}:/usr/bin:/bin", PYTHONDONTWRITEBYTECODE="1")
        dry = subprocess.run(["bash", str(SCRIPTS / "probe-seat.sh"), "claude.test", "--fleet", str(self.fleet),
                              "--out-root", str(self.out), "--dry-run"], text=True, capture_output=True, env=env)
        self.assertEqual(dry.returncode, 0)
        self.assertFalse(self.out.exists())
        for seat in ("missing.test", "../../bad"):
            bad = self.run_probe(seat)
            self.assertEqual(bad.returncode, 2)
            self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
