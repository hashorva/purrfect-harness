#!/usr/bin/env python3
"""Validate and query the Purrfect Harness ownership manifest.

This is deliberately the only manifest parser used by release, install, update,
and discovery sync.  It validates before returning query output so callers never
turn a failed query into an empty destructive loop.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import re

SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")


def fail(message):
    raise ValueError(message)


def path_value(value, name):
    if not isinstance(value, str) or not value or value.strip() != value:
        fail(f"{name} must be a non-empty trimmed relative path")
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        fail(f"{name} is not a safe normalized relative path: {value!r}")
    if path.as_posix() != value:
        fail(f"{name} is not normalized: {value!r}")
    return value


def names(values, name):
    if not isinstance(values, list) or not values:
        fail(f"{name} must be a non-empty array")
    if values != sorted(values) or len(values) != len(set(values)):
        fail(f"{name} must be sorted and unique")
    for value in values:
        path_value(value, name)
        if "/" in value:
            fail(f"{name} entries must be single directory names")
    return values


def paths(values, name):
    if not isinstance(values, list) or not values:
        fail(f"{name} must be a non-empty array")
    if len(values) != len(set(values)):
        fail(f"{name} must be unique")
    return [path_value(value, name) for value in values]


def read_manifest(root, consumer):
    try:
        manifest = json.loads((root / "harness-manifest.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(str(exc))
    if manifest.get("schema_version") != 1:
        fail("schema_version must equal 1")
    release = manifest.get("release")
    ownership = manifest.get("ownership")
    if not isinstance(release, dict) or not isinstance(ownership, dict):
        fail("release and ownership must be objects")
    version = release.get("version")
    tag = release.get("required_tag")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        fail("release.version must be a SemVer version")
    if tag != f"v{version}":
        fail("release.required_tag must equal v<release.version>")
    skills = names(ownership.get("canonical_skills"), "ownership.canonical_skills")
    discovery = paths(ownership.get("discovery_targets"), "ownership.discovery_targets")
    roots = paths(ownership.get("install_payload_roots"), "ownership.install_payload_roots")
    install = paths(ownership.get("install_payload_paths"), "ownership.install_payload_paths")
    update = paths(ownership.get("update_paths"), "ownership.update_paths")
    template = path_value(ownership.get("consumer_agents_template"), "ownership.consumer_agents_template")
    actual = sorted(p.name for p in (root / ".agents/skills").iterdir() if p.is_dir())
    if consumer:
        missing = sorted(set(skills) - set(actual))
        if missing:
            fail("consumer canonical skills missing manifest-owned entries: " + ", ".join(missing))
    elif skills != actual:
        fail("canonical_skills must exactly list every .agents/skills directory")
    if not consumer:
        for value in roots + install + update + [template]:
            if not (root / value).exists():
                fail(f"manifest-owned path is missing: {value}")
        try:
            readme = next(line.split(":", 1)[1].strip() for line in (root / "README.md").read_text().splitlines() if line.startswith("version:"))
            changelog = next(line[3:].split()[0] for line in (root / "CHANGELOG.md").read_text().splitlines() if line.startswith("## "))
        except (OSError, StopIteration, IndexError) as exc:
            fail(f"could not read release version: {exc}")
        if readme != version or changelog != version:
            fail("README, CHANGELOG, and manifest release versions disagree")
    return manifest


def released(root, tag, trigger_tag):
    try:
        tags = subprocess.check_output(["git", "-C", str(root), "tag", "--points-at", "HEAD"], text=True).split()
        tag_type = subprocess.check_output(["git", "-C", str(root), "cat-file", "-t", f"refs/tags/{tag}"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True)
    except subprocess.CalledProcessError as exc:
        fail(f"could not inspect release state: {exc}")
    if trigger_tag is not None and trigger_tag != tag:
        fail(f"release trigger {trigger_tag!r} must exactly equal manifest tag {tag!r}")
    if tag not in tags:
        fail(f"{tag} must point at HEAD; use --dev/--allow-untagged only for explicit development work")
    if tag_type != "tag":
        fail(f"{tag} must be an annotated tag")
    if dirty:
        fail("tagged harness source must be clean before propagation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--consumer", action="store_true")
    parser.add_argument("--require-release", action="store_true")
    parser.add_argument("--trigger-tag")
    parser.add_argument("command", choices=["validate", "validate-version", "get", "install-payload"])
    parser.add_argument("field", nargs="?")
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    try:
        manifest = read_manifest(root, args.consumer)
        if args.require_release:
            if args.consumer:
                fail("release validation is only valid for a harness source")
            released(root, manifest["release"]["required_tag"], args.trigger_tag)
        if args.command == "validate":
            print(manifest["release"]["version"])
        elif args.command == "validate-version":
            if not isinstance(args.field, str) or not SEMVER.fullmatch(args.field):
                fail("version must be SemVer")
            print(args.field)
        elif args.command == "get":
            value = manifest["ownership"].get(args.field)
            if isinstance(value, list):
                print(*value, sep="\n")
            elif isinstance(value, str):
                print(value)
            else:
                fail(f"ownership.{args.field} is not queryable")
        else:
            for skill in manifest["ownership"]["canonical_skills"]:
                for item in sorted((root / ".agents/skills" / skill).rglob("*")):
                    if item.is_file():
                        print(item.relative_to(root))
            for item in manifest["ownership"]["install_payload_roots"]:
                for path in sorted((root / item).rglob("*")):
                    if path.is_file():
                        print(path.relative_to(root))
            print(*manifest["ownership"]["install_payload_paths"], sep="\n")
    except ValueError as exc:
        print(f"ERROR: invalid harness manifest: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
