import json
import re
from datetime import datetime, timezone
from pathlib import Path
from kitchen.config import SKILLS_JSON, CACHE_DIR, CAPABILITIES
from kitchen.cluster import _elect_heads
from kitchen.dedup import resolve_skill_body
from kitchen.utils import load_all_skills, save_skills, atomic_write_json

SUMMARY_INPUT_FILE = CACHE_DIR / "summary_input.json"
SUMMARY_OUTPUT_FILE = CACHE_DIR / "summary_output.json"

SUMMARY_MIN_WORDS = 15
SUMMARY_MAX_WORDS = 120
SUMMARY_MAX_SENTENCES = 5

SENTENCE_SPLIT_RE = re.compile(r'[.!?]+(?=\s|$)')

SUMMARY_INSTRUCTIONS = (
    "For each item in heads_needing_summaries, write a Skill Summary: one factual, "
    "information-dense paragraph (2-5 sentences, 15-120 words) stating what the skill "
    "actually does - the tasks it performs, what it operates on, and what it produces - "
    "in neutral third person. Summaries power semantic comparison between skills "
    "(finding overlapping or related skills across sources), so favor concrete specifics "
    "(tools, file formats, workflows, outputs) over marketing language, and never copy "
    "the frontmatter description verbatim. Single paragraph only, no markdown headings "
    "or lists. Write your answers to summary_output.json as "
    "{\"summaries\": {\"<skill_id>\": \"<summary text>\", ...}} covering every skill_id "
    "listed here, then run `python -m kitchen summary-apply`."
)


def _eligible_skills(skills: list) -> list:
    """The same skill set emit puts into kb.json's all_skills: active and
    not rejected. Not gated on capability_id - skills outside the 8 curated
    capabilities are still browsable via all_skills and still deserve a real
    summary instead of staying empty forever."""
    return [
        s for s in skills
        if s.get("status") == "active"
        and s.get("tier") != "rejected"
    ]


def _needs_summary(head: dict, body_available: bool) -> bool:
    existing = head.get("summary")
    if not existing:
        return True
    if existing.get("generated_by") == "human":
        # Human-written summaries are locked; never queue them for rewriting.
        return False
    if existing.get("basis") == "body":
        if existing.get("body_blob_sha") != head.get("upstream", {}).get("blob_sha"):
            # Stale, but never downgrade: only rewrite once a body is resolvable
            # again (same rule nutrition applies to its metrics).
            return body_available
        return False
    # Description-based summary: rewrite only once a real body becomes available.
    return body_available


def validate_summary(text, frontmatter_description: str = "") -> str:
    """
    Enforces the Skill Summary copy rules (mirrored in the /skilldeck-ingest
    command's instructions): single paragraph, 15-120 words, at most 5
    sentences, and not a verbatim copy of the frontmatter description.
    Raises ValueError on violation, returns the cleaned text otherwise.
    """
    text = text.strip() if isinstance(text, str) else ""
    if not text:
        raise ValueError("Summary validation failed: empty or not a string.")

    if "\n" in text:
        raise ValueError("Summary validation failed: must be a single paragraph (no newlines).")

    word_count = len(text.split())
    if word_count < SUMMARY_MIN_WORDS or word_count > SUMMARY_MAX_WORDS:
        raise ValueError(
            f"Summary validation failed: {word_count} words outside "
            f"{SUMMARY_MIN_WORDS}-{SUMMARY_MAX_WORDS} range."
        )

    sentences = [s for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if len(sentences) > SUMMARY_MAX_SENTENCES:
        raise ValueError(
            f"Summary validation failed: {len(sentences)} sentences > {SUMMARY_MAX_SENTENCES}."
        )

    normalized = " ".join(text.lower().split())
    normalized_desc = " ".join((frontmatter_description or "").lower().split())
    if normalized_desc and normalized == normalized_desc:
        raise ValueError("Summary validation failed: verbatim copy of the frontmatter description.")

    return text


def prepare_summary_input(output_path: Path = None) -> Path:
    """
    Stage 1 of Skill Summary writing. Purely local: elects the same cluster
    heads clustering uses, restricted to the emit-eligible skill set, and
    writes the ones without a current summary to a JSON file. No LLM API
    call - an agent (Claude Code) reads this file and writes the summaries.
    """
    output_path = output_path or SUMMARY_INPUT_FILE
    print("Preparing skill-summary input...")
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    eligible = _eligible_skills(skills)
    skill_lookup = {s["id"]: s for s in skills}

    if not eligible:
        print("No active skills to summarize.")
        atomic_write_json(output_path, {
            "instructions": SUMMARY_INSTRUCTIONS,
            "heads_needing_summaries": []
        })
        return output_path

    heads, head_to_members = _elect_heads(eligible, skill_lookup)
    cap_labels = {c["id"]: c["label"] for c in CAPABILITIES}

    needing = []
    cached_count = 0
    locked_count = 0

    for head in heads:
        body, _source = resolve_skill_body(head)
        body_available = body is not None

        if not _needs_summary(head, body_available):
            if (head.get("summary") or {}).get("generated_by") == "human":
                locked_count += 1
            else:
                cached_count += 1
            continue

        if body_available:
            excerpt = " ".join(body.split()[:1000])
            basis = "body"
        else:
            excerpt = head.get("frontmatter_description", "")
            basis = "description"

        needing.append({
            "skill_id": head["id"],
            "name": head.get("name", ""),
            "frontmatter_description": head.get("frontmatter_description", ""),
            "body_excerpt": excerpt,
            "basis": basis,
            "capability_label": cap_labels.get(head.get("capability_id")),  # None for "unassigned" skills
            "members": [m["id"] for m in head_to_members[head["id"]]]
        })

    payload = {
        "instructions": SUMMARY_INSTRUCTIONS,
        "heads_needing_summaries": needing
    }
    atomic_write_json(output_path, payload)
    print(
        f"Wrote {len(needing)} head(s) needing summaries to {output_path} "
        f"({cached_count} already current, {locked_count} human-locked)."
    )
    return output_path


def apply_summary_assignments(input_path: Path = None) -> None:
    """
    Stage 2 of Skill Summary writing. Reads summary text (produced by an
    agent from prepare_summary_input's output), validates it against the
    copy rules, stamps it onto each cluster head in skills.json, and
    propagates it to every member of the head's duplicate cluster.
    """
    input_path = input_path or SUMMARY_OUTPUT_FILE
    print(f"Applying skill summaries from {input_path}...")
    if not Path(input_path).exists():
        print(
            f"Error: {input_path} does not exist. Run 'summary-prepare' first, have Claude "
            f"Code write summaries to that file, then re-run 'summary-apply'."
        )
        return

    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    with open(input_path, "r", encoding="utf-8") as f:
        summaries_in = json.load(f).get("summaries", {})
    eligible = _eligible_skills(skills)
    skill_lookup = {s["id"]: s for s in skills}

    if not eligible:
        print("No active skills to summarize.")
        return

    heads, head_to_members = _elect_heads(eligible, skill_lookup)
    heads_by_id = {h["id"]: h for h in heads}

    applied = 0
    failed = 0

    for skill_id, raw_text in summaries_in.items():
        head = heads_by_id.get(skill_id)
        if not head:
            print(f"Warning: '{skill_id}' is not an eligible cluster head, skipping.")
            continue
        if (head.get("summary") or {}).get("generated_by") == "human":
            print(f"Warning: '{skill_id}' has a human-locked summary, skipping.")
            continue
        try:
            validated = validate_summary(raw_text, head.get("frontmatter_description", ""))
        except ValueError as e:
            print(f"Summary for '{skill_id}' failed validation ({e}); keeping the previous one if any.")
            failed += 1
            continue

        body, _source = resolve_skill_body(head)
        basis = "body" if body is not None else "description"
        head["summary"] = {
            "text": validated,
            "basis": basis,
            "body_blob_sha": head["upstream"]["blob_sha"] if basis == "body" else None,
            "generated_by": "llm",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        applied += 1

    # Sync every head's summary (fresh or pre-existing) onto its cluster
    # members, so near-duplicates always carry their head's summary even
    # when cluster membership changed since the summary was written.
    propagated = 0
    for head in heads:
        summary = head.get("summary")
        if not summary:
            continue
        for member in head_to_members[head["id"]]:
            if member["id"] == head["id"]:
                continue
            member["summary"] = dict(summary)
            propagated += 1

    save_skills(SKILLS_JSON, skills)
    print(
        f"Applied {applied} summary(ies), {failed} failed validation, "
        f"{propagated} propagated to cluster members."
    )


if __name__ == "__main__":
    prepare_summary_input()
