import re
from datetime import datetime, timezone
from kitchen.config import SKILLS_JSON
from kitchen.dedup import resolve_skill_body
from kitchen.utils import load_all_skills, save_skills

# First sentence containing trigger phrasing wins; falls back to the first
# sentence of the description when nothing matches.
TRIGGER_PHRASE_RE = re.compile(
    r'\b[Uu]se\s+(this\s+|it\s+)?(skill\s+)?(when|for|if)\b|\b[Tt]rigger'
)
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def extract_trigger(description: str) -> str:
    """Pulls the trigger-relevant sentence out of frontmatter_description,
    always working from the description (not the body) so it's available
    even for basis == "description"."""
    description = _normalize((description or "").strip())
    if not description:
        return ""

    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(description) if s.strip()]
    if not sentences:
        return ""

    trigger = next((s for s in sentences if TRIGGER_PHRASE_RE.search(s)), sentences[0])
    if len(trigger) > 200:
        trigger = trigger[:199] + "…"
    return trigger


def compute_metrics(text: str) -> dict:
    """Deterministic chars/4 token estimate plus word/line counts. Never a
    real tokenizer - documented as an estimate."""
    text = _normalize(text)
    return {
        "token_estimate": round(len(text) / 4),
        "word_count": len(text.split()),
        "line_count": text.count("\n") + 1,
    }


def run_nutrition():
    print("Computing context-cost (nutrition) metrics...")
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())

    computed = 0
    kept = 0
    skipped_inactive = 0
    changed = False

    for skill in skills:
        if skill.get("status") != "active" or skill.get("tier") == "rejected":
            skipped_inactive += 1
            continue

        existing = skill.get("nutrition")
        blob_sha = skill.get("upstream", {}).get("blob_sha")

        if existing and existing.get("basis") == "body" and existing.get("body_blob_sha") == blob_sha:
            kept += 1
            continue

        body, _source = resolve_skill_body(skill)

        if existing and existing.get("basis") == "body" and body is None:
            # Never downgrade a real body's metrics to a description fallback.
            kept += 1
            continue

        trigger = extract_trigger(skill.get("frontmatter_description", ""))

        if body is not None:
            text = body
            basis = "body"
            resolved_blob_sha = blob_sha
        else:
            text = skill.get("frontmatter_description", "")
            basis = "description"
            resolved_blob_sha = None

        metrics = compute_metrics(text)
        skill["nutrition"] = {
            "token_estimate": metrics["token_estimate"],
            "word_count": metrics["word_count"],
            "line_count": metrics["line_count"],
            "basis": basis,
            "trigger": trigger,
            "body_blob_sha": resolved_blob_sha,
            "computed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        computed += 1
        changed = True

    if changed:
        save_skills(SKILLS_JSON, skills)
    print(
        f"Nutrition: computed {computed}, kept {kept} unchanged, "
        f"skipped {skipped_inactive} inactive/rejected."
    )


if __name__ == "__main__":
    run_nutrition()
