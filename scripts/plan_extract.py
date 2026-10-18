#!/usr/bin/env python3
"""Extract plan-run task files from a CLI log's final answer into a mission tasks/ folder."""
import re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observe_output import final_answer
from run_id import validate_run_id

FO, TID = re.compile(r"^````[A-Za-z0-9_-]*$"), re.compile(r"^T-\d{3,}(?:-R\d+)?$")
PROT = frozenset(("GOAL.md", "features.json", "fleet.json", "PROGRESS.md"))
FM, FE = "=== FILE: ", "=== END FILE ==="
refuse = lambda m: (print(f"plan_extract: {m}", file=sys.stderr), sys.exit(2))


def _final(arg):
    p = (Path.cwd() / ".tasks/logs" / f"{arg}.log") if _rid(arg) else Path(arg)
    if not p.is_file(): refuse("log not found")
    for door in ("claude", "agy", "codex"):
        t = final_answer(door, p.read_bytes())
        if t is not None: return t
    refuse("no final answer")


def _rid(v):
    try: validate_run_id(v); return True
    except ValueError: return False


def _tasks(out):
    t = Path(out)
    if not t.is_dir() or t.name != "tasks": refuse("out-dir must be an existing tasks directory")
    if not (t.parent / "GOAL.md").is_file(): refuse("mission folder missing GOAL.md")
    return t.resolve(), t.parent.resolve()


def _tid(lines):
    if not lines or lines[0] != "---": return None
    for i in range(1, len(lines)):
        if lines[i] == "---": break
        if lines[i].startswith("task_id:"):
            c = lines[i].split(":", 1)[1].strip()
            if TID.fullmatch(c): return c
    return None


def _body(lines):
    b = list(lines)
    while b and not b[-1]: b.pop()
    return "\n".join(b) + "\n"
def _target(rel, mission, cwd):
    p = Path(rel)
    if p.is_absolute(): refuse("path must be relative")
    r, m = (cwd / p).resolve(), mission.resolve()
    if r == m or m not in r.parents: refuse("path outside mission folder")
    if r.name in PROT and r.parent == m: refuse("protected mission file")
    return r


def _blocks(text):
    lines, i, out = text.splitlines(), 0, []
    while i < len(lines):
        line = lines[i]
        if FO.fullmatch(line):
            i, body = i + 1, []
            while i < len(lines) and lines[i] != "````": body.append(lines[i]); i += 1
            if i >= len(lines): refuse("unclosed fenced block")
            i += 1
            if body and body[0] == "---": out.append(("f", body))
            continue
        if line.startswith(FM) and line.endswith(" ==="):
            rel, i, body = line[len(FM) : -len(" ===")], i + 1, []
            while i < len(lines):
                cur = lines[i]
                if cur.startswith(FM) and cur.endswith(" ==="): break
                if cur == FE: i += 1; break
                body.append(cur); i += 1
            out.append(("p", rel, body)); continue
        i += 1
    return out
def extract(arg, out_dir):
    text = _final(arg); tasks, mission = _tasks(out_dir); cwd = Path.cwd(); blocks = _blocks(text)
    if not blocks: refuse("no task blocks")
    plan, ids, paths = [], set(), set()
    for kind, *rest in blocks:
        body = rest[-1]; tid = _tid(body)
        if tid is None: refuse("task block missing task_id")
        dest = (tasks / f"{tid}.md") if kind == "f" else _target(rest[0], mission, cwd)
        if tid in ids: refuse("duplicate task_id")
        if dest in paths: refuse("duplicate target path")
        if dest.exists(): refuse("target already exists")
        ids.add(tid); paths.add(dest); plan.append((tid, dest, _body(body)))
    for tid, dest, content in plan:
        dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(content, encoding="utf-8"); print(tid)


def main(argv):
    if len(argv) != 2: print("Usage: plan_extract.py <run-id-or-log> <out-dir>", file=sys.stderr); return 2
    try: extract(argv[0], argv[1])
    except SystemExit: raise
    except OSError: refuse("write failed")
    return 0
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
