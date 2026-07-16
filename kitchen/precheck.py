"""Standalone diagnostic for the two classes of failure that most often stop
the kitchen pipeline before it can do anything useful: a missing/invalid
GITHUB_TOKEN, and a machine that can't complete an HTTPS/TLS handshake to
the GitHub API (corporate proxy, VPN, broken cert store, offline).

Run it before `ingest`/`canonicalize`/`freshness`:

    python -m kitchen precheck

Exits 0 if nothing blocks the pipeline (warnings are still printed but don't
fail the run), 1 if something does. Never prints the token value itself.
"""
import importlib.util
import os
import socket
import sys
from pathlib import Path

import requests

from kitchen.config import PROJECT_ROOT, DATA_DIR, CACHE_DIR, MIRROR_DIR

GITHUB_API_HOST = "api.github.com"
ENV_FILE = PROJECT_ROOT / ".env"
REQUIRED_PACKAGES = ["requests", "yaml", "datasketch", "jsonschema"]
PLACEHOLDER_TOKENS = {"ghp_your_token_here", "", "changeme"}


class CheckResult:
    def __init__(self, name: str, status: str, message: str):
        self.name = name
        self.status = status  # "ok" | "warn" | "fail"
        self.message = message


def _read_env_file_token(env_path: Path) -> str:
    """Best-effort read of GITHUB_TOKEN=... from a .env file. Returns the
    value (possibly empty) or None if no such line exists. Never logged."""
    if not env_path.exists():
        return None
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("GITHUB_TOKEN="):
                    return line[len("GITHUB_TOKEN="):].strip().strip('"').strip("'")
    except Exception:
        return None
    return None


def check_python_deps() -> CheckResult:
    missing = [pkg for pkg in REQUIRED_PACKAGES if importlib.util.find_spec(pkg) is None]
    if missing:
        return CheckResult(
            "Python dependencies", "fail",
            f"Missing package(s): {', '.join(missing)}. Run 'pip install -r requirements.txt'."
        )
    return CheckResult("Python dependencies", "ok", "requests/pyyaml/datasketch/jsonschema all importable.")


def check_github_token() -> tuple:
    """Returns (CheckResult, resolved_token_or_None). Mirrors the
    /skilldeck-ingest preflight: env var first, then a GITHUB_TOKEN= line in
    .env (read-only - this never writes to os.environ or any file)."""
    env_token = os.getenv("GITHUB_TOKEN")
    if env_token and env_token not in PLACEHOLDER_TOKENS:
        return CheckResult("GITHUB_TOKEN", "ok", "Set in the shell environment."), env_token

    dotenv_token = _read_env_file_token(ENV_FILE)
    if dotenv_token and dotenv_token not in PLACEHOLDER_TOKENS:
        return (
            CheckResult(
                "GITHUB_TOKEN", "ok",
                f"Not in the shell environment, but found in {ENV_FILE.name} "
                "(the pipeline will need to export this before running)."
            ),
            dotenv_token,
        )

    if dotenv_token in PLACEHOLDER_TOKENS and dotenv_token is not None:
        return (
            CheckResult(
                "GITHUB_TOKEN", "fail",
                f"{ENV_FILE.name} has a GITHUB_TOKEN line but it still looks like the "
                "placeholder value - replace it with a real token from "
                "https://github.com/settings/tokens."
            ),
            None,
        )

    return (
        CheckResult(
            "GITHUB_TOKEN", "warn",
            f"Not set in the shell environment and no {ENV_FILE.name} found. "
            "ingest/canonicalize/freshness will still run but hit GitHub's "
            "unauthenticated rate limit (60 requests/hour)."
        ),
        None,
    )


def check_dns() -> CheckResult:
    try:
        socket.getaddrinfo(GITHUB_API_HOST, 443)
        return CheckResult("DNS resolution", "ok", f"{GITHUB_API_HOST} resolves.")
    except Exception as e:
        return CheckResult(
            "DNS resolution", "fail",
            f"Could not resolve {GITHUB_API_HOST}: {e}. Check network/VPN connectivity."
        )


def check_tls_and_reachability() -> CheckResult:
    try:
        requests.get(f"https://{GITHUB_API_HOST}/zen", timeout=10)
        return CheckResult("HTTPS/TLS to GitHub", "ok", f"HTTPS handshake to {GITHUB_API_HOST} succeeded.")
    except requests.exceptions.SSLError as e:
        return CheckResult(
            "HTTPS/TLS to GitHub", "fail",
            f"TLS handshake failed: {e}. This is usually a corporate proxy/VPN doing TLS "
            "interception with a root CA that isn't trusted, or a broken local cert store - "
            "not a code or token problem. On Windows, `curl -vI https://api.github.com` "
            "showing a schannel/revocation error points at network-level interception rather "
            "than a bad certifi bundle."
        )
    except requests.exceptions.ConnectionError as e:
        return CheckResult(
            "HTTPS/TLS to GitHub", "fail",
            f"Could not connect to {GITHUB_API_HOST}: {e}. Check firewall/proxy/offline status."
        )
    except requests.exceptions.Timeout:
        return CheckResult(
            "HTTPS/TLS to GitHub", "fail",
            f"Connection to {GITHUB_API_HOST} timed out after 10s."
        )
    except Exception as e:
        return CheckResult("HTTPS/TLS to GitHub", "fail", f"Unexpected error reaching {GITHUB_API_HOST}: {e}")


def check_github_api_auth(token: str) -> CheckResult:
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "SkillDeck-Precheck"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        resp = requests.get(f"https://{GITHUB_API_HOST}/rate_limit", headers=headers, timeout=10)
    except Exception as e:
        return CheckResult("GitHub API auth", "fail", f"Could not reach the GitHub API: {e}")

    if resp.status_code == 401:
        return CheckResult(
            "GitHub API auth", "fail",
            "GitHub rejected the token (401 Unauthorized) - it's invalid, expired, or revoked. "
            "Generate a new one at https://github.com/settings/tokens."
        )
    if resp.status_code != 200:
        return CheckResult(
            "GitHub API auth", "fail",
            f"Unexpected status {resp.status_code} from /rate_limit: {resp.text[:200]}"
        )

    try:
        core = resp.json()["resources"]["core"]
        remaining, limit = core["remaining"], core["limit"]
    except Exception:
        return CheckResult("GitHub API auth", "warn", "Reached the API but couldn't parse rate-limit response.")

    if token and limit <= 60:
        return CheckResult(
            "GitHub API auth", "warn",
            f"Token was sent but the limit is still {limit}/hour (unauthenticated tier) - "
            "double-check the token is valid."
        )
    if remaining == 0:
        return CheckResult(
            "GitHub API auth", "fail",
            f"Rate limit exhausted (0/{limit} remaining). ingest/canonicalize/freshness will "
            "fail until it resets."
        )
    status = "ok" if token else "warn"
    auth_state = "authenticated" if token else "unauthenticated"
    return CheckResult(
        "GitHub API auth", status,
        f"{auth_state}, {remaining}/{limit} requests remaining this hour."
    )


def check_writable_dirs() -> CheckResult:
    problems = []
    for d in (DATA_DIR, CACHE_DIR, MIRROR_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".precheck_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except Exception as e:
            problems.append(f"{d}: {e}")
    if problems:
        return CheckResult("Writable data dirs", "fail", "; ".join(problems))
    return CheckResult(
        "Writable data dirs", "ok",
        f"{DATA_DIR.name}/, {CACHE_DIR.name}/, {MIRROR_DIR.name}/ are all writable."
    )


def run_precheck() -> bool:
    print("=" * 80)
    print("SkillDeck kitchen precheck: network + token diagnostics")
    print("=" * 80)

    results = []
    results.append(check_python_deps())

    token_result, token = check_github_token()
    results.append(token_result)

    results.append(check_dns())
    results.append(check_tls_and_reachability())

    # Only worth calling the authenticated endpoint if DNS/TLS work at all -
    # otherwise it's just a duplicate of the reachability failure above.
    tls_ok = results[-1].status == "ok"
    if tls_ok:
        results.append(check_github_api_auth(token))
    else:
        results.append(CheckResult("GitHub API auth", "warn", "Skipped - HTTPS to GitHub isn't working yet."))

    results.append(check_writable_dirs())

    print()
    worst = "ok"
    for r in results:
        label = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}[r.status]
        print(f"[{label:4}] {r.name}: {r.message}")
        if r.status == "fail":
            worst = "fail"
        elif r.status == "warn" and worst != "fail":
            worst = "warn"

    print()
    if worst == "fail":
        print("Result: BLOCKED - fix the FAIL item(s) above before running ingest/canonicalize/freshness.")
    elif worst == "warn":
        print("Result: OK WITH WARNINGS - the pipeline can run, but check the WARN item(s) above.")
    else:
        print("Result: ALL CLEAR - network and token look good.")

    return worst != "fail"


if __name__ == "__main__":
    sys.exit(0 if run_precheck() else 1)
