import json
from datetime import datetime, timezone
from pathlib import Path
from kitchen.config import SKILLS_JSON, TOOLS
from kitchen.dedup import sort_key
from kitchen.utils import load_all_skills, save_skills

def days_since(date_str: str) -> int:
    try:
        # parsed date is UTC (Z)
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        return max(0, delta.days)
    except Exception:
        return 0

def ecosystem_match(ecosystem: str, tool: str) -> bool:
    mappings = {
        "claude": {"claude-code", "claude-ai"},
        "google": {"antigravity", "gemini-cli"},
        "vscode": {"vscode-copilot", "cursor"},
        "generic": set()
    }
    return tool in mappings.get(ecosystem, set())

def score_skill(skill: dict, target_tool: str = None) -> int:
    s = 0
    # Core human-read beats all
    if skill.get("tier") == "core" and skill.get("reviewed_by"):
        s += 1000
        
    prov = skill.get("provenance", "community")
    s += {"official": 300, "partner": 200, "community": 100}.get(prov, 100)
    
    lic = skill.get("license", "unspecified")
    s += {"Apache-2.0": 30, "MIT": 30, "BSD-2-Clause": 30, "BSD-3-Clause": 30,
          "source-available": 20}.get(lic, 0)
          
    fetched_at = skill["upstream"].get("fetched_at", "")
    days = days_since(fetched_at)
    s += max(0, 20 - days // 30)
    
    ecosystem = skill.get("native_ecosystem", "generic")
    if target_tool and ecosystem_match(ecosystem, target_tool):
        s += 50
        
    return s

def run_rank():
    print("Running ranking...")
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    if not skills:
        print("No skills to rank.")
        return

    # Update scores for all active skills
    for s in skills:
        if s.get("status") == "active":
            s["score_default"] = score_skill(s, None)
            s["scores_by_tool"] = {
                t["id"]: score_skill(s, t["id"]) for t in TOOLS
            }
            
    # Save skills database
    save_skills(SKILLS_JSON, skills)
    print(f"Ranked active skills. Scores saved in database.")

if __name__ == "__main__":
    run_rank()
