#!/usr/bin/env python3
"""Validate verdict JSON with the small, explicitly supported schema subset."""
import json
import re
import sys


KEYWORDS = {"$schema", "title", "type", "required", "properties", "additionalProperties",
            "items", "enum", "minItems", "minLength", "pattern", "if", "then"}


class SchemaError(Exception):
    pass


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def check_schema(schema, path="$schema"):
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: schema must be an object")
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise SchemaError(f"{path}: unsupported keyword {sorted(unknown)[0]}")
    for key in ("properties",):
        if key in schema:
            if not isinstance(schema[key], dict):
                raise SchemaError(f"{path}.{key}: must be an object")
            for name, child in schema[key].items():
                check_schema(child, f"{path}.{key}.{name}")
    for key in ("items", "if", "then"):
        if key in schema:
            check_schema(schema[key], f"{path}.{key}")
    if "type" in schema and schema["type"] not in ("object", "array", "string", "integer", "number", "boolean", "null"):
        raise SchemaError(f"{path}.type: unsupported type")
    if "required" in schema and (not isinstance(schema["required"], list) or not all(isinstance(x, str) for x in schema["required"])):
        raise SchemaError(f"{path}.required: must be an array of strings")


def type_matches(value, expected):
    return {
        "object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str), "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool), "null": lambda: value is None,
    }[expected]()


def validate(value, schema, path="$", errors=None):
    errors = [] if errors is None else errors
    if "if" in schema:
        condition_errors = validate(value, schema["if"], path, [])
        if not condition_errors and "then" in schema:
            validate(value, schema["then"], path, errors)
    if "type" in schema and not type_matches(value, schema["type"]):
        errors.append(f"{path}: expected {schema['type']}")
        return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is not an allowed enum member")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}.{name}: required property is missing")
        props = schema.get("properties", {})
        for name, child in props.items():
            if name in value:
                validate(value[name], child, f"{path}.{name}", errors)
        if schema.get("additionalProperties") is False:
            for name in value.keys() - props.keys():
                errors.append(f"{path}.{name}: additional property is not allowed")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: must contain at least {schema['minItems']} item(s)")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], f"{path}[{index}]", errors)
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: must contain at least {schema['minLength']} character(s)")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: does not match required pattern")
    return errors


def main(argv):
    if len(argv) == 3 and argv[1] == "--check-schema":
        try:
            check_schema(read_json(argv[2]))
        except (OSError, json.JSONDecodeError, SchemaError) as exc:
            print(f"ERROR: schema: $: {exc}", file=sys.stderr)
            return 1
        return 0
    if len(argv) != 3:
        print("usage: validate_verdict.py <schema> <json-file> | --check-schema <schema>", file=sys.stderr)
        return 2
    try:
        schema = read_json(argv[1])
        check_schema(schema)
        value = read_json(argv[2])
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"ERROR: verdict: $: {exc}", file=sys.stderr)
        return 1
    errors = validate(value, schema)
    if errors:
        print(f"ERROR: verdict: {errors[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
