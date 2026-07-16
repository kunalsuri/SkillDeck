# System architecture diagrams

Five [Excalidraw](https://excalidraw.com) diagrams describing SkillDeck from a
systems-engineering perspective: who/what talks to what, how the pipeline
executes stage by stage, what the JSON schemas look like, and where each
piece physically runs. Open any `.excalidraw` file directly at
[excalidraw.com](https://excalidraw.com) (File → Open) or in the VS Code
Excalidraw extension — they're editable, not static images.

| File | View | What it shows |
|---|---|---|
| [`01-system-context.excalidraw`](./01-system-context.excalidraw) | C4 Level 1 — System Context | The SkillDeck repo's boundary and every actor/external system around it: the human curator (CLI **or** Web Review Portal), the AI agent running `/skilldeck-ingest`, GitHub, Vercel, and end users. Shows `data/kb.json` as the one artifact bridging Kitchen and Site. Also shows the new `audit/` directory as a local-only developer tool — never served by Vercel. |
| [`02-container-diagram.excalidraw`](./02-container-diagram.excalidraw) | C4 Level 2 — Containers/Components | Every module inside `kitchen/` (CLI, each stage file, `data/skill-<source-id>.json` stores, `.kitchen_cache/`, `mirror/`) and inside `site/` (Astro pages, `Wizard.tsx`, `SkillCard.astro`, build/deploy). Includes: the new **`utils.py`** container (GitHubClient, `load_all_skills`, `save_skills`, `atomic_write_json`, `get_existing_matching_skill`); the **`audit/audit.html` Review Portal** served by the built-in HTTP server inside `review.py`; and the agent hand-off points for clustering and cards. |
| [`03-pipeline-flow.excalidraw`](./03-pipeline-flow.excalidraw) | Process/stage flow | The kitchen pipeline's actual execution order per `.claude/commands/skilldeck-ingest.md`: `ingest → canonicalize → dedup → rank → cluster-prepare → [agent] → cluster-apply → cards-prepare → [agent] → cards-apply → emit`. Includes the updated ingest step's blob-SHA cache-hit short-circuit (unchanged skills skip the GitHub blob fetch). `review.py`/`freshness.py` remain asynchronous, human-triggered steps off the main line — now with two review entry points: `--queue`/`<skill_id>` (CLI) and `--web` (HTTP server + audit.html portal). |
| [`04-data-model.excalidraw`](./04-data-model.excalidraw) | Data model | Field-level shape of `sources.json`, `skill-<source-id>.json` (the new per-source split replacing the monolithic `skills.json`), `install_matrix.json`, and `kb.json` (mirroring `kitchen/schemas.py`). Includes derivation arrows, the `atomic_write_json` write path, the `shell → core / rejected` tier state machine driven by `review.py`, and the `source_id → filename` mapping rule (`skill-{safe_source_id}.json`). Also notes the legacy-migration path: if a `skills.json` exists with no `skill-*.json` siblings, it is read and then deleted on the next `save_skills` call. |
| [`05-deployment.excalidraw`](./05-deployment.excalidraw) | Deployment/infrastructure | Where each piece actually runs: developer machine (Python venv, Node, `GITHUB_TOKEN`, the Claude Code agent, the local HTTP review server at `127.0.0.1:8000` serving `audit/audit.html`), GitHub (source repos + this repo's committed `data/skill-*.json` and `data/kb.json`), and Vercel (builds/serves `site/` only — never invokes the Python kitchen, never exposes the review portal). |

## Why these five

The project is explicitly split into two halves that never share a process
(see the root `CLAUDE.md`), and its "ML pipeline" is actually a human/agent
hand-off pattern (`prepare`/`apply` JSON files), not a scripted model. A
single architecture picture can't carry both of those facts clearly, so this
set follows a systems-engineering C4-style breakdown (context → containers)
plus the two views that matter most for *this* codebase: the exact stage
order and the JSON schema get out of sync easily, so they're each broken out.

## What changed in the last commit

The following additions affect all five diagrams and should be updated next
time each diagram is opened:

| Area | Change |
|---|---|
| **Per-source skill files** | `data/skills.json` (monolithic) replaced by `data/skill-<source-id>.json` per source. `load_all_skills` globs for `skill-*.json`; `save_skills` groups by `source_id` and writes/cleans them atomically. Legacy `skills.json` is auto-deleted on the first `save_skills` call. |
| **`utils.py` — GitHubClient** | Centralized GitHub HTTP client with ETag disk caching (keyed by SHA-256 of URL), per-100 ms rate limiter, and 3-attempt exponential-backoff retry. Permanent 401/403/404 errors fail fast without retrying. |
| **`utils.py` — DB helpers** | `load_all_skills`, `save_skills`, `get_existing_matching_skill`, `atomic_write_json`, `parse_skill_md` extracted/consolidated into `utils.py` and shared across all pipeline stages. |
| **Blob-SHA cache hit in `ingest.py`** | Before fetching a blob, ingest checks `get_existing_matching_skill()`. If the `blob_sha` matches an existing record the fetch is skipped entirely, preserving reviewed/promoted metadata. |
| **Web Review Portal (`audit/audit.html`)** | A single-file, Tailwind + vanilla JS review UI (1 000+ lines). Served by `review.py`'s built-in `http.server` on `127.0.0.1:8000`. Localhost-only guard prevents accidental public exposure. Provides skill list, badge filters, inline card editing, promote/reject with audit trail, and live `kb.json` re-emit via `POST /api/save`. |
| **`review.py` — HTTP server** | `ReviewRequestHandler` + `start_review_server()` added. Exposes `GET /api/skills`, `GET /api/cards`, `GET /api/config`, `POST /api/save`. Triggered by `python -m kitchen review --web`. |
| **`cli.py` — `--web` flag** | `python -m kitchen review --web` (no skill ID) now calls `start_review_server()` instead of opening a GitHub URL. |
| **`test_utils_db.py`** | New `unittest.TestCase` covering single-file fallback, multi-file split/load/cleanup, and `get_existing_matching_skill` (case-insensitive, wrong SHA, wrong path). |
| **`test_cli.py`** | Expanded to cover the new `--web` flag routing and any new CLI sub-commands. |
| **`site/e2e/pages.spec.ts`** | Minor e2e spec additions aligned with any new frontend pages/routes. |

## Keeping these current

These are hand-built, not generated from code, so re-check them against
`kitchen/cli.py`, `kitchen/schemas.py`, `kitchen/utils.py`, and
`.claude/commands/skilldeck-ingest.md` when any of the following change:
pipeline stage order, the `KB_SCHEMA` / `SKILLS_SCHEMA` shape, the
`data/skill-*.json` naming convention, or the deployment split between
`kitchen/` and `site/`.
