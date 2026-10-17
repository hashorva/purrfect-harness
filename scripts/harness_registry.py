#!/usr/bin/env python3
"""Load and validate the manifest-owned provider, door and seat registry."""
import json
import os
from pathlib import Path
import re
import sys

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "harness-registry.json"
FAMILY_RE = re.compile(r"^(?!sk-|ghp_|github_pat_|xox|AKIA)(?!.*[A-Za-z0-9]{20})[a-z][a-z0-9._-]*\Z")
PROVIDER_FIELDS = ("binary", "legacy_names", "probe_command", "list_parser", "identity_check", "identity_pattern", "login_check", "effort_encoding", "fast_encoding", "model_name_encoding", "discovery_directory", "capabilities", "sandbox_limits", "structured_output")
DOOR_FIELDS = ("provider", "billing_class", "pool", "no_zdr", "priority")
POOL_FIELDS = ("windows", "evidence")
POOL_WINDOWS = ("5h", "weekly")
ROOT_FIELDS = ("schema_version", "providers", "doors", "pools", "seat_specs")
DISPLAY_MODEL_PROVIDERS = frozenset({"cursor", "agy"})


class RegistryError(ValueError):
    pass


def _require_fields(value, fields, label):
    if not isinstance(value, dict):
        raise RegistryError(f"{label} must be an object")
    for field in fields:
        if field not in value:
            raise RegistryError(f"{label} missing required field: {field}")


def _validate_display_models(display_models):
    if not isinstance(display_models, dict):
        raise RegistryError("registry.display_models must be an object")
    for provider, table in display_models.items():
        label = f"registry.display_models.{provider}"
        if provider not in DISPLAY_MODEL_PROVIDERS:
            raise RegistryError(f"{label} has unknown provider key")
        if not isinstance(table, dict) or not table:
            raise RegistryError(f"{label} must be a non-empty object")
        for display_name, model_id in table.items():
            if not isinstance(display_name, str) or not display_name:
                raise RegistryError(f"{label} keys must be non-empty text")
            if not isinstance(model_id, str) or not model_id:
                raise RegistryError(f"{label} values must be non-empty text")


def _validate_sandbox_limits(limits, label):
    _require_fields(limits, ("write_denied_prefixes", "login_state_visible", "evidence"), label)
    prefixes = limits["write_denied_prefixes"]
    if not isinstance(prefixes, list):
        raise RegistryError(f"{label}.write_denied_prefixes must be an array")
    for prefix in prefixes:
        if not isinstance(prefix, str) or not prefix.endswith("/") or prefix.startswith("/") or ".." in prefix:
            raise RegistryError(f"{label}.write_denied_prefixes entries must be relative paths ending in /: {prefix!r}")
    login = limits["login_state_visible"]
    if not (isinstance(login, bool) or login == "unknown"):
        raise RegistryError(f"{label}.login_state_visible must be true, false or \"unknown\"")
    if not isinstance(limits["evidence"], str) or not limits["evidence"].strip():
        raise RegistryError(f"{label}.evidence must be non-empty text")


def validate_registry(data):
    _require_fields(data, ROOT_FIELDS, "registry")
    if data["schema_version"] != 1:
        raise RegistryError("registry.schema_version must be 1")
    providers = data["providers"]
    if not isinstance(providers, dict) or not providers:
        raise RegistryError("registry.providers must be a non-empty object")
    if "agent" in providers:
        raise RegistryError("agent is a legacy name, not a provider key")
    for name, provider in providers.items():
        label = f"providers.{name}"
        _require_fields(provider, PROVIDER_FIELDS, label)
        for field in ("binary", "list_parser", "effort_encoding", "fast_encoding", "discovery_directory"):
            if not isinstance(provider[field], str) or not provider[field].strip():
                raise RegistryError(f"{label}.{field} must be non-empty text")
        for field in ("effort_encoding", "fast_encoding"):
            if provider[field] not in ("flag", "model-name", "unsupported"):
                raise RegistryError(f"{label}.{field} invalid")
        model_encoding = provider["model_name_encoding"]
        if provider["effort_encoding"] == "flag":
            if model_encoding is not None:
                raise RegistryError(f"{label}.model_name_encoding must be null when effort_encoding is flag")
        else:
            _require_fields(model_encoding, ("effort_tokens", "fast_suffix", "families_without_effort"),
                            label + ".model_name_encoding")
            tokens = model_encoding["effort_tokens"]
            allowed_tokens = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
            if (not isinstance(tokens, list) or not tokens
                    or any(not isinstance(token, str) or token not in allowed_tokens for token in tokens)
                    or len(tokens) != len(set(tokens))):
                raise RegistryError(f"{label}.model_name_encoding.effort_tokens must be a non-empty list of distinct supported tokens")
            suffix = model_encoding["fast_suffix"]
            if suffix is not None and suffix != "-fast":
                raise RegistryError(f"{label}.model_name_encoding.fast_suffix must be '-fast' or null")
            if (provider["fast_encoding"] == "model-name") != (suffix is not None):
                raise RegistryError(f"{label}.model_name_encoding.fast_suffix must agree with fast_encoding")
            families = model_encoding["families_without_effort"]
            if (not isinstance(families, list)
                    or any(not isinstance(family, str) or not family.strip() for family in families)
                    or len(families) != len(set(families))):
                raise RegistryError(f"{label}.model_name_encoding.families_without_effort must be distinct non-empty text values")
        for field in ("probe_command", "identity_check"):
            if not isinstance(provider[field], list) or not provider[field] or not all(isinstance(x, str) and x for x in provider[field]):
                raise RegistryError(f"{label}.{field} must be a non-empty command array")
        if not isinstance(provider["identity_pattern"], str):
            raise RegistryError(f"{label}.identity_pattern must be text")
        try:
            re.compile(provider["identity_pattern"])
        except re.error as exc:
            raise RegistryError(f"{label}.identity_pattern must be a valid regex: {exc}") from exc
        if not isinstance(provider["login_check"], list) or not provider["login_check"] or not all(isinstance(x, str) and x for x in provider["login_check"]):
            raise RegistryError(f"{label}.login_check must be a non-empty command array")
        if not isinstance(provider["legacy_names"], list):
            raise RegistryError(f"{label}.legacy_names must be an array")
        if len(provider["legacy_names"]) > 1:
            raise RegistryError(f"{label}.legacy_names must have at most one entry")
        for legacy_name in provider["legacy_names"]:
            if not isinstance(legacy_name, str) or not legacy_name.strip():
                raise RegistryError(f"{label}.legacy_names entries must be non-empty text")
            if legacy_name in providers:
                raise RegistryError(f"{label}.legacy_names entry must not equal a provider key")
        if not isinstance(provider["capabilities"], dict):
            raise RegistryError(f"{label}.capabilities must be an object")
        _require_fields(provider["capabilities"], ("efforts", "speeds"), label + ".capabilities")
        for field, allowed in (("efforts", {"none", "minimal", "low", "medium", "high", "xhigh", "max"}),
                               ("speeds", {"unknown", "standard", "fast"})):
            values = provider["capabilities"][field]
            if (not isinstance(values, list) or not values
                    or any(not isinstance(value, str) or value not in allowed for value in values)
                    or len(values) != len(set(values))):
                raise RegistryError(f"{label}.capabilities.{field} must be a non-empty list of distinct supported values")
        _validate_sandbox_limits(provider["sandbox_limits"], label + ".sandbox_limits")
        structured_output = provider["structured_output"]
        _require_fields(structured_output, ("json_schema_flag", "evidence"), label + ".structured_output")
        flag = structured_output["json_schema_flag"]
        if flag is not None and (not isinstance(flag, str) or not flag.startswith("--") or not flag.strip()):
            raise RegistryError(f"{label}.structured_output.json_schema_flag must be a flag or null")
        if not isinstance(structured_output["evidence"], str) or not structured_output["evidence"].strip():
            raise RegistryError(f"{label}.structured_output.evidence must be non-empty text")
    doors = data["doors"]
    if not isinstance(doors, dict) or not doors:
        raise RegistryError("registry.doors must be a non-empty object")
    for name, door in doors.items():
        label = f"doors.{name}"
        _require_fields(door, DOOR_FIELDS, label)
        if not isinstance(door["provider"], str) or door["provider"] not in providers:
            raise RegistryError(f"{label}.provider must be a provider key")
        if door["billing_class"] not in ("included", "credits", "api"):
            raise RegistryError(f"{label}.billing_class invalid")
        if not isinstance(door["pool"], str) or not door["pool"].strip():
            raise RegistryError(f"{label}.pool must be non-empty text")
        if not isinstance(door["no_zdr"], bool):
            raise RegistryError(f"{label}.no_zdr must be boolean")
        if not isinstance(door["priority"], int) or isinstance(door["priority"], bool):
            raise RegistryError(f"{label}.priority must be an integer")
        if "deprecated" in door and not isinstance(door["deprecated"], bool):
            raise RegistryError(f"{label}.deprecated must be boolean")
    pools = data["pools"]
    if not isinstance(pools, dict) or not pools:
        raise RegistryError("registry.pools must be a non-empty object")
    for name, pool in pools.items():
        label = f"pools.{name}"
        _require_fields(pool, POOL_FIELDS, label)
        if set(pool) != set(POOL_FIELDS):
            raise RegistryError(f"{label} has unknown fields")
        windows = pool["windows"]
        if windows != "unknown" and not (
                isinstance(windows, list) and windows
                and all(isinstance(w, str) and w in POOL_WINDOWS for w in windows)
                and len(set(windows)) == len(windows)):
            raise RegistryError(f'{label}.windows must be "unknown" or distinct values from 5h, weekly')
        if not isinstance(pool["evidence"], str) or not pool["evidence"].strip():
            raise RegistryError(f"{label}.evidence must be non-empty text")
    if not isinstance(data["seat_specs"], dict):
        raise RegistryError("registry.seat_specs must be an object")
    for seat, spec in data["seat_specs"].items():
        if (not isinstance(spec, list) or len(spec) < 2
                or not isinstance(spec[0], str) or spec[0] not in providers):
            raise RegistryError(f"registry.seat_specs.{seat} must be [provider key, non-empty family]")
        families = spec[1:]
        if (not families
                or any(not isinstance(f, str) or not FAMILY_RE.fullmatch(f) for f in families)
                or len(set(families)) != len(families)):
            raise RegistryError(f"registry.seat_specs.{seat} must be [provider key, non-empty family]")
    if "display_models" in data:
        _validate_display_models(data["display_models"])
    return data


def load_registry(path=None):
    path = Path(path or os.environ.get("HARNESS_REGISTRY") or REGISTRY_PATH)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot load registry {path}: {exc}") from exc
    return validate_registry(data)


def legacy_view(registry):
    """Return the historical fleet-state names projected from the registry."""
    validate_registry(registry)
    names = {
        key: provider["legacy_names"][0] if provider["legacy_names"] else key
        for key, provider in registry["providers"].items()
    }
    providers = tuple(names[key] for key in registry["providers"])
    capabilities = {
        names[key]: provider["capabilities"]
        for key, provider in registry["providers"].items()
    }
    seat_specs = {
        seat: (names[spec[0]], spec[1])
        for seat, spec in registry["seat_specs"].items()
    }
    executables = {
        names[key]: provider["binary"]
        for key, provider in registry["providers"].items()
    }
    return providers, capabilities, seat_specs, executables


def seat_families(registry):
    """Return each seat's provider (legacy name) and ranked family tuple."""
    validate_registry(registry)
    names = {
        key: provider["legacy_names"][0] if provider["legacy_names"] else key
        for key, provider in registry["providers"].items()
    }
    return {
        seat: (names[spec[0]], tuple(spec[1:]))
        for seat, spec in registry["seat_specs"].items()
    }


def canonical_provider(registry, name):
    """Resolve a canonical key or its one supported persisted legacy name."""
    validate_registry(registry)
    if name in registry["providers"]:
        return name
    for key, provider in registry["providers"].items():
        if name in provider["legacy_names"]:
            return key
    raise RegistryError(f"unknown provider: {name}")


def _is_encoded(registry, key, base):
    """Return True when a base already carries an effort token or a fast suffix."""
    spec = registry["providers"][key]
    if spec["model_name_encoding"] is None:
        return any(base.endswith("-" + token) for token in spec["capabilities"]["efforts"])
    decoded = decode_model(registry, key, base)
    return decoded["effort"] is not None or decoded["fast"]


def encode_model(registry, provider, base, family, effort, fast):
    """Encode requested effort and speed into a provider's model name when configured."""
    validate_registry(registry)
    key = canonical_provider(registry, provider)
    spec = registry["providers"][key]
    if not isinstance(base, str) or not base.strip() or not isinstance(family, str) or not family.strip():
        raise RegistryError("base and family must be non-empty text")
    if not isinstance(fast, bool):
        raise RegistryError("fast must be boolean")
    if _is_encoded(registry, key, base):
        raise RegistryError(f"{key} base {base!r} is already encoded; pass the plain base and let encode_model add effort and fast")
    encoding = spec["model_name_encoding"]
    if encoding is None:
        if fast:
            raise RegistryError(f"{key} does not support fast model names")
        return base
    if fast and encoding["fast_suffix"] is None:
        raise RegistryError(f"{key} does not support fast model names")
    if family not in encoding["families_without_effort"]:
        if effort not in encoding["effort_tokens"]:
            raise RegistryError(f"{key} does not support model-name effort {effort!r}")
        base = f"{base}-{effort}"
    if fast:
        base += encoding["fast_suffix"]
    return base


def decode_model(registry, provider, model):
    """Decode a provider model name into base, optional effort and fast state."""
    validate_registry(registry)
    key = canonical_provider(registry, provider)
    if not isinstance(model, str) or not model:
        raise RegistryError("model must be non-empty text")
    encoding = registry["providers"][key]["model_name_encoding"]
    if encoding is None:
        return {"base": model, "effort": None, "fast": False}
    fast = bool(encoding["fast_suffix"] and model.endswith(encoding["fast_suffix"]))
    if fast:
        model = model[:-len(encoding["fast_suffix"])]
    effort = None
    for token in sorted(encoding["effort_tokens"], key=len, reverse=True):
        suffix = "-" + token
        if model.endswith(suffix):
            model = model[:-len(suffix)]
            effort = token
            break
    if not model:
        raise RegistryError("model name has no base")
    return {"base": model, "effort": effort, "fast": fast}


if __name__ == "__main__":
    try:
        if len(sys.argv) == 1:
            load_registry()
        elif len(sys.argv) == 2 and sys.argv[1] == "encodings":
            data = load_registry()
            for name, provider in data["providers"].items():
                encoding = provider["effort_encoding"]
                tokens = (",".join(provider["model_name_encoding"]["effort_tokens"])
                          if provider["model_name_encoding"] is not None else "-")
                print(f"{name} effort={encoding} fast={provider['fast_encoding']} tokens={tokens}")
        elif len(sys.argv) == 3 and sys.argv[1] == "persisted-name":
            data = load_registry()
            key = canonical_provider(data, sys.argv[2])
            names = {provider_key: provider["legacy_names"][0] if provider["legacy_names"] else provider_key
                     for provider_key, provider in data["providers"].items()}
            print(names[key])
        else:
            raise RegistryError("usage: harness_registry.py [persisted-name NAME | encodings]")
    except RegistryError as exc:
        message = f"ERROR: registry: {exc}"
        if len(sys.argv) > 1:
            print(message, file=sys.stderr)
            raise SystemExit(2) from exc
        raise SystemExit(f"registry error: {exc}") from exc
