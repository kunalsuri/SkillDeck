# Known issues

Standing record of environment/tooling issues that aren't bugs in this
repo's code, but will trip up a fresh dev machine — plus what was done
about them.

Each entry should carry a **Logged** date, the **Environment** it was
observed on, and a **Status** (`Open` / `Resolved` / `Monitoring`) so
this stays a live reference instead of going stale. Add newest entries
at the top.

<!-- Last updated: 2026-07-12 -->

## Windows + Norton Antivirus breaks `kitchen` ingest with SSL errors

- **Logged:** 2026-07-12
- **Environment:** Windows 11 Home Single Language (build 10.0.26200),
  Python 3.13.14, Norton 360 (SSL/TLS scanning enabled)
- **Status:** Resolved (workaround is environment-local; see Fix)

**Symptom:** `python -m kitchen ingest` (or the full pipeline /
`/skilldeck-ingest`) fails on every GitHub source with SSL certificate
verification errors.

**Root cause:** Norton Antivirus's SSL/TLS scanning intercepts HTTPS
traffic to GitHub and re-signs it with its own root CA. Windows trusts
that CA, but Python's OpenSSL-based certificate verification doesn't —
and even once trusted, it also tripped a strict "Basic Constraints not
marked critical" check on Norton's cert.

**Fix:** Installed [`truststore`](https://pypi.org/project/truststore/)
in `.venv` (delegates certificate verification to Windows' native trust
store) via a `sitecustomize.py`, scoped entirely to this project's
gitignored `.venv` — nothing in the repo or system config changed
permanently.

**Important catch — silent data loss on the first failed run:** The
first (failed) ingest run misread the connection failures as "these
files were deleted upstream" and silently flipped 98 previously-active
skills to `status: "gone"` in `data/skills.json`. This was caught via
`git diff` before any downstream stage (cluster/rank/emit) ran, reverted,
and ingest was re-run cleanly with zero false deletions.

**Takeaway:** After any `ingest` run, always check `git diff
data/skills.json` for unexpected `status` changes before running later
pipeline stages — a network/SSL failure should not be able to look like
an upstream deletion.
