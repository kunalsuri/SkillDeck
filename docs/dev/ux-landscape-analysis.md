# UX Landscape Analysis — SkillDeck

*Recon pass: what the "too many skills" problem actually looks like today,
and what to build next. Grounded in the current codebase (6 populated
capabilities, 3 skills, 4 sources, 6 tools) — not a hypothetical.*

## 1. The landscape: why this problem exists

The AI-agent-skill ecosystem is repeating a pattern every plugin/extension
ecosystem goes through before someone curates it (npm circa 2013, Chrome
extensions circa 2011, WordPress plugins forever):

- **Six incompatible install mechanisms for the same idea.** A "skill" is
  the same concept everywhere, but Claude Code wants a folder copied to
  `~/.claude/skills/`, VS Code/Copilot wants `.github/skills/`, Cursor wants
  `.cursor/skills/`, and Antigravity/Gemini CLI want an `npx skills install`
  command. Claude.ai doesn't take arbitrary skills at all — it's a settings
  toggle. Nobody but a directory can absorb that fragmentation for the user.
- **Duplicate proliferation.** `kitchen/dedup.py`'s Jaccard/MinHash pass
  exists because the same idea ("a Playwright testing skill", "a Notion
  skill") gets reinvented by multiple authors independently. This is not a
  theoretical future problem — the live `data/kb.json` already has two
  *different* `cluster_id`s both assigned to the `testing` capability
  (`community-playwright-skill` and `community-playwright-dino`), i.e. they
  weren't deduped into one head+alternative. Because `emit.py` emits one
  `entries[]` object per cluster and the frontend's `entriesByCap` reduce
  (`Wizard.tsx`) keys on `capability_id` and silently overwrites on
  collision, only the *last* one in array order is ever shown — the other
  is dropped from the UI with no error, no alternatives link, nothing. A
  curated, human-reviewed skill can go invisible this way purely because a
  second skill landed in the same capability bucket. Confirmed by inspecting
  `data/kb.json` directly: two `capability_id: "testing"` entries exist
  side by side. Fixing this (either merge same-capability clusters into one
  entry's `alternatives`, or have the frontend render all of them) should be
  a P0 alongside the tier-gating item below — it's actively hiding content
  today, not just a future risk.
- **No universal trust signal.** GitHub stars, license, last-commit-date,
  and "does this do what the README says" are four different axes that
  don't correlate. `rank.py`'s formula (provenance + license + freshness +
  human-review bonus) is SkillDeck's attempt at one axis, but it's only as
  good as the review pipeline's throughput.
- **Discovery is intent-shaped, not name-shaped.** A user thinks "I want my
  agent to write Playwright tests," not "I want `testdino-hq/playwright-skill`."
  The 8 hardcoded `CAPABILITIES` in `kitchen/config.py` are SkillDeck's bet
  that a small, closed taxonomy beats a search box over skill names — a good
  bet, worth doubling down on rather than diluting with free-text tagging.
- **Review is the bottleneck, not ingestion.** The pipeline can crawl and
  dedup automatically, but promotion from `shell` → `core` tier is a manual,
  one-skill-at-a-time CLI (`kitchen/review.py`). That's why the live catalog
  is 3 skills after several ingestion sources — the funnel narrows hard at
  the human step, which is correct for trust but is the thing to attack for
  scale.

## 2. Where the current product already gets this right

Worth naming so it doesn't get diluted by future feature creep:
- The 2-question wizard (tool, then capability) before showing anything —
  no search box, no infinite list, no filters-on-filters.
- One `recommended.default` per capability, with everything else collapsed
  behind a closed `<details>` ("N similar duplicates collapsed").
- A single-line "Try saying" copy action as the primary CTA — the product
  already understands that the point is not to read about a skill, it's to
  use it in the next ten seconds.
- Methodology and trust math are pushed off the main flow entirely (`/about`,
  `/sources`) instead of cluttering the homepage — resist adding a "settings"
  or "advanced filters" panel to `index.astro` for the same reason.

## 3. Steve Jobs lens — ruthless simplicity, taste over completeness

Jobs's instinct was never "add a feature," it was "delete the decision."
Applied here:

- **Collapse the three competing badges into one.** Provenance
  (Official/Partner/Community), review status (✓ Human-read / auto), and
  license currently render as three separate pills of equal visual weight
  in `Wizard.tsx`. A user doesn't need three facts, they need one verdict:
  a single trust glyph (e.g. a solid vs. hollow checkmark) with the
  provenance/license/date detail available on hover or in `/skill/[id]`.
  Three simultaneous badges is a spec sheet; one glyph is a decision.
- **The wizard should feel like it's reading the user's mind, not
  interviewing them.** "Which assistant do you use?" is a fine question
  the first time; asking it every visit is not — it's already persisted to
  `localStorage`, which is right. Push further: detect it. A tiny bit of
  client-side signal (has the user ever pasted a `.claude/` vs `.cursor/`
  path? did they arrive from a Claude Code or Cursor referrer/UTM?) should
  pre-select the tool so the second-ever visit asks *zero* questions before
  showing the one answer.
- **Say no to the search box.** It will be tempting, once the catalog grows
  past ~30 skills, to add free-text search "for power users." Don't — that
  reintroduces the exact naming problem (§1) SkillDeck exists to remove.
  If free text is added, it should map intent → one of the 8 capabilities
  (a bounded classification), never return a raw list of skill names.
- **One primary action per card, always.** Right now a card has: a "View
  details" link, a copy-prompt button, a tool tab strip, a copy-install
  button, and a collapsible alternatives list — five things competing for
  the eye in one card. Visually subordinate everything except the copy
  actions; "View details" and "alternatives" should read as footnotes, not
  as equal-weight buttons.

## 4. Musk lens, stacked on top — first principles + automate last

Musk's five-step process (question the requirement → delete the step →
simplify what's left → speed up the cycle → automate) applied to the parts
of this product that are still manual or still ask the user to do work a
machine could do:

1. **Question the requirement "the user must copy-paste an install
   command."** Nobody actually wants to run `npx skills install
   github.com/...` by hand. First-principles version: SkillDeck ships
   itself *as* a Claude Code Skill / CLI (`skilldeck install <capability>`)
   that detects the caller's environment by checking for `.claude/`,
   `.cursor/`, `.github/`, etc. in the working directory and performs the
   copy/npx step directly. The website becomes optional research; the
   install becomes one command that already knows which of the six formats
   it's writing.
2. **Delete the silent unreviewed-recommendation risk before it becomes
   real.** Today `emit.py` excludes only `tier == "rejected"` — a `shell`
   tier (auto-ingested, never read by a human) skill *can* become a
   capability's `recommended.default` if no `core` alternative exists yet
   for that cluster, and the frontend renders it with the same-size CTA as
   a reviewed one, differing only by a small amber badge. At 3 skills this
   never triggers; at 300 it will constantly. Fix before scale, not after:
   either gate `recommended.default` to `core`-tier only (falling back to
   an explicit "no reviewed skill yet — here's an unreviewed candidate"
   state), or make the amber "auto-summarized" state visually block the
   one-click copy affordance instead of sitting beside it.
3. **Simplify the ranking formula's inputs by adding the one that's
   missing: real usage.** `rank.py` scores on provenance, license,
   freshness, and a human-review flag — all supply-side signals. There is
   no demand-side signal at all: nothing tracks whether the "Try saying"
   or install command that gets copied for a capability is ever actually
   the one people keep. An opt-in, anonymized copy-event count per
   `skill_id` closes the loop and gives `rank.py` a fifth term that reflects
   what users actually chose, not just what the catalog thinks is best.
4. **Speed up the freshness cycle.** `kitchen/freshness.py` already exists
   to diff upstream blob SHAs for drift, but it's a disconnected, manually
   run stage — nothing in `kb.json` or `SkillCard.astro` surfaces its
   output. Wire its result into a "Last verified against upstream: N days
   ago" line on the skill detail page, and run it on a schedule (nightly),
   so staleness is a visible property of a skill, not a fact only the
   maintainer can see by running a script.
5. **Automate the reviewer's first pass, not their judgment.** The real
   bottleneck is `review.py` being fully manual. Don't automate the
   trust decision — automate the triage: flag skills whose `SKILL.md` or
   scripts contain `curl | sh`, unpinned `eval`, obfuscated payloads, or
   outbound network calls to non-source-repo hosts, and surface that flag
   at the top of the review CLI. This doesn't replace human review (which
   this project correctly treats as load-bearing for trust) — it makes each
   review faster so the funnel in §1 stops being the reason the catalog
   stays at 3 skills.

## 5. Prioritized feature list

**P0 — close gaps between what's built and what's shown (small, mechanical, high-leverage):**
- **[Shipped]** Surface `freshness.py`'s drift signal in `kb.json` → both
  the wizard cards and the skill detail page, as a "Verified" / "Upstream
  changed — recheck pending" badge (§4.4). Backend (`schemas.py`,
  `emit.py`) and frontend (`Badge.astro`, `Wizard.tsx`, `SkillCard.astro`)
  wired end to end; covered by a new `test_emit.py` assertion.
- **[Shipped]** Give an unreviewed (`auto_summarized`) recommendation a
  visually distinct treatment — an amber left-border + inline warning
  strip on the whole card, not just a same-size badge among three others
  (§4.2).
- **[Shipped]** Sharpen the primary CTA: the "Copy the prompt" action is
  now a filled accent-colored button (was an icon-only ghost button same
  weight as "View details"), and "View details" is demoted to a small
  subdued link (§3).
- **[Shipped]** Two skills silently colliding on the same `capability_id`
  is fixed: `emit.py` now groups active skills by `capability_id` (the UI's
  actual recommendation slot) instead of by dedup `cluster_id`, so every
  capability emits exactly one merged entry regardless of how many
  independent clusters landed in it. `community-playwright-skill`, which
  was previously invisible, now correctly renders as an alternative under
  `community-playwright-dino`. Covered by a new `test_emit.py` regression
  case (two different clusters, same capability, asserts one entry + both
  in `skill_refs`). The "N similar duplicate skills collapsed" copy was
  also changed to "N other options for this capability," since not every
  alternative under a shared capability is a literal near-duplicate
  anymore.
- **[Shipped]** Collapsed the (now four, with freshness) badge row into a
  single trust glyph — Trusted / Recheck pending / Unverified — with the
  full provenance/review/freshness/license detail one click away via a
  native `<details>` disclosure (`TrustGlyph.astro` on the detail page,
  `renderTrustGlyph()` in `Wizard.tsx`). Same interaction pattern the site
  already used for collapsed alternatives, so no new UI idiom introduced.
- Gate `recommended.default` to `core`-tier where one exists so an
  unreviewed skill only ever wins when there's no reviewed alternative in
  its cluster (§4.2) — not yet implemented, needs a product decision on
  the empty-state copy first. This is now the main open P0.

**P1 — Jobs-style simplification of the core loop:**
- **[Shipped]** Auto-detect the tool on first visit via `document.referrer`
  (cursor.com, code.visualstudio.com/copilot, claude.ai, antigravity.google)
  when there's no URL param or stored preference yet, with a small
  dismissable "Detected X — change anytime" note so it doesn't feel like
  unexplained magic. Falls back to the existing localStorage persistence
  for repeat visits with no referrer signal.
- **[Shipped]** Make "Copy the prompt" the singular visually dominant
  action per card (filled accent button); demote "View details" to a
  small subdued link (§3).
- If/when a search box is added for scale, constrain it to intent →
  capability classification, never a raw skill-name search (§3).

**P2 — Musk-style automation once the catalog scales past hand-curation:**
- `skilldeck` CLI / self-hosted Claude Code Skill that detects the local
  tool from the working directory and performs the install directly,
  collapsing six install formats into one command (§4.1).
- Opt-in anonymized copy/install-click analytics per skill, feeding a real
  usage term into `rank.py`'s scoring (§4.3).
- Automated static pre-triage (`curl | sh`, eval, suspicious network
  calls) surfaced to the reviewer in `review.py`, to raise review
  throughput without lowering the bar for what reaches `core` tier (§4.5).

## 6. What NOT to build

Consistent with §3: no free-standing search-by-name, no user-facing
settings/preferences panel on the homepage, no expanding the 8 capabilities
or 6 tools without updating `config.py`/`schemas.py`/frontend types
together (per `CLAUDE.md`), and no relaxing the "kitchen never runs in
production" boundary to make any of the above real-time — all of P2 should
still run offline in `kitchen/` and land as static `kb.json` updates.
