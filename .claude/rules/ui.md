---
paths:
  - "src/components/**"
  - "src/pages/**"
  - "**/*.css"
---

# UI work — load-bearing pointers

You are touching UI files. Before any edit:

1. Read `.agents/skills/shadcn-luma/SKILL.md` — verify Luma is applied
   (components.json) BEFORE adding any shadcn component.
2. Read `docs/DESIGN.md` if it exists — project-specific overrides
   (e.g. density rules) take priority.
3. Never hand-edit files in `src/components/ui/`. No arbitrary Tailwind
   bracket values when a scale token is close.
