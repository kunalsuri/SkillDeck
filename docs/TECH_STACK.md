# SkillDeck — Technical Stack

Machine-readable-ish reference for AI coding agents. This file lists every
technical brick (language, runtime, framework, library, deploy target) used
in this repository, with exact version pins where they exist. Use it to
compare against another project's stack, or to bootstrap an equivalent
project from a clean slate.

If you change a dependency, update this file in the same commit.

## 1. Repository shape

Two independent halves that never run in the same process, bridged by one
static JSON file (`data/kb.json`):

- `kitchen/` — offline Python pipeline. Runs locally only, never deployed.
- `site/` — static frontend. Deployed to Vercel, has no backend.

There is no server, no database, and no runtime LLM/API calls anywhere in
the deployed surface (`site/`). The only network calls in the whole repo are
the Python kitchen talking to the GitHub REST API, offline, by hand.

## 2. Frontend (`site/`) — deployed to Vercel

| Brick | Version (pinned in `site/package.json`) | Role |
|---|---|---|
| [Astro](https://astro.build) | `^7.0.6` (lockfile: `7.0.6`) | Static site generator / meta-framework. `output: 'static'` — no SSR, no API routes, no adapters. |
| [Preact](https://preactjs.com) | `^10.19.3` (lockfile: `10.29.6`) | UI library for interactive islands (React-compatible API, smaller runtime). |
| [`@astrojs/preact`](https://docs.astro.build/en/guides/integrations-guide/preact/) | `^6.0.1` | Astro integration wiring Preact islands, `compat: true` (React-compat shim for libs expecting React). |
| [Tailwind CSS](https://tailwindcss.com) | `^4.3.2` | Utility-first CSS. **v4 CSS-first config** — no `tailwind.config.js`; config lives in `site/src/styles/global.css` via `@import "tailwindcss"`, `@theme`, `@source`, `@custom-variant`. |
| [`@tailwindcss/vite`](https://tailwindcss.com/docs/installation/using-vite) | `^4.3.2` | Vite plugin form of Tailwind v4, wired into `astro.config.mjs`'s `vite.plugins`. |
| [TypeScript](https://www.typescriptlang.org) | `^6.0.3` | Types for `.astro`/`.tsx`/`.ts`; `astro/tsconfigs/strict` base config, `jsx: react-jsx` / `jsxImportSource: preact`. |
| [`marked`](https://marked.js.org) | `^18.0.5` | Markdown → HTML rendering for skill README content on skill detail pages. |
| [`sanitize-html`](https://github.com/apostrophecms/sanitize-html) | `^2.17.5` | Sanitizes the `marked` HTML output before it's rendered (XSS defense — the source markdown comes from third-party GitHub repos). |
| [Vitest](https://vitest.dev) | `^4.1.10` | Unit/component test runner, `jsdom` environment, `globals: true`. |
| [`jsdom`](https://github.com/jsdom/jsdom) | `^29.1.1` | DOM implementation for Vitest. |
| [`@testing-library/preact`](https://testing-library.com/docs/preact-testing-library/intro/) | `^3.0.0` | Component testing utilities for Preact islands. |
| [Playwright](https://playwright.dev) (`@playwright/test`) | `^1.42.1` (lockfile: `1.61.1`) | End-to-end tests (`site/e2e/*.spec.ts`) against a running dev server, Chromium only (`channel: 'chrome'`). |
| [`@astrojs/check`](https://docs.astro.build/en/guides/typescript/) | `^0.9.9` | `astro check` type-checker, run as part of `npm run build` — **type errors are build failures**. |

No global CSS framework beyond Tailwind; no component library (shadcn,
MUI, etc.); no state-management library (Preact `useState`/props only —
`Wizard.tsx` is the sole stateful component). No routing library — Astro's
file-based routing (`src/pages/`) handles all navigation, including
statically pre-rendered per-skill pages via `getStaticPaths()`.

### Runtime target

- Node.js — CI pins **Node 18** (`.github/workflows/ci.yml`,
  `actions/setup-node@v6` with `node-version: "18"`). No `.nvmrc` /
  `engines` field committed; treat 18 as the floor.
- Package manager: npm (`package-lock.json` committed, not yarn/pnpm).
- Build output: fully static files in `site/dist/` — no Node server at
  runtime, no edge functions, no serverless functions.

### Deploy target: Vercel

- `vercel.json` (repo root) pins:
  - `installCommand`: `npm install --prefix site`
  - `buildCommand`: `npm run build --prefix site`
  - `outputDirectory`: `site/dist`
  - Static security headers (CSP, `X-Content-Type-Options`,
    `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`,
    `Strict-Transport-Security`) applied to all routes at the CDN/edge
    level — not via `<meta>` tags or app code.
- Vercel never runs the Python kitchen. `data/kb.json` must already be
  committed and current at deploy time — there is no build-time data
  fetch, ingest, or LLM call on Vercel.
- `site/prebuild.js` runs as an npm `prebuild` lifecycle script before
  `astro build`; it copies the root `data/kb.json` into
  `site/src/data/kb.json` (a generated file, not hand-edited, not the
  source of truth).

## 3. Backend / data pipeline (`kitchen/`) — local only, never deployed

| Brick | Version (`requirements.txt` / `kitchen/pyproject.toml`) | Role |
|---|---|---|
| Python | `>=3.11` | Language/runtime for the whole `kitchen/` package. |
| [`requests`](https://requests.readthedocs.io) | `>=2.34.2` | HTTP client for the GitHub REST API (`kitchen/utils.py: GitHubClient`). |
| [`pyyaml`](https://pyyaml.org) | `>=6.0.3` | Parses YAML frontmatter in `SKILL.md` files. |
| [`datasketch`](https://ekzhu.github.io/datasketch/) | `>=2.0.0` | MinHash for near-duplicate skill detection (`dedup.py`, Jaccard threshold 0.7). |
| [`jsonschema`](https://python-jsonschema.readthedocs.io) | `>=4.26.0` | Validates `data/kb.json` against `kitchen/schemas.py: KB_SCHEMA` before emit. |

- Standard library `unittest` (not `pytest` fixtures) for all tests, run
  via `pytest kitchen/tests/` in CI and locally; `unittest.mock` mocks
  every GitHub API call — **no network access in tests**.
- [Bandit](https://bandit.readthedocs.io) — security static-analysis
  linter, run in CI (`bandit -r kitchen/ -x kitchen/tests/ -ll`) but not
  in `requirements.txt` (installed ad hoc in the CI job).
- No ORM, no database — all state is flat JSON files under `data/`,
  written atomically (temp file + `os.replace`).
- No ML/embedding model, no LLM SDK, **no `LLM_API_KEY` anywhere**.
  Capability clustering (`cluster.py`), lifecycle-phase classification
  (`phase.py`), and Explainer Card copywriting (`cards.py`) are all done
  by handing small JSON files to an interactive coding agent (via the
  `.claude/commands/skilldeck-ingest.md` slash command) rather than by
  a scripted model call.
- Auth: a single ambient `GITHUB_TOKEN` env var, used only to raise
  GitHub API rate limits for `ingest`/`canonicalize`/`freshness`. No
  OAuth flow, no secrets manager, no `.env` file convention (no
  `.env.example` committed).

## 4. Dev tooling / scripts (`scripts/`)

- Organized into `scripts/win/` (PowerShell scripts for Windows) and `scripts/linux/` (Bash scripts for Linux/macOS).
- `dev-setup` (`.ps1`/`.sh`), `dev-run` (`.ps1`/`.sh`), and `dev-test` (`.ps1`/`.sh`) provide idempotent setup, dev server launch, and a full test-suite runner respectively.

## 5. CI (`.github/workflows/ci.yml`)

GitHub Actions, two parallel jobs on push/PR to `main`:

- **`kitchen-tests`**: `actions/setup-python@v6` → Python 3.11 →
  `pip install -r requirements.txt` → Bandit scan → `pytest kitchen/tests/`.
- **`site-tests`**: `actions/setup-node@v6` → Node 18 (npm cache keyed on
  `site/package-lock.json`) → `npm install` → `npm audit --audit-level=high`
  → `npx playwright install --with-deps chromium` → Vitest → production
  `npm run build` → Playwright e2e.

No linting/type-checking step for the Python `kitchen/` code exists yet
(type-checking exists only on the frontend, via `astro check`).

## 6. License

Apache-2.0 (`LICENSE`).

## 7. What is deliberately *not* in this stack

Useful for an agent comparing this project against another one — these are
intentional omissions, not gaps to "fix":

- No SSR/edge runtime, no API routes, no serverless functions on the
  deployed site — everything is prebuilt static HTML/CSS/JS.
- No database of any kind (not even SQLite) — `data/*.json` is the entire
  persistence layer, hand-reviewed and git-committed.
- No LLM API key/SDK in either half of the codebase at runtime.
- No CSS-in-JS, no component library, no global state manager on the
  frontend.
- No containerization (no `Dockerfile`) — the kitchen runs as a local
  Python process, the site builds directly on Vercel's own build image.
