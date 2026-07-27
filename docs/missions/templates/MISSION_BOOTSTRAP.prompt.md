# Mission bootstrap

Follow `.agents/skills/mission-init/SKILL.md` exactly — create
`docs/missions/<YYYYMMDD-slug>/` with GOAL.md, features.json, PROGRESS.md, and
`tasks/T-001.md` from `docs/missions/templates/`, never freehand.

Default brain is Opus (Cursor intake may brief first; Opus weighs and orchestrates).
Load `docs/missions/MODEL_ROUTING.md` at GATE 0. Run
`bash scripts/fleet-inventory.sh` and **always show** the seat→model map for
human confirm/swap before any dispatch.
