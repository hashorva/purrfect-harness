---
name: shadcn-luma
description: Install, verify, and use shadcn/ui components with the Luma style in any studio project (FinDuck, consulenza360, shyft.me, ...). MUST be used before installing ANY shadcn component, running shadcn init/add/apply, restyling UI, or building any new page or component. Also use when UI "looks wrong" or "doesn't match the design system". Installing default/new-york-style shadcn in a Luma project is a failed task.
---

# shadcn/ui — Luma style (v2, studio-wide)

## The failure this skill prevents

Agents run `npx shadcn@latest init` or `add <component>` with defaults, get the
default/new-york style, and call it done. **Luma is a distinct shadcn style applied
via a preset — it changes component GEOMETRY and SPACING, not only theme colors.**
A component that compiles and renders is NOT proof it's Luma-styled.

## Step 0 — Verify before installing anything (always)

1. Read the project's `docs/DESIGN.md` — it holds project-specific overrides
   (e.g. consulenza360: operational density and 44–52px rows take priority over
   Luma airiness). The skill is the procedure; DESIGN.md is the knowledge.
2. Open `components.json` at repo root. Confirm the project's Luma configuration is
   in place (style/preset recorded there or in DESIGN.md). If it shows plain
   `default` / `new-york` with no Luma preset applied → Luma is NOT applied; do not
   add components on top. Fix per the right step below, or escalate.
3. Spot-check the global CSS: Luma ships its own CSS variable set. Stock shadcn
   defaults = Luma not applied.

## Step 1 — New project setup (greenfield only)

Use shadcn/create or the shadcn CLI with the Vite template, Radix base, pointer
cursors on, and the **current** Luma preset code.

🔴 **Preset codes rotate. Verify before every run — this is not optional and it has
already been skipped once.** Open shadcn/create, select the Luma preset, and copy the
command it generates:

<https://ui.shadcn.com/create?template=vite&base=radix&pointer=true&item=preview>

| Preset code | Status |
| --- | --- |
| `b83suB2Xac` | current — verified on shadcn/create **2026-08-11** |
| `b2D0wqNxT` | superseded — was in this skill unverified for months |

```bash
npx shadcn@latest init --preset b83suB2Xac --base radix --template vite --pointer
```

- `--base radix` — pick Radix UI, **never Base UI** (studio convention).
- `--pointer` — **studio convention: buttons get a pointer cursor.** Real CLI flag
  (`--pointer` / `--no-pointer`, *"enable pointer cursor for buttons"*). Omitting it
  silently gives the default cursor, which reads as "not quite our UI" without ever
  looking broken.

### What the preset code does and does not affect

Know this before blaming a preset for a visual problem:

- `--preset` applies to **`init` and `apply` only**.
- **`add` ignores it** — `npx shadcn@latest add <component>` reads `components.json`
  (e.g. `"style": "radix-luma"`) to decide styling.

**So a rotated preset code does not retroactively change components already installed,
and it does not explain drift in them.** If existing UI stopped looking like Luma, look
instead at: hand-written project components that never went through the CLI, upstream
changes to the style itself between `add` runs, or `docs/DESIGN.md` overrides.

## Step 2 — Applying Luma to an existing app (orchestrator-approved only)

```bash
npx shadcn@latest apply b83suB2Xac    # ALWAYS verify the current code first — see Step 1
```

- `apply` re-installs existing components and updates theme, CSS variables, fonts,
  and icons in one pass — inspect diffs before overwriting local components; prefer
  applying the preset or reinstalling specific components intentionally.
- **Never use `shadcn apply --only theme` when the task is to adopt the full Luma
  style** — Luma changes component geometry and spacing in addition to theme tokens.
- Never approximate Luma by hand-editing CSS or Tailwind config.
- This operation touches every component: it requires an explicit orchestrator task
  and a visual diff of key screens before commit.

## Step 3 — Adding a component (the routine case)

1. Step 0 checks pass.
2. `npx shadcn@latest add <component>` — the CLI reads `components.json` and pulls
   the correctly-styled variant. The recorded config IS the mechanism; that's why
   Step 0 matters.
3. **Never modify files in `src/components/ui/`** — these are shadcn library files,
   not project code. If a primitive must change: reinstall/update via the CLI, or
   wrap/compose it in project code.
4. When adapting existing components manually is unavoidable: update radius, surface
   treatment, shadows, gaps, and control sizing to match Luma — not only theme tokens.

## The `shadcn` package is not only a CLI — check the CSS import

`shadcn/create` may leave a **runtime import** in the project's global CSS:

```css
/* src/index.css */
@import 'shadcn/tailwind.css';
```

That resolves to `node_modules/shadcn/dist/tailwind.css` (Luma `@theme` keyframes and
`@custom-variant` rules), which makes `shadcn` a **real dependency**, not just a CLI you
invoke with `npx`. Consequences seen in production (FinDuck, 2026-08-11):

- `shadcn` sat in **`dependencies`**, pulling `@modelcontextprotocol/sdk`, `express` and
  `msw` — **211 packages** — into every production install.
- `express` hoisted a **CommonJS `cookie@0.7.2`** to the root of `node_modules`, which
  shadowed Astro's ESM `cookie@2.0.1` and made Astro fail to prerender any page at all
  (`Named export 'parseCookie' not found`). The cause looked nothing like its origin.

**Before assuming the package is CLI-only, grep for the CSS import as well as JS/TS
imports** — a `grep` for `from 'shadcn'` finds nothing and proves nothing:

```bash
grep -rn "shadcn/tailwind.css\|from ['\"]shadcn" src/ --include="*.css" --include="*.ts" --include="*.tsx"
```

If the import exists and you need the package out of `dependencies`, **vendor the CSS**
(it is ~95 lines of static rules, no build logic) and repoint the import. Prove the
vendoring is faithful by checking that the **built stylesheet's checksum is unchanged**
before and after — a passing build does not prove the CSS is identical.

## Step 4 — Self-verification before marking done (binary)

- [ ] Project's Luma preset/config confirmed in `components.json` (per Step 0)
- [ ] If `init`/`apply` was run: the preset code was **verified on shadcn/create today**,
      not copied from this file, and `--pointer` was passed
- [ ] New component imported from `@/components/ui/*` (not copied from docs/web)
- [ ] Nothing in `src/components/ui/` was hand-edited
- [ ] No hardcoded hex colors or stock-shadcn tokens introduced — CSS variables only
- [ ] No arbitrary Tailwind bracket values where a scale token is close
      (`mb-14`/`mb-16`, not `mb-[60px]`); no Tailwind config resurrected to
      "inject" theme colors (Tailwind v4 = tokens in CSS `@theme`)
- [ ] Project-specific DESIGN.md overrides respected (e.g. row density)
- [ ] Rendered screen visually consistent with one existing Luma page (compare)
