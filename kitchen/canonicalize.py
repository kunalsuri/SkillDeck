import json
import re
import base64
from datetime import datetime, timezone
from pathlib import Path
from kitchen.config import SOURCES_JSON, SKILLS_JSON, OFFICIAL_ORGS, PARTNER_ORGS
from kitchen.utils import GitHubClient, parse_skill_md, load_all_skills, save_skills, get_existing_matching_skill

def extract_github_repos(readme_text: str) -> list:
    """
    Extracts GitHub repo details from readme.
    Returns list of dicts: {"org": org, "repo": repo, "path": path}
    """
    # Regex to find GitHub repo links
    # Handles:
    # https://github.com/org/repo
    # https://github.com/org/repo/tree/branch/path
    pattern = r'https://github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)(?:/tree/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_\-/]+))?'
    matches = re.findall(pattern, readme_text)
    
    repos = []
    seen = set()
    for org, repo, branch, subpath in matches:
        org_l = org.lower()
        repo_l = repo.lower()
        
        # Filter out common false positives
        if org_l in ("user-attachments", "awesome-re") and repo_l in ("assets", "badge"):
            continue
            
        key = (org_l, repo_l, subpath)
        if key not in seen:
            seen.add(key)
            repos.append({
                "org": org,
                "repo": repo,
                "path": subpath if subpath else ""
            })
    return repos

def resolve_license(client: GitHubClient, org: str, repo: str) -> tuple:
    """
    Resolves the license of a repository.
    Returns (license_name, mirrorable)
    """
    license_url = f"https://api.github.com/repos/{org}/{repo}/license"
    try:
        data = client.get(license_url)
        lic_info = data.get("license", {})
        spdx = lic_info.get("spdx_id")
        
        # Map key to standard names
        canonical = "unspecified"
        if spdx:
            if spdx in ("Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "GPL-3.0", "AGPL-3.0"):
                canonical = spdx
            elif "apache" in spdx.lower():
                canonical = "Apache-2.0"
            elif "mit" in spdx.lower():
                canonical = "MIT"
            elif "bsd" in spdx.lower():
                # guess bsd
                canonical = "BSD-3-Clause"
            else:
                canonical = spdx
        
        mirrorable = canonical in ("Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause")
        return canonical, mirrorable
    except Exception:
        # Fallback to checking readme or repo details
        return "unspecified", False

def canonicalize_all():
    print("Canonicalizing aggregator entries...")
    if not SOURCES_JSON.exists():
        print(f"Error: {SOURCES_JSON} does not exist.")
        return

    with open(SOURCES_JSON, "r", encoding="utf-8") as f:
        sources_data = json.load(f)
    
    # Load existing skills
    existing_skills = load_all_skills(SKILLS_JSON)

    client = GitHubClient()
    new_skills = existing_skills.copy()

    for source in sources_data.get("sources", []):
        if source["kind"] != "aggregator":
            continue
        
        repo_url = source["repo_url"]
        org = source["org"]
        repo = repo_url.split("github.com/")[-1].split("/")[-1]
        
        print(f"Fetching README from aggregator seed: {org}/{repo}")
        readme_url = f"https://api.github.com/repos/{org}/{repo}/readme"
        try:
            readme_data = client.get(readme_url)
            readme_content = base64.b64decode(readme_data.get("content", "")).decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"Failed to fetch README for aggregator {org}/{repo}: {e}")
            continue
            
        discovered_repos = extract_github_repos(readme_content)
        print(f"Found {len(discovered_repos)} unique origin repository links in aggregator README.")
        
        # We will crawl each discovered repository for SKILL.md
        # Limit the crawl for testing or if we have too many, but here we scan all discovered
        for origin in discovered_repos:
            origin_org = origin["org"]
            origin_repo = origin["repo"]
            subpath_filter = origin["path"]
            
            print(f"Crawling origin repo: {origin_org}/{origin_repo} (subpath filter: '{subpath_filter}')")
            
            # Resolve default branch
            branch = client.get_repo_default_branch(origin_org, origin_repo)
            tree_url = f"https://api.github.com/repos/{origin_org}/{origin_repo}/git/trees/{branch}?recursive=1"
            
            try:
                tree_data = client.get(tree_url)
            except Exception as e:
                # Skip if repo is private, deleted, or has no git tree
                print(f"Skipping {origin_org}/{origin_repo}: {e}")
                continue
                
            commit_sha = tree_data.get("sha", "")
            
            # Resolve repo level license
            repo_license, repo_mirrorable = resolve_license(client, origin_org, origin_repo)
            
            for item in tree_data.get("tree", []):
                path = item.get("path", "")
                if path.endswith("SKILL.md") and item.get("type") == "blob":
                    # If there was a subpath tree filter, check if the path starts with it
                    if subpath_filter and not path.startswith(subpath_filter):
                        continue
                        
                    blob_sha = item.get("sha", "")
                    
                    existing_match = get_existing_matching_skill(existing_skills, origin_org, origin_repo, path, blob_sha)
                    if existing_match:
                        print(f"Skipping fetch for unchanged skill '{existing_match['id']}' ({blob_sha})")
                        existing_match["upstream"]["fetched_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        new_skills[existing_match["id"]] = existing_match
                        continue
                    
                    # Fetch blob content
                    blob_url = f"https://api.github.com/repos/{origin_org}/{origin_repo}/git/blobs/{blob_sha}"
                    try:
                        blob_response = client.get(blob_url)
                        raw_content = base64.b64decode(blob_response.get("content", "")).decode("utf-8", errors="ignore")
                    except Exception as e:
                        print(f"Failed to fetch blob {blob_sha} for {path}: {e}")
                        continue
                        
                    frontmatter, body = parse_skill_md(raw_content)
                    skill_name = frontmatter.get("name", Path(path).parent.name)
                    if not skill_name or skill_name == "." or skill_name == "":
                        skill_name = Path(path).parent.name
                        
                    # Generate a unique kebab ID stable for aggregator-discovered entries
                    # E.g. angular-skills-skillname or angular-skillname
                    # If org name matches repo name (e.g. lackeyjb/playwright-skill), just org-skillname
                    skill_id = f"{origin_org.lower()}-{skill_name.lower().replace('_', '-')}"
                    
                    # Resolve license (frontmatter wins, then repo license, then default)
                    license_val = frontmatter.get("license") or repo_license
                    mirrorable = license_val in ("Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause")
                    
                    # Determine provenance based on origin owner
                    provenance = "community"
                    if origin_org.lower() in OFFICIAL_ORGS:
                        provenance = "official"
                    elif origin_org.lower() in PARTNER_ORGS:
                        provenance = "partner"
                        
                    # Re-use existing fields if present
                    existing = existing_skills.get(skill_id, {})
                    tier = existing.get("tier", "shell")
                    
                    # Store skill record
                    # The source_id for aggregator-discovered skills must NOT be the aggregator ID.
                    # It should be the origin repository source ID, like "repo-origin_org-origin_repo"
                    origin_source_id = f"repo-{origin_org.lower()}-{origin_repo.lower()}"
                    
                    new_skills[skill_id] = {
                        "id": skill_id,
                        "source_id": origin_source_id,
                        "provenance": provenance,
                        "origin": {
                            "org": origin_org,
                            "repo": origin_repo,
                            "path": str(Path(path).parent).replace("\\", "/"),
                            "default_branch": branch
                        },
                        "name": skill_name,
                        "frontmatter_description": frontmatter.get("description", ""),
                        "license": license_val,
                        "mirrorable": mirrorable,
                        "upstream": {
                            "commit_sha": commit_sha,
                            "blob_sha": blob_sha,
                            "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        },
                        "status": "active",
                        "tier": tier,
                        "capability_id": existing.get("capability_id") or frontmatter.get("capability") or "unassigned",
                        "native_ecosystem": frontmatter.get("native_ecosystem") or ("claude" if origin_org == "anthropics" else "google" if origin_org == "google" else "generic"),
                        "install_hints": existing.get("install_hints") or frontmatter.get("install_hints") or {},
                        "reviewed_by": existing.get("reviewed_by"),
                        "reviewed_at": existing.get("reviewed_at"),
                        "reviewed_commit_sha": existing.get("reviewed_commit_sha"),
                        "reject_reason": existing.get("reject_reason"),
                        "freshness": existing.get("freshness"),
                        "upstream_changed_at": existing.get("upstream_changed_at")
                    }

    # Write output database
    save_skills(SKILLS_JSON, list(new_skills.values()))
    print(f"Canonicalized aggregator entries. Total skills: {len(new_skills)}.")

if __name__ == "__main__":
    canonicalize_all()
