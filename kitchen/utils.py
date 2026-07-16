import os
import time
import json
import hashlib
import requests
import yaml
from pathlib import Path
from datetime import datetime, timezone
from kitchen.config import CACHE_DIR

class GitHubClient:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SkillDeck-Pipeline"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self.last_request_time = 0.0

    def _rate_limit(self):
        # Enforce max 1 request per 100ms
        elapsed = time.time() - self.last_request_time
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self.last_request_time = time.time()

    def get(self, url: str, is_json: bool = True):
        self._rate_limit()

        # Cache key based on URL hash
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cache_file = CACHE_DIR / f"{url_hash}.json"
        
        cached_data = None
        etag = None
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    etag = cached_data.get("etag")
            except Exception:
                pass

        req_headers = self.headers.copy()
        if etag:
            req_headers["If-None-Match"] = etag

        # Retry with exponential backoff
        max_attempts = 3
        backoff = 1.0
        for attempt in range(max_attempts):
            try:
                response = requests.get(url, headers=req_headers, timeout=15)
                if response.status_code == 304 and cached_data:
                    # Cache hit
                    return cached_data["body"]
                
                # Check for rate limit or server error
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt < max_attempts - 1:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                
                response.raise_for_status()
                
                # Successful response (200 OK)
                new_etag = response.headers.get("ETag")
                body = response.json() if is_json else response.text
                
                # Write to cache
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({"etag": new_etag, "body": body}, f, indent=2, ensure_ascii=False)
                
                return body
            except Exception as e:
                # Permanent errors like 404, 403 (e.g. repo not found or private) should fail immediately
                if hasattr(e, 'response') and e.response is not None:
                    status = e.response.status_code
                    if status in (404, 403, 401):
                        print(f"Permanent error {status} fetching {url}: {e}")
                        raise e
                if attempt == max_attempts - 1:
                    raise e
                time.sleep(backoff)
                backoff *= 2

    def get_repo_default_branch(self, org: str, repo: str) -> str:
        url = f"https://api.github.com/repos/{org}/{repo}"
        try:
            info = self.get(url)
            return info.get("default_branch", "main")
        except Exception:
            return "main"

def parse_skill_md(content: str):
    """
    Parses frontmatter and body from a SKILL.md content.
    Returns (frontmatter, body_text).
    """
    lines = content.splitlines()
    if not lines or not lines[0].strip() == "---":
        return {}, content
    
    fm_lines = []
    body_start_idx = 1
    found_end = False
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start_idx = i + 1
            found_end = True
            break
        fm_lines.append(lines[i])
        
    if not found_end:
        return {}, content
    
    try:
        frontmatter = yaml.safe_load("\n".join(fm_lines)) or {}
    except Exception as e:
        print(f"Error parsing yaml frontmatter: {e}")
        frontmatter = {}
        
    body = "\n".join(lines[body_start_idx:])
    return frontmatter, body

def atomic_write_json(file_path: Path, data: dict):
    temp_path = file_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, file_path)

def load_all_skills(skills_json_path: Path) -> dict:
    """
    Loads all skills from the database.
    If skills_json_path is not named 'skills.json' or doesn't belong to 'data/' directory
    (e.g., in unit tests where it is mocked to a temporary file), we load from that single file.
    Otherwise, we search for all 'skill-*.json' files in the parent directory.
    If none are found, we fallback to the legacy 'skills.json' path if it exists (for migration).
    Returns a dict of {skill_id: skill_dict}.
    """
    skills_map = {}
    is_default = (skills_json_path.name == "skills.json" and skills_json_path.parent.name == "data")
    
    if is_default:
        data_dir = skills_json_path.parent
        skill_files = list(data_dir.glob("skill-*.json"))
        if skill_files:
            for sf in skill_files:
                try:
                    with open(sf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for s in data.get("skills", []):
                            skills_map[s["id"]] = s
                except Exception as e:
                    print(f"Warning: Failed to load {sf}: {e}")
            return skills_map
            
        # Legacy fallback
        if skills_json_path.exists():
            try:
                with open(skills_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for s in data.get("skills", []):
                        skills_map[s["id"]] = s
            except Exception as e:
                print(f"Warning: Failed to load legacy {skills_json_path}: {e}")
            return skills_map
    else:
        # Custom mock path (e.g. in tests)
        if skills_json_path.exists():
            try:
                with open(skills_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for s in data.get("skills", []):
                        skills_map[s["id"]] = s
            except Exception as e:
                print(f"Warning: Failed to load {skills_json_path}: {e}")
            return skills_map
            
    return skills_map

def save_skills(skills_json_path: Path, skills: list):
    """
    Saves the list of skills back to the database.
    If skills_json_path is not named 'skills.json' or doesn't belong to 'data/' directory,
    we write all skills to that single file (supporting mocked test paths).
    Otherwise, we group skills by their 'source_id' and write each group to 'skill-<source_id>.json'.
    We also delete the legacy 'skills.json' if it still exists.
    """
    is_default = (skills_json_path.name == "skills.json" and skills_json_path.parent.name == "data")
    
    if not is_default:
        output_data = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "skills": skills
        }
        atomic_write_json(skills_json_path, output_data)
        return
        
    data_dir = skills_json_path.parent
    
    # Track existing skill files to remove obsolete ones
    existing_files = {f.name: f for f in data_dir.glob("skill-*.json")}
    written_files = set()
    
    # Group skills by source_id
    skills_by_source = {}
    for s in skills:
        sid = s.get("source_id", "unknown")
        # Ensure source_id is safe for filenames
        safe_sid = "".join(c for c in sid if c.isalnum() or c in ("-", "_")).lower()
        skills_by_source.setdefault(safe_sid, []).append(s)
        
    for safe_sid, group in skills_by_source.items():
        file_name = f"skill-{safe_sid}.json"
        file_path = data_dir / file_name
        output_data = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "skills": group
        }
        atomic_write_json(file_path, output_data)
        written_files.add(file_name)
        
    # Delete legacy skills.json if it exists
    if skills_json_path.exists():
        try:
            skills_json_path.unlink()
        except Exception as e:
            print(f"Warning: Failed to delete legacy skills.json: {e}")
            
    # Clean up obsolete source files
    for name, path in existing_files.items():
        if name not in written_files:
            try:
                path.unlink()
                print(f"Removed obsolete source file: {name}")
            except Exception as e:
                print(f"Warning: Failed to delete obsolete file {name}: {e}")

def get_existing_matching_skill(existing_skills: dict, org: str, repo: str, path: str, blob_sha: str) -> dict:
    """
    Checks if a skill with the same repository and path already exists and has the same blob_sha.
    If so, returns the skill dict. Otherwise returns None.
    """
    normalized_path = str(Path(path).parent).replace("\\", "/")
    for skill in existing_skills.values():
        origin = skill.get("origin", {})
        if (origin.get("org", "").lower() == org.lower() and 
            origin.get("repo", "").lower() == repo.lower() and 
            origin.get("path") == normalized_path and 
            skill.get("upstream", {}).get("blob_sha") == blob_sha):
            return skill
    return None

