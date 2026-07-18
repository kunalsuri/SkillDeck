# Skill Summary stage (built) and the cross-skill similarity matrix (designed)

Session notes from 2026-07-18. Follows up on
`20260717-kitchen-llm-scope-and-cross-skill-similarity.md`, which left two
open decisions. Both are now resolved:

1. **Mechanism: LLM pairwise judgment, not embeddings.** The comparison work
   will be done by the agent running the kitchen locally (Claude Code, on
   the user's subscription), through the same prepare/apply hand-off files
   every other judgment stage already uses. No `OPENAI_API_KEY`, no
   embedding model download, no new dependency — `CLAUDE.md`'s "no LLM API
   key anywhere in the kitchen" statement stays true.
2. **Substrate: Skill Summaries, not raw bodies.** A new pipeline stage
   (`kitchen/summary.py`, **built this session**) gives every emit-eligible
   skill a dense, factual paragraph describing what it actually does.
   Pairwise comparison then happens between ~15–120-word summaries instead
   of 1,000-word bodies, which is what makes agent-driven O(n·k) comparison
   affordable on a subscription.

## Why dedup/cluster couldn't answer "are these two skills similar?"

Recap of yesterday's analysis, confirmed in source:

- `dedup.py` is **lexical**: MinHash/Jaccard over 5-word shingles. It finds
  near-copies (same text, different repo), never same-purpose skills that
  are worded differently. On today's catalog it finds zero multi-member
  clusters — all 447 active skills are their own "head".
- `cluster.py` is **semantic but not pairwise**: the agent classifies each
  head independently into one of 8 fixed capability buckets. Two skills
  share a bucket because they were independently stamped with the same
  label — no distance between them is ever computed, and a bucket like
  `cloud-ops` (55 skills today) says almost nothing about which of its
  members overlap.

So the catalog had no notion of *semantic proximity* between two specific
skills. The Skill Summary + similarity matrix adds exactly that axis.

## Stage 9: Skill Summary (`kitchen/summary.py`) — built

Same prepare/apply pattern as cluster/phase/cards:

- `python -m kitchen summary-prepare` → `.kitchen_cache/summary_input.json`
  with `heads_needing_summaries`: emit-eligible cluster heads (active, not
  rejected, real capability) whose summary is missing or stale. Each entry
  carries `skill_id`, `name`, `frontmatter_description`, a `body_excerpt`
  (first 1,000 words via `resolve_skill_body`: blob cache → `mirror/`),
  a `basis` flag (`body` vs `description`), `capability_label`, `members`.
- Agent writes `.kitchen_cache/summary_output.json` as
  `{"summaries": {"<skill_id>": "<text>", ...}}`.
- `python -m kitchen summary-apply` validates each text
  (`validate_summary()`: single paragraph, 15–120 words, ≤5 sentences, not
  a verbatim copy of the description), stamps a `summary` object
  (`text`/`basis`/`body_blob_sha`/`generated_by`/`generated_at`) on the
  head, and propagates it to every dedup-cluster member.

Storage decisions, deliberately different from cards:

- Summaries live **on the skill record in `data/skill-*.json`** (committed),
  not in the gitignored cards cache — they're durable pipeline data that a
  later stage (the matrix) depends on, and a fresh clone must not lose them.
- Idempotency mirrors `nutrition.py`: skip when `body_blob_sha` still
  matches; when upstream drifts, only rewrite once a fresh body is
  resolvable (never downgrade a body-based summary to description-based);
  upgrade description-based summaries when a body appears. A
  `generated_by: "human"` summary is locked and never queued or overwritten.
- `emit.py` mirrors just the text into each `kb.json` `skill_refs` entry as
  `summary: string | null` — this is the field the user asked for ("stored
  under the skill name in kb.json") and what the site and any external
  consumer read. First real run will queue ~100 heads (83 with real bodies,
  17 description-only, measured on today's data).

## Next: the similarity matrix (designed, not yet built)

Goal (user): given a new skill idea, find which existing skills it's
closest to — to reuse official/pre-existing skill concepts, or to hand the
nearest skills to an agent as inspiration input. Also: browse "related
skills" for any catalog entry.

### Scale, measured on today's data

| Scope | Skills | Naive pairs |
|---|---|---|
| SDLC skills (non-null `lifecycle_phase`) | 30 | 435 |
| All kb.json skills (capability-assigned heads) | 100 | 4,950 |
| Whole active catalog (if ever extended) | 447 | ~99.7k |

435 pairs is trivially affordable as direct pairwise scoring. 4,950 is
still feasible in chunks but wasteful; beyond that, naive O(n²) is out.

### Proposed mechanism: shortlist-then-score, summaries only

Two-pass agent workflow, same prepare/apply file contract:

1. `simmatrix-prepare` writes `.kitchen_cache/simmatrix_input.json`: every
   eligible head's `skill_id` + `summary` text (+ capability/phase as
   context), plus the list of pair scores that are missing or stale.
2. **Pass 1 — shortlist.** The agent reads all summaries in one pass (100
   summaries ≈ 8–10k tokens) and, for each skill, names its top-k candidate
   neighbors (k ≈ 10). This is O(n) reading, not O(n²).
3. **Pass 2 — score.** The agent scores only shortlisted pairs 0–100 with a
   one-line reason each (~n·k/2 ≈ 500 scored pairs for the full kb scope),
   writing `.kitchen_cache/simmatrix_output.json`.
4. `simmatrix-apply` validates (score range, known ids, symmetric
   de-duplication of `[a,b]`/`[b,a]`) and writes `data/similarity.json`.
   Pairs never shortlisted are implicitly "below threshold" — absence means
   dissimilar, so the full matrix never needs materializing.

### Storage: `data/similarity.json`, not kb.json

```json
{
  "schema_version": 1,
  "generated_at": "...",
  "pairs": [
    {
      "a": "<skill_id>", "b": "<skill_id>",
      "score": 82,
      "reason": "Both scaffold Playwright test suites from a running dev server.",
      "a_summary_sha": "...", "b_summary_sha": "..."
    }
  ]
}
```

- Keyed by sorted `[a, b]` so the matrix is symmetric by construction.
- `*_summary_sha` (SHA-256 of each summary text) makes re-runs
  **incremental**: `simmatrix-prepare` only queues pairs where a summary
  changed or a new skill appeared — the "one-time computing cost" is paid
  once, then updates are marginal (a new skill costs n comparisons, not n²).
- kb.json stays lean: at emit time, derive each skill's top 3–5 neighbors
  above a threshold into a small `related: [{id, score}]` list on the
  `skill_refs` entry (schema change, same three-way update rule). The full
  pair file stays kitchen-side; the site never ships O(n²) data.

### The "idea matcher" use case

Once summaries exist, matching a *new idea* against the catalog needs no
matrix at all: paste the idea paragraph, have the agent compare it against
`summary_input`-style data (or `kb.json` summaries directly) and rank the
nearest skills. A future `/skilldeck-match` command can formalize this; the
matrix adds the pre-computed skill↔skill view for browsing and for
"related skills" on detail pages.

### Constraints to preserve when building it

- All judgment via the agent running locally (Claude Code subscription);
  `simmatrix-prepare`/`simmatrix-apply` stay network-free and deterministic.
- Scores are ordinal judgments, not calibrated probabilities — pick display
  thresholds once (e.g. ≥80 "very similar", 60–79 "related") and label them
  as judgments in the UI.
- Start with the SDLC scope (30 skills, 435 pairs) as the pilot; expand to
  the full kb scope once the shortlist workflow proves out.

## Status / next steps

- [x] Skill Summary stage: code, schemas, emit passthrough, CLI, tests,
      `/skilldeck-ingest` step 5, docs (this session).
- [ ] Run `/skilldeck-ingest` (or `summary-prepare` → agent → `summary-apply`
      → `emit`) locally to populate the ~100 summaries and commit the
      regenerated `data/` files.
- [ ] Build `kitchen/simmatrix.py` (prepare/apply as designed above) +
      `data/similarity.json` schema + tests.
- [ ] Emit `related` neighbors into kb.json and render them on the skill
      detail page; optionally add `/skilldeck-match` for the idea-matcher
      flow.
