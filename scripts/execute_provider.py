#!/usr/bin/env python3
"""Translate one persisted ExecutionSpec into a provider argv and launch it safely."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from execution_spec import SpecError, load_persisted


def provider_contract(spec):
    """Return argv and explicit environment overrides for one validated spec."""
    provider, model, effort, speed, repo, prompt = (
        spec["provider"], spec["model"], spec["effort"], spec["speed"], spec["repo"], spec["prompt"]
    )
    # v1/v2 predate the marker and therefore bind the historical contract 1.
    # Only a v3 authorization can select contract 2 or 3.
    contract_version = spec.get("provider_contract_version", 1)
    if provider == "codex":
        if effort not in {"low", "medium", "high", "xhigh"}:
            raise SpecError("codex does not support requested effort")
        if speed != "unknown":
            raise SpecError("codex speed must be unknown")
        codex_git_dir = (["--add-dir", str(Path(repo) / ".git")]
                         if contract_version >= 2 else [])
        # Contract 5+: the workspace-write sandbox refuses .agents/ unless it is mounted too (probe P-1).
        writes_agents = any(pattern.startswith(".agents/") for pattern in spec.get("write_scope", []))
        codex_agents_dir = (["--add-dir", str(Path(repo) / ".agents")]
                            if contract_version >= 5 and writes_agents else [])
        argv = ["codex", "exec"]
        if contract_version >= 6:
            argv.append("--json")
        argv.extend(["-C", repo, "-s", "workspace-write", *codex_git_dir, *codex_agents_dir, "-m", model,
                     "-c", f'model_reasoning_effort="{effort}"', prompt])
    elif provider == "claude":
        if effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise SpecError("claude does not support requested effort")
        if speed != "unknown":
            raise SpecError("claude speed must be unknown")
        argv = ["claude", "-p", prompt]
        # Contract 7: a stall watchdog needs output before the end;
        # an unattended run must not wait on an MCP server (--strict-mcp-config starts none).
        if contract_version >= 7:
            argv.extend(["--output-format", "stream-json", "--verbose", "--strict-mcp-config"])
        elif contract_version >= 6:
            argv.extend(["--output-format", "json"])
        argv.extend(["--model", model, "--effort", effort,
                     "--allowedTools", "Read,Write,Edit,Bash"])
    elif provider == "agy":
        if effort not in {"low", "medium", "high"}:
            raise SpecError("agy does not support requested effort")
        if speed != "unknown":
            raise SpecError("agy speed must be unknown")
        argv = ["agy", "--dangerously-skip-permissions", "--print-timeout", "30m", "--model", model,
                "--effort", effort, "-p", prompt]
    else:
        if effort not in {"low", "medium", "high", "xhigh"} or speed not in {"standard", "fast"}:
            raise SpecError("agent requires a supported explicit effort and speed")
        if "[" in model or "]" in model:
            raise SpecError("agent model must not already contain parameters")
        # Contract 4 sends only the model ID; models without name-encoded effort receive no effort argument.
        if contract_version >= 4:
            fast_model = model.endswith("-fast")
            if fast_model != (speed == "fast"):
                raise SpecError("cursor model -fast suffix and spec speed must agree")
            effort_match = re.search(r"-(none|minimal|low|medium|high|xhigh|max)(?:-fast)?$", model)
            if effort_match and effort_match.group(1) != effort:
                raise SpecError(f"cursor model name encodes effort {effort_match.group(1)}; spec effort is {effort}")
            resolved_model = model
        else:
            resolved_model = f"{model}[effort={effort},fast={'true' if speed == 'fast' else 'false'}]"
        # Contract 3+: Grok Build also installs a bare `agent`, so use Cursor's unambiguous CLI.
        cursor_cli = "cursor-agent" if contract_version >= 3 else "agent"
        argv = [cursor_cli, "-p", "--force", "--trust"]
        if contract_version >= 6:
            argv.extend(["--output-format", "stream-json"])
        argv.extend(["--workspace", repo, "--model", resolved_model, prompt])
    return argv, {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, help="persisted .tasks/specs/<run_id>.json")
    parser.add_argument("--sha256", required=True, help="exact SHA-256 returned by execution_spec persist")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9a-f]{64}", args.sha256):
            raise SpecError("sha256 must be a lowercase SHA-256 digest")
        spec, raw_bytes = load_persisted(args.spec)
        if hashlib.sha256(raw_bytes).hexdigest() != args.sha256:
            raise SpecError("persisted spec SHA-256 does not match authorization")
        argv, env_overrides = provider_contract(spec)
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps({"argv": argv, "env_overrides": env_overrides,
                          "observed": {"model": "unknown", "effort": "unknown", "speed": "unknown"}},
                         sort_keys=True, separators=(",", ":")))
        return 0
    try:
        return subprocess.run(argv, check=False, stdin=subprocess.DEVNULL).returncode
    except OSError as exc:
        print(f"ERROR: provider launch failed: {exc}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())
