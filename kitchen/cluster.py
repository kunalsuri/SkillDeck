import json
from pathlib import Path
from kitchen.config import SKILLS_JSON, CACHE_DIR, CAPABILITIES
from kitchen.dedup import get_skill_body, sort_key
from kitchen.utils import load_all_skills, save_skills, atomic_write_json

CLUSTER_INPUT_FILE = CACHE_DIR / "cluster_input.json"
CLUSTER_OUTPUT_FILE = CACHE_DIR / "cluster_output.json"

def get_skill_text(skill: dict) -> str:
    body = get_skill_body(skill)
    # limit body to first 500 words
    words = body.split()
    body_excerpt = " ".join(words[:500])

    name = skill.get("name", "")
    desc = skill.get("frontmatter_description", "")

    return f"{name} — {desc} {body_excerpt}"

def _elect_heads(active_skills: list, skill_lookup: dict):
    """
    Groups active skills by cluster_id (assigning a temp singleton cluster_id
    to any skill dedup didn't group), then deterministically elects one head
    per cluster using the same ordering dedup.py uses to rank duplicates.
    Mutates cluster_id onto skill dicts in place where missing.
    """
    cluster_groups = {}
    for s in active_skills:
        cid = s.get("cluster_id")
        if cid:
            cluster_groups.setdefault(cid, []).append(s)

    for s in active_skills:
        if not s.get("cluster_id"):
            cid = f"temp-{s['id']}"
            s["cluster_id"] = cid
            cluster_groups[cid] = [s]

    heads = []
    head_to_members = {}
    for cid, members in cluster_groups.items():
        sorted_members = sorted([m["id"] for m in members], key=lambda sid: sort_key(sid, skill_lookup))
        head_id = sorted_members[0]
        heads.append(skill_lookup[head_id])
        head_to_members[head_id] = [skill_lookup[mid] for mid in sorted_members]

    return heads, head_to_members

def _capability_is_current(head: dict, valid_caps: set) -> bool:
    """True if head's capability_id was already decided by an agent (or is
    "unassigned") against the skill's current blob_sha, so classification
    can be skipped this round. False for skills never classified, or whose
    content changed since the cached decision."""
    cap_id = head.get("capability_id")
    if cap_id not in valid_caps and cap_id != "unassigned":
        return False
    assigned_sha = head.get("capability_assigned_blob_sha")
    if not assigned_sha:
        return False
    return assigned_sha == head.get("upstream", {}).get("blob_sha")

def prepare_cluster_input(output_path: Path = None) -> Path:
    """
    Stage 1 of capability clustering. Purely local: elects cluster heads and
    writes the ones that still need a capability assigned to a JSON file.
    No network calls, no ML model — an agent (Claude Code) reads this file
    and decides the capability assignments.
    """
    output_path = output_path or CLUSTER_INPUT_FILE
    print("Preparing clustering input...")
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    active_skills = [s for s in skills if s.get("status") == "active"]
    skill_lookup = {s["id"]: s for s in skills}

    if not active_skills:
        print("No active skills to cluster.")
        atomic_write_json(output_path, {
            "capabilities": CAPABILITIES,
            "heads_needing_classification": [],
            "already_assigned": []
        })
        return output_path

    heads, head_to_members = _elect_heads(active_skills, skill_lookup)

    # Persist any newly assigned temp cluster_ids before handing off.
    save_skills(SKILLS_JSON, skills)

    valid_caps = {c["id"] for c in CAPABILITIES}
    needs_classification = []
    already_assigned = []

    for head in heads:
        member_ids = [m["id"] for m in head_to_members[head["id"]]]
        if head.get("tier") == "core" and head.get("capability_id") in valid_caps:
            # Manually reviewed skills keep their human-assigned capability.
            already_assigned.append({
                "skill_id": head["id"],
                "capability_id": head["capability_id"],
                "members": member_ids
            })
            continue
        if _capability_is_current(head, valid_caps):
            # Already classified by an agent against this exact blob_sha -
            # nothing changed since, so don't re-spend agent effort on it.
            already_assigned.append({
                "skill_id": head["id"],
                "capability_id": head["capability_id"],
                "members": member_ids
            })
            continue
        needs_classification.append({
            "skill_id": head["id"],
            "name": head.get("name", ""),
            "description": head.get("frontmatter_description", ""),
            "body_excerpt": get_skill_text(head),
            "members": member_ids
        })

    payload = {
        "instructions": (
            "For each item in heads_needing_classification, choose the single best-fitting "
            "capability_id from the capabilities list below, based on its name/description/"
            "body_excerpt. If nothing fits reasonably well, use \"unassigned\". Write your "
            "answers to cluster_output.json as "
            "{\"assignments\": {\"<skill_id>\": \"<capability_id>\", ...}} covering every "
            "skill_id listed here, then run `python -m kitchen cluster-apply`."
        ),
        "capabilities": CAPABILITIES,
        "heads_needing_classification": needs_classification,
        "already_assigned": already_assigned
    }
    atomic_write_json(output_path, payload)
    print(
        f"Wrote {len(needs_classification)} head(s) needing classification to {output_path} "
        f"({len(already_assigned)} already assigned/unchanged, skipped)."
    )
    return output_path

def apply_cluster_assignments(input_path: Path = None) -> None:
    """
    Stage 2 of capability clustering. Reads capability assignments (produced
    by an agent from prepare_cluster_input's output) and writes them back
    into skills.json, propagating each head's assignment to every member of
    its duplicate cluster.
    """
    input_path = input_path or CLUSTER_OUTPUT_FILE
    print(f"Applying cluster assignments from {input_path}...")
    if not Path(input_path).exists():
        print(
            f"Error: {input_path} does not exist. Run 'cluster-prepare' first, have Claude "
            f"Code write assignments to that file, then re-run 'cluster-apply'."
        )
        return

    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    with open(input_path, "r", encoding="utf-8") as f:
        assignments = json.load(f).get("assignments", {})
    active_skills = [s for s in skills if s.get("status") == "active"]
    skill_lookup = {s["id"]: s for s in skills}

    if not active_skills:
        print("No active skills to cluster.")
        return

    heads, head_to_members = _elect_heads(active_skills, skill_lookup)
    valid_caps = {c["id"] for c in CAPABILITIES}

    assigned_count = 0
    unassigned_count = 0

    for head in heads:
        members = head_to_members[head["id"]]
        head_id = head["id"]
        current_sha = head.get("upstream", {}).get("blob_sha")

        if head.get("tier") == "core" and head.get("capability_id") in valid_caps:
            # Human-reviewed lock: never touched by agent assignments.
            cap_id = head["capability_id"]
        elif head_id in assignments:
            cap_id = assignments[head_id]
            if cap_id not in valid_caps:
                if cap_id != "unassigned":
                    print(f"Warning: unknown capability_id '{cap_id}' for '{head_id}', parking as unassigned.")
                cap_id = "unassigned"
            head["capability_assigned_blob_sha"] = current_sha
        else:
            # Not in this round's assignments - prepare already decided it
            # didn't need reclassification (unchanged since it was last
            # classified), so keep the existing value instead of wiping it.
            cap_id = head.get("capability_id") or "unassigned"
            if cap_id not in valid_caps and cap_id != "unassigned":
                cap_id = "unassigned"

        head["capability_id"] = cap_id

        if cap_id == "unassigned":
            unassigned_count += 1
        else:
            assigned_count += 1

        for member in members:
            member["capability_id"] = cap_id

    save_skills(SKILLS_JSON, skills)
    print(f"Clustering complete. Assigned: {assigned_count}, Unassigned: {unassigned_count}.")

if __name__ == "__main__":
    prepare_cluster_input()
