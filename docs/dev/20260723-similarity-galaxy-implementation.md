# Similarity Galaxy: end-to-end implementation

Session notes from 2026-07-23 (afternoon). Implements the cross-skill
similarity matrix designed in `20260718-skill-summary-and-similarity-matrix.md`
and verified-as-not-yet-built in `20260723-similarity-matrix-status-verification.md`
(same day, earlier session): a new kitchen stage, real scored data, and an
interactive frontend visualization. Built, run against real data, and
verified in a live browser session - not a design doc.

## What "explainable, content-grounded" means here

Two independent, complementary signals, both traceable to actual skill text
- neither is an arbitrary or fabricated number:

1. **Lexical (deterministic, code-computed).** `kitchen/simmatrix.py:
   normalize_words()`/`lexical_jaccard()` - stopword-filtered word-set
   Jaccard over each skill's Skill Summary text. Zero new dependencies
   (same spirit as `dedup.py`'s shingling, just word-set instead of
   shingle-set). Used two ways: (a) a cheap prefilter that shortlists each
   skill's ~6 nearest neighbors by word overlap before any agent judgment
   runs, bounding an otherwise O(n²) comparison; (b) `shared_keywords` in
   the UI - the literal words present in both summaries, which a user can
   verify themselves by re-reading the two summaries.
2. **Semantic (agent judgment, grounded in the same text).** For each
   shortlisted pair, an agent reads both Skill Summaries (not raw bodies,
   not descriptions) and produces `score` (0-100), `shared_elements`
   (concrete things both skills do), `key_differences` (required even at a
   high score - dedup.py already removed literal near-duplicates before
   this stage runs), and a one-sentence `reason`. This is the same
   prepare/apply, no-embedding-model, no-LLM-API-key pattern every other
   judgment stage in the kitchen already uses (`cluster.py`, `phase.py`,
   `cards.py`, `summary.py`) - deliberately kept consistent with
   `CLAUDE.md`'s "no ML/LLM dependencies" architecture rule and with the
   07-18 doc's explicit decision to reject the embeddings route.

Both signals derive from the same underlying dense, factual paragraph
(`summary.py`'s output) - never from marketing copy, never randomly
assigned. Scores are ordinal judgments, not calibrated probabilities; the
UI labels them as such ("judgments, not a calibrated probability").

## Backend: `kitchen/simmatrix.py` (new stage)

Same prepare/apply contract as every other judgment stage:

- **Scope** (`_eligible_skills`): active skills with both a real Skill
  Summary and one of the 8 curated `capability_id`s. 152 of 519 active
  skills qualified today (the ones with `summary` populated - see the
  status-verification doc for why 361 don't have one yet).
- **Bucketing**: pairs are only ever compared *within* the same
  `capability_id` (a `frontend` skill is never scored against a
  `cloud-ops` skill). Deliberate v1 scope limit to keep the comparison
  space small and relevant, not a technical ceiling - documented in the
  module docstring so it's easy to revisit.
- `simmatrix-prepare` → `.kitchen_cache/simmatrix_input.json`:
  `pairs_needing_scores`, each with `pair_key`, both skills' `id`/`name`/
  `summary`, `capability_label`, `lexical_score`, `shared_keywords`.
  Incremental: a pair already scored for the current summary text (SHA
  match) is skipped.
- `simmatrix-apply` → `data/similarity.json`: validates every score
  (`validate_pair_score()`: int 0-100, 1-4 `shared_elements`, 1-3
  `key_differences`, single-line `reason` ≤220 chars), recomputes the
  lexical signal fresh at apply time (never trusts round-tripped numbers),
  and carries over any previously-applied pair whose skills are still
  eligible and unchanged - coverage only grows across runs, never
  regresses.
- `kitchen/emit.py: load_related_map()` derives each skill's top 8
  neighbors from `data/similarity.json` into `kb.json`'s `related` field
  (capped, so the static site never ships the full O(n²) pair set - the
  full matrix stays kitchen-side).
- Three-way schema update done: `kitchen/schemas.py` (`SIMILARITY_SCHEMA`,
  `RELATED_ENTRY_SCHEMA`, `related` added to `SKILL_REF_SCHEMA`),
  `emit.py`, `site/src/types/kb.ts`.
- `kitchen/tests/test_simmatrix.py`: 15 tests (lexical helpers, validation,
  bucket isolation, full prepare/apply roundtrip, incremental skip/requeue,
  carry-over + drop-when-ineligible). All pass, plus the full existing
  suite (150 tests total) still passes.
- `.claude/commands/skilldeck-ingest.md` updated with a new step 6
  (renumbering nutrition/emit/report to 7/8/9) so a future `/skilldeck-ingest`
  run keeps the matrix current automatically.

## Real data generated this session

`simmatrix-prepare` on the actual catalog shortlisted **585 pairs** across
8 capability buckets (26 in `testing` to 170 in `agent-building`/`cloud-ops`
combined). Scoring 585 pairs by hand in one context would have been slow
and inconsistent, so the work was **delegated to 10 parallel subagents**,
one per capability bucket (the two largest buckets split into two chunks
each to keep any single agent's workload under ~90 pairs). Each subagent
got a self-contained chunk file + the exact scoring rubric and wrote its
results straight to disk; merging the 10 output files gave **585/585
pairs covered, 0 missing, 0 unexpected keys**. `simmatrix-apply` then
validated and wrote all 585 (0 failed validation) to `data/similarity.json`,
and `emit` populated `related` on all 152 eligible skills in `data/kb.json`.

Score distributions read as intended: near-substitute pairs (e.g. the two
`skill-creator` skills from different vendors, or `anthropics-pdf` vs
`openai-pdf`) land 70-85+; same-capability-but-different-purpose pairs
(the common case) land 10-45; near-zero for pairs sharing only generic
domain vocabulary. `key_differences` is populated on every pair, including
the highest-scoring ones, as required.

## Frontend: Similarity Galaxy (`/similarity`)

New nav item, new Astro page (`site/src/pages/similarity.astro`), one new
Preact island (`site/src/components/SimilarityGalaxy.tsx`) plus a pure,
tested layout-math module (`site/src/utils/similarityLayout.ts`). No new
npm dependency - the "magnet" effect is CSS transitions plus one
interpolation formula, not a physics or graph-layout library:

- **Drag-to-attract**: the center ("anchor") skill is the only draggable
  node (pointer events, works with mouse and touch). Every neighbor's
  displayed position is `home + (anchor − home) × pullFactor(score)` on
  every render, where `pullFactor` is a curved 0-1 function of the score
  (never reaches 1, so a node never lands exactly on the anchor). The
  anchor tracks the pointer 1:1 (no transition); neighbors ease toward
  their new target via a plain CSS `transition: left/top 200ms` - so
  higher-scored skills visibly swoop in close while low-scored ones barely
  move, with zero JS animation loop.
- **Threshold slider** (0-95%, step 5, default 40%): filters which
  neighbors render at all - "show only skills at or above X%" exactly as
  requested.
- **Explain panel**: clicking any neighbor shows a "What they share" /
  "How they differ" two-column breakdown (`shared_elements` +
  `shared_keywords` chips vs `key_differences`), the one-line `reason`, the
  numeric score with a tier label (Near-duplicate/Strong overlap/Related/
  Loosely related), and two actions - "Explore from X" (recenters the
  whole galaxy on that skill) and "Open full skill page" (links to the
  existing `/skill/[id]` detail page).
- **Scope transparency**: a footer line states the comparison covers 152
  of 519 catalog skills and that scores are judgments, not a calibrated
  probability - matching the "explainable" requirement rather than
  presenting a bare number.

### Bundle size (the Vercel free-tier constraint)

`SimilarityGalaxy.BYT6JUp0.js` is **10.3 KB** in the production build -
smaller than every other interactive island already in the site
(`SkillExplorer.js` 27.8 KB, `Doctor.js` 24.3 KB). No new dependency was
added to `package.json`. All computation (lexical scoring, agent judgment)
happens offline in the kitchen at build time; the deployed site does zero
runtime computation beyond reading the already-scored JSON baked into
`kb.json` - consistent with "the kitchen never runs in production."

## Verification performed

- `python -m pytest kitchen/tests/` - **150/150 pass** (15 new + all
  pre-existing, no regressions).
- `node node_modules/vitest/dist/cli.js run` (site) - **50/50 pass**
  (9 new `similarityLayout.test.ts` + all pre-existing).
- `astro check` - **0 errors, 0 warnings** across 42 files.
- `astro build` - succeeds, 526 pages including `/similarity`.
- **Live browser walkthrough** (dev server, real interaction, not just a
  static render check):
  - Anchor picker lists all 152 eligible skills; default anchor is the
    most-connected skill in the catalog.
  - Threshold slider tested at 40% (1 neighbor shown) and 10% (4 neighbors
    shown) - confirmed reactive.
  - Clicked a neighbor node → detail panel updated to the correct pair,
    correct tier label ("26% · Loosely related").
  - **Drag verified mathematically, not just visually**: dispatched a real
    pointer down/move/up sequence, read the resulting DOM `style.left/top`
    of both the anchor and a neighbor, and recomputed `pullFactor`/
    `pulledPosition` by hand from the same score/home-position inputs - the
    rendered percentages matched the formula to 4 decimal places.
  - "Reset position" snaps the anchor back to center; "Explore from X"
    correctly recenters the galaxy (dropdown selection and detail heading
    both updated) - confirmed via DOM inspection.
  - No console errors, no dev-server errors, at any point.

## Blocker hit and worked around (documented, not silently patched)

`npm` itself is broken in this environment: any `npm ...` invocation
(`npm -v`, `npm run dev`, `npm run test`, `npx ...`) fails with
`EPERM: operation not permitted, lstat 'C:\Users\admin-local\AppData'` -
npm's own CLI launcher tries to resolve a symlinked install path under a
different Windows user profile this session can't access. Confirmed this
is environment-level (not sandbox-specific): the same failure occurs
running `npm -v` directly in PowerShell outside any tool sandbox.

**Workaround**: invoke each tool's own entry point directly, bypassing
npm's wrapper entirely - `node node_modules/vitest/dist/cli.js run`,
`./node_modules/.bin/astro build`, `node node_modules/astro/bin/astro.mjs
dev --root site` (this is now `.claude/launch.json`'s dev-server config,
so `preview_start` works without touching `npm`). All verification in this
session used this path. This is a local Node/npm install issue, unrelated
to the code changes - worth fixing at the environment level (likely an
`nvm4w` symlink pointing at a stale/foreign profile) but out of scope here.

## Scope / known limitations (by design, not oversight)

- **Coverage is 152 of 519 active skills.** The other 367 either lack a
  Skill Summary yet (361, per the status-verification doc - a bulk NVIDIA
  ingest landed after the last summary run) or were never assigned one of
  the 8 curated capabilities. Re-running `summary-prepare`/`-apply` then
  `simmatrix-prepare`/`-apply` closes this gap incrementally; nothing here
  needs to be re-architected to do it.
- **Same-capability-only pairing.** A skill can't currently show up as a
  neighbor of a skill in a different capability, even if genuinely related
  (e.g. a `frontend` skill and a `testing` skill for the same framework).
  Documented as a deliberate scope limit in `simmatrix.py`'s docstring;
  lifting it means shortlisting across the whole eligible pool instead of
  per-bucket, which changes the O(n²) cost model and would need its own
  pass.
- **585 pairs is a shortlist, not the full matrix.** Each skill has ~6
  lexically-nearest neighbors scored, not all ~40 same-capability peers.
  A skill with no lexically-similar-enough peer in its bucket may show
  zero or few neighbors even below a low threshold - the UI's "no
  neighbors at or above X%" message handles this honestly rather than
  hiding it.
- **Scores are this session's agent judgment**, produced by 10 different
  subagent runs (one per capability bucket) rather than a single pass -
  each was given the identical rubric and shown its own calibration notes
  in-response (see the Agent tool outputs), and cross-bucket comparison
  never happens (scope limit above), so inter-agent calibration drift
  can't skew any single skill's neighbor ranking. Re-scoring with a single
  agent pass would be a reasonable follow-up if inter-bucket comparison is
  ever added.

## Not committed

Per instructions, nothing was staged or committed. `git status` at the end
of this session:

```
 M .claude/commands/skilldeck-ingest.md
 M data/kb.json
 M kitchen/cli.py
 M kitchen/config.py
 M kitchen/emit.py
 M kitchen/schemas.py
 M site/src/layouts/Layout.astro
 M site/src/types/kb.ts
?? .claude/launch.json
?? data/similarity.json
?? docs/dev/20260723-similarity-matrix-status-verification.md
?? kitchen/simmatrix.py
?? kitchen/tests/test_simmatrix.py
?? site/src/components/SimilarityGalaxy.tsx
?? site/src/pages/similarity.astro
?? site/src/utils/similarityLayout.test.ts
?? site/src/utils/similarityLayout.ts
```

`site/src/data/kb.json` (the copy `prebuild.js` makes) is gitignored, so
it doesn't appear here despite being refreshed locally for the dev-server
walkthrough - regenerate it with `node site/prebuild.js` (or a normal
build) after pulling `data/kb.json`.
