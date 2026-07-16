# SPEC: Software Engineering / SDLC page

Status: **Approved** — implementation in progress (see `docs/implementation-SDLC.md`).

## 1. Motivation

A public LinkedIn post highlighted [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills):
24 skills for coding agents, organized into six software-development-lifecycle
(SDLC) phases — **Define, Plan, Build, Verify, Review, Ship** — rendered as a
six-column colored "map," each phase mapped to a matching slash command
(`/spec`, `/plan`, `/build`, `/test`, `/review`, `/ship`).

SkillDeck currently only groups skills by **capability** (`kitchen/config.py:
CAPABILITIES` — "Create & edit documents", "Build web pages & UI", etc.),
which answers "what does this skill help me *do*." The SDLC phase model
answers a different question: "*when* in the software development lifecycle
do I use this." The request is to add a page in that second style, scoped
only to coding-agent/software-engineering skills, and to bring in
`addyosmani/agent-skills` as a source (Anthropic's and Google's official
repos are already registered in `data/sources.json`).

## 2. Scope decision

Two designs were considered:

- **(A) Second dimension on the existing homepage Wizard** — rejected. The
  user explicitly asked for a single, separate page/nav tab, not a second
  filter axis mixed into the capability-based catalog.
- **(B) New standalone top-level page, own nav tab** — **chosen**. A page
  named **"Software Engineering / SDLC"**, peer to the existing "Catalog" /
  "Sources" / "About" tabs, scoped only to skills that are part of a
  software-engineering lifecycle. The existing capability-based homepage
  Wizard is untouched.

## 3. Data model

A new, independent, nullable classification axis: `lifecycle_phase`.

- Values: `"define" | "plan" | "build" | "verify" | "review" | "ship" | null`.
- Lives at the same level as `capability_id` on a skill record
  (`data/skills.json`) and is carried through per-`skill_ref` in
  `data/kb.json` (NOT per capability-entry, since different skills sharing a
  capability bucket can land in different phases, or in no phase at all).
- `null` means "not a software-engineering-lifecycle skill" (e.g. document
  creation, design/branding, spreadsheet analysis) — most existing
  capabilities (`documents`, `design`, `data-analysis`, `cloud-ops`) will
  contain a mix of phase-tagged and null skills; `frontend`/`testing`/
  `agent-building`-flavored skills are expected to skew non-null.
- `LIFECYCLE_PHASES` (`kitchen/config.py`), same `{id, label, order}` shape
  as `CAPABILITIES`:
  ```python
  LIFECYCLE_PHASES = [
      {"id": "define", "label": "Define", "order": 1},
      {"id": "plan", "label": "Plan", "order": 2},
      {"id": "build", "label": "Build", "order": 3},
      {"id": "verify", "label": "Verify", "order": 4},
      {"id": "review", "label": "Review", "order": 5},
      {"id": "ship", "label": "Ship", "order": 6},
  ]
  ```

### Schema changes (`kitchen/schemas.py`)

- `SKILLS_SCHEMA`: add nullable `lifecycle_phase` enum property (not
  required).
- `KB_SCHEMA`: add top-level `lifecycle_phases` array (required, mirrors
  `capabilities`); add nullable `lifecycle_phase` enum property to each
  `skill_refs` item (not required).

## 4. Pipeline: new `phase` stage

A new agent-driven stage, `kitchen/phase.py`, structurally mirroring the
existing `cluster.py` prepare/apply split (see `CLAUDE.md`'s "The data
pipeline" section for the general pattern):

- `prepare_phase_input()` — reuses `cluster._elect_heads()` and
  `cluster.get_skill_text()` for deterministic head election (no duplicated
  logic). Operates only on skills that already have a real `capability_id`
  (phase classification depends on capability having been decided first).
  Writes `.kitchen_cache/phase_input.json`: `already_assigned` (human-locked,
  already-valid-phase heads) + `heads_needing_classification` (skill_id,
  name, description, body_excerpt, capability_label, members).
- An agent (Claude Code) reads that file and decides, per head, either one
  of the six phase ids or `null`, writing
  `.kitchen_cache/phase_output.json`: `{"assignments": {"<skill_id>":
  "<phase_id-or-null>"}}`.
- `apply_phase_assignments()` — reads that back, resolves each head's phase
  (falling back to `null` with a warning for unrecognized values), and
  propagates it to every member of the head's duplicate cluster.
- New CLI subcommands: `phase-prepare`, `phase-apply` (mirrors
  `cluster-prepare`/`cluster-apply` in `kitchen/cli.py`).
- Pipeline order: `... -> cluster-prepare/apply -> phase-prepare/apply ->
  cards-prepare/apply -> emit`.
- `kitchen/emit.py`: stamps `lifecycle_phase` onto every `skill_refs[mid]`
  entry, and emits `LIFECYCLE_PHASES` as top-level `lifecycle_phases` in
  `kb.json`.
- `.claude/commands/skilldeck-ingest.md`: gets a new numbered section for
  this stage, between capability clustering and card writing.

## 5. New source

Add to `data/sources.json` (`SOURCES_SCHEMA`-conformant):

```json
{
  "id": "addyosmani-agent-skills",
  "org": "addyosmani",
  "repo_url": "https://github.com/addyosmani/agent-skills",
  "kind": "community",
  "vendor": null,
  "default_license": "MIT",
  "notes": "24 SDLC-phase skills (Define/Plan/Build/Verify/Review/Ship) with matching slash commands; inspiration for SkillDeck's Software Engineering / SDLC page."
}
```

## 6. Frontend: `/sdlc` page

- No shared `Layout.astro` exists in this codebase today — every page
  (`index.astro`, `sources.astro`, `about.astro`, `skill/[id].astro`)
  hand-copies the same header/footer/head markup. The new page follows that
  existing convention rather than introducing a new abstraction.
- New nav link `<a href="/sdlc">Software Engineering / SDLC</a>` added to
  all 5 pages' header blocks (the 4 existing pages + the new page itself),
  matching existing active/inactive link classes.
- `site/src/utils/phaseColors.ts` (new — not `src/lib/`, which collides with
  the root `.gitignore`'s `lib/` rule for Python venvs) — hardcoded Tailwind
  class strings per
  phase (header background + chip colors), following the same
  hardcode-per-category convention `Badge.astro` already uses for
  provenance/epistemic colors, rather than extending `tailwind.config.mjs`.
- `site/src/pages/sdlc.astro` (new) — **static**, no Preact island (all six
  columns render at once from `kb.json` at build time, no client-side
  filtering needed, matching the reference image which shows all phases
  simultaneously). Flattens every `entries[].skill_refs` into skill
  records, filters out `lifecycle_phase == null`, groups into six columns
  ordered by `kb.lifecycle_phases`. Each skill renders as a small name chip
  linking to `/skill/{id}` (the existing skill detail route) — not the full
  `SkillCard.astro`, since the reference layout is dense name chips. Empty
  phases show a placeholder message. Includes an attribution line crediting
  Addy Osmani's `agent-skills` repo as the layout's inspiration.
- `site/src/components/Wizard.tsx` — add `lifecycle_phase` to the `SkillRef`
  interface and a `LifecyclePhase`/`lifecycle_phases` to the `KB` interface,
  per the project's convention of keeping these TS interfaces in sync with
  `kitchen/schemas.py`'s `KB_SCHEMA`, even though `Wizard.tsx` itself doesn't
  use the new fields.

**Out of scope for this pass** (explicitly deferred, not forgotten): a
`phase` badge type in `Badge.astro`; surfacing `lifecycle_phase` on the
individual skill detail page (`skill/[id].astro`).

## 7. Data population

1. Register the new source (§5).
2. Run the full pipeline for real against the live GitHub API
   (`GITHUB_TOKEN` available): `ingest -> canonicalize -> dedup -> rank ->
   cluster-prepare -> [agent classifies new heads] -> cluster-apply ->
   phase-prepare -> [agent classifies lifecycle_phase for ALL
   capability-assigned heads, since this is a brand-new field — full
   backfill, not just the new skills] -> phase-apply -> cards-prepare ->
   [agent writes cards for new heads] -> cards-apply -> emit`.
3. Per repo convention, `data/skills.json`/`data/kb.json` are committed as
   part of this SDD process's own commit for this step (see
   `docs/implementation-SDLC.md`), not left silently uncommitted — this spec
   intentionally overrides the kitchen's normal "leave regenerated JSON for
   the user to review" default because the SDD process requires every
   completed step to be committed immediately.

## 8. Acceptance criteria

1. `python -m pytest kitchen/tests/` (or `python -m unittest discover -s
   kitchen/tests`) passes, including new/updated tests for `phase.py`,
   schema, emit, and CLI dispatch.
2. `python -m kitchen emit` succeeds (schema validation passes);
   `data/kb.json` contains a top-level `lifecycle_phases` array and
   non-null `lifecycle_phase` values on software-engineering skills.
3. `cd site && npm run build` succeeds (`astro check` type-checks cleanly)
   with `/sdlc` as a generated route.
4. Manual check in a browser: all 5 nav tabs present and link correctly with
   correct active-state highlighting; `/sdlc` renders six phase columns with
   skills grouped correctly, each skill links to its `/skill/[id]` detail
   page; layout holds in both light and dark theme.
