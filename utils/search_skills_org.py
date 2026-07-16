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

def search_skills_org():
    """
    Searches for files named SKILL.md in the 'skills' GitHub organization.
    """
    github_token = load_env_token()
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SkillDeck-Pipeline-Checker"
    }
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    else:
        print("[WARNING] GITHUB_TOKEN environment variable not set. Code search requires authentication.")

    search_url = "https://api.github.com/search/code?q=filename:SKILL.md+org:skills"
    print(f"Searching: {search_url}")
    try:
        response = requests.get(search_url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            print(f"Found {data.get('total_count')} files:")
            for item in data.get("items", []):
                print(f"  Repo: {item['repository']['full_name']}, Path: {item['path']}")
        else:
            print(f"Failed: HTTP status {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Error searching organization: {e}")

if __name__ == "__main__":
    search_skills_org()
