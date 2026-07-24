# UI/UX Improvement Log

Status tracker for the frontend UI/UX audit performed on `site/`. Each
improvement is implemented, validated, and committed independently. This
file is updated after every completed unit of work — treat it as the
source of truth for what's done vs. planned.

## Methodology

- Read every component/page under `site/src/` (Layout, SkillCard,
  SkillExplorer, Badge, TrustGlyph, Doctor, all pages, all style/util
  files).
- Ran the app locally (`npm run dev`) and captured Playwright screenshots
  at mobile (375×900) and desktop (1440×1000) for every route.
- Established baseline: `npm run lint` clean, `astro check` clean (0
  errors), `npm run test` 50/50 passing.
- Findings ranked by user impact × frequency (how many pages/sessions hit
  it) × consistency benefit × implementation confidence, discounted by
  regression risk. Cosmetic-only items were dropped rather than padding
  the list to 10.

## Prioritized improvements

### 1. Mobile navigation is unusable — no collapse behavior (P0)
**Where:** `src/layouts/Layout.astro` (shared header, every page)
**Problem:** The header renders all 7 nav links (`Skill Catalog`,
`General Skills`, `SDLC`, `Similarity`, `Skill Doctor`, `FAQ`, `About`) in
one `flex` row with no wrap handling and no mobile alternative. At a
375px viewport every multi-word label line-wraps individually, producing
a ~90px tall, visually broken header on every single page before any
content is visible. Confirmed via screenshot on `/`, `/sdlc`,
`/general-skills`, `/faq`, `/doctor`.
**Fix:** Add a mobile hamburger toggle (Tailwind + a few lines of
vanilla JS matching the existing `ThemeToggle.astro` pattern — no new
dependency) that shows a slide-down/overlay nav below `md`, and hide the
inline nav row below `md`. Preserve the desktop row unchanged.
**Acceptance criteria:**
- At <768px, header height is constant (~64px) across all 7 pages; nav
  links are reachable via a toggle button, each a real tappable target
  (≥40px height).
- At ≥768px, layout is visually unchanged from before.
- Keyboard-operable (toggle is a real `<button>`, closes on link click
  and `Escape`).
- `npm run build` and `npm run test:e2e` still pass.

### 2. Install-command tool tabs don't work at all — for anyone (P0)
**Where:** `src/components/SkillCard.astro` (rendered on every
`/skill/[id]` page — 150+ pages — and embedded standalone)
**Problem:** The per-tool install-command tabs use a CSS-only
radio+label trick, but the radio inputs were `class="hidden peer"`.
Tailwind's `hidden` is `display:none`, which removes the input from the
tab order entirely — a keyboard or screen-reader user could never reach
or switch these tabs. **While fixing this, found a deeper pre-existing
bug: the entire tab-switching mechanism was non-functional for every
user, mouse included.** The per-tool CSS rules lived in
`<style is:global>{`...`}</style>`, but Astro never evaluates a
`{jsExpression}` child of `<style>` — it renders the literal,
un-interpolated JS source text (`${t.id}` verbatim) into the page, which
is not valid CSS and does nothing. Confirmed via a clean checkout: click
+ arrow-key tests both showed the `:checked` radio updating correctly,
but the panel's `display` stayed `none` and the label stayed
default-gray — clicking a tool never actually revealed its install
command. The adjacent copy-command button also sets `focus:outline-none`
with no replacement focus ring.
**Fix:** Replace `hidden` on the radio inputs with Tailwind's `sr-only`
(visually hidden, still focusable). Move the per-tool CSS generation
into frontmatter (real JS, evaluated correctly) and render the computed
string via `<style is:global set:html={tabCss} />` instead of an
unevaluated template-literal child — this makes tab-switching work for
mouse users for the first time as a side effect of the accessibility
fix, verified against both dev SSR and the static `astro build` output.
Added a `:focus-visible` outline rule to the same computed CSS. While auditing
this pattern, grepped the whole `src/` tree for `focus:outline-none`
and found the identical missing-replacement-ring bug in 4 more spots:
`SkillCard.astro`'s alternatives `<summary>` toggle, `SkillExplorer.tsx`'s
skill-list-item button, its install-tool tab buttons, its install-copy
button, and `SimilarityGalaxy.tsx`'s graph-node buttons (which also
never revealed their name label on keyboard focus, only on mouse hover).
Fixed all of them with the same `focus-visible:ring-2
focus-visible:ring-accent` pattern (and `group-focus-visible:opacity-100`
for the galaxy label).
**Acceptance criteria:**
- Tabbing through a skill detail page reaches every tool tab and the
  copy button, each with a visible focus indicator.
- Arrow keys / Space toggle the radio group per native semantics.
- Every other fixed control (skill list items, SkillExplorer install
  tabs/copy button, similarity graph nodes) shows a visible ring on
  keyboard focus and no change on mouse click.
- No visual regression for mouse users (screenshot diff on one skill
  page, light + dark).
- `npm run test:e2e` still passes.

### 3. Dead Tailwind color classes silently drop styling sitewide (P1)
**Where:** `src/pages/index.astro`, `src/pages/about.astro`,
`src/components/Doctor.tsx`, `src/pages/skill/[id].astro` (~80
occurrences)
**Problem:** These files use shade numbers that don't exist in Tailwind's
default scale (only `50,100,...,900,950` are real) — e.g. `zinc-150`,
`zinc-250`, `zinc-305`, `zinc-350`, `zinc-450`, `zinc-455`, `zinc-550`,
`zinc-650`, `zinc-750`, `zinc-850`. Tailwind silently emits no CSS for an
unrecognized utility, so the intended muted-gray text/border styling
never applies — the element just inherits whatever color surrounds it.
This is invisible in casual review (no console error) but is a real,
widespread, silent styling bug and a consistency risk for anyone copying
these patterns forward.
**Fix:** Mechanical find/replace to the nearest real Tailwind shade
(150/250/350→ round to nearest of 100/200/300/400; 850/750/650/550/450→
round to nearest of 800/700/600/500), verified with a grep sweep for the
regex used during the audit, then a visual diff of the affected pages.
**Acceptance criteria:**
- `rg 'zinc-(1[0-9][0-9]|2[0-9][0-9]|3[0-9][0-9]|4[0-9][0-9]|5[0-9][0-9]|6[0-9][0-9]|7[0-9][0-9]|8[0-9][0-9]|9[0-9][0-9])\b' src` (excluding the valid `900`) returns zero matches outside the standard scale.
- Screenshot diff of `/`, `/about`, `/doctor` shows only color-depth
  changes, no layout shift.
- `npm run lint`, `astro check`, `npm run test` stay clean.

### 4. Missing skip-to-content link + silent copy-button state (P1)
**Where:** `src/layouts/Layout.astro`, `SkillCard.astro`,
`SkillExplorer.tsx` copy actions
**Problem:** Every page requires a keyboard user to tab through the full
7-item nav before reaching `<main>` — no skip link. Separately, all
"Copy" buttons (prompt copy, install-command copy, skill-ID copy)
communicate success only via a visual icon/text swap; screen-reader users
get no announcement that the copy succeeded.
**Fix:** Add a standard visually-hidden "Skip to content" link as the
first focusable element in `Layout.astro`, targeting a new `id="main"` on
the `<main>` element. Add a shared `aria-live="polite"` status region (or
`aria-live` on the existing "Copied" swap) so assistive tech announces
the copy confirmation.
**Acceptance criteria:**
- First `Tab` press on any page reveals a "Skip to content" link that
  jumps focus to `<main>`.
- A screen reader (or accessibility tree inspection) announces "Copied"
  after a copy action.
- No visual change for sighted mouse users.

## Explicitly out of scope

- Rewriting `SkillCard.astro` vs. `SkillExplorer.tsx`'s duplicated detail
  markup into a shared component — the two intentionally use different
  rendering models (static Astro vs. Preact island); consolidating is a
  larger architectural change the task asks us to avoid absent a
  specific ask.
- Any change to `data/kb.json`, the kitchen pipeline, or the 8
  capabilities/6 tools taxonomy.
- New dependencies — every fix above uses Tailwind + existing patterns
  already in the codebase (see `ThemeToggle.astro` for the vanilla-JS
  toggle style to match).

## Progress log

| # | Improvement | Status | Commit |
|---|---|---|---|
| — | Audit + this plan | Done | (this commit) |
| 1 | Mobile navigation collapse | Done | df40070 |
| 2 | Install-tab non-functional + keyboard access | Done | (this commit) |
| 3 | Dead Tailwind color classes | Pending | — |
| 4 | Skip link + copy-button live region | Pending | — |
