---
name: react-conventions
description: Conventions for writing React components, hooks, and TypeScript in Vite + React + Tailwind projects in this studio. MUST be used whenever creating or refactoring a component, page, custom hook, or context; wiring data fetching; or adding types. Also use when deciding where a new file goes or whether logic belongs in a hook vs a component.
---

# React / TypeScript conventions

## File placement (check the repo's existing pattern first — conform, don't invent)

- Pages → `src/pages/<PageName>.tsx` (one route = one page component)
- Shared UI → `src/components/<domain>/<Component>.tsx`; shadcn primitives stay in
  `src/components/ui/` untouched (see `shadcn-luma` skill)
- Hooks → `src/hooks/use<Thing>.ts` — any logic used by 2+ components, or any
  component whose non-JSX logic exceeds ~30 lines, gets a hook
- Types → the project's canonical types file/folder (check AGENTS.md; e.g.
  `src/types/`). Never redeclare a domain type locally — import it.

## Component rules

- Function components + hooks only. No classes.
- Props: explicit interface above the component, no `any`, no implicit `children`.
- Data fetching lives in hooks, never inline in JSX; components receive data + render.
- All backend calls go through the project's API layer/client (check AGENTS.md — e.g.
  "frontend never calls the DB directly, always the Worker"). Adding a direct DB/SDK
  call in a component is a failed task.
- Loading, empty, and error states are part of the feature — a component that only
  handles the happy path does not meet exit criteria.
- i18n: if the project is multilingual, no user-facing hardcoded strings — use the
  project's translation mechanism.

## Hook rules

- One responsibility per hook; return a typed object, not positional tuples (except
  trivial `[value, setValue]`).
- Effects: every `useEffect` needs a correct dependency array and a cleanup if it
  subscribes/schedules. If an effect syncs state from props, reconsider — derive it.

## TypeScript rules

- `strict` mode is assumed. No `any`, no `@ts-ignore` (use `@ts-expect-error` with a
  comment only when unavoidable).
- Exit criterion for every task: `npx tsc --noEmit` green.

## Self-verification (binary)

- [ ] File is where the repo's pattern says it goes
- [ ] No domain type redeclared; imports from canonical types
- [ ] No direct backend/DB call from a component
- [ ] Loading/empty/error states handled
- [ ] tsc green
