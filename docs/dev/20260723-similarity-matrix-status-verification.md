# Similarity matrix: verified status, 2026-07-23

Verification pass on the design in `20260717-kitchen-llm-scope-and-cross-skill-similarity.md`
and `20260718-skill-summary-and-similarity-matrix.md`. Checked against actual
code, not memory. Terse by request.

## Built (confirmed in code)

- **`kitchen/dedup.py`** — MinHash/Jaccard, 5-word shingles, threshold 0.7.
  Lexical only. Finds copy-paste near-dupes. Does not detect same-purpose
  skills worded differently. Working as designed, not a semantic tool, don't
  expect it to become one.
- **`kitchen/summary.py`** — prepare/apply stage, built 2026-07-19. Writes
  `heads_needing_summaries` → agent writes summary text → `validate_summary()`
  (single paragraph, 15-120 words, ≤5 sentences, no verbatim frontmatter
  copy) → stamps `summary{text,basis,body_blob_sha,generated_by,generated_at}`
  on skill record, propagates to cluster members.
- **Schema** — `kitchen/schemas.py` `SUMMARY_SCHEMA`, required field on
  skill records.
- **Emit passthrough** — `emit.py:build_skill_ref()` flattens to
  `"summary": <text|null>` in `kb.json` skill_refs.
- **CLI** — `summary-prepare` / `summary-apply` wired in `cli.py`.
- **Tests** — `kitchen/tests/test_summary.py` exists.
- **`/skilldeck-ingest` command** — step 5 covers summary writing.

## NOT built (checked: no files, no references, anywhere)

- `kitchen/simmatrix.py` — does not exist.
- `data/similarity.json` — does not exist.
- `related` field — not in `KB_SCHEMA`, not in `kb.json`, not in any
  frontend type or component. Grep-clean across `kitchen/` and `site/src/`.
- No `simmatrix-prepare` / `simmatrix-apply` in `cli.py`.
- No `/skilldeck-match` idea-matcher command.
- No UI for "related skills" on the skill detail page
  (`site/src/pages/skill/[id].astro`) — only same-cluster "alternatives"
  (exact dupes) are shown there today, that's a different, already-built
  feature.

**Conclusion: the plan in the 07-18 doc is unchanged and unstarted.** Nothing
new in code since that session except the summary stage itself, which was
already logged as built there.

## New finding this pass: summary coverage is incomplete

Ran the numbers directly against `data/skill-*.json` (not the docs, which
are 5 days stale):

| Metric | Count |
|---|---|
| Active skill records | 519 |
| Active records with a `summary` | 158 |
| Active records **missing** a `summary` | **361** |
| — body-based summaries | 91 |
| — description-based summaries | 67 |
| Distinct dedup clusters | 518 (i.e. ~all skills are their own head — dedup is not shrinking the summary workload) |

70% of active skills have no summary yet. Likely cause: the NVIDIA
DOCA/NeMo bulk ingest (commit `b3eb4b7`) added a large batch of skills after
the last `summary-prepare`/`summary-apply` run.

**This blocks simmatrix from covering the full catalog.** Building the
matrix now would only compare the 158 skills that already have summaries —
silently invisible gap, not a crash, so it'd look done when it isn't.

## Pending work, in order

1. Run `summary-prepare` → agent writes `summary_output.json` →
   `summary-apply` → `emit`, to close the 361-skill gap. Cheap, mechanical,
   same pattern already proven on the first 158.
2. Build `kitchen/simmatrix.py` per the 07-18 design: shortlist-then-score,
   two-pass agent workflow, `simmatrix-prepare` / `simmatrix-apply`,
   `data/similarity.json` (schema already specified in that doc — don't
   redesign it, it's sound: symmetric `[a,b]` pairs, score 0-100, one-line
   reason, `*_summary_sha` for incremental re-runs).
3. Add `kitchen/tests/test_simmatrix.py` — follow the `test_summary.py`
   prepare/apply-file-contract pattern (write input, simulate agent output,
   apply, assert).
4. Schema three-way update: `KB_SCHEMA` in `schemas.py` +
   `emit.py` (derive top 3-5 `related: [{id, score}]` per skill from
   `similarity.json`) + `site/src/types/kb.ts`.
5. Frontend: render `related` on `site/src/pages/skill/[id].astro`
   (distinct section from the existing same-cluster "alternatives" list —
   don't conflate exact-dupe alternatives with semantic neighbors).
6. Pilot scope: SDLC skills only first (102 active have `lifecycle_phase`
   today, up from 30 in the 07-18 doc — still cheap, ~5,151 naive pairs
   worst case, shortlist step cuts this hard). Expand to full
   capability-assigned set (152 skills) after that proves out.
7. Optional, later: `/skilldeck-match` command for the "paste an idea, find
   nearest existing skills" flow — needs no matrix, just summaries + one
   agent pass, per the 07-18 doc's design.

## What this doc adds over the 07-17/07-18 docs

Those two are design docs (recommendation + schema). This one is a status
check: confirms the design is still current, confirms nothing beyond
`summary.py` got built, and surfaces the summary-coverage gap as a concrete
blocker to fix before step 2 (simmatrix) starts. Don't re-read those two for
"is X built" questions going forward — this doc is the source of truth for
that as of 2026-07-23.
