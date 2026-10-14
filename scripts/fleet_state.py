#!/usr/bin/env python3
"""Frozen-fleet policy: truthful local inventory, immutable approved snapshots.

This module intentionally has no third-party dependencies.  The shell inventory
entry point delegates here so all consumers get the same validator and policy.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# This module is run directly, imported by sibling scripts, and loaded from a
# file location by tests.  Make the sibling registry loader available in each.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from harness_registry import RegistryError, legacy_view, load_registry

try:
    PROVIDERS, CAPABILITIES, SEAT_SPECS, EXECUTABLES = legacy_view(load_registry())
except RegistryError as exc:
    print(f"ERROR: registry: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

FALLBACKS = {"grok":"cursor-grok-4.5-high", "composer":"composer-2.5", "sol":"gpt-5.6-sol", "terra":"gpt-5.6-terra", "luna":"gpt-5.6-luna", "pro":"gemini-3.1-pro-high", "flash":"gemini-3.6-flash-high"}
RFC3339 = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$")

class PolicyError(ValueError): pass

def fail(message): raise PolicyError(message)
def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
def sha(raw): return hashlib.sha256(raw).hexdigest()
def timestamp(value, name):
    if not isinstance(value, str) or not RFC3339.fullmatch(value): fail(f"{name} must be RFC3339")
    try: datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError: fail(f"{name} must be RFC3339")
def obj(value, name):
    if not isinstance(value, dict): fail(f"{name} must be an object")
def text(value, name):
    if not isinstance(value, str) or not value.strip(): fail(f"{name} must be non-empty text")
def exact_keys(value, keys, name):
    obj(value, name)
    if set(value) != set(keys): fail(f"{name} has missing or extra fields")
def read_json(path, name, require_canonical=False):
    try: raw = Path(path).read_bytes(); value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc: fail(f"invalid {name}: {exc}")
    if require_canonical and raw != canonical(value).encode(): fail(f"{name} is not canonical JSON")
    return value, raw
def atomic_write_new(path, raw, no_clobber=False, read_only=False):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if no_clobber and path.exists(): fail(f"refusing to overwrite existing {path}")
    fd, tmp = tempfile.mkstemp(prefix=".fleet-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        if read_only: os.chmod(tmp, 0o444)
        if no_clobber:
            try: os.link(tmp, path)
            except FileExistsError: fail(f"refusing to overwrite existing {path}")
            os.unlink(tmp)
        else: os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

# One model id per line, in the three real CLI shapes:
#   Cursor  "composer-2.5 - Composer 2.5"
#   agy     "gemini-3.8-flash-high     Gemini 3.8 Flash (High)"
#   Grok    "  * grok-4.7 (default)" / "  - grok-4.6"
# Ids start with a letter and contain "-"; headers, tips and errors do not match.
MODEL_LINE = re.compile(r"^\s*(?:[*-]\s+)?([A-Za-z][A-Za-z0-9._:+/-]*)(?=\s|$)")
def models_from_text(text):
    out=[]
    for line in text.splitlines():
        m=MODEL_LINE.match(line)
        if m and "-" in m.group(1): out.append(m.group(1))
    return list(dict.fromkeys(out))
def run(args):
    try:
        p=subprocess.run(args, text=True, capture_output=True, timeout=25, env={**os.environ,"TERM":"dumb"})
        return p.returncode, (p.stdout or "")+(p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc: return 1, str(exc)
def probe(provider):
    base={"probed_at":now(),"capabilities":CAPABILITIES[provider]}
    executable=EXECUTABLES.get(provider, provider)
    path=shutil.which(executable)
    if not path: return {**base,"status":"unavailable","error":"not on PATH"}
    if provider == "claude": return {**base,"status":"success","path":path,"aliases":["opus","sonnet","haiku","fable"],"observed_models":[]}
    if provider == "codex":
        cache=Path.home()/".codex/models_cache.json"
        try:
            data=json.loads(cache.read_text()); vals=[x.get("slug") or x.get("id") or x.get("model") if isinstance(x,dict) else x for x in data.get("models",[])]
            vals=[x for x in vals if isinstance(x,str) and x]
            if vals: return {**base,"status":"success","path":path,"observed_models":vals,"aliases":[]}
            raise ValueError("empty model cache")
        except (OSError,json.JSONDecodeError,ValueError) as exc: return {**base,"status":"failure","path":path,"error":str(exc)}
    code, output=run([executable,"models"])
    vals=models_from_text(output)
    if code == 0 and vals: return {**base,"status":"success","path":path,"observed_models":vals,"aliases":[]}
    return {**base,"status":"failure","path":path,"error":output[:200] or "empty model list"}
def validate_provider(value, name):
    provider=name.split(".")[-1]
    obj(value,name)
    timestamp(value.get("probed_at"),name+".probed_at"); status=value.get("status")
    if status not in {"success","failure","unavailable"}: fail(f"{name}.status invalid")
    caps=value.get("capabilities"); exact_keys(caps,{"efforts","speeds"},name+".capabilities")
    if caps != CAPABILITIES[provider]: fail(f"{name}.capabilities must equal canonical provider matrix")
    if status=="success":
        exact_keys(value,{"probed_at","capabilities","status","path","aliases","observed_models"},name)
        text(value["path"],name+".path")
        if not all(isinstance(x,str) and x.strip() for x in value["aliases"]+value["observed_models"]): fail(f"{name} models must be non-empty text")
        vals=value.get("observed_models",[])+value.get("aliases",[])
        if not vals or not all(isinstance(x,str) and x for x in vals): fail(f"{name} success requires a non-empty model list")
    elif status=="failure":
        exact_keys(value,{"probed_at","capabilities","status","path","error"},name)
        text(value["path"],name+".path"); text(value["error"],name+".error")
    else:
        exact_keys(value,{"probed_at","capabilities","status","error"},name)
        text(value["error"],name+".error")

def provider_models(record, provider):
    return record["aliases"] if provider == "claude" else record["observed_models"]

def seat_source_is_truthful(value, current, retained, seat, name):
    provider, family = SEAT_SPECS[seat]
    if value["provider"] != provider or value["family"] != family:
        fail(f"{name} has an invalid canonical provider/family relationship")
    if value["capabilities"] != CAPABILITIES[provider]: fail(f"{name} capabilities must equal canonical provider matrix")
    model, health, source = value["model"], value["health"], value["source"]
    if source == "observed":
        if provider == "claude" or current["status"] != "success" or model not in current["observed_models"] or health != "healthy": fail(f"{name} forged healthy observed source")
    elif source == "alias":
        if provider != "claude" or current["status"] != "success" or model not in current["aliases"] or health != "healthy": fail(f"{name} forged healthy alias source")
    elif source == "last_good":
        if current["status"] == "success" or retained is None or model not in provider_models(retained,provider) or health != "degraded": fail(f"{name} invalid retained source")
    elif source == "fallback":
        if current["status"] == "unavailable" or retained is not None or FALLBACKS.get(family) != model or health != "degraded": fail(f"{name} invalid fallback source")
    elif source == "unavailable":
        if model != "unavailable" or health != "unknown": fail(f"{name} invalid unavailable source")
    else: fail(f"{name} source invalid")
def validate_inventory(doc):
    exact_keys(doc,{"schema_version","probed_at","providers","last_good","seats"},"inventory")
    if doc["schema_version"] != 1: fail("inventory schema_version must be 1")
    timestamp(doc["probed_at"],"inventory.probed_at"); exact_keys(doc["providers"],PROVIDERS,"inventory.providers")
    obj(doc["last_good"],"inventory.last_good")
    if not set(doc["last_good"]).issubset(PROVIDERS): fail("inventory.last_good has unknown provider")
    exact_keys(doc["seats"],SEAT_SPECS,"inventory.seats")
    for provider in PROVIDERS:
        validate_provider(doc["providers"][provider],"inventory.providers."+provider)
        if provider in doc["last_good"]:
            validate_provider(doc["last_good"][provider],"inventory.last_good."+provider)
            if doc["last_good"][provider]["status"] != "success": fail("last_good must be successful")
    for seat, value in doc["seats"].items():
        exact_keys(value,{"provider","model","family","health","source","capabilities"},"inventory.seats."+seat)
        if value["health"] not in {"healthy","degraded","unknown"} or value["source"] not in {"observed","alias","last_good","fallback","unavailable"}: fail("invalid inventory seat")
        text(value["model"],"inventory.seats."+seat+".model")
        seat_source_is_truthful(value, doc["providers"][SEAT_SPECS[seat][0]], doc["last_good"].get(SEAT_SPECS[seat][0]), seat, "inventory.seats."+seat)
    return doc
EFFORT_RANK = {"xhigh": 50, "max": 45, "high": 40, "medium": 20, "low": 10, "none": 0}
UNSTABLE = {"preview", "exp", "experimental", "lite"}
def model_tokens(model): return [t for t in re.split(r"[-_.]", model.lower()) if t]
def is_fast(model): return "fast" in model_tokens(model)
def model_rank(model):
    """Stable before preview, then version, then release date, then effort."""
    tokens=model_tokens(model)
    date=int(tokens.pop()) if tokens and re.fullmatch(r"\d{8}", tokens[-1]) else 0
    version=[]
    for token in tokens:
        if token.isdigit(): version.append(int(token))
        elif version: break
    effort=next((EFFORT_RANK[t] for t in tokens if t in EFFORT_RANK), 0)
    return (not UNSTABLE.intersection(tokens), tuple(version), date, effort)
def choose(values, family):
    # Fast modes cost more and are opt-in only: never chosen automatically.
    choices=[x for x in values if family in x.lower() and not is_fast(x)]
    # sorted() is stable, so equal ranks keep the provider's own order.
    return sorted(choices, key=model_rank, reverse=True)[0] if choices else None
def make_seats(providers,last_good):
    result={}
    for seat,(provider,family) in SEAT_SPECS.items():
        current=providers[provider]; record=current; health="healthy"; source="alias" if provider=="claude" else "observed"
        if current["status"] != "success":
            if provider in last_good: record=last_good[provider]; health="degraded"; source="last_good"
            elif current["status"] == "unavailable":
                # A missing executable must never advertise a viable binding.
                result[seat]={"provider":provider,"model":"unavailable","family":family,"health":"unknown","source":"unavailable","capabilities":CAPABILITIES[provider]}; continue
            else:
                model=FALLBACKS.get(family)
                if not model: result[seat]={"provider":provider,"model":"unavailable","family":family,"health":"unknown","source":"unavailable","capabilities":CAPABILITIES[provider]}; continue
                result[seat]={"provider":provider,"model":model,"family":family,"health":"degraded","source":"fallback","capabilities":CAPABILITIES[provider]}; continue
        values=record.get("aliases",[]) if provider=="claude" else record.get("observed_models",[])
        model=choose(values,family)
        if not model:
            # A real model list without this family is a fact, not a reason to guess an id.
            result[seat]={"provider":provider,"model":"unavailable","family":family,"health":"unknown","source":"unavailable","capabilities":CAPABILITIES[provider]}; continue
        result[seat]={"provider":provider,"model":model,"family":family,"health":health,"source":source,"capabilities":record["capabilities"]}
    return result
def inventory(out, json_only):
    out=Path(out); prior={}
    if out.exists(): prior,_=read_json(out,"inventory",require_canonical=True); validate_inventory(prior)
    previous=prior.get("last_good",{})
    providers={p:probe(p) for p in PROVIDERS}
    retained=dict(previous)
    for p,v in providers.items():
        if v["status"]=="success": retained[p]=v
    doc={"schema_version":1,"probed_at":now(),"providers":providers,"last_good":retained,"seats":make_seats(providers,retained)}
    validate_inventory(doc); raw=canonical(doc).encode(); atomic_write_new(out,raw)
    if json_only: print(raw.decode(),end="")
    else: print(f"Fleet inventory @ {doc['probed_at']}\nWrote {out}")
    return doc
def validate_fleet(doc):
    exact_keys(doc,{"schema_version","mission","inventory","approval","seats"},"fleet")
    if doc["schema_version"]!=1: fail("fleet schema_version must be 1")
    exact_keys(doc["mission"],{"path"},"fleet.mission"); text(doc["mission"]["path"],"fleet.mission.path")
    exact_keys(doc["inventory"],{"sha256","probed_at"},"fleet.inventory");
    if not re.fullmatch(r"[0-9a-f]{64}",doc["inventory"]["sha256"]): fail("fleet inventory hash invalid")
    timestamp(doc["inventory"]["probed_at"],"fleet.inventory.probed_at")
    exact_keys(doc["approval"],{"status","approved_by","approved_at"},"fleet.approval")
    if doc["approval"]["status"]!="approved": fail("fleet is not approved")
    text(doc["approval"]["approved_by"],"fleet.approval.approved_by"); timestamp(doc["approval"]["approved_at"],"fleet.approval.approved_at")
    obj(doc["seats"],"fleet.seats")
    if not doc["seats"]: fail("fleet requires seats")
    for name,v in doc["seats"].items():
        exact_keys(v,{"provider","model","family","effort","speed","health","source","capabilities"},"fleet.seats."+name)
        if v["provider"] not in PROVIDERS or not isinstance(v["model"],str) or not v["model"].strip() or v["model"]=="unavailable": fail("fleet seat invalid")
        if v["health"] not in {"healthy","degraded","unknown"} or v["source"] not in {"observed","alias","last_good","fallback"}: fail("fleet seat health/source invalid")
        if v["source"] in {"observed","alias"} and v["health"] != "healthy": fail("observed or alias fleet seat must be healthy")
        if v["source"] in {"last_good","fallback"} and v["health"] != "degraded": fail("guessed or retained fleet seat must be degraded")
        if v["source"] == "alias" and v["provider"] != "claude": fail("alias is Claude-only")
        if v["source"] == "observed" and v["provider"] == "claude": fail("observed is non-Claude")
        caps=v["capabilities"]
        if caps != CAPABILITIES[v["provider"]]: fail("fleet seat capabilities must equal canonical provider matrix")
        if v["family"] not in {family for p,family in SEAT_SPECS.values() if p == v["provider"]}: fail("fleet seat provider/family mismatch")
        if v["effort"] not in caps["efforts"] or v["speed"] not in caps["speeds"]: fail("fleet seat unsupported capability")
    return doc
def freeze(args):
    inv,raw=read_json(args.inventory,"inventory",require_canonical=True); validate_inventory(inv)
    try: binds=json.loads(Path(args.bindings).read_text())
    except (OSError,json.JSONDecodeError) as exc: fail(f"invalid bindings: {exc}")
    obj(binds,"bindings"); timestamp(args.approved_at,"approved_at"); text(args.approved_by,"approved_by")
    seats={}
    for name,b in binds.items():
        exact_keys(b,{"inventory_seat","effort","speed"},"bindings."+name); source=inv["seats"].get(b["inventory_seat"])
        if source is None: fail(f"binding {name} references missing inventory seat")
        if source["model"]=="unavailable": fail(f"binding {name} has unavailable model")
        if b["effort"] not in source["capabilities"]["efforts"] or b["speed"] not in source["capabilities"]["speeds"]: fail(f"binding {name} requests unsupported capability")
        seats[name]={k:source[k] for k in ("provider","model","family","health","source","capabilities")}; seats[name].update(effort=b["effort"],speed=b["speed"])
    mission=Path(args.mission_dir); fleet=mission/"fleet.json"
    doc={"schema_version":1,"mission":{"path":str(mission)},"inventory":{"sha256":sha(raw),"probed_at":inv["probed_at"]},"approval":{"status":"approved","approved_by":args.approved_by,"approved_at":args.approved_at},"seats":seats}
    validate_fleet(doc); atomic_write_new(fleet,canonical(doc).encode(),no_clobber=True,read_only=True); print(canonical(doc),end="")
def resolve(args):
    doc,_=read_json(args.fleet,"fleet",require_canonical=True); validate_fleet(doc)
    if args.mission_path is not None and doc["mission"]["path"] != args.mission_path: fail("fleet mission path assertion failed")
    seat=doc["seats"].get(args.seat)
    if seat is None: fail("fleet seat not found")
    for key in ("provider","model","effort","speed"):
        val=getattr(args,key)
        if val is not None and seat[key] != val: fail(f"fleet {key} assertion failed")
    print(canonical({"seat":args.seat,**seat}),end="")
def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("inventory"); p.add_argument("--json",action="store_true"); p.add_argument("--out",default=".tasks/fleet-inventory.json")
    p=sub.add_parser("freeze"); p.add_argument("--mission-dir",required=True); p.add_argument("--inventory",required=True); p.add_argument("--bindings",required=True); p.add_argument("--approved-by",required=True); p.add_argument("--approved-at",required=True)
    p=sub.add_parser("resolve"); p.add_argument("--fleet",required=True); p.add_argument("--seat",required=True); p.add_argument("--mission-path"); p.add_argument("--provider"); p.add_argument("--model"); p.add_argument("--effort"); p.add_argument("--speed")
    p=sub.add_parser("validate-inventory"); p.add_argument("file")
    p=sub.add_parser("validate-fleet"); p.add_argument("file")
    args=parser.parse_args()
    try:
        if args.command=="inventory": inventory(args.out,args.json)
        elif args.command=="freeze": freeze(args)
        elif args.command=="resolve": resolve(args)
        elif args.command=="validate-inventory": validate_inventory(read_json(args.file,"inventory",True)[0])
        else: validate_fleet(read_json(args.file,"fleet",True)[0])
    except PolicyError as exc: print(f"ERROR: {exc}",file=sys.stderr); return 1
    return 0
if __name__=="__main__": sys.exit(main())
