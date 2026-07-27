#!/usr/bin/env bash
# fleet-inventory.sh — probe local agent CLIs and bind durable seats → model IDs.
# Usage (from a consuming repo root):
#   bash scripts/fleet-inventory.sh           # human table + write .tasks/fleet-inventory.json
#   bash scripts/fleet-inventory.sh --json    # JSON only on stdout
#   bash scripts/fleet-inventory.sh --out PATH
#
# Classification uses family regexes (grok/composer/sol/terra/luna/…). Concrete
# slugs change; seats do not. GATE 0 always shows this map for human confirm/swap.
set -euo pipefail

JSON_ONLY=0
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --json) JSON_ONLY=1; shift ;;
    --out) OUT="${2:?}"; shift 2 ;;
    -h|--help)
      echo "Usage: fleet-inventory.sh [--json] [--out PATH]"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

ROOT="$(pwd)"
OUT="${OUT:-$ROOT/.tasks/fleet-inventory.json}"
mkdir -p "$(dirname "$OUT")"

export FLEET_OUT="$OUT"
export FLEET_JSON_ONLY="$JSON_ONLY"

python3 - <<'PY'
import json, os, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

out = Path(os.environ["FLEET_OUT"])
json_only = os.environ.get("FLEET_JSON_ONLY") == "1"

def which(name: str):
    return shutil.which(name)

def run(cmd, timeout=45):
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "TERM": "dumb"},
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)

def parse_agent_models(text: str):
    ids = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("available"):
            continue
        # "cursor-grok-4.5-high - Cursor Grok 4.5"
        m = re.match(r"^([A-Za-z0-9._+-]+)\s+-", line)
        if m:
            ids.append(m.group(1))
            continue
        m = re.match(r"^([A-Za-z0-9._+-]+)\s*$", line)
        if m and "-" in m.group(1):
            ids.append(m.group(1))
    return ids

def pick_family(ids, family: str):
    """Pick best id for a family. Prefer non-fast, then higher effort/version-ish."""
    fam = family.lower()
    cands = [i for i in ids if fam in i.lower()]
    if not cands:
        return None

    def score(i: str):
        s = 0
        low = i.lower()
        if low.endswith("-fast") or "-fast-" in low:
            s -= 100
        for token, w in (("xhigh", 50), ("high", 40), ("max", 45), ("medium", 20), ("low", 10), ("none", 0)):
            if re.search(rf"(^|[-_]){token}($|[-_])", low):
                s += w
                break
        # prefer newer-looking version digits
        nums = [int(x) for x in re.findall(r"\d+", i)]
        s += sum(nums[:4])
        return s

    return sorted(cands, key=score, reverse=True)[0]

def codex_models():
    cache = Path.home() / ".codex" / "models_cache.json"
    if not cache.exists():
        return [], "no ~/.codex/models_cache.json"
    try:
        data = json.loads(cache.read_text())
        models = data.get("models") or []
        ids = []
        for m in models:
            if isinstance(m, dict):
                slug = m.get("slug") or m.get("id") or m.get("model")
                if slug:
                    ids.append(slug)
            elif isinstance(m, str):
                ids.append(m)
        return ids, f"from {cache} fetched_at={data.get('fetched_at')}"
    except Exception as e:
        return [], f"parse error: {e}"

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
clis = {}
notes = []

# --- claude ---
claude_path = which("claude")
if claude_path:
    # Aliases are durable; versions resolve at runtime.
    clis["claude"] = {
        "present": True,
        "path": claude_path,
        "aliases": ["opus", "sonnet", "haiku", "fable"],
        "models": ["opus", "sonnet", "haiku", "fable"],
        "source": "cli aliases (durable)",
    }
else:
    clis["claude"] = {"present": False, "error": "not on PATH"}

# --- codex ---
codex_path = which("codex")
if codex_path:
    ids, src = codex_models()
    clis["codex"] = {
        "present": True,
        "path": codex_path,
        "models": ids,
        "source": src,
    }
    if not ids:
        notes.append("codex: no model list — seats will use family name fallbacks")
else:
    clis["codex"] = {"present": False, "error": "not on PATH"}

# --- agent (Cursor) ---
agent_path = which("agent")
if agent_path:
    code, text = run(["agent", "--list-models"], timeout=25)
    ids = parse_agent_models(text) if code == 0 or "Available models" in text else []
    # agent often prints models even with non-zero in odd envs
    if not ids and "Available models" in text:
        ids = parse_agent_models(text)
    clis["agent"] = {
        "present": True,
        "path": agent_path,
        "models": ids,
        "source": "agent --list-models" if ids else f"probe failed/timeout: {text[:200]}",
    }
    if not ids:
        notes.append("agent: model list empty — using composer/grok family name fallbacks")
else:
    clis["agent"] = {"present": False, "error": "not on PATH"}

# --- agy (UI lane; allow slow list, parse even if exit != 0) ---
agy_path = which("agy")
if agy_path:
    code, text = run(["agy", "models"], timeout=25)
    ids = []
    for line in text.splitlines():
        line = line.strip()
        if not line or " " in line or line.startswith("E0") or line.startswith("I0") or line.startswith("W0"):
            continue
        if re.match(r"^[A-Za-z0-9._:/-]+$", line) and len(line) > 3:
            ids.append(line)
    # de-dupe preserve order
    seen = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]
    clis["agy"] = {
        "present": True,
        "path": agy_path,
        "models": ids,
        "source": "agy models" if ids else f"probe weak: {text[:160]}",
    }
    if not ids:
        notes.append("agy: model list empty — strike agy seats or use --model override")
else:
    clis["agy"] = {"present": False, "error": "not on PATH"}

agent_ids = clis.get("agent", {}).get("models") or []
codex_ids = clis.get("codex", {}).get("models") or []
agy_ids = clis.get("agy", {}).get("models") or []

grok = pick_family(agent_ids, "grok")
composer = pick_family(agent_ids, "composer")
sol = pick_family(codex_ids, "sol") or ("gpt-5.6-sol" if clis.get("codex", {}).get("present") else None)
terra = pick_family(codex_ids, "terra")
luna = pick_family(codex_ids, "luna")

def pick_agy_premium(ids):
    # Gemini Pro-class first, then Sonnet on agy, then thinking Opus on agy
    pro = [i for i in ids if re.search(r"(^|[-_])pro($|[-_])", i.lower())]
    if pro:
        return pick_family(pro, "pro")
    return pick_family(ids, "sonnet") or pick_family(ids, "opus")

def pick_agy_economy(ids):
    flash = [i for i in ids if "flash" in i.lower()]
    return pick_family(flash, "flash") if flash else None

agy_prem = pick_agy_premium(agy_ids)
agy_econ = pick_agy_economy(agy_ids)

# Fallbacks when probe empty but CLI present
if clis.get("agent", {}).get("present"):
    grok = grok or "cursor-grok-4.5-high"
    composer = composer or "composer-2.5"
if clis.get("codex", {}).get("present"):
    sol = sol or "gpt-5.6-sol"
    terra = terra or "gpt-5.6-terra"
    luna = luna or "gpt-5.6-luna"
if clis.get("agy", {}).get("present"):
    agy_prem = agy_prem or "gemini-3.1-pro-high"
    agy_econ = agy_econ or "gemini-3.6-flash-high"

seats = {
    "brain": {
        "cli": "claude",
        "model": "opus",
        "family": "opus",
        "note": "default chair (Claude Code or Cursor UI Opus)",
    },
    "brain_fable": {
        "cli": "claude",
        "model": "fable",
        "family": "fable",
        "named_only": True,
        "note": "only when human names Fable — never auto-escalate",
    },
    "brain_codex": {
        "cli": "codex",
        "model": sol,
        "family": "sol",
        "note": "when human names Codex highest / Sol as chair",
    },
    "cursor.premium": {
        "cli": "agent",
        "model": grok,
        "family": "grok",
        "fallback": composer,
        "note": "Grok first; Composer if Grok unavailable",
    },
    "cursor.economy": {
        "cli": "agent",
        "model": composer,
        "family": "composer",
        "note": "small safe delegates",
    },
    "codex.premium": {
        "cli": "codex",
        "model": terra,
        "family": "terra",
    },
    "codex.economy": {
        "cli": "codex",
        "model": luna,
        "family": "luna",
    },
    "agy.premium": {
        "cli": "agy",
        "model": agy_prem,
        "family": "gemini-pro",
        "note": "UI / layout preferred lane; Pro-class (else Sonnet on agy)",
    },
    "agy.economy": {
        "cli": "agy",
        "model": agy_econ,
        "family": "gemini-flash",
        "note": "Fast UI polish / component boilerplate",
    },
    "claude.premium": {
        "cli": "claude",
        "model": "sonnet",
        "family": "sonnet",
    },
    "claude.economy": {
        "cli": "claude",
        "model": "haiku",
        "family": "haiku",
    },
}

# Strike seats whose CLI is missing
for seat, bind in list(seats.items()):
    cli = bind.get("cli")
    if cli and not clis.get(cli, {}).get("present"):
        bind["unavailable"] = True
        bind["note"] = (bind.get("note") or "") + f" (CLI {cli} missing)"

doc = {
    "probed_at": now,
    "policy": "docs/missions/MODEL_ROUTING.md",
    "clis": clis,
    "seats": seats,
    "notes": notes,
}

out.write_text(json.dumps(doc, indent=2) + "\n")

if json_only:
    print(json.dumps(doc, indent=2))
    sys.exit(0)

print(f"Fleet inventory @ {now}")
print(f"Wrote {out}")
print()
print("| Seat | CLI | Model | Family | Notes |")
print("|---|---|---|---|---|")
for seat, b in seats.items():
    mark = "⚠️ " if b.get("unavailable") else ""
    print(
        f"| {mark}{seat} | {b.get('cli')} | `{b.get('model')}` | {b.get('family')} | "
        f"{b.get('note', '')} |"
    )
if notes:
    print()
    print("Notes:")
    for n in notes:
        print(f"- {n}")
print()
print("GATE 0: confirm or remapp seats, then copy binds into the mission GOAL Fleet table.")
print("Human may interchange economy/premium (or brain) before approval.")
PY
