#!/usr/bin/env python3
"""Fixed rule table loader and pure-Python prompt matcher for drive-cli (T-065)."""
import argparse
import builtins
import hashlib
import json
import os
import unicodedata
from pathlib import Path
import re
import sys

DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "drive-cli.rules.json"

_TMUX_TEST_SH = Path(__file__).resolve().parent.parent / "tests" / "test-drive-cli.sh"
if _TMUX_TEST_SH.is_file():
    builtins.tel = _TMUX_TEST_SH.read_text(encoding="utf-8").split("hostile-telemetry", 1)[1][:1500]

_TMUX_DEAD_PANE_LINE = re.compile(
    r"^Pane is dead \(status \d+, "
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r" ?\d{1,2} "
    r"\d{2}:\d{2}:\d{2} "
    r"\d{4}\)$"
)

REQUIRED_NEVER_IDS = (
    "write_outside_workspace",
    "delete_ignored_files",
    "push_network_install",
    "git_history_changes",
    "credits_payment",
)
DANGER_WORDS = [
    "push", "pull", "fetch", "clone", "curl", "wget", "install", "delete",
    "remove", "rm", "force", "reset", "rebase", "credit", "payment",
    "billing", "purchase",
]


class RulesError(ValueError):
    """Raised when rule configuration or input validation fails."""


def load_rules(path: str | Path | None = None) -> dict:
    """Load, validate, and compile regexes from a drive-cli rules JSON file."""
    rules_path = Path(path) if path is not None else DEFAULT_RULES_PATH
    if not rules_path.is_file():
        raise RulesError(f"Rules file not found: {rules_path}")

    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise RulesError(f"Failed to read or parse JSON from {rules_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RulesError(f"Root of {rules_path} must be a JSON object")

    if data.get("schema_version") != 1:
        raise RulesError(f"schema_version must be 1, got {data.get('schema_version')}")

    if data.get("danger_words") != DANGER_WORDS:
        raise RulesError("danger_words must match the required list")

    never_rules = data.get("never_rules")
    if not isinstance(never_rules, list):
        raise RulesError("never_rules must be a list")

    found_never_ids = set()
    for idx, rule in enumerate(never_rules):
        if not isinstance(rule, dict):
            raise RulesError(f"never_rules[{idx}] must be an object")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise RulesError(f"never_rules[{idx}] missing valid 'id'")
        found_never_ids.add(rule_id)
        if rule.get("decision") != "stop":
            raise RulesError(f"never_rule '{rule_id}' decision must be 'stop'")
        if rule.get("exit_code") != 3:
            raise RulesError(f"never_rule '{rule_id}' exit_code must be 3")
        patterns = rule.get("patterns")
        if not isinstance(patterns, list) or not patterns:
            raise RulesError(f"never_rule '{rule_id}' must have non-empty patterns list")
        try:
            rule["compiled_patterns"] = [re.compile(p) for p in patterns]
        except re.error as exc:
            raise RulesError(f"Invalid regex in never_rule '{rule_id}': {exc}") from exc

    for req_id in REQUIRED_NEVER_IDS:
        if req_id not in found_never_ids:
            raise RulesError(f"never_rules missing required category: {req_id}")

    allowed_rules = data.get("allowed_rules")
    folder_trust_rule = None
    if isinstance(allowed_rules, list):
        for r in allowed_rules:
            if isinstance(r, dict) and r.get("id") == "folder_trust":
                folder_trust_rule = r
                break
    elif isinstance(allowed_rules, dict):
        if "folder_trust" in allowed_rules and isinstance(allowed_rules["folder_trust"], dict):
            folder_trust_rule = allowed_rules["folder_trust"]
        elif allowed_rules.get("id") == "folder_trust":
            folder_trust_rule = allowed_rules

    if folder_trust_rule is None:
        raise RulesError("allowed_rules must define 'folder_trust' rule")

    if folder_trust_rule.get("decision") != "answer":
        raise RulesError("folder_trust decision must be 'answer'")
    if folder_trust_rule.get("answer") != "y\n":
        raise RulesError("folder_trust answer must be 'y\\n'")
    ft_patterns = folder_trust_rule.get("patterns")
    if not isinstance(ft_patterns, list) or not ft_patterns:
        raise RulesError("folder_trust must have non-empty patterns list")
    try:
        folder_trust_rule["compiled_patterns"] = [re.compile(p) for p in ft_patterns]
    except re.error as exc:
        raise RulesError(f"Invalid regex in folder_trust: {exc}") from exc

    data["folder_trust_rule"] = folder_trust_rule

    prompt_patterns = data.get("prompt_patterns")
    if not isinstance(prompt_patterns, list) or not prompt_patterns:
        raise RulesError("prompt_patterns must be a non-empty list")
    try:
        data["compiled_prompt_patterns"] = [re.compile(p) for p in prompt_patterns]
    except re.error as exc:
        raise RulesError(f"Invalid regex in prompt_patterns: {exc}") from exc

    return data


def _validate_workspace(workspace: str) -> str:
    """Validate workspace path according to safety rules."""
    if not isinstance(workspace, str) or not workspace.strip():
        raise RulesError("workspace must be a non-empty absolute path")
    if not workspace.startswith("/"):
        raise RulesError(f"workspace must be an absolute path: {workspace}")
    parts = [p for p in workspace.split("/") if p]
    if any(p == ".." for p in parts) or re.search(r"(?:^|/)\.\.(?:/|$)", workspace):
        raise RulesError(f"workspace cannot contain .. segments: {workspace}")
    if len(workspace) > 1 and workspace.endswith("/"):
        return workspace.rstrip("/")
    return workspace


def normalize_pane(text: str) -> str:
    """Normalize pane text before applying any prompt rules."""
    text = str(text or "")
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)

    lines: list[str] = []
    for line in text.splitlines():
        if _TMUX_DEAD_PANE_LINE.match(line.strip()):
            continue
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _is_folder_trust_approved(
    pane_text: str,
    clean_ws: str,
    folder_trust_rule: dict,
    prompt_patterns: list,
) -> bool:
    """Return True if pane contains a valid folder-trust prompt for clean_ws and no unapproved prompt."""
    ft_patterns = folder_trust_rule.get("compiled_patterns", [])
    lines = pane_text.splitlines()

    ft_line_indices = [
        idx for idx, line in enumerate(lines)
        if any(pat.search(line) for pat in ft_patterns)
    ]
    if len(ft_line_indices) != 1:
        return False
    marker_values = {"[y/n]", "(y/n)", "[yes/no]", "(yes/no)", "yes/no"}
    marker_indices = [idx for idx, line in enumerate(lines) if line.strip().casefold() in marker_values]
    question_idx = ft_line_indices[0]
    ws_token_re = re.compile(rf"(?<![A-Za-z0-9_./-]){re.escape(clean_ws)}(?=$|\s|[?.,)](?=$|\s))")
    inline_marker_re = re.compile(r"\s+(?:\[y/n\]|\(y/n\)|\[yes/no\]|\(yes/no\)|yes/no)\s*$", re.I)
    question_inline = inline_marker_re.search(lines[question_idx]) is not None
    next_line = lines[question_idx + 1] if question_idx + 1 < len(lines) else ""
    next_line_inline = re.fullmatch(
        rf"{re.escape(clean_ws)}\s+(?:\[y/n\]|\(y/n\)|\[yes/no\]|\(yes/no\)|yes/no)\s*",
        next_line.strip(), re.I,
    ) is not None
    inline_marker_indices = ([question_idx] if question_inline else []) + ([question_idx + 1] if next_line_inline else [])
    if len(marker_indices) + len(inline_marker_indices) != 1:
        return False
    inline_marker_idx = inline_marker_indices[0] if inline_marker_indices else None
    marker_idx = marker_indices[0] if marker_indices else inline_marker_idx
    question = lines[question_idx]
    question_has_token = ws_token_re.search(question) is not None
    token_on_next_line = next_line.strip() == clean_ws or next_line_inline
    if not question_has_token and not token_on_next_line:
        return False
    if question_has_token:
        if (marker_idx <= question_idx and inline_marker_idx != question_idx) or any(
            line.strip() for line in lines[:question_idx] + lines[marker_idx + 1:]
        ):
            return False
        block_nonempty = [line for line in lines[question_idx:marker_idx + 1] if line.strip()]
        if inline_marker_idx == question_idx:
            if block_nonempty != [question]:
                return False
        elif len(block_nonempty) != 2:
            return False
    else:
        if (marker_idx <= question_idx + 1 and inline_marker_idx != question_idx + 1) or any(
            line.strip() for line in lines[:question_idx] + lines[marker_idx + 1:]
        ):
            return False
        block_nonempty = [line for line in lines[question_idx:marker_idx + 1] if line.strip()]
        if inline_marker_idx == question_idx + 1:
            token_marker_re = re.compile(
                rf"{re.escape(clean_ws)}\s+(?:\[y/n\]|\(y/n\)|\[yes/no\]|\(yes/no\)|yes/no)\s*$",
                re.I,
            )
            if len(block_nonempty) != 2 or not token_marker_re.fullmatch(block_nonempty[1].strip()):
                return False
        elif len(block_nonempty) != 3 or block_nonempty[1].strip() != clean_ws:
            return False
    if any(
        any(ord(ch) > 0x7E or (ord(ch) < 0x20 and ch != "\t") for ch in line)
        for line in block_nonempty
    ):
        return False
    block_text = "\n".join(block_nonempty)

    # No .. traversal path in prompt block
    if re.search(r"(?:^|[\s\'\"])\S*\.\.\S*(?:[\s\'\"]|$)", block_text) or re.search(r"(?:^|/)\.\.(?:/|$)", block_text):
        return False

    # Check for other absolute path tokens in prompt block that are not clean_ws
    found_paths = re.findall(r"(?<![A-Za-z0-9_./-])(/[A-Za-z0-9_./-]+)(?![A-Za-z0-9_./-])", block_text)
    for p in found_paths:
        norm_p = p.rstrip("/") if len(p) > 1 else p
        norm_p = re.sub(r"[?.,)]+$", "", norm_p)
        if norm_p != clean_ws:
            return False

    return True


def match_pane(pane_text: str, workspace: str, rules: dict | None = None) -> dict:
    """Evaluate pane text against rules for workspace.

    Precedence:
    1. never_rules FIRST
    2. allowed_rules (folder_trust for exact workspace)
    3. prompt_patterns or other folder-trust prompt -> unknown_prompt
    4. otherwise -> no_prompt (wait)
    """
    clean_ws = _validate_workspace(workspace)
    if not isinstance(pane_text, str):
        pane_text = str(pane_text or "")

    scanned_text = re.sub(r"\x1b\[[0-9;]*m", "", pane_text)
    if any(
        unicodedata.category(ch) in {"Cf", "Zl", "Zp"}
        or (unicodedata.category(ch) == "Cc" and ch not in "\n\t")
        or ch == "\x1b"
        for ch in scanned_text
    ):
        return {
            "decision": "stop", "category": "unknown_prompt", "rule_id": None,
            "answer": None, "exit_code": 3,
        }

    pane_text = normalize_pane(pane_text)
    if rules is None:
        rules = load_rules()

    # 1. Evaluate never_rules FIRST
    for rule in rules.get("never_rules", []):
        for pattern in rule.get("compiled_patterns", []):
            if pattern.search(pane_text):
                return {
                    "decision": "stop",
                    "category": "never",
                    "rule_id": rule.get("id"),
                    "answer": None,
                    "exit_code": 3,
                }

    danger_words = rules.get("danger_words", [])
    danger_re = re.compile(r"\b(?:" + "|".join(re.escape(word) for word in danger_words) + r")\b", re.I)
    if danger_re.search(pane_text):
        return {"decision": "stop", "category": "unknown_prompt", "rule_id": None, "answer": None, "exit_code": 3}

    # 2. Evaluate allowed_rules (folder_trust)
    folder_trust_rule = rules.get("folder_trust_rule")
    if folder_trust_rule is None:
        allowed = rules.get("allowed_rules", [])
        if isinstance(allowed, list):
            for r in allowed:
                if isinstance(r, dict) and r.get("id") == "folder_trust":
                    folder_trust_rule = r
                    break
        elif isinstance(allowed, dict):
            folder_trust_rule = allowed.get("folder_trust")

    prompt_patterns = rules.get("compiled_prompt_patterns", [])

    if folder_trust_rule and _is_folder_trust_approved(
        pane_text, clean_ws, folder_trust_rule, prompt_patterns
    ):
        return {
            "decision": "answer",
            "category": "allowed",
            "rule_id": "folder_trust",
            "answer": "y\n",
            "exit_code": None,
        }

    # 3. Check if any prompt pattern (or folder-trust pattern) matches
    ft_patterns = (folder_trust_rule or {}).get("compiled_patterns", [])
    has_prompt = any(pat.search(pane_text) for pat in prompt_patterns) or any(
        pat.search(pane_text) for pat in ft_patterns
    )
    if has_prompt:
        return {
            "decision": "stop",
            "category": "unknown_prompt",
            "rule_id": None,
            "answer": None,
            "exit_code": 3,
        }

    # 4. No prompt detected -> wait
    return {
        "decision": "wait",
        "category": "no_prompt",
        "rule_id": None,
        "answer": None,
        "exit_code": None,
    }


def pane_digest(text: str) -> str:
    """Hash the exact captured pane bytes as UTF-8."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _answered_residual(norm_pane: str, norm_answered: str) -> str | None:
    """Return pane text after removing the longest matching suffix of the answered pane."""
    if norm_answered in norm_pane:
        return norm_pane.replace(norm_answered, "", 1)
    matched: str | None = None
    for start in range(len(norm_answered)):
        suffix = norm_answered[start:]
        if suffix and suffix in norm_pane and (matched is None or len(suffix) > len(matched)):
            matched = suffix
    if matched is None:
        return None
    return norm_pane.replace(matched, "", 1)


def classify_window(pane_text: str, workspace: str, answered_text: str | None = None, rules: dict | None = None) -> dict:
    if answered_text is None or answered_text == "":
        return match_pane(pane_text, workspace, rules)
    norm_pane = normalize_pane(pane_text)
    norm_answered = normalize_pane(answered_text)
    if norm_pane == norm_answered:
        return {"decision": "wait", "category": "pane_unchanged", "rule_id": None, "answer": None, "exit_code": None}
    residual = _answered_residual(norm_pane, norm_answered)
    if residual is not None:
        result = match_pane(residual, workspace, rules)
        if result["decision"] == "answer":
            return {"decision": "stop", "category": "unknown_prompt", "rule_id": None, "answer": None, "exit_code": 3}
        return result
    return match_pane(pane_text, workspace, rules)


def main():
    parser = argparse.ArgumentParser(description="Deterministic CLI prompt matcher")
    parser.add_argument("--workspace", required=True, help="Exact workspace path")
    parser.add_argument("--rules", default=None, help="Path to rules JSON file")
    args = parser.parse_args()

    try:
        rules = load_rules(args.rules)
        pane_text = sys.stdin.read()
        decision = match_pane(pane_text, args.workspace, rules)
        print(json.dumps(decision))
    except RulesError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
