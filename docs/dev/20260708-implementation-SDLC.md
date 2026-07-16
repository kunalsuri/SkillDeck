# Implementation checklist: Software Engineering / SDLC page

Tracks execution of `docs/SPECS-SDLC.md`. Each item is implemented, tested,
and committed individually — check the box and commit this file's update
together with (or immediately after) the corresponding code commit. This
file is the resume point if the session is interrupted: read `SPECS-SDLC.md`
for the "what/why", then continue from the first unchecked box below.

## 0. Process setup

- [x] Write `docs/SPECS-SDLC.md`, commit standalone.
- [x] Write this checklist, commit standalone.

## 1. Kitchen: data model + `phase` pipeline stage

- [x] `kitchen/config.py`: add `LIFECYCLE_PHASES` list.
- [x] `kitchen/schemas.py`: nullable `lifecycle_phase` on `SKILLS_SCHEMA`;
      top-level `lifecycle_phases` + nullable `lifecycle_phase` on
      `skill_refs` in `KB_SCHEMA`.
- [x] `kitchen/phase.py`: new module, `prepare_phase_input()` /
      `apply_phase_assignments()`, reusing `cluster._elect_heads()` /
      `get_skill_text()`.
- [x] `kitchen/cli.py`: wire `phase-prepare` / `phase-apply` subcommands.
- [x] `kitchen/emit.py`: stamp `lifecycle_phase` on `skill_refs` entries,
      emit top-level `lifecycle_phases`.
- [x] `.claude/commands/skilldeck-ingest.md`: insert lifecycle-phase
      classification section, renumber card writing/emit/report.
- [x] Tests: new `kitchen/tests/test_phase.py`; update `test_schema.py`,
      `test_emit.py`, `test_cli.py` for the new field/stage.
- **Test gate:** `python -m unittest discover -s kitchen/tests` — all pass.
- [x] Commit. (`d9143ac`)

## 2. Data source registration

- [x] `data/sources.json`: add `addyosmani-agent-skills` source entry.
- **Test gate:** valid JSON, conforms to `SOURCES_SCHEMA` (covered by
      `test_schema.py`).
- [x] Commit. (`c9d4636`)

## 3. Frontend: `/sdlc` page

- [x] `site/src/utils/phaseColors.ts`: new phase color constants (not
      `src/lib/` — collides with the root `.gitignore`'s `lib/` rule).
- [x] `site/src/pages/sdlc.astro`: new page, six-column phase layout,
      Addy Osmani attribution.
- [x] Nav link `Software Engineering / SDLC` added to `index.astro`,
      `sources.astro`, `about.astro`, `skill/[id].astro`, and `sdlc.astro`
      itself.
- [x] `site/src/components/Wizard.tsx`: add `LifecyclePhase` interface,
      `lifecycle_phase` on `SkillRef`, `lifecycle_phases` on `KB`.
- **Test gate:** `cd site && npm run build` (`astro check` + build) —
      deferred until real `kb.json` with the new schema exists (step 5),
      since the current committed `data/kb.json` predates this schema.
- [x] Commit (test deferred to section 6, as noted above).

## 4. Documentation

- [x] `CLAUDE.md`: document the new `phase` stage, `LIFECYCLE_PHASES`,
      and `site/src/pages/sdlc.astro`.
- **Test gate:** none (docs-only).
- [x] Commit.

## 5. Data population (real pipeline run)

**Blocker found:** `api.github.com` is blocked by this session's egress
policy (403 from the agent proxy = org policy denial — not retried, not
routed around, per proxy policy). This means `addyosmani/agent-skills`
cannot actually be ingested in this session; it stays registered in
`data/sources.json` (already committed) for a future run with real GitHub
access (e.g. `/skilldeck-ingest` run locally by the user). A failed
`ingest` run was also observed to incorrectly mark unreachable sources'
previously-active skills as `"gone"` (a latent bug in `ingest.py`'s error
handling, out of scope here) — that bad diff was reverted before being
committed.

Revised scope: back-fill `lifecycle_phase` for the 117 skills already in
`data/skills.json` from prior sessions (all local-only stages, no network
needed — `capability_id`/`cluster_id`/scores are already populated).
`addyosmani`'s own skills are deferred to a follow-up ingest.

- [x] ~~Run `python -m kitchen ingest`~~ — skipped, network-blocked (see
      above).
- [x] ~~Run `canonicalize`, `dedup`, `rank`~~ — skipped, no new skills to
      process; existing data already has scores from prior sessions.
- [x] Run `python -m kitchen cluster-prepare`; classify remaining
      unclassified heads (81 heads — cluster.py re-sends every non-core
      head each run, not just new ones); write `cluster_output.json`; run
      `cluster-apply`. Result: 96 assigned, 1 left `unassigned`
      (`anthropics-template-skill`, a placeholder skill).
- [x] Run `python -m kitchen phase-prepare`; classify lifecycle_phase for
      **all** heads needing it (full backfill); write `phase_output.json`;
      run `phase-apply`. Result: 80 phase-tagged (across all six phases),
      16 left `null` (document/design/data-analysis skills not part of a
      coding SDLC — docx/pdf/pptx/xlsx, brand/theme/art skills, Analytics
      admin/reporting, BigQuery basics/ML/lineage).
- [x] Run `python -m kitchen cards-prepare`; write cards for the 96 heads
      needing them; run `cards-apply`. Result: 96 applied, 0 failed
      validation.
- [x] Run `python -m kitchen emit`; confirm schema validation passes.
      Result: `data/kb.json` has 7 capability entries, 97 total
      `skill_refs`, 81 with a non-null `lifecycle_phase`
      (build: 49, ship: 15, review: 15, verify: 2 — none landed in
      `define`/`plan`; that's expected, since those phases match
      spec/planning skills like addyosmani's `interview-me` /
      `spec-driven-development` / `planning-and-task-breakdown`, which
      couldn't be ingested this session — see the blocker note above).
- **Test gate:** `python -m kitchen emit` exits 0 (confirmed above);
      `data/kb.json` has a non-empty `lifecycle_phases` array and at
      least some non-null `lifecycle_phase` values in `skill_refs`
      (confirmed: 81/97).
- [x] Commit `data/skill-*.json`, `data/kb.json`, `mirror/`.

## 6. Frontend verification

- [x] `cd site && npm run build` — succeeded. `astro check`: 0 errors,
      0 warnings (12 hints). 101 pages built, `/sdlc/index.html` present.
- [x] `npm run preview` + Playwright against the pre-installed Chromium;
      confirmed via screenshot: all 5 nav tabs present with correct
      active-state highlighting on `/sdlc`, six phase columns render
      (Define/Plan empty-state message shown correctly, Build/Verify/
      Review/Ship populated with colored chips), light and dark theme
      both render correctly (initial dark screenshot showed a grey band —
      confirmed to be a mid-`transition-colors` screenshot timing
      artifact, not a real bug; re-shot with theme set before navigation
      and it's correct). Spot-checked `/skill/google-gcloud`, `/sources`,
      `/about` — all 200.
- [x] No fixes needed — nothing to commit for this section (verification
      only, no code changes required).

## Done

- [x] All boxes above checked; `docs/SPECS-SDLC.md` acceptance criteria
      (§8) satisfied except addyosmani's own skills being ingested
      (blocked by this session's network policy — source is registered,
      ingest deferred to a future run with GitHub access); final summary
      posted to the user.
