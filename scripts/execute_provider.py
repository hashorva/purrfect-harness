#!/usr/bin/env python3
"""Translate one persisted ExecutionSpec into a provider argv and launch it safely."""
import argparse
import json
import subprocess
import sys

from execution_spec import SpecError, load_persisted


def provider_contract(spec):
    """Return argv and explicit environment overrides for one validated spec."""
    provider, model, effort, speed, repo, prompt = (
        spec["provider"], spec["model"], spec["effort"], spec["speed"], spec["repo"], spec["prompt"]
    )
    if provider == "codex":
        if effort not in {"low", "medium", "high", "xhigh"}:
            raise SpecError("codex does not support requested effort")
        if speed != "unknown":
            raise SpecError("codex speed must be unknown")
        argv = ["codex", "exec", "-C", repo, "-s", "workspace-write", "-m", model,
                "-c", f'model_reasoning_effort="{effort}"', prompt]
    elif provider == "claude":
        if effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise SpecError("claude does not support requested effort")
        if speed != "unknown":
            raise SpecError("claude speed must be unknown")
        argv = ["claude", "-p", prompt, "--model", model, "--effort", effort,
                "--allowedTools", "Read,Write,Edit,Bash"]
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
        resolved_model = f"{model}[effort={effort},fast={'true' if speed == 'fast' else 'false'}]"
        argv = ["agent", "-p", "--force", "--trust", "--workspace", repo, "--model", resolved_model, prompt]
    return argv, {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, help="persisted .tasks/specs/<run_id>.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        spec, _ = load_persisted(args.spec)
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
        return subprocess.run(argv, check=False).returncode
    except OSError as exc:
        print(f"ERROR: provider launch failed: {exc}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())
