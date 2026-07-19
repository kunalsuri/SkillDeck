---
description: Run the SkillDeck kitchen pipeline locally, doing capability clustering and card writing yourself instead of downloading an embedding model or calling an LLM API.
---

# SkillDeck: local ingest pipeline

You are running the SkillDeck kitchen pipeline (`kitchen/`) on the user's own
machine, using their own `GITHUB_TOKEN`. The judgment-based stages —
capability clustering, lifecycle-phase classification, Explainer Card
writing, and Skill Summary writing — are things **you** do directly by
reading a JSON file and writing your answers to another JSON file. No
embedding model download, no `LLM_API_KEY`.

Work from the repository root. Stop and report back to the user (don't just
barrel through) if any step fails — most failures here mean a missing
`GITHUB_TOKEN` or an un-migrated environment, and the user should fix that
before continuing.

## 0. Preflight

1. Confirm you're in the SkillDeck repo root (`kitchen/`, `data/`, `site/` exist).
2. Check `GITHUB_TOKEN` is set (`echo $GITHUB_TOKEN` / `$env:GITHUB_TOKEN` on
   Windows). If it's not already set in the shell, check for a `.env` file in
   the repo root and read a `GITHUB_TOKEN=...` line from it before concluding
   it's missing — export that value into the shell environment for this run
   (don't print the token value, and don't write it anywhere new). Only if
   there's no `.env` file, or it has no `GITHUB_TOKEN` line, tell the user to
   set it and stop — `ingest`/`canonicalize` will otherwise hit GitHub's
   unauthenticated rate limit.
3. Make sure Python deps are installed: `pip install -r requirements.txt`
   (only `requests`, `pyyaml`, `datasketch`, `jsonschema` — no
   `sentence-transformers`, no `anthropic`/`openai`/`google-genai` SDKs).
4. **Run `python -m kitchen precheck` (with `GITHUB_TOKEN` exported) before
   touching `ingest`.** This is a one-shot diagnostic for exactly the two
   classes of failure that stop this pipeline before it does anything useful:
   a bad/missing token and a broken TLS/network path to `api.github.com`. If
   it exits non-zero, **stop immediately and report the FAIL line(s) to the
   user verbatim** — do not go debug it yourself with ad-hoc `curl`/Python
   SSL one-liners, and do not attempt to patch around a TLS failure (e.g. by
   disabling cert verification). A TLS `FAIL` here means a corporate
   proxy/VPN/AV is intercepting HTTPS with an untrusted root CA, or the local
   cert store is broken — that's an environment fix only the user can make
   (turn off the VPN/SSL-inspection, or trust the intercepting CA), not
   something to work around in code. Only proceed to section 1 once
   `precheck` reports `ALL CLEAR` or `OK WITH WARNINGS`.

## 1. Scriptable stages

Run, in order, stopping if any command exits non-zero:

```bash
python -m kitchen ingest
python -m kitchen canonicalize
python -m kitchen dedup
python -m kitchen rank
```

These only touch the GitHub API (via `GITHUB_TOKEN`) and do local
MinHash/scoring math. They update the per-source `data/skill-<source_id>.json` files in place.

## 2. Capability clustering (you do this part)

```bash
python -m kitchen cluster-prepare
```

This writes `.kitchen_cache/cluster_input.json` with two lists:
`already_assigned` (manually-reviewed skills, plus skills already classified
by a prior agent run whose content hasn't changed since — leave these alone)
and `heads_needing_classification`, each with `skill_id`, `name`,
`description`, a `body_excerpt` (first 500 words of the skill body), and a
`members` list (all skill IDs in that dedup cluster — useful context for how
broadly the capability applies). Only new or content-changed heads show up
in `heads_needing_classification`, so this list gets shorter on repeat runs.

Read that file. For every entry in `heads_needing_classification`, pick the
single best-fitting capability from the `capabilities` list in the same file
(id + label + short description of what it covers), based on the skill's
name/description/body excerpt. If nothing fits reasonably well, assign
`"unassigned"` rather than forcing a bad match.

Write `.kitchen_cache/cluster_output.json`:

```json
{"assignments": {"<skill_id>": "<capability_id-or-unassigned>", "...": "..."}}
```

Every `skill_id` from `heads_needing_classification` must have an entry.
Then apply it:

```bash
python -m kitchen cluster-apply
```

## 3. Lifecycle phase classification (you do this part too)

```bash
python -m kitchen phase-prepare
```

This writes `.kitchen_cache/phase_input.json` with two lists:
`already_assigned` (manually-reviewed skills, plus skills already classified
by a prior agent run whose content hasn't changed since — leave these alone)
and `heads_needing_classification`, each with `skill_id`, `name`,
`description`, a `body_excerpt`, a `capability_label` (the capability just
assigned in step 2), and a `members` list. This only covers skills that
already have a real `capability_id` — it feeds the "Software Engineering /
SDLC" page. Only new or content-changed heads show up in
`heads_needing_classification`, so this list gets shorter on repeat runs.

Read that file. For every entry in `heads_needing_classification`, decide
whether it's a software-engineering / coding-agent lifecycle skill, and if
so which single phase from the `phases` list in the same file it fits best
(Define, Plan, Build, Verify, Review, or Ship). If it isn't part of a
software development lifecycle (e.g. document creation, design/branding,
spreadsheet analysis), write `null` rather than forcing a bad match.

Write `.kitchen_cache/phase_output.json`:

```json
{"assignments": {"<skill_id>": "<phase_id-or-null>", "...": "..."}}
```

Every `skill_id` from `heads_needing_classification` must have an entry.
Then apply it:

```bash
python -m kitchen phase-apply
```

## 4. Card writing (you do this part too)

```bash
python -m kitchen cards-prepare
```

This writes `.kitchen_cache/cards_input.json` with `heads_needing_cards`
(every active skill without a cached or human-locked card, whether or not it
was assigned one of the 8 capabilities in step 2). Each entry has `skill_id`,
`name`, `frontmatter_description`, a `body_excerpt` (first 1000 words), and a
`capability_label` (the user-facing category this skill belongs to, e.g.
`"Build web pages & UI"` — use this to frame the card when present; it's
`null` for a skill that isn't assigned one of the 8 capabilities, so frame
the card from its name/description instead). Skills with a human-written
card, or one already cached for the current `blob_sha`, are skipped
automatically.

For each entry, write one product card for a curated catalog of AI agent
skills, aimed at non-technical users:

- `title`: outcome-phrased, verb-first, max 6 words, no jargon, never the
  skill's internal name.
- `what_it_does`: max 2 sentences, plain language, no unexpanded acronyms.
- `try_saying`: one realistic prompt a user could type verbatim to trigger
  this skill — concrete, task-shaped, max 25 words.

Write `.kitchen_cache/cards_output.json`:

```json
{"cards": {"<skill_id>": {"title": "...", "what_it_does": "...", "try_saying": "..."}, "...": "..."}}
```

Every `skill_id` from `heads_needing_cards` must have an entry. Then apply
it (cards that violate the length rules above are rejected and logged, not
silently truncated — re-check and re-run if you see failures):

```bash
python -m kitchen cards-apply
```

## 5. Skill Summaries (you do this part too)

```bash
python -m kitchen summary-prepare
```

This writes `.kitchen_cache/summary_input.json` with `heads_needing_summaries`
(every active skill whose summary is missing or stale for the current
upstream body, whether or not it was assigned one of the 8 capabilities in
step 2). Each entry has `skill_id`, `name`, `frontmatter_description`,
a `body_excerpt` (first 1000 words, or just the description when no body is
available — see the entry's `basis` field), a `capability_label` (`null` for
a skill outside the 8 capabilities), and a `members` list. Skills with a
human-locked summary, or one already written for the current body, are
skipped automatically.

For each entry, write one **Skill Summary** — a factual statement of what
the skill actually does. Unlike the marketing-friendly card copy, summaries
power semantic comparison between skills (finding overlapping or related
skills across sources), so precision beats polish:

- One paragraph, 2–5 sentences, 15–120 words. No markdown headings, lists,
  or line breaks.
- Neutral third person: the tasks it performs, what it operates on (tools,
  file formats, services), and what it produces.
- Concrete specifics over marketing language; never copy the frontmatter
  description verbatim.

Write `.kitchen_cache/summary_output.json`:

```json
{"summaries": {"<skill_id>": "<summary text>", "...": "..."}}
```

Every `skill_id` from `heads_needing_summaries` must have an entry. Then
apply it (summaries that violate the rules above are rejected and logged,
not silently truncated — re-check and re-run if you see failures):

```bash
python -m kitchen summary-apply
```

## 6. Context-cost (nutrition) metrics — no agent involvement

```bash
python -m kitchen nutrition
```

This is fully offline and deterministic — nothing for you to read or
decide. It computes a `token_estimate` (chars ÷ 4), `word_count`,
`line_count`, and a trigger sentence for every active, non-rejected skill,
using whatever body is available (GitHub blob cache, then `mirror/<id>.md`,
else the frontmatter description as a last resort with `basis:
"description"`). Run it any time after `rank`; it's idempotent and safe to
re-run.

## 7. Emit

```bash
python -m kitchen emit
```

This validates and writes `data/kb.json`. It groups skills by capability
bucket (one `kb.json` entry per capability, which may contain multiple
`skill_refs` if more than one dedup cluster mapped to the same capability),
and stamps each `skill_refs` entry with its `lifecycle_phase`, `nutrition`
(or `null`), and `summary` text (or `null`) so the Software Engineering /
SDLC page, the context-cost chip, and the skill detail page can read them. It also updates `mirror/` non-destructively:
only `.md` files for skills no longer emitted are deleted, and a file is
only overwritten when there's fresh GitHub blob cache content for it — a
cold cache never truncates a committed mirror body down to a one-line
description fallback.

## 8. Report, don't commit

Run `git status` and `git diff --stat` on `data/` and `mirror/` and summarize
for the user: how many skills were ingested, how many capability buckets got
entries, how many skills were classified into each lifecycle phase, how many
cards and Skill Summaries you wrote vs. reused from cache, and anything that
looked off (e.g. a skill you had to leave `unassigned`, or a card or summary
that failed validation twice).

Also remind the user that the **web review dashboard** is available for
human promotion/rejection of skills and manual card editing:

```bash
python -m kitchen review --web
```

This starts a local server at `http://127.0.0.1:8000/` (opens in the browser
automatically). Saving in the dashboard auto-runs `emit` — no separate step
needed.

**Do not `git add`, commit, or push.** Leave the regenerated JSON staged in
the working tree for the user to review and commit themselves.
