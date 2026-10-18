#!/usr/bin/env python3
"""Print the planning prompt a Front Desk planning run starts from.

Usage: python3 scripts/brain_prompt.py planning <mission> --provider claude [--request PATH]
prints the planning prompt that a Front Desk planning run starts from.
"""
import argparse
import sys
from pathlib import Path

ROLES = {"mission-init": "planning", "planning": "planning", "gate0": "gate", "gate": "gate", "review": "review"}
BUDGETS = {"planning": 1000000, "gate": 1000000, "review": 400000}
PROVIDERS = ("claude", "codex", "agent", "agy")
GOALS = {
    "planning": ("The planning work this run was asked for is done. For mission-init: GOAL.md, features.json, "
                 "PROGRESS.md and tasks/T-001.md exist (templates in docs/missions/templates/) and the status stays "
                 "draft until Gate 0. For a task-planning request: each task file it names is written in the "
                 "mission's task format."),
    "gate": "The feature list and the fleet-inventory map are ready for the owner; no worker is dispatched.",
    "review": "A verdict on the worker's change, judged by its effects against the task's exit criteria.",
}
# Only Claude Code's committed --help capture (docs/missions/capabilities/claude.txt) shows subagents;
# no committed capture shows one for codex, cursor-agent or agy, so their prompts name none.
SUBAGENTS = ("Subagents: the explorer subagent (.claude/agents/explorer.md, model haiku) for wide reading and "
             "searching, and the read-only code-reviewer (.claude/agents/code-reviewer.md).")
NO_SUBAGENTS = "Subagents: none is named for this CLI, because no committed --help capture shows one."


def render(action, mission, provider, log_rel=None, request=None):
    """The brain prompt for one run: Goal, Resources, Budget and Acceptance checks."""
    if action not in ROLES:
        raise ValueError(f"unknown action {action!r}")
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}")
    role = ROLES[action]
    claude = provider == "claude"
    delegate = ("to the explorer subagent" if claude else
                "to a subagent only where your CLI offers one; otherwise read only the excerpts you need")
    log = f" Your log: {log_rel}." if log_rel else ""
    return "\n".join([
        f"You are the mission BRAIN for {mission}. Role: {role}.",
        "## Goal", GOALS[role],
        "## Resources",
        "Context: AGENTS.md, docs/missions/ORCHESTRATION.md, docs/missions/MODEL_ROUTING.md, the mission folder, "
        "and the repo skills in .agents/skills (mission-init, dispatch-worker). Tools: your CLI's native tools and "
        "web search. " + (SUBAGENTS if claude else NO_SUBAGENTS),
        "## Budget",
        f"{BUDGETS[role]} tokens for this run (input + output + cache read, your own total). Stay within it by "
        f"delegating reading and searching {delegate}, and make the decisions yourself. Run your checks before you "
        f"finish and stop when the goal is met.{log}",
        "## Acceptance checks",
        f"shellcheck scripts/*.sh tests/*.sh, bash tests/run-tests.sh, and bash scripts/verify-mission.sh {mission} "
        "(ruff and a type check join when the repo adds them). A worker run counts only when .tasks/receipts/ proves it.",
    ]) + ("\n## Request\n" + request.strip() if request is not None else "")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("mission")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--log")
    parser.add_argument("--request")
    args = parser.parse_args(argv)
    try:
        request = Path(args.request).read_text(encoding="utf-8") if args.request is not None else None
        if request is not None and not request.strip():
            raise ValueError("request file is empty")
        print(render(args.action, args.mission, args.provider, args.log, request))
    except (ValueError, OSError) as exc:
        print(f"brain_prompt: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
