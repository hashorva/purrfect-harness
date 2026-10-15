#!/usr/bin/env python3
"""Load and validate the manifest-owned provider, door and seat registry."""
import json
from pathlib import Path
import re
import sys

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "harness-registry.json"
PROVIDER_FIELDS = ("binary", "legacy_names", "probe_command", "list_parser", "identity_check", "identity_pattern", "login_check", "effort_encoding", "fast_encoding", "discovery_directory", "capabilities", "sandbox_limits")
DOOR_FIELDS = ("billing_class", "pool", "no_zdr", "priority")
ROOT_FIELDS = ("schema_version", "providers", "doors", "seat_specs", "fallbacks")


class RegistryError(ValueError):
    pass


def _require_fields(value, fields, label):
    if not isinstance(value, dict):
        raise RegistryError(f"{label} must be an object")
    for field in fields:
        if field not in value:
            raise RegistryError(f"{label} missing required field: {field}")


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
    doors = data["doors"]
    if not isinstance(doors, dict) or not doors:
        raise RegistryError("registry.doors must be a non-empty object")
    for name, door in doors.items():
        label = f"doors.{name}"
        _require_fields(door, DOOR_FIELDS, label)
        if door["billing_class"] not in ("included", "credits", "api"):
            raise RegistryError(f"{label}.billing_class invalid")
        if not isinstance(door["pool"], str) or not door["pool"].strip():
            raise RegistryError(f"{label}.pool must be non-empty text")
        if not isinstance(door["no_zdr"], bool):
            raise RegistryError(f"{label}.no_zdr must be boolean")
        if not isinstance(door["priority"], int) or isinstance(door["priority"], bool):
            raise RegistryError(f"{label}.priority must be an integer")
    if not isinstance(data["seat_specs"], dict) or not isinstance(data["fallbacks"], dict):
        raise RegistryError("registry.seat_specs and registry.fallbacks must be objects")
    for seat, spec in data["seat_specs"].items():
        if (not isinstance(spec, list) or len(spec) != 2
                or not isinstance(spec[0], str) or spec[0] not in providers
                or not isinstance(spec[1], str) or not spec[1].strip()):
            raise RegistryError(f"registry.seat_specs.{seat} must be [provider key, non-empty family]")
    for key, value in data["fallbacks"].items():
        if not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip():
            raise RegistryError("registry.fallbacks keys and values must be non-empty text")
    return data


def load_registry(path=REGISTRY_PATH):
    try:
        data = json.loads(Path(path).read_text())
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
        seat: (names[provider], family)
        for seat, (provider, family) in registry["seat_specs"].items()
    }
    executables = {
        names[key]: provider["binary"]
        for key, provider in registry["providers"].items()
    }
    return providers, capabilities, seat_specs, executables


def canonical_provider(registry, name):
    """Resolve a canonical key or its one supported persisted legacy name."""
    validate_registry(registry)
    if name in registry["providers"]:
        return name
    for key, provider in registry["providers"].items():
        if name in provider["legacy_names"]:
            return key
    raise RegistryError(f"unknown provider: {name}")


if __name__ == "__main__":
    try:
        if len(sys.argv) == 1:
            load_registry()
        elif len(sys.argv) == 3 and sys.argv[1] == "persisted-name":
            data = load_registry()
            key = canonical_provider(data, sys.argv[2])
            names = {provider_key: provider["legacy_names"][0] if provider["legacy_names"] else provider_key
                     for provider_key, provider in data["providers"].items()}
            print(names[key])
        else:
            raise RegistryError("usage: harness_registry.py [persisted-name NAME]")
    except RegistryError as exc:
        message = f"ERROR: registry: {exc}"
        if len(sys.argv) > 1:
            print(message, file=sys.stderr)
            raise SystemExit(2) from exc
        raise SystemExit(f"registry error: {exc}") from exc
