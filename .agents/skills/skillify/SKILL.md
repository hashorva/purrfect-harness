---
name: skillify
description: >
  Graduate a battle-tested procedure into a new SKILL.md in .agents/skills/.
  MUST be used at mission end (after the last feature passes), whenever the
  code-reviewer's flywheel notes flag the same failure class or procedure twice,
  or when the user says "skillify this", "make this a skill", or "we keep doing
  this". Orchestrator-only. Produces skills from EVIDENCE (PROGRESS.md, review
  findings, git log) — never from speculation.
---

# Skillify — evidence-based skill graduation

## Step 1 — Gather evidence (disk, not memory)

Read: PROGRESS.md (whole mission), the mission's review findings / flywheel
notes, `git log --oneline` for the mission's commits, and the task files in
docs/tasks/. Session memory is unreliable (compaction); the loop's artifacts
are the record.

## Step 2 — Graduation criteria (ALL must hold, else stop)

- **Recurrence:** the procedure or correction appeared ≥2 times across tasks
  or missions. Once = anecdote, not a skill.
- **Determinism:** the steps were the same each time and can be written as an
  ordered sequence with no unstated judgment calls.
- **Verifiability:** success is checkable (command output, file state, binary
  checklist) — "looks right" does not graduate.
- **Not already covered:** grep existing .agents/skills/ descriptions; if an
  existing skill covers it, propose a PATCH to that skill instead (smaller is
  better — one new line beats one new file).

## Step 3 — Draft (agentskills.io format, house style)

- Frontmatter: `name` (slug) + `description` that front-loads TRIGGERS
  ("MUST be used when...") — the description is the only thing loaded at
  startup, it does the routing.
- Body: the failure this prevents (one paragraph) → numbered procedure with
  exact commands → binary self-verification checklist → "Never do these".
- Keep it lean; details go in a references/ subfolder only if truly needed.
- Agnostic core + "check AGENTS.md / docs/*.md for project specifics" pointers
  — never hardcode one repo's paths into a studio-wide skill.

## Step 4 — Human gate (mandatory)

Present: the evidence (which PROGRESS entries / findings triggered this), the
full draft SKILL.md, and whether it's a NEW skill or a PATCH. Only after
approval: write to .agents/skills/<name>/SKILL.md (propagates via symlinks),
commit as `docs(skills): graduate <name> from mission <goal>`. If the skill is
studio-wide, remind the human to copy it to the agent-harness kit and other
repos.

## Never

- Never create a skill from a single occurrence or a hypothetical.
- Never duplicate an existing skill's territory — patch it.
- Never skip the human gate; skills are law for every future worker.
