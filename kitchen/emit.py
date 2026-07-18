import json
import re
from datetime import datetime, timezone
from pathlib import Path
from kitchen.config import (
    SKILLS_JSON, INSTALL_MATRIX_JSON, KB_JSON, MIRROR_DIR, TOOLS, CAPABILITIES, LIFECYCLE_PHASES
)
from kitchen.utils import load_all_skills, atomic_write_json
from kitchen.dedup import resolve_skill_body
from kitchen.cards import load_cards_cache
from kitchen.schemas import validate_json, KB_SCHEMA

def resolve_install_command(skill: dict, tool_id: str, methods_dict: dict, fallback_order: list) -> str:
    org = skill["origin"]["org"]
    repo = skill["origin"]["repo"]
    skill_path = skill["origin"]["path"]
    skill_name = skill["name"]
    
    hints = skill.get("install_hints", {}).get(tool_id, {})
    
    # Available variables
    variables = {
        "org": org,
        "repo": repo,
        "skill_path": skill_path,
        "skill_name": skill_name,
    }
    # Add hints
    for k, v in hints.items():
        variables[k] = v
        
    for method_id in fallback_order:
        method = methods_dict.get((tool_id, method_id))
        if not method:
            continue
            
        template = method["template"]
        requires_hints = method.get("requires_hints", [])
        
        # Check required hints
        can_resolve = True
        for req in requires_hints:
            if req not in variables:
                can_resolve = False
                break
                
        # Parse template placeholders
        placeholders = re.findall(r'\{([a-zA-Z0-9_]+)\}', template)
        for p in placeholders:
            if p not in variables:
                can_resolve = False
                break
                
        if can_resolve:
            try:
                return template.format(**variables)
            except Exception:
                pass
    return None

def get_vendor(org: str) -> str:
    org_l = org.lower()
    if "anthropic" in org_l:
        return "anthropic"
    if "google" in org_l:
        return "google"
    return None

def load_previous_cards_by_capability() -> dict:
    """Best-effort read of the kb.json this emit is about to overwrite,
    indexed by capability_id. Tolerates a missing or malformed file (fresh
    clone) by treating it as "no previous kb"."""
    if not KB_JSON.exists():
        return {}
    try:
        with open(KB_JSON, "r", encoding="utf-8") as f:
            previous_kb = json.load(f)
    except Exception:
        return {}

    cards_by_cap = {}
    for entry in previous_kb.get("entries", []):
        cap_id = entry.get("capability_id")
        card = entry.get("card")
        if cap_id and card:
            cards_by_cap[cap_id] = card
    return cards_by_cap

def run_emit():
    print("Emitting cooked kb.json...")
    if not INSTALL_MATRIX_JSON.exists():
        print(f"Error: {INSTALL_MATRIX_JSON} does not exist.")
        return

    skills_map = load_all_skills(SKILLS_JSON)
    with open(INSTALL_MATRIX_JSON, "r", encoding="utf-8") as f:
        install_matrix = json.load(f)

    skills = list(skills_map.values())

    # Load cards cache, plus the previous kb.json's cards as a second-line
    # fallback so a cold cache on a fresh clone doesn't stomp real card copy
    # with generic fallback text (see Phase 0 / T2 in SPEC-01).
    cards_cache = load_cards_cache()
    previous_cards_by_cap = load_previous_cards_by_capability()

    # Build methods lookup dictionary
    methods_dict = {}
    for m in install_matrix.get("methods", []):
        methods_dict[(m["tool_id"], m["method"])] = m
    fallback_order = install_matrix.get("fallback_order", {})

    # Filter active, assigned, and non-rejected skills
    valid_caps = {c["id"] for c in CAPABILITIES}
    active_skills = [
        s for s in skills 
        if s.get("status") == "active" 
        and s.get("tier") != "rejected"
        and s.get("capability_id") in valid_caps
    ]

    # Group skills by capability_id. A capability is the UI's recommendation
    # slot: exactly one entry must be emitted per capability, even when two
    # independent dedup clusters (cluster_id) both landed in it - otherwise
    # only one of them would ever render (see entriesByCap in Wizard.tsx).
    capability_groups = {}
    for s in active_skills:
        cap_id = s.get("capability_id")
        if cap_id:
            capability_groups.setdefault(cap_id, []).append(s)

    # Compile entries
    entries = []

    # Track mirrorable skills to write them to mirror/
    mirrorable_skills = {}

    for cap_id, members in capability_groups.items():
        # Elect head using score_default, but prefer a core-tier (human-reviewed)
        # member whenever one exists in the group, so an unreviewed skill only
        # ever becomes the recommendation when there's no reviewed alternative
        # in its capability. If tie, highest score_default, then alphabetical ID.
        sorted_by_default = sorted(
            members,
            key=lambda m: (0 if m.get("tier") == "core" else 1, -m.get("score_default", 0), m["id"]),
        )
        head = sorted_by_default[0]
        
        # Determine recommendations by tool
        recommended_default = head["id"]
        recommended_by_tool = {}
        
        for tool in TOOLS:
            tool_id = tool["id"]
            # Sort by score for this tool
            sorted_by_tool = sorted(members, key=lambda m: (-m.get("scores_by_tool", {}).get(tool_id, 0), m["id"]))
            best_tool_member = sorted_by_tool[0]
            
            if best_tool_member["id"] != recommended_default:
                recommended_by_tool[tool_id] = best_tool_member["id"]

        # Fetch Card: cache hit first, then the previous kb.json's card for
        # this capability (as long as it wasn't itself a fallback), then a
        # freshly generated fallback. See Phase 0 / T2 in SPEC-01 - this
        # keeps a cold cards cache on a fresh clone from overwriting real
        # card copy with generic fallback text.
        cache_key = f"{head['id']}:{head['upstream']['blob_sha']}"
        card = cards_cache.get(cache_key)

        if not card:
            previous_card = previous_cards_by_cap.get(cap_id)
            if previous_card and previous_card.get("generated_by") != "fallback":
                card = previous_card

        if not card:
            # Fallback card if not cached yet
            cap_label = next((c["label"] for c in CAPABILITIES if c["id"] == cap_id), cap_id)
            card = {
                "title": cap_label,
                "what_it_does": head.get("frontmatter_description", ""),
                "try_saying": f"How do I use skills in {cap_label.lower()}?",
                "generated_by": "fallback",
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            }

        # Resolve details for all members assigned to this capability
        skill_refs = {}
        for member in members:
            mid = member["id"]
            org = member["origin"]["org"]
            repo = member["origin"]["repo"]
            path = member["origin"]["path"]
            branch = member["origin"]["default_branch"]
            
            # Resolve install commands for all tools
            install_block = {}
            for tool in TOOLS:
                tool_id = tool["id"]
                tool_fallback = fallback_order.get(tool_id, [])
                resolved_cmd = resolve_install_command(member, tool_id, methods_dict, tool_fallback)
                if resolved_cmd:
                    install_block[tool_id] = resolved_cmd
            
            review_status = "auto_summarized"
            if member.get("tier") == "core" and member.get("reviewed_by"):
                review_status = "human_read"
                
            skill_refs[mid] = {
                "name": member["name"],
                "repo_url": f"https://github.com/{org}/{repo}/tree/{branch}/{path}",
                "provenance": member["provenance"],
                "vendor": get_vendor(org),
                "license": member["license"],
                "review_status": review_status,
                "reviewed_at": member.get("reviewed_at"),
                "freshness": member.get("freshness"),
                "upstream_changed_at": member.get("upstream_changed_at"),
                "upstream_fetched_at": member.get("upstream", {}).get("fetched_at"),
                "lifecycle_phase": member.get("lifecycle_phase"),
                "install": install_block,
                "nutrition": member.get("nutrition"),
                "summary": (member.get("summary") or {}).get("text")
            }
            
            # Track if mirrorable
            if member.get("mirrorable"):
                mirrorable_skills[mid] = member

        # Alternatives are all members except default head
        alternatives = [m["id"] for m in sorted_by_default[1:]]

        entries.append({
            "capability_id": head["capability_id"],
            "recommended": {
                "default": recommended_default,
                "by_tool": recommended_by_tool
            },
            "card": card,
            "skill_refs": skill_refs,
            "alternatives": alternatives
        })

    # Assemble cooked data
    cooked_data = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tools": TOOLS,
        "capabilities": CAPABILITIES,
        "lifecycle_phases": LIFECYCLE_PHASES,
        "entries": entries
    }

    # Validate against JSON Schema
    try:
        validate_json(cooked_data, KB_SCHEMA)
    except Exception as e:
        print(f"Schema validation failed for kb.json: {e}")
        # We refuse to emit if validation fails
        raise e

    # Write kb.json atomically
    atomic_write_json(KB_JSON, cooked_data)
    print(f"Emitted valid kb.json to {KB_JSON}.")

    # Mirror mirrorable SKILL.md contents. Non-destructive: only delete
    # mirror files that are no longer emitted, and only overwrite a mirror
    # file when we have fresh cache content for it - a cold GitHub blob
    # cache (e.g. a fresh clone, see T1/T2 in SPEC-01) must never truncate a
    # committed mirror down to the one-line description fallback.
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    expected_mirrors = set(mirrorable_skills.keys())
    for f in MIRROR_DIR.glob("*.md"):
        if f.stem not in expected_mirrors:
            try:
                f.unlink()
            except Exception:
                pass

    written = 0
    for mid, skill in mirrorable_skills.items():
        body, source = resolve_skill_body(skill)
        mirror_path = MIRROR_DIR / f"{mid}.md"
        if source == "cache":
            with open(mirror_path, "w", encoding="utf-8") as f:
                f.write(body)
            written += 1
        elif source == "mirror":
            pass  # existing mirror file is already authoritative; leave untouched
        else:
            if not mirror_path.exists():
                print(f"Warning: no body available for mirrorable skill '{mid}'; skipping mirror.")
    print(f"Mirrored {written} SKILL.md file(s) from fresh cache content; left {len(mirrorable_skills) - written} existing mirror(s) untouched.")

if __name__ == "__main__":
    run_emit()
