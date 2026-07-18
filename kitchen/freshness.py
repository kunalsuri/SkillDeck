from datetime import datetime, timezone
from kitchen.config import SKILLS_JSON
from kitchen.utils import GitHubClient, load_all_skills, save_skills

def check_freshness():
    print("Checking upstream freshness for core skills...")
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    if not skills:
        print("No skills to check.")
        return

    client = GitHubClient()
    modified = False

    for s in skills:
        if s.get("status") == "active" and s.get("tier") == "core":
            org = s["origin"]["org"]
            repo = s["origin"]["repo"]
            path = s["origin"]["path"]
            branch = s["origin"]["default_branch"]
            current_sha = s["upstream"].get("blob_sha")
            
            skill_id = s["id"]
            print(f"Checking freshness of '{skill_id}' in {org}/{repo}...")
            
            # API: GET /repos/{org}/{repo}/contents/{path}/SKILL.md
            url = f"https://api.github.com/repos/{org}/{repo}/contents/{path}/SKILL.md?ref={branch}"
            try:
                content_info = client.get(url)
                upstream_sha = content_info.get("sha")
                
                if upstream_sha and upstream_sha != current_sha:
                    print(f"  Drift detected for '{skill_id}': local blob {current_sha} != upstream blob {upstream_sha}")
                    s["freshness"] = "drifted"
                    s["upstream_changed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    # Update blob_sha so next runs don't keep repeating it
                    # But we retain reviewed_commit_sha which tracks what was promoted!
                    s["upstream"]["blob_sha"] = upstream_sha
                    modified = True
                else:
                    print(f"  '{skill_id}' is up-to-date.")
            except Exception as e:
                print(f"  Failed to check freshness for '{skill_id}': {e}")
                
    if modified:
        save_skills(SKILLS_JSON, skills)
        print("Freshness database updated.")
    else:
        print("No freshness drift detected.")

if __name__ == "__main__":
    check_freshness()
