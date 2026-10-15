# P-2: structured-output flags per CLI (help text only, no model call)

Probed 2026-10-15 by the Front Desk with `--help` greps; no provider turn was run.

| provider | flag listed in help | note |
|---|---|---|
| claude | `--json-schema <schema>` ("JSON Schema for structured output") | takes the schema text |
| codex | `codex exec --output-schema <FILE>` ("Path to a JSON Schema file describing the model's final response shape") | takes a file path; different name |
| cursor | none (`--output-format text\|json\|stream-json` only) | validate after the run |
| agy | `--json-schema` ("JSON string or path to a schema file") | every agy turn hangs on this Mac, so the flag is listed but unproven |

For T-034: `structured_output.json_schema_flag` is `--json-schema` (claude), `--output-schema` (codex), `null` (cursor), `--json-schema` (agy). The 2A adapter does not send any of these flags; they are recorded only.
