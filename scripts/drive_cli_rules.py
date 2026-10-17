#!/usr/bin/env python3
"""Fixed rule table loader and pure-Python prompt matcher for drive-cli (T-065)."""
import argparse
import hashlib
import json
import os
import unicodedata
from pathlib import Path
import re
import sys

DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "drive-cli.rules.json"

_TMUX_DEAD_PANE_LINE = re.compile(
    r"^Pane is dead \(status \d+, "
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r" ?\d{1,2} "
    r"\d{2}:\d{2}:\d{2} "
    r"\d{4}\)$"
)

_PROMPT_RESIDUE_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"(?i)\[y/n\]",
    r"(?i)\(y/n\)",
    r"(?i)\[yes/no\]",
    r"(?i)\byes/no\b",
    r"(?i)\bdo you trust\b",
    r"(?i)\ballow\b",
    r"(?i)\bapprove\b",
    r"(?i)\bconfirm\b",
    r"(?i)\bpress enter\b",
    r"(?i)\b(?:select|choose)\s+(?:an?\s+)?option\b",
    r"(?i)\b(?:select|choose)\s+\[?[0-9]+(?:-[0-9]+)?\]?",
    r"(?i)^\s*(?:>\s*)?\[?[0-9]+\]\s+[A-Za-z]",
    r"(?i)\b(?:type|enter)\s+(?:yes|no|y|n)\b",
    r"(?i)\bcontinue\?\s*\[",
    r"(?i)\bproceed\?\s*\[",
))

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
    """Return True only when the whole normalized pane equals an allowed template."""
    text = normalize_pane(pane_text).rstrip()
    return any(
        re.fullmatch(re.escape(template).replace(re.escape("{workspace}"), re.escape(clean_ws)), text)
        for template in prompt_patterns
    )


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

    prompt_patterns = rules.get("prompt_patterns", [])

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
    has_prompt = any(pat.search(pane_text) for pat in _PROMPT_RESIDUE_PATTERNS) or any(
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
