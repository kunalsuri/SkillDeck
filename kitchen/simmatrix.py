import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from kitchen.config import SKILLS_JSON, SIMILARITY_JSON, CACHE_DIR, CAPABILITIES
from kitchen.utils import load_all_skills, atomic_write_json

SIMMATRIX_INPUT_FILE = CACHE_DIR / "simmatrix_input.json"
SIMMATRIX_OUTPUT_FILE = CACHE_DIR / "simmatrix_output.json"

# How many nearest-by-lexical-overlap candidates each skill shortlists before
# the agent scores anything. Bounds the O(n^2) agent-judgment workload to
# roughly O(n*k) per capability bucket instead of every possible pair.
SHORTLIST_K = 6
MAX_SHARED_KEYWORDS = 8

# Small built-in stopword list so the lexical signal isn't dominated by
# function words. No NLTK/spaCy dependency - the kitchen stays at
# requests/pyyaml/datasketch/jsonschema.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "has", "have", "if", "in", "into", "is", "it", "its",
    "may", "not", "of", "on", "or", "over", "run", "runs", "such", "than",
    "that", "the", "their", "them", "then", "these", "this", "those",
    "through", "to", "use", "used", "uses", "using", "via", "when", "which",
    "while", "will", "with", "within", "without", "you", "your", "also",
    "any", "each", "how", "so", "up", "out", "no", "yes", "one", "two",
    "skill", "skills", "provides", "provide", "including", "include",
}

WORD_RE = re.compile(r"[a-z0-9]+")


def normalize_words(text: str) -> set:
    """Lowercases, strips punctuation, drops stopwords and short tokens.
    Same normalize-then-tokenize spirit as dedup.py's normalize_text/
    get_shingles, but word-set based (order-free) instead of shingle-based
    (order-sensitive) - shingles are for catching near-verbatim copies,
    this is for catching topical overlap between differently-worded text."""
    words = WORD_RE.findall((text or "").lower())
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def lexical_jaccard(words_a: set, words_b: set) -> float:
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def shared_keywords(words_a: set, words_b: set, cap: int = MAX_SHARED_KEYWORDS) -> list:
    """Deterministic, verifiable overlap list: the actual words present in
    both summaries. This is the part of the similarity explanation a user
    can check themselves by re-reading the two summaries - unlike the
    agent's shared_elements/key_differences judgment, it's pure set math."""
    shared = sorted(words_a & words_b, key=lambda w: (-len(w), w))
    return shared[:cap]


def _summary_sha(skill: dict) -> str:
    text = (skill.get("summary") or {}).get("text", "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _eligible_skills(skills: list) -> list:
    """Similarity comparison scope: active skills with both a real Skill
    Summary (the substrate compared) and one of the 8 curated capabilities
    (used to bucket the O(n^2) comparison down to same-capability pairs -
    a documented v1 scope limit, not a technical ceiling; see
    docs/dev/20260723-similarity-matrix-implementation.md)."""
    valid_caps = {c["id"] for c in CAPABILITIES}
    return [
        s for s in skills
        if s.get("status") == "active"
        and (s.get("summary") or {}).get("text")
        and s.get("capability_id") in valid_caps
    ]


def _load_existing_similarity() -> dict:
    if not SIMILARITY_JSON.exists():
        return {}
    try:
        with open(SIMILARITY_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _build_shortlist(bucket_skills: list, k: int = SHORTLIST_K):
    """All-pairs lexical scoring within one capability bucket (bucket sizes
    are small - dozens, not thousands - so O(n^2) here is milliseconds of
    pure Python, not a scaling concern), then each skill keeps its top-k
    neighbors by lexical score. Returns (shortlisted pair-id-tuples sorted
    (a,b), {(a,b): lexical_score}, {skill_id: word_set})."""
    ids = [s["id"] for s in bucket_skills]
    word_sets = {s["id"]: normalize_words(s["summary"]["text"]) for s in bucket_skills}

    scores = {}
    neighbors = {sid: [] for sid in ids}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            score = lexical_jaccard(word_sets[a_id], word_sets[b_id])
            key = tuple(sorted((a_id, b_id)))
            scores[key] = score
            neighbors[a_id].append((b_id, score))
            neighbors[b_id].append((a_id, score))

    shortlisted = set()
    for sid in ids:
        top = sorted(neighbors[sid], key=lambda t: (-t[1], t[0]))[:k]
        for other_id, _score in top:
            shortlisted.add(tuple(sorted((sid, other_id))))

    return sorted(shortlisted), scores, word_sets


SIMMATRIX_INSTRUCTIONS = (
    "For each item in pairs_needing_scores, judge how similar skill a and "
    "skill b actually are in purpose and functionality, using their Skill "
    "Summary text. lexical_score (0-1) and shared_keywords are a cheap "
    "word-overlap hint, not a ceiling or a floor - two skills can score high "
    "on meaning with almost no shared words, or share jargon while doing "
    "unrelated things; judge the actual substance. Write, for every "
    "pair_key listed: score (integer 0-100; 100 = same purpose/near-"
    "duplicate, 0 = unrelated), shared_elements (1-4 short phrases naming "
    "concrete things both skills actually do or operate on), "
    "key_differences (1-3 short phrases on what distinguishes them - "
    "required even for a high score, since dedup.py already removed literal "
    "near-duplicates before this stage ever runs), and reason (one plain "
    "sentence). Write your answers to simmatrix_output.json as "
    "{\"scores\": {\"<pair_key>\": {\"score\": 0, \"shared_elements\": [], "
    "\"key_differences\": [], \"reason\": \"\"}, ...}} covering every "
    "pair_key listed here, then run `python -m kitchen simmatrix-apply`."
)


def prepare_simmatrix_input(output_path: Path = None) -> Path:
    """
    Stage 1 of similarity scoring. Purely local: buckets emit-eligible
    skills by capability_id, computes a deterministic lexical shortlist per
    bucket, and writes pairs whose score is missing or stale (summary
    changed since last scored) to a JSON file. No network call, no
    embedding model - an agent (Claude Code) reads this file and writes the
    pairwise judgments.
    """
    output_path = output_path or SIMMATRIX_INPUT_FILE
    print("Preparing similarity-matrix input...")
    skills_map = load_all_skills(SKILLS_JSON)
    eligible = _eligible_skills(list(skills_map.values()))

    if not eligible:
        print("No eligible skills (active + summary + real capability_id) to compare.")
        atomic_write_json(output_path, {"instructions": SIMMATRIX_INSTRUCTIONS, "pairs_needing_scores": []})
        return output_path

    existing = _load_existing_similarity()
    existing_by_key = {(p["a"], p["b"]): p for p in existing.get("pairs", [])}
    cap_labels = {c["id"]: c["label"] for c in CAPABILITIES}

    buckets = {}
    for s in eligible:
        buckets.setdefault(s["capability_id"], []).append(s)

    pairs_needing_scores = []
    total_shortlisted = 0
    already_current = 0

    for cap_id, bucket_skills in sorted(buckets.items()):
        if len(bucket_skills) < 2:
            continue
        shortlist, lex_scores, word_sets = _build_shortlist(bucket_skills)
        total_shortlisted += len(shortlist)
        skill_by_id = {s["id"]: s for s in bucket_skills}

        for a_id, b_id in shortlist:
            a, b = skill_by_id[a_id], skill_by_id[b_id]
            a_sha, b_sha = _summary_sha(a), _summary_sha(b)
            prior = existing_by_key.get((a_id, b_id))
            if prior and prior.get("a_summary_sha") == a_sha and prior.get("b_summary_sha") == b_sha:
                already_current += 1
                continue

            pairs_needing_scores.append({
                "pair_key": f"{a_id}|{b_id}",
                "a": {"id": a_id, "name": a.get("name", ""), "summary": a["summary"]["text"]},
                "b": {"id": b_id, "name": b.get("name", ""), "summary": b["summary"]["text"]},
                "capability_label": cap_labels.get(cap_id),
                "lexical_score": round(lex_scores[(a_id, b_id)], 3),
                "shared_keywords": shared_keywords(word_sets[a_id], word_sets[b_id]),
            })

    payload = {"instructions": SIMMATRIX_INSTRUCTIONS, "pairs_needing_scores": pairs_needing_scores}
    atomic_write_json(output_path, payload)
    print(
        f"Wrote {len(pairs_needing_scores)} pair(s) needing scores to {output_path} "
        f"({total_shortlisted} shortlisted across {len(buckets)} capability bucket(s), "
        f"{already_current} already current)."
    )
    return output_path


def validate_pair_score(raw: dict) -> dict:
    """Enforces the score-writing rules given in SIMMATRIX_INSTRUCTIONS.
    Raises ValueError on violation, returns the cleaned fields otherwise."""
    if not isinstance(raw, dict):
        raise ValueError("score entry must be an object.")

    score = raw.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not (0 <= score <= 100):
        raise ValueError(f"score must be an integer 0-100, got {score!r}.")

    shared_elements = raw.get("shared_elements")
    if not isinstance(shared_elements, list) or not (1 <= len(shared_elements) <= 4) \
            or not all(isinstance(x, str) and x.strip() for x in shared_elements):
        raise ValueError("shared_elements must be a list of 1-4 non-empty strings.")

    key_differences = raw.get("key_differences")
    if not isinstance(key_differences, list) or not (1 <= len(key_differences) <= 3) \
            or not all(isinstance(x, str) and x.strip() for x in key_differences):
        raise ValueError("key_differences must be a list of 1-3 non-empty strings.")

    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip() or "\n" in reason or len(reason) > 220:
        raise ValueError("reason must be a single-line, non-empty string <= 220 chars.")

    return {
        "score": score,
        "shared_elements": [s.strip() for s in shared_elements],
        "key_differences": [s.strip() for s in key_differences],
        "reason": reason.strip(),
    }


def apply_simmatrix_assignments(input_path: Path = None) -> None:
    """
    Stage 2 of similarity scoring. Reads pairwise judgments (produced by an
    agent from prepare_simmatrix_input's output), validates them, recomputes
    the lexical signal fresh (never trusts round-tripped numbers), and
    merges the result into data/similarity.json - carrying over any
    previously-applied pair whose skills are still eligible and whose
    summaries haven't changed since, even if this round's shortlist didn't
    re-select it, so accumulated coverage never regresses between runs.
    """
    input_path = input_path or SIMMATRIX_OUTPUT_FILE
    print(f"Applying similarity scores from {input_path}...")
    if not Path(input_path).exists():
        print(
            f"Error: {input_path} does not exist. Run 'simmatrix-prepare' first, have Claude "
            f"Code write scores to that file, then re-run 'simmatrix-apply'."
        )
        return

    skills_map = load_all_skills(SKILLS_JSON)
    eligible_by_id = {s["id"]: s for s in _eligible_skills(list(skills_map.values()))}

    with open(input_path, "r", encoding="utf-8") as f:
        scores_in = json.load(f).get("scores", {})

    existing = _load_existing_similarity()
    carried = []
    for p in existing.get("pairs", []):
        a, b = eligible_by_id.get(p.get("a")), eligible_by_id.get(p.get("b"))
        if not a or not b:
            continue  # a skill dropped out of the eligible pool - drop the pair
        if _summary_sha(a) != p.get("a_summary_sha") or _summary_sha(b) != p.get("b_summary_sha"):
            continue  # stale - only re-added below if this round rescored it
        carried.append(p)

    new_pairs = []
    applied = 0
    failed = 0
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    for pair_key, raw in scores_in.items():
        if "|" not in pair_key:
            print(f"Warning: malformed pair key '{pair_key}', skipping.")
            continue
        a_id, b_id = pair_key.split("|", 1)
        if a_id == b_id:
            print(f"Warning: '{pair_key}' compares a skill to itself, skipping.")
            continue
        a, b = eligible_by_id.get(a_id), eligible_by_id.get(b_id)
        if not a or not b:
            print(f"Warning: '{pair_key}' references an unknown or ineligible skill, skipping.")
            continue
        if a_id > b_id:
            a_id, b_id, a, b = b_id, a_id, b, a

        try:
            validated = validate_pair_score(raw)
        except ValueError as e:
            print(f"Score for '{pair_key}' failed validation ({e}); skipping.")
            failed += 1
            continue

        a_words = normalize_words(a["summary"]["text"])
        b_words = normalize_words(b["summary"]["text"])
        new_pairs.append({
            "a": a_id,
            "b": b_id,
            "a_name": a.get("name", ""),
            "b_name": b.get("name", ""),
            "score": validated["score"],
            "lexical_score": round(lexical_jaccard(a_words, b_words), 3),
            "shared_keywords": shared_keywords(a_words, b_words),
            "shared_elements": validated["shared_elements"],
            "key_differences": validated["key_differences"],
            "reason": validated["reason"],
            "a_summary_sha": _summary_sha(a),
            "b_summary_sha": _summary_sha(b),
            "generated_by": "llm",
            "generated_at": now,
        })
        applied += 1

    new_keys = {(p["a"], p["b"]) for p in new_pairs}
    final_pairs = [p for p in carried if (p["a"], p["b"]) not in new_keys] + new_pairs
    final_pairs.sort(key=lambda p: (p["a"], p["b"]))

    payload = {"schema_version": 1, "generated_at": now, "pairs": final_pairs}
    atomic_write_json(SIMILARITY_JSON, payload)
    print(
        f"Applied {applied} score(s), {failed} failed validation, "
        f"{len(final_pairs)} total pair(s) in {SIMILARITY_JSON} "
        f"({len(final_pairs) - applied} carried over unchanged)."
    )


if __name__ == "__main__":
    prepare_simmatrix_input()
