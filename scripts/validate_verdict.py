#!/usr/bin/env python3
"""Validate verdict JSON with the small, explicitly supported schema subset."""
import json
import re
import sys


KEYWORDS = {"$schema", "title", "type", "required", "properties", "additionalProperties",
            "items", "enum", "minItems", "minLength", "pattern", "if", "then"}
KNOWN_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})


class SchemaError(Exception):
    pass


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def check_non_negative_int(value, path, keyword):
    if type(value) is not int or value < 0:
        raise SchemaError(f"{path}.{keyword}: must be a non-negative integer")


def check_type_keyword(value, path):
    if isinstance(value, str):
        if value not in KNOWN_TYPES:
            raise SchemaError(f"{path}.type: unsupported type")
        return
    if isinstance(value, list):
        if not value:
            raise SchemaError(f"{path}.type: must be a non-empty array of type names")
        for item in value:
            if not isinstance(item, str) or item not in KNOWN_TYPES:
                raise SchemaError(f"{path}.type: unsupported type")
        return
    raise SchemaError(f"{path}.type: must be a type name or array of type names")


def check_schema(schema, path="$schema"):
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: schema must be an object")
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise SchemaError(f"{path}: unsupported keyword {sorted(unknown)[0]}")
    if "type" in schema:
        check_type_keyword(schema["type"], path)
    if "enum" in schema:
        enum_value = schema["enum"]
        if not isinstance(enum_value, list) or not enum_value:
            raise SchemaError(f"{path}.enum: must be a non-empty array")
    if "minItems" in schema:
        check_non_negative_int(schema["minItems"], path, "minItems")
    if "minLength" in schema:
        check_non_negative_int(schema["minLength"], path, "minLength")
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise SchemaError(f"{path}.required: must be an array of strings")
    if "additionalProperties" in schema:
        extra = schema["additionalProperties"]
        if extra is not True and extra is not False:
            raise SchemaError(f"{path}.additionalProperties: must be boolean true or false")
    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            raise SchemaError(f"{path}.pattern: must be a string")
        try:
            re.compile(pattern)
        except re.error:
            raise SchemaError(f"{path}.pattern: invalid regular expression")
    if "properties" in schema:
        props = schema["properties"]
        if not isinstance(props, dict):
            raise SchemaError(f"{path}.properties: must be an object")
        for name, child in props.items():
            check_schema(child, f"{path}.properties.{name}")
    for key in ("items", "if", "then"):
        if key in schema:
            check_schema(schema[key], f"{path}.{key}")


def type_matches(value, expected):
    if isinstance(expected, list):
        return any(type_matches(value, item) for item in expected)
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }[expected]()


def validate(value, schema, path="$", errors=None):
    errors = [] if errors is None else errors
    if "if" in schema:
        condition_errors = validate(value, schema["if"], path, [])
        if not condition_errors and "then" in schema:
            validate(value, schema["then"], path, errors)
    if "type" in schema and not type_matches(value, schema["type"]):
        expected = schema["type"]
        if isinstance(expected, list):
            expected = " or ".join(expected)
        errors.append(f"{path}: expected {expected}")
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
        min_items = schema.get("minItems", 0)
        if len(value) < min_items:
            errors.append(f"{path}: must contain at least {min_items} item(s)")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], f"{path}[{index}]", errors)
    if isinstance(value, str):
        min_length = schema.get("minLength", 0)
        if len(value) < min_length:
            errors.append(f"{path}: must contain at least {min_length} character(s)")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: does not match required pattern")
    return errors


def report_schema_error(exc):
    print(f"ERROR: verdict: $: {exc}", file=sys.stderr)


def main(argv):
    if len(argv) == 3 and argv[1] == "--check-schema":
        try:
            check_schema(read_json(argv[2]))
        except (OSError, json.JSONDecodeError, SchemaError) as exc:
            report_schema_error(exc)
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
        report_schema_error(exc)
        return 1
    errors = validate(value, schema)
    if errors:
        print(f"ERROR: verdict: {errors[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
