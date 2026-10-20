#!/usr/bin/env python3
"""Validate verdict JSON with the small, explicitly supported schema subset."""
import json
import re
import sys
from pathlib import Path


KEYWORDS = {"$schema", "title", "type", "required", "properties", "additionalProperties",
            "items", "enum", "minItems", "minLength", "pattern", "if", "then"}
KNOWN_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})
REGISTRY_PATH = Path(__file__).resolve().parent.parent / "harness-registry.json"
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
class SchemaError(Exception):
    pass


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def read_bounded_text(path):
    """Read at most MAX_OUTPUT_BYTES, refusing larger output before decoding it."""
    with open(path, "rb") as stream:
        data = stream.read(MAX_OUTPUT_BYTES + 1)
    if len(data) > MAX_OUTPUT_BYTES:
        raise ValueError(f"output exceeds {MAX_OUTPUT_BYTES} bytes")
    return data.decode("utf-8")


SCAN_BUDGET = 16 * MAX_OUTPUT_BYTES
ATTEMPT_COST = 64
# A JSON object can begin only at "{", JSON whitespace, then '"' or '}' (RFC 8259; json.decoder.WHITESPACE).
OBJECT_START = re.compile(r'\{[ \t\n\r]*["}]')
_DECODER = json.JSONDecoder()


def top_level_objects(text):
    """Return every top-level JSON object in text, left to right, or raise ValueError."""
    objects = []
    pos = 0
    spent = 0
    while True:
        match = OBJECT_START.search(text, pos)
        if match is None:
            return objects
        start = match.start()
        try:
            value, end = _DECODER.raw_decode(text, start)
        except RecursionError:
            raise ValueError("JSON nests too deeply to read") from None
        except json.JSONDecodeError as exc:
            if exc.msg.startswith("Unterminated string"):
                scanned = len(text) - start
            else:
                scanned = exc.pos - start
            spent += ATTEMPT_COST + scanned + exc.pos // 16
            pos = start + 1
        else:
            spent += ATTEMPT_COST + (end - start)
            objects.append(value)
            pos = end
        if spent > SCAN_BUDGET:
            raise ValueError("output is too costly to scan for a JSON object")


def _last_object(text, accept=lambda value: True):
    """Return the last top-level JSON object in text that accept() takes, or None."""
    for value in reversed(top_level_objects(text)):
        if accept(value):
            return value
    return None


def final_answer_text(output):
    """Return the result text of the last CLI envelope, or the whole output if there is none."""
    envelope = _last_object(
        output,
        lambda value: value.get("type") == "result" and isinstance(value.get("result"), str),
    )
    return output if envelope is None else envelope["result"]


def extract_last_json_object(output):
    """Extract the last top-level object from the final answer only; never earlier events."""
    value = _last_object(final_answer_text(output))
    if value is None:
        raise ValueError("output contains no JSON object")
    return value


def provider_json_schema_flag(provider):
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    providers = registry["providers"]
    if provider not in providers:
        for key, spec in providers.items():
            if provider in spec.get("legacy_names", []):
                provider = key
                break
        else:
            raise ValueError(f"unknown provider: {provider}")
    return providers[provider]["structured_output"]["json_schema_flag"]


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
        except (OSError, ValueError, RecursionError, SchemaError) as exc:
            report_schema_error(exc)
            return 1
        return 0
    if len(argv) == 5 and argv[1] == "--after-run":
        provider, schema_path, output_path = argv[2:]
        try:
            flag = provider_json_schema_flag(provider)
            schema = read_json(schema_path)
            check_schema(schema)
            if flag is None:
                output = read_bounded_text(output_path)
                value = extract_last_json_object(output)
                mode = "after-run"
            else:
                value = json.loads(read_bounded_text(output_path))
                mode = "flag"
        except (OSError, ValueError, RecursionError, SchemaError, KeyError) as exc:
            report_schema_error(exc)
            return 1
        errors = validate(value, schema)
        if errors:
            print(f"ERROR: verdict: {errors[0]}", file=sys.stderr)
            return 1
        print(f"mode={mode}")
        return 0
    if len(argv) == 3 and argv[1] == "--receipt":
        try:
            receipt = read_json(argv[2])
            from observe_output import final_answer
            raw = Path(receipt["log_path"]).read_bytes()
            answer = final_answer(receipt["provider"], raw) or ""
            value = extract_last_json_object(answer)
            schema = read_json(REGISTRY_PATH.parent / "schemas/review-verdict.schema.json")
            errors = validate(value, schema)
            if errors:
                raise SchemaError(errors[0])
            print(value["verdict"])
        except (OSError, ValueError, KeyError, TypeError, RecursionError, SchemaError) as exc:
            report_schema_error(exc)
            return 1
        return 0
    if len(argv) != 3:
        print("usage: validate_verdict.py <schema> <json-file> | --check-schema <schema> | --after-run <provider> <schema> <output-file>", file=sys.stderr)
        return 2
    try:
        schema = read_json(argv[1])
        check_schema(schema)
        value = read_json(argv[2])
    except (OSError, ValueError, RecursionError, SchemaError) as exc:
        report_schema_error(exc)
        return 1
    errors = validate(value, schema)
    if errors:
        print(f"ERROR: verdict: {errors[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
