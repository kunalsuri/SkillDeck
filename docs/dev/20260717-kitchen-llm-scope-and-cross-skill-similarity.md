# Kitchen LLM scope, and a proposed cross-skill similarity feature

Session notes from 2026-07-17. Covers (1) a local network diagnostic for
running `/skilldeck-ingest`, (2) a walkthrough of exactly which kitchen
stages need agent/LLM judgment vs. which are purely mechanical, and (3) a
not-yet-built feature idea: numeric similarity/confidence between two
specific skills (e.g. "is skill-1 from company-1 similar to skill-5 from
company-7").

## 1. TLS precheck failure — diagnosis, not yet root-caused

`python -m kitchen precheck` fails with
`SSLCertVerificationError: unable to get local issuer certificate` when run
through Claude Code's Bash tool, but passes with `ALL CLEAR` when run
directly in the user's own PowerShell (same `.venv`, same `python.exe`, same
`certifi` bundle — confirmed identical paths in both contexts).

- `env | grep -i proxy` in the Bash-tool shell shows Norton Antivirus's SSL
  inspection filter is active: `SSLKEYLOGFILE` points at
  `\\.\nllMonFltProxy\...` (Norton's proxy filter driver) and
  `NODE_EXTRA_CA_CERTS` points at `C:\ProgramData\Norton\Antivirus\wscert.pem`
  (Norton's injected root CA, trusted by Node but not by Python's `certifi`).
- `curl -vI https://api.github.com/zen` from the same Bash-tool shell fails
  with a schannel `CRYPT_E_NO_REVOCATION_CHECK` error — consistent with
  network-level TLS interception, not a Python-side cert bundle problem.
- Disabling the Bash tool's sandbox (`dangerouslyDisableSandbox: true`) made
  no difference — same failure — so it isn't Claude Code's own sandbox
  imposing a different network path.
- Working theory (unconfirmed): Norton applies its interception/trust policy
  per-process-ancestry, and treats a process launched by the Claude Code
  Bash tool differently than one launched interactively from
  `powershell.exe`. Not verified further this session.

**Workaround in use**: run the two network-dependent stages
(`ingest`, `canonicalize`) directly in the user's PowerShell, where they're
confirmed working; everything after that (`dedup`, `rank`, `nutrition`,
`emit`, plus the agent-driven `cluster`/`phase`/`cards` steps) runs fine
through Claude Code since those stages don't need outbound network calls
themselves (or, for `cluster`/`phase`/`cards`, are int
he prepare/apply hand-off files, no live network call at apply time).

## 2. Which kitchen stages actually need LLM/agent judgment

Only three of the ten pipeline stages do. Confirmed by reading source, not
just the docs:

| Stage | File | Needs agent? | Why / why not |
|---|---|---|---|
| ingest | `ingest.py` | No | GitHub API fetch + base64 decode + YAML frontmatter parse. Plain HTTP + string logic. |
| canonicalize | `canonicalize.py` | No | Regex-scans aggregator READMEs for GitHub links (`extract_github_repos`), resolves license via GitHub API + SPDX string matching. |
| dedup | `dedup.py` | No | MinHash + Jaccard similarity (`datasketch`) over 5-word text shingles. Lexical near-duplicate detection, not semantic. |
| **cluster** | `cluster.py` | **Yes** | Assigns one of 8 fixed `CAPABILITIES` to each dedup-cluster "head" by reading its name/description/body excerpt. Closed-set text classification over free-form, uncontrolled-vocabulary prose — not similarity, not embeddings. |
| rank | `rank.py` | No | Pure arithmetic scoring: tier/provenance/license/freshness/ecosystem-match point values, hardcoded formula. |
| nutrition | `nutrition.py` | No | Deterministic chars÷4 token estimate, word/line counts. |
| **phase** | `phase.py` | **Yes** | Same prepare/apply pattern as `cluster`, classifies into 6 SDLC phases or `null`. Same reasoning: free-text classification. |
| **cards** | `cards.py` | **Yes** | Generates title/description/example-prompt copy per skill — genuinely generative, not classificatory. |
| review | `review.py` | No (human) | Interactive CLI for human promote/reject. |
| emit | `emit.py` | No | Validates against `KB_SCHEMA`, writes `data/kb.json`. |

### How `cluster.py` actually works (it is not similarity/clustering in the ML sense)

Common confusion: the file is named `cluster.py` and groups things, but it
does **not** compute distance/similarity between skills anywhere.

1. `dedup.py` already grouped near-duplicate skills into `cluster_id`
   buckets (lexical shingle overlap, described above).
2. `cluster.py`'s `_elect_heads()` deterministically picks one representative
   "head" skill per bucket (ranked by provenance/tier/date).
3. Each head's name + description + 500-word body excerpt is written to
   `.kitchen_cache/cluster_input.json`.
4. An agent (Claude Code) reads each head **independently**, with no
   knowledge of any other skill, and picks **one label from a fixed list of
   8 capabilities** (or `"unassigned"`).
5. That single label is copied onto every skill in the head's dedup bucket.

So two unrelated skills end up in the same capability bucket because each
was independently classified into the same slot from a fixed menu — never
because a pairwise similarity score was computed between them. Same pattern
for `phase.py` and `cards.py`: per-item text-in, label-or-copy-out, no
cross-skill comparison ever happens in the current pipeline.

### Why this genuinely needs an LLM instead of a rule-based classifier

- **No controlled vocabulary.** Skill authors describe the same capability
  in unpredictable ways ("scaffolds a component" / "renders a widget" /
  "makes your app look right on any screen"). A keyword table needs
  constant hand-maintenance and still loses to unanticipated phrasing.
- **Genuine ambiguity.** A skill that "generates React components and
  writes Playwright tests for them" plausibly spans `frontend` and
  `testing` — deciding the *primary* purpose is judgment, not a keyword
  count.
- **Fuzzy threshold.** The instructions allow `"unassigned"` when nothing
  "fits reasonably well" — a rule engine has no notion of "sort of
  relevant but not really," only match/no-match.
- **Generalization to unseen phrasing.** New sources get added to
  `sources.json` regularly; an LLM reading text needs no new rules to
  correctly classify a skill phrased in a way it's never seen before.

Contrast with `dedup`/`rank`: dedup only needs lexical overlap (do these
*look* like copies?), never meaning; rank only operates on already-structured
fields (tier, provenance, license, timestamp), never free text.

## 3. Proposed feature (not yet built): cross-skill similarity/confidence

Goal stated by user: given two specific skills — e.g. skill-1 from
company-1 and skill-5 from company-7 — surface a similarity score/confidence
so an end user can tell if they're "the same kind of thing," even when
wording differs completely (i.e. beyond what `dedup.py`'s lexical
MinHash/Jaccard already catches).

### Two candidate mechanisms

1. **Embeddings + cosine similarity.** Run each skill's text through an
   *embedding model* (a different model class than a generative LLM — e.g.
   OpenAI `text-embedding-3-small`/`-large`, Voyage AI, Cohere). Cosine
   similarity between two vectors is pure linear algebra (no LLM call at
   comparison time), continuous score ~0–1, cheap to compute at scale once
   vectors exist (a single `numpy` matmul over the whole catalog).
   - **Architectural conflict**: `CLAUDE.md` currently states the kitchen
     has "no ML/LLM dependencies... not by a downloaded embedding model."
     Adding this is a deliberate, documented architecture change, not a
     tweak — `CLAUDE.md` would need updating if adopted.
2. **Direct LLM pairwise judgment.** Hand two skills' text to an LLM, ask
   for a 0–100 similarity judgment + reasoning. No embeddings/new infra,
   reuses the existing prepare/apply hand-off pattern, gives an explainable
   "why" alongside the number — but is O(n²) if run naively across the
   whole catalog.

### Recommendation

Hybrid: use the MinHash/Jaccard score `dedup.py` already computes (or the
shared `capability_id` bucket from `cluster.py`) as a cheap first-pass
filter to cut the pair count down to plausible candidates, then only run
the (embeddings-cosine or LLM-pairwise) comparison on that reduced set —
avoids both an O(n²) blow-up and, if going the embeddings route, avoids
computing/storing vectors for pairs that were never going to be similar
anyway.

### OpenAI `text-embedding-3` setup/cost, if that path is chosen

Catalog size today: **466 skills** (summed from `data/skill-*.json` source
files as of this session). Estimated ~700 tokens/skill embedding input
(name + description + ~500-word body excerpt, matching the same text
`cluster.py:get_skill_text()` already builds).

| Model | Price (standard) | 466 skills | 5,000 skills (headroom) |
|---|---|---|---|
| `text-embedding-3-small` (1536-dim) | $0.02 / 1M tokens | ~$0.007 | ~$0.07 |
| `text-embedding-3-large` (3072-dim) | $0.13 / 1M tokens | ~$0.04 | ~$0.46 |

Cost is a non-factor at this scale; `small` is more than sufficient
precision for this use case.

Setup steps if adopted:

1. New secret `OPENAI_API_KEY` in `.env`, exported the same way
   `GITHUB_TOKEN` already is. Requires consciously updating `CLAUDE.md`'s
   "no LLM API key anywhere in the kitchen" statement.
2. No new SDK needed — a plain `requests.post` to
   `https://api.openai.com/v1/embeddings`, mirroring the existing
   `GitHubClient` pattern in `kitchen/utils.py`, keeps the repo's minimal
   dependency footprint (`requests`/`pyyaml`/`datasketch`/`jsonschema` only).
3. Batch requests (~100–200 skills/call) rather than one call per skill.
4. Cache vectors keyed by `skill_id` + `body_blob_sha`, same
   skip-if-unchanged idempotency `nutrition.py` already uses. Open design
   question: commit vectors to `data/` (small but a fundamentally different
   kind of artifact than the rest of the human-readable, diffable JSON
   there) vs. treat as a regenerable cache under `.kitchen_cache/`
   (gitignored, like the GitHub response cache) — leaning toward the
   latter since vectors are fully reproducible from model + input text.
5. Cosine similarity over ~466–5,000 vectors is a single small `numpy`
   matmul — no vector DB / ANN library needed at this scale.
6. Cosine similarity is a similarity score, not a calibrated probability —
   presenting a "confidence %" to end users means picking thresholds
   (e.g. >0.85 "very similar") as a deliberate, one-time calibration choice.

## Status / next steps

Nothing implemented yet. Open decisions before writing code:
- Root-cause (or just permanently work around) the Norton/Bash-tool TLS
  discrepancy, so `/skilldeck-ingest` can run `ingest`/`canonicalize`
  end-to-end again without a manual PowerShell detour.
- Decide whether to actually adopt the embeddings route (and update
  `CLAUDE.md` accordingly) vs. the no-new-infra LLM-pairwise route, for the
  cross-skill similarity feature.
- If embeddings: decide commit-to-git vs. regenerable-cache for the vector
  store.
