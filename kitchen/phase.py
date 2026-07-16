import json
from pathlib import Path
from kitchen.config import SKILLS_JSON, CACHE_DIR, CAPABILITIES, LIFECYCLE_PHASES
from kitchen.cluster import _elect_heads, get_skill_text
from kitchen.utils import load_all_skills, save_skills, atomic_write_json

PHASE_INPUT_FILE = CACHE_DIR / "phase_input.json"
PHASE_OUTPUT_FILE = CACHE_DIR / "phase_output.json"

def prepare_phase_input(output_path: Path = None) -> Path:
    """
    Stage 1 of lifecycle-phase classification for the Software Engineering /
    SDLC page. Purely local: elects the same cluster heads clustering uses,
    restricted to skills that already have a real capability, and writes the
    ones that still need a phase decided to a JSON file. An agent (Claude
    Code) reads this file and decides the phase assignments (or "not a
    software-engineering-lifecycle skill", written as null).
    """
    output_path = output_path or PHASE_INPUT_FILE
    print("Preparing lifecycle-phase input...")
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    valid_caps = {c["id"] for c in CAPABILITIES}
    active_skills = [
        s for s in skills
        if s.get("status") == "active" and s.get("capability_id") in valid_caps
    ]
    skill_lookup = {s["id"]: s for s in skills}

    if not active_skills:
        print("No capability-assigned skills to classify by phase.")
        atomic_write_json(output_path, {
            "phases": LIFECYCLE_PHASES,
            "heads_needing_classification": [],
            "already_assigned": []
        })
        return output_path

    heads, head_to_members = _elect_heads(active_skills, skill_lookup)

    valid_phases = {p["id"] for p in LIFECYCLE_PHASES}
    cap_labels = {c["id"]: c["label"] for c in CAPABILITIES}
    needs_classification = []
    already_assigned = []

    for head in heads:
        member_ids = [m["id"] for m in head_to_members[head["id"]]]
        if head.get("tier") == "core" and head.get("lifecycle_phase") in valid_phases:
            # Manually reviewed skills keep their human-assigned phase.
            already_assigned.append({
                "skill_id": head["id"],
                "lifecycle_phase": head["lifecycle_phase"],
                "members": member_ids
            })
            continue
        needs_classification.append({
            "skill_id": head["id"],
            "name": head.get("name", ""),
            "description": head.get("frontmatter_description", ""),
            "body_excerpt": get_skill_text(head),
            "capability_label": cap_labels.get(head.get("capability_id"), head.get("capability_id")),
            "members": member_ids
        })

    payload = {
        "instructions": (
            "For each item in heads_needing_classification, decide whether it's a "
            "software-engineering / coding-agent lifecycle skill, and if so which single "
            "phase from the phases list below it fits best (based on its name/description/"
            "body_excerpt/capability_label). If it isn't part of a software development "
            "lifecycle (e.g. document creation, design/branding, spreadsheet analysis), "
            "write null rather than forcing a bad match. Write your answers to "
            "phase_output.json as {\"assignments\": {\"<skill_id>\": \"<phase_id-or-null>\", "
            "...}} covering every skill_id listed here, then run "
            "`python -m kitchen phase-apply`."
        ),
        "phases": LIFECYCLE_PHASES,
        "heads_needing_classification": needs_classification,
        "already_assigned": already_assigned
    }
    atomic_write_json(output_path, payload)
    print(
        f"Wrote {len(needs_classification)} head(s) needing phase classification to "
        f"{output_path} ({len(already_assigned)} already manually assigned)."
    )
    return output_path

def apply_phase_assignments(input_path: Path = None) -> None:
    """
    Stage 2 of lifecycle-phase classification. Reads phase assignments
    (produced by an agent from prepare_phase_input's output) and writes them
    back into skills.json, propagating each head's assignment to every
    member of its duplicate cluster.
    """
    input_path = input_path or PHASE_OUTPUT_FILE
    print(f"Applying phase assignments from {input_path}...")
    if not Path(input_path).exists():
        print(
            f"Error: {input_path} does not exist. Run 'phase-prepare' first, have Claude "
            f"Code write assignments to that file, then re-run 'phase-apply'."
        )
        return

    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    with open(input_path, "r", encoding="utf-8") as f:
        assignments = json.load(f).get("assignments", {})
    valid_caps = {c["id"] for c in CAPABILITIES}
    active_skills = [
        s for s in skills
        if s.get("status") == "active" and s.get("capability_id") in valid_caps
    ]
    skill_lookup = {s["id"]: s for s in skills}

    if not active_skills:
        print("No capability-assigned skills to classify by phase.")
        return

    heads, head_to_members = _elect_heads(active_skills, skill_lookup)
    valid_phases = {p["id"] for p in LIFECYCLE_PHASES}

    assigned_count = 0
    not_applicable_count = 0

    for head in heads:
        members = head_to_members[head["id"]]
        if head.get("tier") == "core" and head.get("lifecycle_phase") in valid_phases:
            phase_id = head["lifecycle_phase"]
        else:
            phase_id = assignments.get(head["id"])
            if phase_id is not None and phase_id not in valid_phases:
                print(f"Warning: unknown lifecycle_phase '{phase_id}' for '{head['id']}', parking as null.")
                phase_id = None

        if phase_id is None:
            not_applicable_count += 1
        else:
            assigned_count += 1

        for member in members:
            member["lifecycle_phase"] = phase_id

    save_skills(SKILLS_JSON, skills)
    print(f"Phase classification complete. Assigned: {assigned_count}, Not applicable: {not_applicable_count}.")

if __name__ == "__main__":
    prepare_phase_input()
