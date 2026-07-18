# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Cursor, and similar)
working in this repository.

## What this is

SkillDeck is a curated directory of AI agent skills (Claude Code Skills, and
equivalents for VS Code Copilot, Cursor, Antigravity, Gemini CLI, etc.). It
has two halves that intentionally never run in the same process:

- **`kitchen/`** — an offline Python pipeline (the only place that talks to
  the GitHub API or does human review). Runs locally, never in production.
  It has no ML/LLM dependencies: capability clustering and Explainer Card
  writing are done by an agent (Claude Code, via `.claude/commands/
  skilldeck-ingest.md`) reading and writing small hand-off JSON files under
  `.kitchen_cache/`, not by a downloaded embedding model or a scripted LLM
  API call.
- **`site/`** — a static Astro + Preact + Tailwind frontend deployed to
  Vercel. It only reads the pre-built `data/kb.json`; it has no backend, no
  database, and makes no runtime calls to LLMs or GitHub.

The bridge between the two is a single static JSON file:
**`data/kb.json`**. The kitchen writes it; the site reads it (copied into
`site/src/data/kb.json` at build time by `site/prebuild.js`). If you change
the shape of `kb.json`, you must update `kitchen/schemas.py` (`KB_SCHEMA`),
`kitchen/emit.py`, and the frontend types in `site/src/types/kb.ts`
(shared by the components; `SkillCard.astro` also re-declares a local
subset) together.

## Repository layout

```
kitchen/          Python offline pipeline (ingest -> emit) + CLI + tests
.claude/commands/ skilldeck-ingest.md — the slash command that runs the
                   pipeline locally and does clustering/cards itself
site/             Astro v4 static frontend (Preact islands, Tailwind)
data/             Pipeline state & output (sources.json, skills.json,
                   install_matrix.json, kb.json) — committed JSON, not a DB
mirror/           Markdown mirrors of community skills fetched by the kitchen
docs/             Architecture images (docs/README.md is currently empty)
scripts/          OS-specific dev scripts (scripts/win/ and scripts/linux/)
requirements.txt  Python deps for the kitchen (mirrors kitchen/pyproject.toml)
vercel.json       Vercel build config (installs/builds only `site/`)
```

## The data pipeline (`kitchen/`)

Stages run in this order (see `kitchen/cli.py: run_pipeline()`), each stage
reads/writes the JSON files under `data/` idempotently via
`atomic_write_json` (write to `.tmp`, then `os.replace`):

1. **`ingest.py`** — fetches `SKILL.md` files + metadata from GitHub sources
   listed in `data/sources.json`, writes/updates `data/skills.json`.
2. **`canonicalize.py`** — resolves `"aggregator"` sources (awesome-lists)
   to their true origin repos by regex-scanning READMEs for GitHub links.
3. **`dedup.py`** — MinHash + Jaccard similarity (`datasketch`) to detect
   near-duplicate skills (`JACCARD_THRESHOLD = 0.7` in `config.py`).
4. **`cluster.py`** — groups skills into the fixed `CAPABILITIES` list in
   `config.py`. Split into two local, network-free halves:
   `prepare_cluster_input()` elects one deterministic "head" per duplicate
   cluster and writes the heads that still need a capability to
   `.kitchen_cache/cluster_input.json`; an agent (Claude Code) reads that
   file, decides each capability, and writes
   `.kitchen_cache/cluster_output.json`; `apply_cluster_assignments()` reads
   that back and propagates it to every member of the cluster. No embedding
   model, nothing downloaded.
5. **`rank.py`** — scores skills within a cluster by provenance
   (official > partner > community), license, tier, and freshness
   (`score_skill()` in `rank.py`); the top skill becomes the
   `recommended.default` for that capability.
6. **`cards.py`** — generates the "Explainer Card" (`title`,
   `what_it_does`, `try_saying`). Same prepare/apply split as clustering:
   `prepare_cards_input()` writes cluster heads needing a card to
   `.kitchen_cache/cards_input.json` (skipping human-locked or already-cached
   ones); an agent writes the copy to `.kitchen_cache/cards_output.json`;
   `apply_card_assignments()` validates it (`validate_card()`: title ≤6
   words, ≤2 sentence description, ≤25 word "try saying") and caches it. No
   `LLM_API_KEY`, no scripted API call — `emit.py` falls back to a generic
   card if a head has no cached card yet.
7. **`summary.py`** — writes the "Skill Summary": one factual, dense
   paragraph per cluster head stating what the skill actually does, stored
   as a `summary` object on the skill record and propagated to cluster
   members. Same prepare/apply split as clustering:
   `prepare_summary_input()` writes emit-eligible heads whose summary is
   missing or stale to `.kitchen_cache/summary_input.json`; an agent writes
   the text to `.kitchen_cache/summary_output.json`;
   `apply_summary_assignments()` validates it (`validate_summary()`: single
   paragraph, 15–120 words, ≤5 sentences, not a verbatim copy of the
   frontmatter description) and writes it back.
8. **`review.py`** — human-in-the-loop CLI. Promotes a skill from
   `"shell"` tier to `"core"`, stamping `reviewed_by` / `reviewed_at` /
   `reviewed_commit_sha`. This is the only stage a human runs interactively;
   everything else is automatable.
9. **`emit.py`** — writes the final `data/kb.json` (validated against
   `KB_SCHEMA` in `schemas.py`) and resolves per-tool install commands from
   `data/install_matrix.json` templates. Mirrors each skill's `summary`
   text into its `skill_refs` entry.
10. **`freshness.py`** — separate, not part of the default pipeline; diffs
    upstream blob SHAs for `"core"` skills to flag drift.

### Running the kitchen

The easiest way to run the whole thing is the **`/skilldeck-ingest`** Claude
Code command (`.claude/commands/skilldeck-ingest.md`) — invoke it in a
Claude Code session with `GITHUB_TOKEN` set, and it runs every stage below in
order, doing the clustering/card-writing steps itself.

To run stages by hand:

```bash
python -m kitchen pipeline              # scriptable stages only: ingest -> canonicalize -> dedup -> rank
python -m kitchen ingest                # single stage
python -m kitchen cluster-prepare       # writes .kitchen_cache/cluster_input.json for an agent to read
python -m kitchen cluster-apply         # reads .kitchen_cache/cluster_output.json, writes capability_id back
python -m kitchen cards-prepare         # writes .kitchen_cache/cards_input.json for an agent to read
python -m kitchen cards-apply           # reads .kitchen_cache/cards_output.json, validates + caches cards
python -m kitchen summary-prepare       # writes .kitchen_cache/summary_input.json for an agent to read
python -m kitchen summary-apply         # reads .kitchen_cache/summary_output.json, validates + writes summaries back
python -m kitchen review --queue        # list skills awaiting human review
python -m kitchen review <skill_id>     # interactive review/promote/reject
python -m kitchen review <skill_id> --web  # also opens the upstream GitHub page
python -m kitchen emit                  # regenerate data/kb.json only (needs cluster-apply to have run for entries to appear)
python -m kitchen freshness             # check upstream drift for core skills
```

`GITHUB_TOKEN` is optional but raises GitHub API rate limits, and is
required in practice for `ingest`/`canonicalize`/`freshness`
(`kitchen/utils.py: GitHubClient`). No LLM API key is needed anywhere in the
kitchen anymore.

GitHub API responses are cached on disk under `.kitchen_cache/` (gitignored,
keyed by SHA-256 of the URL) with ETag support — delete that directory to
force a full refetch.

### Data model conventions (`kitchen/schemas.py`)

- `skills.json` entries have a `tier`: `"shell"` (auto-ingested, unreviewed)
  → `"core"` (human-promoted) or `"rejected"`.
- `provenance` is `"official"` / `"partner"` / `"community"`, derived from
  `OFFICIAL_ORGS` / `PARTNER_ORGS` in `config.py` — update those sets when
  onboarding a new trusted org.
- `native_ecosystem` (`claude`/`google`/`vscode`/`generic`) drives which
  tool tabs get a recommended install command via `rank.py:
  ecosystem_match()`.
- The 8 capabilities and 6 supported tools are hardcoded lists in
  `kitchen/config.py` (`CAPABILITIES`, `TOOLS`) — this is intentionally
  small and curated, not open-ended; adding one requires updating
  `config.py`, `schemas.py` enums, and the frontend's own copies of these
  lists (`Wizard.tsx`, `SkillCard.astro` both hardcode the tool list too —
  keep them in sync manually).

### Kitchen tests

```bash
python -m pytest kitchen/tests/
# or
python -m unittest discover -s kitchen/tests
```
Tests are `unittest`-style (`unittest.TestCase` + `unittest.mock`), one file
per module (`test_<module>.py`), plus `test_golden_pipeline.py` and
`test_pipeline.py` for end-to-end coverage. No network calls in tests — the
GitHub client is mocked; clustering/cards are tested through their
prepare/apply file contracts (write an input file, simulate the agent's
JSON output, apply it), not through a mocked model or LLM client.

## The frontend (`site/`)

Astro v4, static output only (`output: 'static'` in `astro.config.mjs`), with
Preact islands (`@astrojs/preact`, `compat: true`) for interactivity and
Tailwind for styling. There is no server-side rendering and no API routes.

- `src/pages/index.astro` — landing page, renders the `Wizard` Preact
  island with the full `kb.json` passed as props.
- `src/pages/skill/[id].astro` — statically generated per-skill detail page
  (`getStaticPaths()` fans out over every `skill_refs` entry in `kb.json`);
  uses `marked` to render skill README content and `SkillCard.astro` to lay
  it out.
- `src/pages/sources.astro`, `src/pages/about.astro` — static content pages.
- `src/components/Wizard.tsx` — the only stateful component (tool +
  capability filtering, install-command tabs, copy-to-clipboard). Duplicates
  the `Tool`/`Capability`/`KBEntry` TypeScript interfaces that mirror
  `kitchen/schemas.py`'s `KB_SCHEMA` — keep both in sync when the schema
  changes.
- `src/components/SkillCard.astro` — server-rendered card with CSS-only
  (radio input) tabs for per-tool install commands, no JS framework needed.
- `src/components/Badge.astro` — small provenance/license/review badges.
- `src/data/kb.json` — **generated file**, not checked in as source; it's
  copied from `data/kb.json` by `prebuild.js`. Don't hand-edit it.

### Running the frontend

```bash
cd site
npm install
npm run dev          # http://localhost:4321
npm run build         # astro check && astro build (runs prebuild.js first)
npm run preview
npm run test          # Vitest (jsdom), *.test.ts/tsx under src/
npm run test:e2e      # Playwright, e2e/*.spec.ts against a running dev server
```

`npm run build` type-checks with `astro check` before building — treat
TypeScript errors as build failures, not warnings. `astro build` implicitly
runs `prebuild` first (npm `pre<script>` convention), so `data/kb.json` must
exist before building — the kitchen's `emit` stage or `scripts/win/dev-setup.ps1`
generates it if missing.

Vercel deploy config (`vercel.json`) runs
`npm install --prefix site` / `npm run build --prefix site` and serves
`site/dist` — it does not invoke the Python kitchen, so `data/kb.json` must
already be committed/up to date before a Vercel deploy.

## Dev scripts (`scripts/`)

Cross-platform support: PowerShell scripts (`.ps1`) are provided for Windows, and matching Bash scripts (`.sh`) are provided for Linux/macOS.

- `scripts/win/dev-setup.ps1` / `scripts/linux/dev-setup.sh` — idempotent full setup: checks Python 3.11+/Node 18+,
  creates `.venv`, installs `requirements.txt` and `site/` npm deps,
  generates `data/kb.json` if missing, then runs Python tests, frontend
  Vitest, Playwright e2e, and a production build as a validation gate.
- `scripts/win/dev-run.ps1` / `scripts/linux/dev-run.sh` — verifies the environment, ensures `kb.json` exists, then
  starts `npm run dev` in `site/`.
- `scripts/win/dev-test.ps1` / `scripts/linux/dev-test.sh` — runs all three test suites (pytest, Vitest, Playwright)
  and prints a pass/fail summary; doesn't stop on first failure.

## Conventions to follow

- **Never edit `data/kb.json` by hand.** It's pipeline output; regenerate it
  with `python -m kitchen emit` (after `cluster-apply`/`cards-apply` have
  run, or via the `/skilldeck-ingest` command which does the whole thing)
  after changing `data/skills.json`, `data/sources.json`, or
  `data/install_matrix.json`.
- **`data/*.json` files are atomically written** (temp file + rename) by
  every kitchen stage. Follow the same pattern (`kitchen/ingest.py:
  atomic_write_json`) if you add a stage that writes JSON — don't write
  partial files directly.
- **Schema changes are three-way.** A field added to a skill/kb record
  needs updates in `kitchen/schemas.py` (jsonschema), the stage(s) that
  populate it, and the frontend TS interfaces that consume it.
- **Capabilities/tools/orgs are closed, curated lists**, not user input —
  they live in `kitchen/config.py` and are duplicated in the frontend. This
  is deliberate (the product is a small, opinionated taxonomy); don't make
  them dynamic without discussing the tradeoff.
- **The kitchen never runs in production.** Don't add imports from
  `kitchen/` into anything under `site/`, and don't add network/LLM calls to
  `site/` code — the whole point of the architecture is that Vercel serves
  static files only.
- **Tests use `unittest`, not `pytest` fixtures**, on the Python side (even
  though the tests are *run* with `pytest kitchen/tests/`). Match the
  existing `unittest.TestCase` + `unittest.mock.patch` style in new tests.
- Card copy (`title`/`what_it_does`/`try_saying`) has strict length/tone
  rules enforced in `kitchen/cards.py: validate_card()` (called from
  `apply_card_assignments()`) and repeated in the `/skilldeck-ingest`
  command's instructions to the agent writing them — if you touch card
  writing, preserve those constraints (outcome-phrased title ≤6 words, ≤2
  sentence description, ≤25 word "try saying" prompt) in both places.
- Skill Summary text has the same dual enforcement: `kitchen/summary.py:
  validate_summary()` (single paragraph, 15–120 words, ≤5 sentences, no
  verbatim copy of the frontmatter description) and the matching rules in
  the `/skilldeck-ingest` command — keep both in sync if you change either.
  Summaries are factual comparison material, not marketing copy; that tone
  distinction is deliberate.
- License: Apache-2.0 (see `LICENSE`).

## Things that look unfinished (don't be surprised)

- `docs/README.md` is currently empty.
- No CI workflow files exist yet (no `.github/workflows/`) — test suites are
  only run manually via `scripts/win/dev-*.ps1` or `scripts/linux/dev-*.sh` or directly.
- No `.env.example`; `GITHUB_TOKEN` is expected as an ambient environment
  variable. There is no LLM API key anywhere in the kitchen — capability
  clustering and card writing are done by whatever agent runs
  `/skilldeck-ingest`, not by a scripted API call.

## Relation to CLAUDE.md

This file is the vendor-neutral counterpart to `CLAUDE.md` (which some
tools, like Claude Code, read specifically). The two are kept in sync
deliberately — if you update one, update the other.
