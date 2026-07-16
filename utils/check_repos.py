#!/usr/bin/env python3
import os
from pathlib import Path
import requests

def load_env_token():
    """
    Attempts to load GITHUB_TOKEN from the environment or from a .env file
    located in the project root directory.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        project_root = Path(__file__).resolve().parent.parent
        env_path = project_root / ".env"
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        # Ignore comments and empty lines
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, val = line.split("=", 1)
                            if key.strip() == "GITHUB_TOKEN":
                                val = val.strip()
                                # Strip optional quotes around value
                                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                                    val = val[1:-1]
                                os.environ["GITHUB_TOKEN"] = val
                                token = val
                                break
            except Exception as e:
                print(f"[WARNING] Failed to read .env file: {e}")
    return token

def check_repositories():
    """
    Checks the status, default branch, and license of specified GitHub repositories.
    """
    github_token = load_env_token()
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SkillDeck-Pipeline-Checker"
    }
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    else:
        print("[WARNING] GITHUB_TOKEN environment variable not set. API rate limits will apply.")

    repos_to_check = [
        ("GitHub Skills (skills/exercise-creator)", "skills", "exercise-creator"),
        ("OpenAI Skills", "openai", "skills"),
        ("NVIDIA Skills", "nvidia", "skills"),
        ("Datadog Labs Agent Skills", "datadog-labs", "agent-skills"),
        ("Block Agent Skills", "block", "agent-skills")
    ]

    for label, org, repo in repos_to_check:
        url = f"https://api.github.com/repos/{org}/{repo}"
        print(f"Checking {label}: {url}")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                license_info = data.get("license")
                license_name = license_info.get("spdx_id") if license_info else None
                print(f"  [SUCCESS] Found {org}/{repo}!")
                print(f"  Default branch: {data.get('default_branch')}")
                print(f"  License: {license_name}")
                print(f"  Description: {data.get('description')}")
            else:
                print(f"  [FAILED] HTTP status {response.status_code}: {response.text}")
        except Exception as e:
            print(f"  [ERROR] {e}")

if __name__ == "__main__":
    check_repositories()
