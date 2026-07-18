# 🚀 Start Here — SkillDeck New User Guide

Welcome to **SkillDeck**, a curated directory of AI agent skills.
This guide walks you through everything — from first clone to curating live data with AI — so you can be productive in minutes.

---

## Table of Contents

1. [What You're Working With](#1-what-youre-working-with)
2. [Prerequisites](#2-prerequisites)
3. [First-Time Setup](#3-first-time-setup)
4. [Run the Local Website](#4-run-the-local-website)
5. [Add a New Skill Source](#5-add-a-new-skill-source)
6. [Run the Data Pipeline (with AI)](#6-run-the-data-pipeline-with-ai)
   - [The Easy Way: `/skilldeck-ingest`](#-the-easy-way-skilldeck-ingest-claude-code) — Before · During · After
   - [Using a Different AI Tool?](#-using-a-different-ai-tool-antigravity-gemini-cli-cursor-etc)
   - [The Manual Way: Stage by Stage](#-the-manual-way-stage-by-stage)
7. [Review & Curate Skills (Human-in-the-Loop)](#7-review--curate-skills-human-in-the-loop)
8. [Publish Your Changes](#8-publish-your-changes)
9. [Day-to-Day Cheat Sheet](#9-day-to-day-cheat-sheet)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. What You're Working With

SkillDeck has two halves that never mix:

| Part | What It Does | Where It Lives |
|------|-------------|----------------|
| **The Kitchen** (Python) | Offline pipeline that fetches, deduplicates, clusters, ranks, and writes skill data | `kitchen/` |
| **The Site** (Astro + Preact) | Static frontend that displays the curated skills — no backend, no database | `site/` |

They communicate through **one file**: `data/kb.json`.
The Kitchen writes it; the Site reads it. That's the entire contract.

### The Key Data Files

| File | Purpose | Hand-Edit? |
|------|---------|------------|
| `data/sources.json` | List of GitHub repos/orgs to fetch skills from | ✅ Yes — this is how you add sources |
| `data/skills.json` | Every ingested skill with metadata, tier, cluster, score | ⚠️ Rarely — the pipeline manages it |
| `data/install_matrix.json` | Per-tool install command templates | ✅ Yes — when install methods change |
| `data/kb.json` | The final output that powers the website | ❌ Never — regenerate with `python -m kitchen emit` |

---

## 2. Prerequisites

You need these installed on your machine:

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **Git** — [git-scm.com](https://git-scm.com/)
- **A GitHub Personal Access Token** — [Create one here](https://github.com/settings/tokens) (only needs `public_repo` scope)

> [!TIP]
> No LLM API key is needed. Capability clustering and card writing are done by your AI coding assistant (Claude Code, Antigravity, Gemini CLI, etc.) reading and writing local JSON files — not by a scripted API call.

---

## 3. First-Time Setup

### Option A: Automated (Windows PowerShell — Recommended)

```powershell
# Clone the repo
git clone https://github.com/kunalsuri/SkillDeck.git
cd SkillDeck

# Set your GitHub token for this session
$env:GITHUB_TOKEN = 'ghp_your_token_here'

# Run the idempotent setup script — it does everything:
#   ✓ Creates .venv and installs Python deps
#   ✓ Installs site/ npm deps
#   ✓ Generates data/kb.json if missing
#   ✓ Runs all test suites as validation
# Windows:
.\scripts\win\dev-setup.ps1
# Linux/macOS:
./scripts/linux/dev-setup.sh
```

### Option B: Manual (Any OS)

```bash
# 1. Clone
git clone https://github.com/kunalsuri/SkillDeck.git
cd SkillDeck

# 2. Python environment
python -m venv .venv

# Activate it:
#   Windows:  .venv\Scripts\activate
#   macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt

# 3. Frontend dependencies
cd site
npm install
cd ..

# 4. Set your GitHub token
#   Windows PowerShell:  $env:GITHUB_TOKEN = 'ghp_...'
#   Bash/Zsh:            export GITHUB_TOKEN='ghp_...'

# 5. Generate the initial knowledge base (if data/kb.json doesn't exist)
python -m kitchen emit

# 6. Verify everything works
python -m pytest kitchen/tests/     # Kitchen unit tests
cd site && npm run test && cd ..    # Frontend unit tests
```

> [!IMPORTANT]
> The `GITHUB_TOKEN` is optional for running the website locally, but **required** for the pipeline's `ingest` and `canonicalize` stages (which hit the GitHub API). Without it, you'll get rate-limited fast.

---

## 4. Run the Local Website

```powershell
# Windows (uses the dev script):
.\scripts\win\dev-run.ps1

# Linux/macOS (uses the dev script):
./scripts/linux/dev-run.sh

# Or manually (any OS):
cd site
npm run dev
```

Open **<http://localhost:4321>** in your browser. You should see the SkillDeck homepage with skill cards, filtering, and install-command tabs.

---

## 5. Add a New Skill Source

This is how you tell the Kitchen "go fetch skills from this GitHub repo."

### Step 1 — Edit `data/sources.json`

Open `data/sources.json` and add a new entry to the `sources` array:

```json
{
  "id": "my-new-source",
  "org": "github-org-name",
  "repo_url": "https://github.com/org/repo",
  "kind": "official",
  "vendor": "org-name",
  "default_license": "MIT",
  "notes": "Short description of this source."
}
```

**Field reference:**

| Field | Value | Notes |
|-------|-------|-------|
| `id` | Unique string identifier | e.g. `"acme-skills"` |
| `org` | GitHub org or user | e.g. `"acme-corp"` |
| `repo_url` | Full GitHub URL | Must be a valid repo |
| `kind` | `"official"` or `"aggregator"` | Aggregators are awesome-lists that link to other repos |
| `vendor` | Vendor name or `null` | Used for provenance mapping |
| `default_license` | License string or `null` | e.g. `"MIT"`, `"Apache-2.0"` |
| `notes` | Free text | Context for maintainers |

### Step 2 — Update Provenance (if needed)

If the org should be treated as an official or partner source, add it to the appropriate set in `kitchen/config.py`:

```python
OFFICIAL_ORGS = {
    "anthropics",
    "google",
    "your-new-org",        # ← add here
}
```

### Step 3 — Run the Pipeline

See the next section.

---

## 6. Run the Data Pipeline (with AI)

This is the core workflow. The pipeline has **scriptable stages** (pure code) and **AI-assisted stages** (where your coding assistant does the thinking).

### 🤖 The Easy Way: `/skilldeck-ingest` (Claude Code)

The `/skilldeck-ingest` command is a Claude Code slash command that runs the **entire pipeline end-to-end** — including the AI-driven capability clustering and card writing steps that normally require a human to orchestrate. Here's exactly what you need to know:

---

#### ✅ BEFORE You Run `/skilldeck-ingest`

You need **three things** in place before running the command:

**1. Set your `GITHUB_TOKEN`**

The pipeline's `ingest` and `canonicalize` stages make GitHub API calls to fetch `SKILL.md` files and resolve aggregator links. Without a token, GitHub rate-limits you to 60 requests/hour and the pipeline will likely fail partway through.

```powershell
# Windows PowerShell:
$env:GITHUB_TOKEN = 'ghp_your_token_here'

# Bash/Zsh:
export GITHUB_TOKEN='ghp_your_token_here'
```

**2. Install Python dependencies**

The kitchen needs four lightweight packages — no ML models, no LLM SDKs:

```bash
pip install -r requirements.txt
# Installs: requests, pyyaml, datasketch, jsonschema
```

If you ran the dev-setup script (`.\scripts\win\dev-setup.ps1` or `./scripts/linux/dev-setup.sh`) during first-time setup, this is already done inside your `.venv`.

**3. Ensure `data/sources.json` lists the repos you want to fetch from**

This file tells the pipeline *where* to look for skills. It ships with default sources (Anthropic, Google, Vercel). If you want to add a new source, edit this file first (see [Section 5](#5-add-a-new-skill-source)).

> [!TIP]
> No LLM API key is needed — not for Claude, not for OpenAI, not for anything. The "AI" steps are done by Claude Code itself (the agent running in your terminal), reading and writing local JSON files. There's nothing to configure.

---

#### 🔄 DURING the `/skilldeck-ingest` Process

When you type `/skilldeck-ingest` in a Claude Code session, the agent follows a 5-phase playbook defined in `.claude/commands/skilldeck-ingest.md`. Here's what happens at each phase:

```
┌─────────────────────────────────────────────────────────────────┐
│                    /skilldeck-ingest Flow                        │
│                                                                 │
│  Phase 0: Preflight checks                                      │
│     │                                                           │
│     ▼                                                           │
│  Phase 1: Scriptable stages (4 commands)                        │
│     │   ingest → canonicalize → dedup → rank                    │
│     ▼                                                           │
│  Phase 2: AI clusters skills into capabilities                  │
│     │   cluster-prepare → AI decides → cluster-apply            │
│     ▼                                                           │
│  Phase 3: AI writes explainer cards                             │
│     │   cards-prepare → AI writes copy → cards-apply            │
│     ▼                                                           │
│  Phase 4: AI writes Skill Summaries                             │
│     │   summary-prepare → AI writes text → summary-apply        │
│     ▼                                                           │
│  Phase 5: Emit final kb.json                                    │
│     │                                                           │
│     ▼                                                           │
│  Phase 6: Report (does NOT commit)                              │
└─────────────────────────────────────────────────────────────────┘
```

**Phase 0 — Preflight**

The agent confirms it's in the repo root, checks that `GITHUB_TOKEN` is set, and verifies Python deps are installed. If anything is missing, **it stops and tells you** — it won't silently barrel through.

**Phase 1 — Scriptable Stages** (runs 4 Python commands)

| Command | What It Does | Reads | Writes |
|---------|-------------|-------|--------|
| `python -m kitchen ingest` | Fetches `SKILL.md` files + metadata from every repo in `sources.json` via the GitHub API | `data/sources.json` | `data/skills.json` |
| `python -m kitchen canonicalize` | Resolves `"aggregator"` sources (awesome-lists) to their true origin repos | `data/skills.json` | `data/skills.json` |
| `python -m kitchen dedup` | Runs MinHash + Jaccard similarity to detect near-duplicate skills | `data/skills.json` | `data/skills.json` |
| `python -m kitchen rank` | Scores skills by provenance (official > partner > community), license, and freshness | `data/skills.json` | `data/skills.json` |

If any command exits with a non-zero code, the agent **stops and reports the error** to you.

**Phase 2 — Capability Clustering** (AI does the thinking)

| Step | What Happens | File Involved |
|------|-------------|---------------|
| `python -m kitchen cluster-prepare` | Writes a list of skills that need a capability assignment | `.kitchen_cache/cluster_input.json` |
| **Claude reads the file** | The agent reads each skill's name, description, and body excerpt, then picks the best-fit capability from the 8-category list | *(reads)* `.kitchen_cache/cluster_input.json` |
| **Claude writes its decisions** | The agent writes `{"assignments": {"skill-id": "capability-id", ...}}` | `.kitchen_cache/cluster_output.json` |
| `python -m kitchen cluster-apply` | Reads Claude's output and propagates the capability to every member of each duplicate cluster | `data/skills.json` |

**Phase 3 — Card Writing** (AI writes the copy)

| Step | What Happens | File Involved |
|------|-------------|---------------|
| `python -m kitchen cards-prepare` | Writes a list of skills that need an explainer card (skips any with a cached or human-locked card) | `.kitchen_cache/cards_input.json` |
| **Claude reads the file** | The agent reads each skill's metadata and writes a product card (title, description, sample prompt) | *(reads)* `.kitchen_cache/cards_input.json` |
| **Claude writes the cards** | The agent writes `{"cards": {"skill-id": {"title": "...", "what_it_does": "...", "try_saying": "..."}}}` | `.kitchen_cache/cards_output.json` |
| `python -m kitchen cards-apply` | Validates each card against length rules (title ≤6 words, description ≤2 sentences, try_saying ≤25 words), rejects violations, and caches valid cards | `data/skills.json`, `.kitchen_cache/cards_cache.json` |

> [!NOTE]
> If a card fails validation, the agent is expected to re-check and retry. Cards that are too long are **rejected and logged**, not silently truncated.

**Phase 4 — Skill Summaries** (AI writes the comparison text)

| Step | What Happens | File Involved |
|------|-------------|---------------|
| `python -m kitchen summary-prepare` | Writes a list of skills whose Skill Summary is missing or stale for the current upstream body (skips human-locked or already-current ones) | `.kitchen_cache/summary_input.json` |
| **Claude reads the file** | The agent reads each skill's name, description, and body excerpt, then writes one factual paragraph describing what the skill actually does | *(reads)* `.kitchen_cache/summary_input.json` |
| **Claude writes the summaries** | The agent writes `{"summaries": {"skill-id": "summary text", ...}}` | `.kitchen_cache/summary_output.json` |
| `python -m kitchen summary-apply` | Validates each summary (single paragraph, 15–120 words, ≤5 sentences, not a verbatim description copy), stamps it on the cluster head, and propagates it to duplicate-cluster members | `data/skills.json` |

Summaries end up in `kb.json` under each skill entry and are the substrate for cross-skill semantic comparison (the planned similarity matrix).

**Phase 4 — Emit**

| Command | What It Does | Reads | Writes |
|---------|-------------|-------|--------|
| `python -m kitchen emit` | Validates the full dataset against `KB_SCHEMA`, resolves per-tool install commands from `install_matrix.json`, and writes the final knowledge base | `data/skills.json`, `data/install_matrix.json` | `data/kb.json`, `mirror/*.md` |

**Phase 5 — Report**

The agent runs `git status` and `git diff --stat` on `data/` and `mirror/`, then gives you a summary:

- How many skills were ingested
- How many capability buckets got entries
- How many cards were written vs. reused from cache
- Anything that looked unusual (skills left `"unassigned"`, cards that failed validation)

> [!IMPORTANT]
> **The agent does NOT commit, push, or deploy anything.** It leaves all changes in your working tree for you to review, `git add`, and commit yourself.

---

#### ✅ AFTER `/skilldeck-ingest` Completes

Once the command finishes, here's what you should do:

**1. Review what changed**

```bash
git status                    # See which files were modified
git diff data/skills.json     # Review skill metadata changes
git diff data/kb.json         # Review the final knowledge base output
```

**2. Inspect the website locally**

```bash
cd site
npm run dev                   # Start the dev server
```

Open **<http://localhost:4321>** and verify the new skills appear correctly — check their cards, capability grouping, and install commands.

**3. (Optional) Review and promote skills**

New skills enter as `"shell"` tier. To promote them to `"core"` (which gives them higher visibility on the site), use the review CLI:

```bash
python -m kitchen review --queue        # See what's waiting
python -m kitchen review <skill_id>     # Review a specific skill
python -m kitchen emit                  # Re-emit kb.json after promoting
```

See [Section 7](#7-review--curate-skills-human-in-the-loop) for the full review workflow.

**4. Commit and deploy**

```bash
git add data/ mirror/
git commit -m "chore: refresh skill data via /skilldeck-ingest"
git push origin main          # Triggers Vercel deployment
```

---

### 🧑‍💻 Using a Different AI Tool? (Antigravity, Gemini CLI, Cursor, etc.)

The `/skilldeck-ingest` command is specific to Claude Code, but the underlying workflow is **tool-agnostic**. Any AI coding assistant can do the same thing — the "AI steps" are just reading a JSON file, making decisions, and writing the answers to another JSON file.

You can either:

- **Ask your AI assistant to follow the same playbook** — point it at `.claude/commands/skilldeck-ingest.md` and tell it to execute those steps
- **Run the stages manually** and ask your AI to handle only the clustering and card-writing steps (see the "Manual Way" section below)

### 🔧 The Manual Way: Stage by Stage

Here's the full pipeline, broken into clear steps:

---

#### Stage 1 — Fetch & Score (Scriptable, No AI Needed)

```bash
# Run all four scriptable stages in order:
python -m kitchen pipeline

# This runs:
#   1. ingest        — fetches SKILL.md files from GitHub sources
#   2. canonicalize  — resolves aggregator links to origin repos
#   3. dedup         — MinHash duplicate detection
#   4. rank          — scores skills by provenance, license, freshness
```

After this, `data/skills.json` is updated with all discovered skills.

---

#### Stage 2 — Capability Clustering (AI-Assisted)

Skills need to be grouped into one of 8 capability categories. Your AI assistant picks the best fit.

**Step A — Prepare the input:**

```bash
python -m kitchen cluster-prepare
```

This writes `.kitchen_cache/cluster_input.json` containing:

- A list of skills that need classification
- The available capabilities to choose from

**Step B — Have your AI read the file and decide:**

Ask your AI coding assistant:

> *"Read `.kitchen_cache/cluster_input.json`. For each skill in `heads_needing_classification`, pick the best capability from the `capabilities` list based on the skill's name, description, and body excerpt. Write the results to `.kitchen_cache/cluster_output.json` in this format:"*
>
> ```json
> {"assignments": {"skill-id-1": "capability-id", "skill-id-2": "capability-id"}}
> ```

The 8 capabilities are:

| ID | Label |
|----|-------|
| `documents` | Create & edit documents |
| `data-analysis` | Analyze data & spreadsheets |
| `frontend` | Build web pages & UI |
| `cloud-ops` | Work with Google Cloud |
| `testing` | Test web apps & code |
| `planning` | Plan long agent tasks |
| `agent-building` | Build MCP servers & agents |
| `design` | Design, themes & branding |

**Step C — Apply the assignments:**

```bash
python -m kitchen cluster-apply
```

---

#### Stage 3 — Card Writing (AI-Assisted)

Each skill needs an "Explainer Card" — a short, user-friendly summary. Your AI writes these.

**Step A — Prepare the input:**

```bash
python -m kitchen cards-prepare
```

This writes `.kitchen_cache/cards_input.json` with skills that need cards.

**Step B — Have your AI write the cards:**

Ask your AI coding assistant:

> *"Read `.kitchen_cache/cards_input.json`. For each skill in `heads_needing_cards`, write a product card for a non-technical audience. Write the results to `.kitchen_cache/cards_output.json` in this format:"*
>
> ```json
> {"cards": {"skill-id": {"title": "...", "what_it_does": "...", "try_saying": "..."}}}
> ```

**Card rules (enforced by the pipeline):**

| Field | Rules |
|-------|-------|
| `title` | Outcome-phrased, verb-first, **max 6 words**, no jargon |
| `what_it_does` | **Max 2 sentences**, plain language, no unexpanded acronyms |
| `try_saying` | One realistic prompt a user could type, **max 25 words** |

**Step C — Apply the cards:**

```bash
python -m kitchen cards-apply
```

> [!NOTE]
> Cards that violate the length rules are rejected and logged — they aren't silently truncated. If you see failures, ask your AI to rewrite the offending cards and run `cards-apply` again.

---

#### Stage 4 — Emit the Knowledge Base

```bash
python -m kitchen emit
```

This validates everything and writes the final `data/kb.json` — the file the website reads.

---

## 7. Review & Curate Skills (Human-in-the-Loop)

After the pipeline runs, all new skills enter as `"shell"` tier (unreviewed). A human must promote them to `"core"` before they appear prominently on the site.

### See What's Waiting for Review

```bash
python -m kitchen review --queue
```

This shows a table of cluster heads sorted by importance.

### Review a Specific Skill

```bash
python -m kitchen review <skill_id>
```

The CLI shows you:

- The skill's origin, license, and metadata
- The AI-generated explainer card
- A prompt with four options:

| Key | Action |
|-----|--------|
| `p` | **Promote** — upgrades to `"core"`, stamps your name + timestamp |
| `e` | **Edit card** — opens the card JSON in your editor for manual refinement |
| `r` | **Reject** — marks as rejected with a reason |
| `s` | **Skip** — leave for later |

### View the Skill on GitHub

```bash
python -m kitchen review <skill_id> --web
```

This opens the skill's `SKILL.md` on GitHub in your browser so you can inspect the upstream source.

### After Reviewing, Regenerate

```bash
python -m kitchen emit
```

Always re-emit after promoting or rejecting skills so `data/kb.json` reflects your changes.

---

## 8. Publish Your Changes

### Local Preview

```bash
cd site
npm run build     # Full production build (also runs type-checking)
npm run preview   # Serve the production build locally
```

### Deploy to Vercel

SkillDeck is configured for Vercel via `vercel.json`. The deployment process:

1. **Commit your updated `data/kb.json`** (and any changed `data/*.json` files)
2. **Push to your main branch**
3. Vercel automatically builds and deploys `site/dist`

> [!IMPORTANT]
> Vercel does **not** run the Python kitchen. The `data/kb.json` file must already be up-to-date in your repo before pushing. Always run `python -m kitchen emit` and commit the result before deploying.

---

## 9. Day-to-Day Cheat Sheet

### "I want to refresh all skill data"

```bash
$env:GITHUB_TOKEN = 'ghp_...'          # Ensure token is set
python -m kitchen pipeline             # Fetch + dedup + rank
python -m kitchen cluster-prepare      # Then have your AI classify
python -m kitchen cluster-apply
python -m kitchen cards-prepare        # Then have your AI write cards
python -m kitchen cards-apply
python -m kitchen summary-prepare      # Then have your AI write Skill Summaries
python -m kitchen summary-apply
python -m kitchen emit                 # Regenerate kb.json
```

Or just run `/skilldeck-ingest` in Claude Code and it does all of the above.

### "I want to check if upstream skills have changed"

```bash
python -m kitchen freshness
```

This diffs upstream blob SHAs for `"core"` skills and flags any that have drifted.

### "I want to run the tests"

```powershell
# Everything at once:
#   Windows:
.\scripts\win\dev-test.ps1
#   Linux/macOS:
./scripts/linux/dev-test.sh

# Or individually:
python -m pytest kitchen/tests/           # Python kitchen tests
cd site && npm run test                    # Frontend unit tests (Vitest)
cd site && npm run test:e2e               # End-to-end browser tests (Playwright)
```

### "I want to add a new capability category"

This requires changes in **three places** (keep them in sync):

1. `kitchen/config.py` — add to `CAPABILITIES` list
2. `kitchen/schemas.py` — add to the enum validation
3. `site/src/components/Wizard.tsx` and `SkillCard.astro` — add to the frontend's hardcoded lists

### "I want to add a new supported tool"

Same pattern — update all three:

1. `kitchen/config.py` — add to `TOOLS` list
2. `data/install_matrix.json` — add install method templates
3. `site/src/components/Wizard.tsx` and `SkillCard.astro` — add to the frontend's tool lists

---

## 10. Troubleshooting

### GitHub rate limit errors during ingest

```
Set your token:  $env:GITHUB_TOKEN = 'ghp_...'
```

Without a token, GitHub's API allows only 60 requests/hour. With one, you get 5,000.

### `data/kb.json` not found

```bash
python -m kitchen emit
```

This regenerates it. If `skills.json` is also missing, run `python -m kitchen pipeline` first.

### Card validation failures during `cards-apply`

The pipeline rejects cards that exceed length limits. Ask your AI to rewrite them within the constraints:

- Title: ≤ 6 words
- Description: ≤ 2 sentences
- Try saying: ≤ 25 words

Then run `python -m kitchen cards-apply` again.

### Frontend build fails with TypeScript errors

```bash
cd site
npx astro check
```

This shows you exactly which type errors need fixing. Common cause: the shape of `kb.json` changed but the TypeScript interfaces in `Wizard.tsx` weren't updated.

### `.kitchen_cache/` is stale or corrupted

Delete it and re-run:

```bash
# Windows:
Remove-Item -Recurse -Force .kitchen_cache

# Then re-run the pipeline
python -m kitchen pipeline
```

The cache is gitignored and fully reconstructable.

---

> **License:** Apache-2.0 — see [LICENSE](LICENSE) for details.
>
> **Questions?** Open an issue on the [GitHub repo](https://github.com/kunalsuri/SkillDeck) or ask your AI coding assistant — it has full context from `AGENTS.md` and `CLAUDE.md`.
