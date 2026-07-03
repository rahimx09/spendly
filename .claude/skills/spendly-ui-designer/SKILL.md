---
name: spendly-ui-designer
description: Generates and redesigns Jinja2/Flask UI pages and components for the Spendly expense tracker (github.com/rahimx09/spendly), matching its existing warm-editorial fintech design system exactly. Use this skill whenever the user asks to design, create, build, style, or redesign any page or UI piece for Spendly — phrases like "design the dashboard page," "create UI for expense list," "build a component for category filters," "redesign the settings page," or any Spendly-related frontend/UI/CSS request. Also use it if the user just says "add a page for X" or "make X look better" inside the spendly repo. Do not use for backend/route logic, database models, or non-Spendly projects.
---

# Spendly UI Designer

Generates production-ready Jinja2 templates + CSS for Spendly, a Flask expense tracker. No React, no build step — this is server-rendered HTML with one hand-written global stylesheet.

## Before doing anything: read the live files

Token values below are a snapshot. The repo is the source of truth and may have drifted since. Every time this skill runs:

1. Read `templates/base.html` (layout shell, nav, footer, block structure)
2. Read `static/css/style.css` (design tokens + every existing class)
3. Skim `templates/` for a page that's visually close to what's being asked for (e.g. `landing.html` for marketing-style sections, `login.html`/`register.html` for form patterns)

If what you find conflicts with this file, **trust the repo** and proceed — but mention the drift to the user in your Design Notes so this skill can be updated.

## Design tokens (Spendly design system)

```css
--ink: #0f0f0f;            --paper: #f7f6f3;           --accent: #1a472a;      /* forest green */
--ink-soft: #2d2d2d;       --paper-warm: #f0ede6;      --accent-light: #e8f0eb;
--ink-muted: #6b6b6b;      --paper-card: #ffffff;      --accent-2: #c17f24;    /* mustard */
--ink-faint: #a0a0a0;                                   --accent-2-light: #fdf3e3;
--border: #e4e1da;         --danger: #c0392b;
--border-soft: #eeebe4;    --danger-light: #fdecea;

--font-display: 'DM Serif Display', Georgia, serif;   /* headings only */
--font-body: 'DM Sans', system-ui, sans-serif;         /* everything else */

--radius-sm: 6px;   --radius-md: 12px;   --radius-lg: 20px;
--max-width: 1200px;   --auth-width: 440px;
```

**The vibe:** warm-paper editorial fintech, not generic blue/gray SaaS. Off-white paper background, near-black ink text, forest green as the one confident accent, mustard as a rare secondary accent (badges, category dots), serif display font for headings/emphasis, sans for everything functional. Currency is `₹`. Brand glyph is `◈` (unicode, not an image).

**Spacing:** loosely an 8px grid (0.5rem increments). Cards use `1.25rem–2rem` padding. Section padding is generous (`4–6rem` vertical on marketing-style sections, `2–3rem` on app-like pages).

**Reusable classes already in `style.css` — check these before inventing new ones:**
| Pattern | Classes |
|---|---|
| Buttons | `.btn-primary` (solid ink, hover→accent), `.btn-ghost` (outlined), `.btn-submit` (full-width form button) |
| Forms | `.form-group`, `.form-input`, `.auth-error` |
| Cards | `.auth-card`, `.feature-card`, `.mock-card` / `.mock-stat` (dashboard-style stat cards — good starting point for new stat widgets) |
| Nav/shell | `.navbar`, `.nav-inner`, `.nav-brand`, `.nav-links`, `.nav-cta` |
| Modal | `.modal`, `.modal-backdrop`, `.modal-dialog`, `.modal-close` (JS toggles `.is-open`) |
| Page shells | `.legal-page` (narrow content pages), `.hero`/`.features`/`.cta-section` (marketing sections) |

Reusing a class beats writing a near-duplicate one. Only add new CSS for genuinely new UI (e.g. an expense table, a category chip, a chart legend).

## Icons

Use `assets/icons.svg.md` (bundled with this skill) — it has ~47 real Lucide icons as verbatim inline `<svg>` markup, all using `stroke="currentColor"` so they inherit text color automatically. **Copy the `<path>`/`<circle>`/etc. shape data exactly, character for character. Never hand-write or guess an SVG path's `d` value** — a wrong path silently renders a broken or blank icon. If a needed icon isn't in the bundled set, say so rather than improvising one; the user can pull it from lucide.dev and it can be added to the bundle.

It's fine to drop the bundled snippet's `xmlns`/`width`/`height` attributes when embedding inline and sizing via CSS (`.icon svg { width: 18px; height: 18px; }`) — those are cosmetic and CSS overrides them anyway. What must never change is the shape data itself.

Typical usage inline in a template:
```html
<span class="icon">{# paste the <svg>...</svg> block here #}</span>
```
Size icons with CSS (`.icon svg { width: 18px; height: 18px; }`) rather than editing the SVG's own width/height attributes, so sizing stays consistent and centrally controlled.

## Workflow

1. **Clarify inputs** if not given: page/component name, what data it displays, any constraints. If genuinely ambiguous (e.g. unclear what fields an "expense" has, or the request conflicts with an existing pattern), ask — don't guess and generate the wrong thing.
2. **Read the live repo files** (see above).
3. **Plan before coding:** decide layout, which existing classes get reused, which are new, where icons go.
4. **Generate**, in this order, every time:
   1. **UI Structure** — a short brief: layout + key sections, and the 2-3 UX decisions that matter (why this layout, not an essay).
   2. **Code** — the actual Jinja2 template (extends `base.html`, fills `{% block content %}`) plus any new CSS as a clearly marked addition to append to `static/css/style.css` (with a section comment header matching the existing file's `/* ---- Section ---- */` convention). Full files or clean diffs — never a fragment dump with no home.
   3. **Design Notes** — which existing classes were reused, what's new and why, any repo drift noticed in step 2.
5. **Self-check before returning:**
   - Card-based layout using `--radius-sm/md/lg`, not arbitrary radii
   - Colors only from the token list above — no invented hex values
   - Spacing roughly on the 8px grid, consistent with sibling pages
   - Icons are copy-pasted from the bundled reference, sized via CSS
   - Headings use `--font-display`, body/UI text uses `--font-body` — not mixed arbitrarily
   - No inline `style=""` attributes for anything reusable — it belongs in `style.css`
   - Responsive: check against the existing breakpoints (`900px`, `700px`, `600px`) and add a media query if the new layout needs one

## Explicitly avoid

- Generic/dated UI: default browser form controls, Bootstrap-looking components, drop shadows/gradients that clash with the flat warm-paper look, off-palette colors
- Unstructured code dumps: never return code without the UI Structure brief above it
- Reinventing existing patterns (new button style when `.btn-primary`/`.btn-ghost` already fit)
- Introducing a frontend framework, build step, or icon package — this project has none and isn't adding one

## Output when running in Claude Code (repo checked out)

Edit/create the actual files in `templates/` and `static/css/style.css` directly rather than only printing code blocks, since the user works this way. Still show the UI Structure brief and Design Notes in the chat response.
