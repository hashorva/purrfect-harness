---
name: mcp-hygiene
description: How to use MCP servers (Supabase, browser, GitHub, any connector) without polluting the context window. MUST be used whenever a task involves querying an MCP server, verifying database state, fetching external data mid-task, or when a session is getting long and slow. Also use when deciding whether to reach for MCP at all versus a CLI/script.
---

# MCP hygiene — query, persist, drop

## The problem

Every MCP tool definition and every raw MCP result sits in the context window for the
rest of the session. Ten "quick checks" against a DB server = thousands of stale tokens
degrading everything after them. Context rot is architectural (attention is n²), so the
fix is behavioral: **keep knowledge on disk, not in the window.**

## Rules

1. **Prefer a CLI or script over MCP when both exist.** `supabase db push --dry-run`,
   `gh pr view`, a `psql` one-liner, or a small script that writes its output to a file
   is deterministic and leaves ~zero residue. MCP is for interactive verification and
   for capabilities with no CLI equivalent.
2. **Query once, persist immediately.** The moment an MCP result matters beyond the
   current thought, write the distilled version to a file:
   - schema verification → append to the task's PROGRESS.md entry or a `notes/` scratch file
   - fetched reference data → a file in the repo (with provenance)
   Then work from the file, not from re-querying.
3. **Batch your questions.** Before calling, list everything you need from that server
   in this session. One structured query beats five conversational ones.
4. **Read-only by default.** Writes through MCP (DB mutations, posting, publishing) are
   forbidden unless the task file explicitly authorizes that exact write. Schema changes
   NEVER go through MCP (see `supabase-migration` skill).
5. **Verify-then-drop.** MCP's proper role in this harness: verify a state ("did the
   migration land?", "does the endpoint return 200?"), record the boolean + one line of
   evidence in PROGRESS.md, move on. Don't keep raw result payloads around.
6. **Don't load servers you won't use.** If your task file doesn't name an MCP server,
   don't connect one. If your tool loads all servers by default, ignore the ones not
   named in the task.

## Self-check when a session feels sluggish

- Am I re-querying something I already learned? → It should be in a file. Put it there.
- Is a huge tool result sitting mid-history? → Summarize its 2-line conclusion into
  PROGRESS.md; if the tool supports clearing/compacting tool results, do it — and treat
  the need as a signal the task should have been split.
