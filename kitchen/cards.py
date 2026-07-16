import json
import re
from datetime import datetime, timezone
from pathlib import Path
from kitchen.config import SKILLS_JSON, CACHE_DIR, CAPABILITIES
from kitchen.dedup import get_skill_body
from kitchen.utils import load_all_skills, atomic_write_json

CARDS_CACHE_FILE = CACHE_DIR / "cards_cache.json"
CARDS_INPUT_FILE = CACHE_DIR / "cards_input.json"
CARDS_OUTPUT_FILE = CACHE_DIR / "cards_output.json"

def load_cards_cache() -> dict:
    if CARDS_CACHE_FILE.exists():
        try:
            with open(CARDS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cards_cache(cache: dict):
    atomic_write_json(CARDS_CACHE_FILE, cache)

def _heads_needing_cards(skills: list) -> list:
    active_skills = [
        s for s in skills
        if s.get("status") == "active" and s.get("capability_id") != "unassigned"
    ]
    cluster_groups = {}
    for s in active_skills:
        cid = s.get("cluster_id")
        if cid:
            cluster_groups.setdefault(cid, []).append(s)

    from kitchen.rank import score_skill
    heads = []
    for cid, members in cluster_groups.items():
        sorted_members = sorted(members, key=lambda m: (-m.get("score_default", score_skill(m)), m["id"]))
        heads.append(sorted_members[0])
    return heads

def validate_card(card: dict) -> dict:
    """
    Enforces the same copy rules the old LLM prompt did: outcome-phrased
    title <= 6 words, what_it_does <= 2 sentences, try_saying <= 25 words.
    Raises ValueError on violation.
    """
    title = (card.get("title") or "").strip()
    what_it_does = (card.get("what_it_does") or "").strip()
    try_saying = (card.get("try_saying") or "").strip()

    title_words = title.split()
    if not title or len(title_words) > 6:
        raise ValueError(f"Title validation failed: '{title}' has {len(title_words)} words > 6.")

    sentences = [s for s in re.split(r'[.!?]+(?=\s|$)', what_it_does) if s.strip()]
    if not what_it_does or len(sentences) > 2:
        raise ValueError(f"what_it_does validation failed: {len(sentences)} sentences > 2.")

    try_saying_words = try_saying.split()
    if not try_saying or len(try_saying_words) > 25:
        raise ValueError(f"try_saying validation failed: {len(try_saying_words)} words > 25.")

    return {"title": title, "what_it_does": what_it_does, "try_saying": try_saying}

def prepare_cards_input(output_path: Path = None) -> Path:
    """
    Stage 1 of card writing. Purely local: finds cluster heads that need an
    Explainer Card and don't already have a human-locked or cached one, and
    writes them to a JSON file. No LLM API call — an agent (Claude Code)
    reads this file and writes the card copy.
    """
    output_path = output_path or CARDS_INPUT_FILE
    print("Preparing card-writing input...")
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    if not skills:
        print("No skills to process.")
        atomic_write_json(output_path, {"instructions": "", "heads_needing_cards": []})
        return output_path

    cards_cache = load_cards_cache()
    cap_labels = {c["id"]: c["label"] for c in CAPABILITIES}
    heads = _heads_needing_cards(skills)

    needing = []
    locked_count = 0
    cached_count = 0
    cache_modified = False

    for head in heads:
        skill_id = head["id"]
        blob_sha = head["upstream"]["blob_sha"]
        cap_id = head["capability_id"]
        cap_label = cap_labels.get(cap_id, cap_id)
        cache_key = f"{skill_id}:{blob_sha}"

        human_card = None
        for key, card in cards_cache.items():
            if key.startswith(f"{skill_id}:") and card.get("generated_by") == "human":
                human_card = card
                break

        if human_card:
            if cache_key not in cards_cache:
                cards_cache[cache_key] = human_card
                cache_modified = True
            locked_count += 1
            continue

        if cache_key in cards_cache:
            cached_count += 1
            continue

        body = get_skill_body(head)
        body_words = body.split()
        body_excerpt = " ".join(body_words[:1000])
        needing.append({
            "skill_id": skill_id,
            "name": head["name"],
            "frontmatter_description": head.get("frontmatter_description", ""),
            "body_excerpt": body_excerpt,
            "capability_label": cap_label
        })

    if cache_modified:
        save_cards_cache(cards_cache)

    payload = {
        "instructions": (
            "You write one product card for a curated catalog of AI agent skills, aimed at "
            "non-technical users, for each item in heads_needing_cards. Rules: title = "
            "outcome-phrased, verb-first, max 6 words, no jargon, never the skill's internal "
            "name. what_it_does = max 2 sentences, plain language, no unexpanded acronyms. "
            "try_saying = one realistic prompt a user could type verbatim to trigger this "
            "skill; concrete, task-shaped, max 25 words. Write your answers to "
            "cards_output.json as {\"cards\": {\"<skill_id>\": {\"title\": \"...\", "
            "\"what_it_does\": \"...\", \"try_saying\": \"...\"}, ...}} covering every "
            "skill_id listed here, then run `python -m kitchen cards-apply`."
        ),
        "heads_needing_cards": needing
    }
    atomic_write_json(output_path, payload)
    print(
        f"Wrote {len(needing)} head(s) needing cards to {output_path} "
        f"({locked_count} human-locked, {cached_count} already cached)."
    )
    return output_path

def apply_card_assignments(input_path: Path = None) -> None:
    """
    Stage 2 of card writing. Reads card text (produced by an agent from
    prepare_cards_input's output), validates it against the copy rules, and
    writes it into the cards cache keyed by skill_id:blob_sha.
    """
    input_path = input_path or CARDS_OUTPUT_FILE
    print(f"Applying card assignments from {input_path}...")
    if not Path(input_path).exists():
        print(
            f"Error: {input_path} does not exist. Run 'cards-prepare' first, have Claude "
            f"Code write cards to that file, then re-run 'cards-apply'."
        )
        return
    skills_map = load_all_skills(SKILLS_JSON)
    with open(input_path, "r", encoding="utf-8") as f:
        cards_in = json.load(f).get("cards", {})

    skills = skills_map
    cards_cache = load_cards_cache()

    applied = 0
    failed = 0
    for skill_id, raw_card in cards_in.items():
        skill = skills.get(skill_id)
        if not skill:
            print(f"Warning: '{skill_id}' not found in skills.json, skipping.")
            continue
        blob_sha = skill["upstream"]["blob_sha"]
        cache_key = f"{skill_id}:{blob_sha}"
        try:
            validated = validate_card(raw_card)
        except ValueError as e:
            print(f"Card for '{skill_id}' failed validation ({e}); leaving uncached (emit will use a fallback card).")
            failed += 1
            continue
        validated["generated_by"] = "llm"
        validated["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        cards_cache[cache_key] = validated
        applied += 1

    save_cards_cache(cards_cache)
    print(f"Applied {applied} card(s), {failed} failed validation.")

if __name__ == "__main__":
    prepare_cards_input()
