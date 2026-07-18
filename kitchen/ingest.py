import json
from datetime import datetime, timezone
from pathlib import Path
from kitchen.config import SOURCES_JSON, SKILLS_JSON, OFFICIAL_ORGS, PARTNER_ORGS
from kitchen.utils import GitHubClient, parse_skill_md, load_all_skills, save_skills, get_existing_matching_skill

def ingest_all():
    print("Ingesting sources...")
    if not SOURCES_JSON.exists():
        print(f"Error: {SOURCES_JSON} does not exist.")
        return

    with open(SOURCES_JSON, "r", encoding="utf-8") as f:
        sources_data = json.load(f)
    
    # Load existing skills
    existing_skills = load_all_skills(SKILLS_JSON)

    client = GitHubClient()
    new_skills = {}
    failed_source_ids = set()

    for source in sources_data.get("sources", []):
        source_id = source["id"]
        kind = source["kind"]
        if kind == "aggregator":
            print(f"Skipping aggregator source '{source_id}' during ingest (will be processed in canonicalize).")
            continue

        repo_url = source["repo_url"]
        org = source["org"]
        # extract repo name from url
        repo = repo_url.split("github.com/")[-1].split("/")[-1]

        print(f"Ingesting from direct source: {org}/{repo} ({source_id})")

        branch = client.get_repo_default_branch(org, repo)
        tree_url = f"https://api.github.com/repos/{org}/{repo}/git/trees/{branch}?recursive=1"

        try:
            tree_data = client.get(tree_url)
        except Exception as e:
            print(f"Failed to fetch tree for {org}/{repo}: {e}")
            # We didn't actually see this source's current skill list, so we
            # can't tell "skill was deleted upstream" from "network/auth
            # failure" - don't let the vanished-skill sweep below mark this
            # source's existing skills 'gone' on the strength of a fetch we
            # never completed.
            failed_source_ids.add(source_id)
            continue

        commit_sha = tree_data.get("sha", "")
        
        for item in tree_data.get("tree", []):
            path = item.get("path", "")
            if path.endswith("SKILL.md") and item.get("type") == "blob":
                blob_sha = item.get("sha", "")
                
                existing_match = get_existing_matching_skill(existing_skills, org, repo, path, blob_sha)
                if existing_match:
                    print(f"Skipping fetch for unchanged skill '{existing_match['id']}' ({blob_sha})")
                    existing_match["upstream"]["fetched_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    # Found in the upstream tree this run, so it is active regardless of
                    # any stale "gone" status left over from a previous ingest.
                    existing_match["status"] = "active"
                    new_skills[existing_match["id"]] = existing_match
                    continue
                
                # Fetch blob contents
                blob_url = f"https://api.github.com/repos/{org}/{repo}/git/blobs/{blob_sha}"
                try:
                    blob_response = client.get(blob_url)
                    # Content is base64 encoded
                    import base64
                    raw_content = base64.b64decode(blob_response.get("content", "")).decode("utf-8", errors="ignore")
                except Exception as e:
                    print(f"Failed to fetch blob {blob_sha} for {path}: {e}")
                    continue

                frontmatter, body = parse_skill_md(raw_content)
                skill_name = frontmatter.get("name", Path(path).parent.name)
                # Ensure name is a string and fallback
                if not skill_name or skill_name == "." or skill_name == "":
                    skill_name = Path(path).parent.name
                
                # Deduce capability if already present, or default to unassigned
                capability_id = frontmatter.get("capability", "unassigned")
                
                # Generate unique kebab ID
                # anthropic-docx, google-analytics, etc.
                skill_id = f"{org.lower()}-{skill_name.lower().replace('_', '-')}"
                
                # Determine default license
                default_license = source.get("default_license") or "unspecified"
                license_val = frontmatter.get("license") or default_license
                
                # Re-use properties from existing record if it exists
                existing = existing_skills.get(skill_id, {})
                tier = existing.get("tier", "shell")
                status = "active"
                
                # Keep reviewed fields
                reviewed_by = existing.get("reviewed_by")
                reviewed_at = existing.get("reviewed_at")
                reviewed_commit_sha = existing.get("reviewed_commit_sha")
                reject_reason = existing.get("reject_reason")
                
                # Keep install_hints if available
                install_hints = existing.get("install_hints") or frontmatter.get("install_hints") or {}

                provenance = "community"
                if org.lower() in OFFICIAL_ORGS:
                    provenance = "official"
                elif org.lower() in PARTNER_ORGS:
                    provenance = "partner"

                new_skills[skill_id] = {
                    "id": skill_id,
                    "source_id": source_id,
                    "provenance": provenance,
                    "origin": {
                        "org": org,
                        "repo": repo,
                        "path": str(Path(path).parent).replace("\\", "/"),
                        "default_branch": branch
                    },
                    "name": skill_name,
                    "frontmatter_description": frontmatter.get("description", ""),
                    "license": license_val,
                    "mirrorable": license_val in ("Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause"),
                    "upstream": {
                        "commit_sha": commit_sha,
                        "blob_sha": blob_sha,
                        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    },
                    "status": status,
                    "tier": tier,
                    "capability_id": existing.get("capability_id") or capability_id,
                    "native_ecosystem": frontmatter.get("native_ecosystem") or ("claude" if org == "anthropics" else "google" if org == "google" else "generic"),
                    "install_hints": install_hints,
                    "reviewed_by": reviewed_by,
                    "reviewed_at": reviewed_at,
                    "reviewed_commit_sha": reviewed_commit_sha,
                    "reject_reason": reject_reason,
                    "freshness": existing.get("freshness"),
                    "upstream_changed_at": existing.get("upstream_changed_at")
                }

    # Now verify which of the existing skills have vanished.
    # Only skills belonging to a direct source whose tree we actually
    # fetched this run are eligible - if the fetch failed we have no signal
    # either way, so we leave those skills' status untouched.
    processed_source_ids = {s["id"] for s in sources_data.get("sources", []) if s["kind"] != "aggregator"}
    preserved_after_failure = 0
    for skill_id, skill in existing_skills.items():
        if skill_id in new_skills:
            continue
        source_id = skill.get("source_id")
        if source_id in processed_source_ids and source_id not in failed_source_ids:
            # Skill has vanished!
            skill["status"] = "gone"
        elif source_id in failed_source_ids:
            preserved_after_failure += 1
        new_skills[skill_id] = skill

    if failed_source_ids:
        print(
            f"Warning: {len(failed_source_ids)} source(s) failed to fetch this run "
            f"({', '.join(sorted(failed_source_ids))}); left {preserved_after_failure} "
            f"of their existing skill(s) untouched instead of marking them 'gone'."
        )

    # Update output skills.json
    save_skills(SKILLS_JSON, list(new_skills.values()))
    print(f"Ingested {len(new_skills)} skills database.")

if __name__ == "__main__":
    ingest_all()
