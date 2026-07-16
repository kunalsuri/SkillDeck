# SPEC-01 — Context Cost Labels, Skill Doctor, and the Concepts Page

**Audience:** an AI coding agent (Sonnet) implementing this end-to-end in the
SkillDeck repository.
**Read `CLAUDE.md` at the repo root first.** This spec assumes you have. Where
this spec and `CLAUDE.md` conflict, this spec wins; where this spec is silent,
`CLAUDE.md` wins.

---

## 1. What you are building, and why

Three user-facing features plus one prerequisite hardening task, in four
phases. Do them **in order** — Phase 0 is a safety prerequisite for Phase 1,
and later phases assume earlier ones are merged.

| Phase | Feature | Problem it solves |
|---|---|---|
| 0 | Make `emit` safe on a fresh clone | Today, re-running `python -m kitchen emit` without the local `.kitchen_cache/` **destroys committed data** (see §3, traps T1/T2). You cannot ship Phase 1 without this. |
| 1 | **Context Cost label** ("nutrition label") | Users install skills with no idea what they cost: token footprint, when they trigger. We compute deterministic metrics offline and show them on every skill card. |
| 2 | **Skill Doctor** (`/doctor`) | The #1 complaint of skill authors is "my skill never fires." A fully client-side linter grades a pasted `SKILL.md` against known trigger/format heuristics. |
| 3 | **Concepts page** (`/concepts`) | Newcomers can't map vocabulary across tools (skill vs. rule vs. hook vs. subagent vs. MCP). One static equivalence table fixes that. |

**Explicitly out of scope** (do not start these, even if they seem adjacent):
cross-tool format translation, skill bundles/"decks", a kitchen-side security
scanning stage, any new network calls anywhere, changes to the
`CAPABILITIES`/`TOOLS`/`LIFECYCLE_PHASES` taxonomies, adding new pipeline
sources, adding an LLM API client, replacing the sharded `data/skill-*.json`
storage.

---

## 2. Ground rules (non-negotiable invariants)

1. **Never hand-edit `data/kb.json` or anything in `mirror/`.** They are
   pipeline output. Regenerate `kb.json` with `python -m kitchen emit` — but
   only after Phase 0 lands, because today that command is destructive on a
   fresh clone.
2. **The site is static-only.** No backend, no API routes, no runtime network
   calls, no imports from `kitchen/` into `site/`. The Skill Doctor must work
   entirely in the browser.
3. **Schema changes are three-way.** Any new field on a skill/kb record must
   land in (a) `kitchen/schemas.py`, (b) the kitchen stage + `kitchen/emit.py`
   that populate it, and (c) the frontend TypeScript interfaces in
   `site/src/components/Wizard.tsx` (and any `.astro` component that consumes
   it). `emit` validates against `KB_SCHEMA` and **raises** on mismatch — if
   you add a field to emit output but not to the schema, emit will fail.
4. **All kitchen JSON writes go through `atomic_write_json`**
   (`kitchen/utils.py`) or `save_skills`. Never write data files directly.
5. **The skills database is sharded.** There is **no `data/skills.json`** on
   disk anymore — skills live in `data/skill-<source_id>.json` and are
   read/written only via `load_all_skills(SKILLS_JSON)` /
   `save_skills(SKILLS_JSON, skills)` in `kitchen/utils.py` (the `SKILLS_JSON`
   path constant is passed but the helpers resolve the shards themselves). Do
   not create a `skills.json` file.
6. **Python tests are `unittest`-style** (`unittest.TestCase` +
   `unittest.mock.patch`), one file per module, run with
   `python -m pytest kitchen/tests/`. No network in tests, ever. Follow the
   existing prepare/apply file-contract testing pattern where relevant.
7. **TypeScript errors are build failures.** `npm run build` runs
   `astro check` first. Trust `site/package.json` for versions (Astro 7,
   Tailwind 4 via `@tailwindcss/vite`, Preact with `compat: true`) — the
   "Astro v4" mention in CLAUDE.md is stale.
8. **Determinism.** Every metric this spec adds must be a pure function of
   committed repository content. Same input → byte-identical output. No
   timestamps in derived metrics except the explicitly specified
   `computed_at`, no randomness, no tokenizer libraries.
9. **No new dependencies** — Python or npm — unless this spec names one. (It
   names none.)
10. **Keep `schema_version` at `1`** in all data files. These changes are
    additive; do not bump versions.

---

## 3. Known traps — read before writing any code

These are real, verified behaviors of the current codebase. Each one will
silently corrupt data or waste hours if you don't plan around it.

- **T1 — Fresh clones have no `.kitchen_cache/`.** It is gitignored. The
  Explainer Card cache (`.kitchen_cache/cards_cache.json`) and the GitHub blob
  cache both start empty in your environment.
- **T2 — `emit` is currently destructive without that cache.** Two ways:
  1. *Cards:* `run_emit()` falls back to a generic `generated_by: "fallback"`
     card when the cache has no entry. Every card in the committed
     `data/kb.json` today is `generated_by: "llm"` — a naive re-emit replaces
     all of them with junk.
  2. *Mirror:* `run_emit()` **deletes every `mirror/*.md`** and rewrites them
     from `get_skill_body()`, which on a cache miss silently returns
     `frontmatter_description` — so a naive re-emit replaces 80 committed
     full skill bodies with one-line stubs.
  Phase 0 exists to fix exactly this. Do not run `python -m kitchen emit`
  before Phase 0 is implemented and its tests pass.
- **T3 — `get_skill_body()` never fails loudly.** It returns the
  frontmatter description as a lookalike fallback. Any code that computes
  body metrics must distinguish "real body" from "description fallback"
  explicitly (this spec's `basis` field), never by guessing from content.
- **T4 — You cannot run the network stages.** `ingest`, `canonicalize`,
  `freshness`, and `python -m kitchen pipeline` (which starts with ingest)
  need the GitHub API and a `GITHUB_TOKEN` you likely don't have. Everything
  in this spec is designed to run offline from committed data + `mirror/`.
  Do not try to warm the cache from the network.
- **T5 — `data/kb.json` must be committed after regeneration.** Vercel never
  runs the kitchen; it builds `site/` from whatever `data/kb.json` is in git.
  `site/src/data/kb.json` is gitignored and copied by `site/prebuild.js` —
  never commit or hand-edit that copy.
- **T6 — jsonschema nullable-enum quirk.** The existing schemas express
  nullable enums as `"type": ["string", "null"], "enum": [..., None]` (Python
  `None` inside the enum list). Match that style exactly for new nullable
  fields.
- **T7 — `save_skills` rewrites shard files wholesale** and refreshes their
  `generated_at`. Expect large-looking-but-mechanical diffs in
  `data/skill-*.json`; that's normal. Do not try to minimize the diff by
  writing JSON manually.
- **T8 — Windows-first project.** Use `pathlib`, always pass
  `encoding="utf-8"` to `open()`, and normalize `\r\n` → `\n` before any
  line-based parsing (both Python and TypeScript).
- **T9 — Playwright e2e tests the *built* site.** `playwright.config.ts`'s
  `webServer` runs `node serve.js` against `site/dist`, and uses
  `channel: 'chrome'`. Run `npm run build` before `npm run test:e2e`. If a
  Chrome channel isn't available in your environment, do **not** edit the
  Playwright config to force a pass — write the e2e tests correctly, state
  that they couldn't run locally, and rely on CI (`.github/workflows/ci.yml`
  runs pytest, Vitest, the production build, and Playwright).
- **T10 — There is no shared page layout.** Every page under
  `site/src/pages/` duplicates its own header/footer markup. When you add nav
  links (Phases 2–3), you must update **every** page's header consistently:
  `index.astro`, `sdlc.astro`, `sources.astro`, `about.astro`,
  `skill/[id].astro`, plus the pages you create. Extracting a shared
  `Header.astro` is permitted if you keep rendered markup equivalent, but it
  is optional — do not let it balloon the diff.
- **T11 — `.claude/commands/skilldeck-ingest.md` is a second source of
  pipeline truth.** It walks an agent through every stage by hand. If you add
  a stage (Phase 1 adds `nutrition`), add it to that command file and to
  CLAUDE.md's stage list, or future ingest runs will skip it.

---

## 4. Environment & validation gates

Setup (Linux/macOS — the PowerShell scripts are Windows-only, run commands
directly):

```bash
python -m pip install -r requirements.txt
cd site && npm install && cd ..
```

**Gate G1 (kitchen):** `python -m pytest kitchen/tests/` — all pass.
**Gate G2 (frontend unit):** `cd site && npm run test` — all pass.
**Gate G3 (build):** `cd site && npm run build` — zero `astro check` errors.
**Gate G4 (e2e):** `cd site && npm run test:e2e` — pass, or documented as
environment-blocked per T9.

Run G1–G3 before **every** commit. Commit at the end of each phase (one or
two commits per phase, descriptive messages). Work on a feature branch; never
commit to `main`.

---

## 5. Phase 0 — Make `emit` safe on a fresh clone

### 5.1 Body resolution helper

In `kitchen/dedup.py`, alongside the existing `get_skill_body()` (leave it
untouched — dedup itself still uses it), add:

```python
def resolve_skill_body(skill: dict) -> tuple:
    """Best-effort offline body lookup. Returns (body_text, source) where
    source is "cache" | "mirror" | None. Never falls back to the
    frontmatter description — callers decide what to do when no body exists."""
```

Resolution order:
1. The GitHub blob cache (same lookup `get_skill_body` does today — reuse its
   logic, but return `(None, ...)` instead of the description on a miss).
2. `mirror/<skill_id>.md` if the file exists and is non-empty
   (`MIRROR_DIR` from `kitchen/config.py`). Read with `encoding="utf-8"`.
3. `(None, None)`.

### 5.2 Card preservation in `run_emit()`

Before building entries, load the existing `data/kb.json` if present
(tolerate absence and malformed JSON — treat both as "no previous kb") and
index its cards by `capability_id`. Card precedence per entry becomes:

1. Cards cache hit for `f"{head_id}:{blob_sha}"` (current behavior).
2. The previous kb.json card for the same `capability_id`, **only if** its
   `generated_by != "fallback"`. Reuse the card object verbatim, including
   its original `generated_by` and `generated_at`.
3. The generic fallback card (current behavior).

### 5.3 Non-destructive mirroring in `run_emit()`

Replace the current delete-all-then-rewrite mirror logic:

1. Compute `expected = {skill_id for mirrorable skills in emitted entries}`.
2. Delete only `mirror/*.md` files whose stem is **not** in `expected`.
3. For each mirrorable skill, call `resolve_skill_body`:
   - `source == "cache"` → write the file (fresh upstream content is
     authoritative).
   - `source == "mirror"` → leave the existing file untouched.
   - `source is None` → leave any existing file untouched; if no file exists,
     skip and print a one-line warning naming the skill id.

### 5.4 Tests (`kitchen/tests/test_emit.py`, extend in existing unittest style)

All with a temp directory standing in for `data/`, `mirror/`, and the cache
(the existing tests show the patch points — follow them):

- Cold cache + existing kb.json with an `"llm"` card → re-emit keeps that
  card verbatim.
- Cold cache + no existing kb.json → fallback card (existing behavior intact).
- Warm cards cache → cache wins over previous kb card.
- Mirror file exists, blob cache cold → after emit the mirror file content is
  unchanged (not truncated to the description).
- Mirror file for a skill no longer emitted → deleted.
- Blob cache warm → mirror file rewritten from cache content.

### 5.5 Acceptance for Phase 0

- G1–G3 green.
- Running `python -m kitchen emit` twice on the fresh clone produces:
  `git diff --stat` touching **only** `data/kb.json`, and only its
  `generated_at` line(s) — no card text changes, no `mirror/` changes.
  Verify this concretely before moving on; revert the incidental
  `generated_at`-only kb.json churn rather than committing it (i.e., don't
  commit a kb.json regeneration in Phase 0 at all).

---

## 6. Phase 1 — Context Cost label ("nutrition")

### 6.1 Data shape

New optional field on each skill record, and mirrored into each
`skill_refs[*]` entry of `kb.json`:

```jsonc
"nutrition": {
  "token_estimate": 1234,        // int ≥ 0
  "word_count": 900,             // int ≥ 0
  "line_count": 120,             // int ≥ 1
  "basis": "body",               // "body" (real SKILL.md body) | "description" (metadata only)
  "trigger": "Use this when users request generative art.", // string, ≤ 200 chars
  "body_blob_sha": "634f6fa…",   // blob sha metrics were computed from; null when basis=="description"
  "computed_at": "2026-07-10T00:00:00Z"
}
```

The whole object is nullable (`null` = stage hasn't run for this skill).

### 6.2 Kitchen stage — `kitchen/nutrition.py`

`run_nutrition()`:

1. `skills_map = load_all_skills(SKILLS_JSON)`; operate on every skill with
   `status == "active"` and `tier != "rejected"`.
2. Resolve body via `resolve_skill_body(skill)` (Phase 0 helper).
3. **Skip/keep rules (idempotency + never-downgrade):**
   - If existing `nutrition.basis == "body"` and
     `nutrition.body_blob_sha == skill["upstream"]["blob_sha"]` → keep as-is
     (no recompute, no `computed_at` churn).
   - If existing `nutrition.basis == "body"` but no body is resolvable now
     → keep the existing object untouched (never downgrade to description).
   - Otherwise compute fresh.
4. **Metrics** (deterministic; normalize `\r\n` → `\n` first):
   - text = resolved body when available, else `frontmatter_description`
     (then `basis = "description"`, `body_blob_sha = None`).
   - `token_estimate = round(len(text) / 4)` — a documented chars÷4
     estimate. Do not add a tokenizer dependency.
   - `word_count = len(text.split())`
   - `line_count = text.count("\n") + 1`
5. **Trigger extraction** — always from `frontmatter_description` (not the
   body), so it's available even for `basis == "description"`:
   - Split into sentences on the regex `(?<=[.!?])\s+`.
   - Return the first sentence matching
     `\b[Uu]se\s+(this\s+|it\s+)?(skill\s+)?(when|for|if)\b|\b[Tt]rigger`;
     if none matches, return the first sentence.
   - If longer than 200 chars, truncate to 199 and append `…`.
   - Empty description → `trigger` is `""`.
6. `computed_at` = current UTC time in the repo's standard format
   (`isoformat().replace("+00:00", "Z")`). Only stamped when actually
   (re)computing (step 3 guards).
7. `save_skills(SKILLS_JSON, skills)` only if anything changed.

**CLI wiring** (`kitchen/cli.py`): add a `nutrition` subcommand
("Compute deterministic context-cost metrics from cached/mirrored bodies").
Also call `run_nutrition()` inside `run_pipeline()` after `rank` (it is fully
offline, so it's safe there), but you will only ever invoke it standalone.

### 6.3 Schema updates (`kitchen/schemas.py`)

- `SKILLS_SCHEMA` → skill items: add optional `nutrition`
  (`"type": ["object", "null"]`) with the properties above; `basis` enum
  `["body", "description"]`; `body_blob_sha` nullable string. Do **not** add
  it to the item's `required` list (old records without it must validate).
- `KB_SCHEMA` → `skill_refs.additionalProperties`: add `nutrition` with the
  same shape, and **do** add `"nutrition"` to that object's `required` list —
  emit will always set it (possibly `null`), and requiring it makes the
  validator catch a forgotten emit change.

### 6.4 Emit (`kitchen/emit.py`)

In the `skill_refs[mid] = {...}` block, add
`"nutrition": member.get("nutrition")`.

### 6.5 Frontend

- **`site/src/utils/contextCost.ts`** (new, pure, unit-tested):
  - `formatTokens(n: number): string` → `"~320 tokens"`, `"~1.2k tokens"`
    (one decimal, `k` at ≥1000; `"~12k tokens"` no decimal at ≥10000).
  - `costBucket(n: number): 'light' | 'moderate' | 'heavy'` →
    light `< 500`, moderate `500–2000` (inclusive), heavy `> 2000`.
- **`Wizard.tsx`**: extend the `SkillRef` interface with
  `nutrition: Nutrition | null` (define the `Nutrition` interface matching
  §6.1). Render a context-cost chip in the badge row near the trust glyph:
  - `basis === "body"` → `⛁ ~1.2k tokens` with a bucket-tinted style
    (reuse the existing zinc/amber palette conventions: light = zinc,
    moderate = amber, heavy = red tints) and a `title` attribute
    `"Estimated context cost when this skill loads (chars ÷ 4)"`.
  - `basis === "description"` → muted chip `size unknown — metadata only`.
  - `nutrition === null` → render nothing.
  - If `nutrition.trigger` is non-empty, show under the card description a
    one-liner: `Loads when: "<trigger>"` in the existing small-mono-label
    style.
- **`SkillCard.astro`** (detail page): same chip + trigger line, importing
  the same util (Astro components can import TS utilities server-side).
  Update its `skill` prop typing to include `nutrition`.

### 6.6 Regenerate data (order matters)

```bash
python -m kitchen nutrition   # writes data/skill-*.json
python -m kitchen emit        # safe after Phase 0; rewrites data/kb.json
```

Commit the changed `data/skill-*.json`, `data/kb.json`. `mirror/` must show
**no diff** — if it does, Phase 0 has a bug; stop and fix it.

### 6.7 Tests

- **`kitchen/tests/test_nutrition.py`** (new, unittest): formula values on a
  fixed string (assert exact numbers); CRLF normalization; mirror-fallback
  basis `"body"`; description fallback basis `"description"` with null
  `body_blob_sha`; trigger extraction (match, no-match→first sentence,
  truncation, empty); idempotency (second run → zero changes, `computed_at`
  unchanged); never-downgrade; rejected/gone skills untouched.
- **`kitchen/tests/test_emit.py`**: `nutrition` propagates into
  `skill_refs`; a skill without it emits `nutrition: null`; KB validation
  passes both ways.
- **`site/src/utils/contextCost.test.ts`** (Vitest): formatting boundaries
  (499/500/999/1000/2000/2001/10000) and buckets.
- **`Wizard.test.tsx`**: chip renders for body-basis nutrition; "metadata
  only" for description-basis; nothing for `null` (build the fixture kb
  accordingly).

### 6.8 Docs

Add the `nutrition` stage to CLAUDE.md's stage list and command table, and to
`.claude/commands/skilldeck-ingest.md` (run it between `rank` and the
review/emit steps; it needs no agent involvement).

### 6.9 Acceptance for Phase 1

- G1–G3 green (G4 per T9).
- In the regenerated `data/kb.json`: every `skill_refs` entry has a
  `nutrition` key; entries whose skill has a committed `mirror/<id>.md` file
  (~80 of 96 skills) have `basis: "body"`.
- The homepage renders token chips without layout breakage in both themes
  (the existing e2e + build gates cover regressions; eyeball via
  `npm run preview` if you can).

---

## 7. Phase 2 — Skill Doctor (`/doctor`)

Fully client-side. No network. No new npm dependencies.

### 7.1 Rules engine — `site/src/utils/skillDoctor.ts` (new)

```ts
export interface Finding {
  id: string;                       // "SD01"…
  severity: 'error' | 'warn' | 'info';
  title: string;                    // one line
  detail: string;                   // 1–2 sentences, plain language, says how to fix
}
export interface ParsedSkill {
  hasFrontmatter: boolean;
  frontmatter: Record<string, string>;
  body: string;
}
export function parseSkillMd(text: string): ParsedSkill;
export function estimateTokens(text: string): number;   // round(chars / 4) — keep in parity with kitchen/nutrition.py
export function diagnose(text: string): Finding[];
export function verdict(findings: Finding[]): 'ready' | 'needs-work' | 'blocked';
```

`parseSkillMd`: normalize `\r\n` → `\n`. Frontmatter = first line exactly
`---`, up to the next `---` line. Inside, parse only **top-level
`key: value` lines** plus simple continuation (a key ending in `>` or `|`, or
a value continued on following more-indented lines, concatenated with
spaces). This is deliberately minimal — do not add a YAML library; unparsed
lines are ignored silently.

Rules (exact ids, deterministic, evaluated in order; regexes
case-insensitive):

| id | severity | fires when |
|---|---|---|
| SD01 | error | no frontmatter block (missing/unclosed `---` fence) |
| SD02 | error | no `name` key |
| SD03 | warn | `name` present but not kebab-case (`^[a-z0-9]+(-[a-z0-9]+)*$`) or > 64 chars |
| SD04 | error | no `description` key |
| SD05 | warn | description < 80 chars — too thin for the harness to match against |
| SD06 | warn | description > 1024 chars |
| SD07 | warn | description lacks trigger phrasing: none of `use when`, `use this when`, `use it when`, `use for`, `use if`, `trigger` — the single most common cause of "my skill never fires" |
| SD08 | warn | description written in first person: starts with `I ` or contains ` I can ` / ` I will ` |
| SD09 | info | `estimateTokens(body)` > 5000 — suggest splitting into referenced files (progressive disclosure) |
| SD10 | warn | body contains override phrasing: `ignore previous instructions`, `ignore all previous`, `disregard the above` — reads as prompt injection and will fail review |
| SD11 | info | body empty or whitespace-only (frontmatter-only skill) |

Skip SD03/SD05–SD08 when their prerequisite key is absent (don't stack a
warn on top of the missing-key error). `verdict`: any error → `blocked`;
zero errors and ≥ 2 warns → `needs-work`; otherwise `ready`.

### 7.2 UI — `site/src/components/Doctor.tsx` (Preact island) + `site/src/pages/doctor.astro`

- Island: a large textarea ("Paste your SKILL.md"), diagnosis recomputed on
  input (pure sync call — no debounce needed at this scale). Below it:
  - A verdict banner (`ready` emerald / `needs-work` amber / `blocked` red —
    reuse the palette conventions already in `Wizard.tsx`).
  - Findings grouped error → warn → info, each showing `id`, `title`,
    `detail` in the existing card/mono styling.
  - A mini nutrition preview: `estimateTokens`, word count, and the extracted
    trigger sentence — reuse `contextCost.ts` for formatting so the numbers
    match the catalog's labels.
  - Empty textarea → a short "how this works" placeholder state, not zero
    findings.
- Page: copy the header/footer/theme pattern from `about.astro`; mount with
  `client:load` (same as the Wizard on `index.astro`). Everything runs in
  the browser; guard any `window`/`document` access for SSR the way
  `Wizard.tsx` does.
- Nav: add a `Doctor` link to every page header (see T10).

### 7.3 Tests

- **`site/src/utils/skillDoctor.test.ts`** (Vitest): one positive and one
  negative case per rule; parser edges: no frontmatter, unclosed fence, CRLF
  input, continuation values; verdict thresholds.
- **e2e (`site/e2e/pages.spec.ts`)**: `/doctor` loads with header + textarea;
  pasting a description-less skill surfaces `SD04`; pasting a well-formed
  skill shows the `ready` verdict.

### 7.4 Acceptance for Phase 2

G1–G3 green (G4 per T9); `/doctor` present in the built output
(`site/dist/doctor/index.html`); no kitchen files touched in this phase.

---

## 8. Phase 3 — Concepts page (`/concepts`)

A single static Astro page (no island, no JS) mapping the vocabulary across
the six supported tools. Same header/footer pattern; add a `Concepts` nav
link everywhere (T10).

Structure: an intro paragraph ("Same ideas, six names for them"), then a
comparison table — rows are mechanisms, columns are the six tools from the
taxonomy (Claude Code, Claude.ai, VS Code / Copilot, Antigravity, Gemini
CLI, Cursor). Wrap the table in an `overflow-x-auto` container. Rows:

1. **Reusable skill / instruction pack** — the on-demand expertise unit
   (Claude Code `SKILL.md`; Copilot instruction files; Cursor rules;
   Gemini CLI extensions; etc.)
2. **Always-on project instructions** — repo-level context files
   (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`,
   `.github/copilot-instructions.md`, `GEMINI.md`)
3. **Slash / prompt commands** — user-invoked prompt templates
4. **Hooks / automations** — deterministic code the harness runs on events
5. **Subagents** — delegated agents with their own context
6. **MCP servers** — external tool/data connections (roughly common to all)

After the table, a short "which mechanism do I want?" list (5–6 bullets:
"reusable expertise → skill; always-relevant project fact → project
instructions; deterministic guarantee → hook; …").

**Accuracy rule:** keep every cell coarse-grained (mechanism name + one
clause). Where you are not confident a tool has a native equivalent, write
"—" or "via <adjacent mechanism>". Do **not** invent file paths, flags, or
version-specific behavior for non-Claude tools, and do not add external doc
links you cannot verify — a wrong "fact" here is worse than a dash.

Tests: extend `site/e2e/pages.spec.ts` — `/concepts` loads, the table
renders with 6 tool column headers, nav link works from the homepage.

Acceptance: G1–G3 green (G4 per T9); `site/dist/concepts/index.html` exists.

---

## 9. Definition of done (whole spec)

- [ ] All four phases implemented **in order**, each committed separately
      with gates G1–G3 green at every commit (G4 per T9).
- [ ] `python -m kitchen emit` run twice in a row is a no-op except
      `generated_at` (T2 fixed, proven by test + manual check).
- [ ] `data/skill-*.json` and `data/kb.json` regenerated via the kitchen
      commands only, and committed; `mirror/` has zero diff.
- [ ] Every `skill_refs` entry in `kb.json` carries `nutrition`
      (object or `null`); ~80 skills have `basis: "body"`.
- [ ] `KB_SCHEMA`, `SKILLS_SCHEMA`, `Wizard.tsx` interfaces, and
      `SkillCard.astro` props all agree on the new field (rule 3-way sync).
- [ ] `/doctor` and `/concepts` build statically, appear in every page's
      nav, and have e2e coverage.
- [ ] CLAUDE.md and `.claude/commands/skilldeck-ingest.md` mention the
      `nutrition` stage.
- [ ] No new dependencies, no network calls added anywhere, no edits to
      `data/kb.json` or `mirror/` by hand, no taxonomy changes.

## 10. Reference — current shapes (for orientation, not to re-verify)

- A skill record (see `data/skill-anthropic-official.json`) carries:
  `id`, `source_id`, `provenance`, `origin{org,repo,path,default_branch}`,
  `name`, `frontmatter_description`, `license`, `mirrorable`,
  `upstream{commit_sha,blob_sha,fetched_at}`, `status`, `tier`,
  `capability_id`, `native_ecosystem`, `install_hints`, `reviewed_by`,
  `reviewed_at`, `reviewed_commit_sha`, `reject_reason`, `freshness`,
  `upstream_changed_at`, `cluster_id`, `score_default`, `scores_by_tool`,
  `lifecycle_phase`.
- A `kb.json` `skill_refs` value carries: `name`, `repo_url`, `provenance`,
  `vendor`, `license`, `review_status`, `reviewed_at`, `freshness`,
  `upstream_changed_at`, `upstream_fetched_at`, `lifecycle_phase`,
  `install` — Phase 1 adds `nutrition`.
- Current inventory: 96 skills across 3 shard files, 7 kb entries,
  80 committed `mirror/*.md` bodies.
