import json
import re
import hashlib
import base64
from datetime import datetime
from datasketch import MinHash, MinHashLSH
from kitchen.config import SKILLS_JSON, CACHE_DIR, MIRROR_DIR
from kitchen.utils import load_all_skills, save_skills

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return " ".join(text.split())

def get_shingles(text: str, k: int = 5) -> set:
    words = text.split()
    shingles = set()
    for i in range(len(words) - k + 1):
        shingle = " ".join(words[i:i+k])
        shingles.add(shingle)
    return shingles

def _get_cached_body(skill: dict):
    """Looks up a skill's body in the GitHub blob cache. Returns the
    frontmatter-stripped body text, or None on a cache miss."""
    org = skill["origin"]["org"]
    repo = skill["origin"]["repo"]
    blob_sha = skill["upstream"]["blob_sha"]

    url = f"https://api.github.com/repos/{org}/{repo}/git/blobs/{blob_sha}"
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{url_hash}.json"

    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                content = data["body"]["content"]
                body = base64.b64decode(content).decode("utf-8", errors="ignore")

                # strip yaml frontmatter from body
                lines = body.splitlines()
                if lines and lines[0].strip() == "---":
                    for i in range(1, len(lines)):
                        if lines[i].strip() == "---":
                            body = "\n".join(lines[i+1:])
                            break
                return body
        except Exception:
            pass

    return None

def get_skill_body(skill: dict) -> str:
    body = _get_cached_body(skill)
    if body is not None:
        return body
    return skill.get("frontmatter_description", "")

def resolve_skill_body(skill: dict) -> tuple:
    """Best-effort offline body lookup. Returns (body_text, source) where
    source is "cache" | "mirror" | None. Never falls back to the
    frontmatter description - callers decide what to do when no body exists."""
    body = _get_cached_body(skill)
    if body is not None:
        return body, "cache"

    mirror_path = MIRROR_DIR / f"{skill['id']}.md"
    if mirror_path.exists():
        try:
            content = mirror_path.read_text(encoding="utf-8")
            if content.strip():
                return content, "mirror"
        except Exception:
            pass

    return None, None

def sort_key(sid, skill_lookup):
    sk = skill_lookup[sid]
    prov_score = {"official": 3, "partner": 2, "community": 1}[sk["provenance"]]
    tier_score = {"core": 2, "shell": 1}[sk["tier"]]
    
    fetched_at_str = sk["upstream"]["fetched_at"]
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
    except Exception:
        fetched_at = datetime.min
        
    return (-prov_score, -tier_score, fetched_at.timestamp(), sid)

def run_dedup():
    print("Running deduplication...")
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    if not skills:
        print("No skills to deduplicate.")
        return

    lsh = MinHashLSH(threshold=0.7, num_perm=128)
    minhashes = {}
    active_skills = [s for s in skills if s.get("status") == "active"]
    
    for s in active_skills:
        skill_id = s["id"]
        body = get_skill_body(s)
        normalized = normalize_text(body)
        shingles = get_shingles(normalized, k=5)
        
        m = MinHash(num_perm=128)
        for shingle in shingles:
            m.update(shingle.encode("utf-8"))
            
        minhashes[skill_id] = m
        lsh.insert(skill_id, m)

    visited = set()
    dup_groups = []
    
    for s in active_skills:
        skill_id = s["id"]
        if skill_id in visited:
            continue
            
        matches = lsh.query(minhashes[skill_id])
        group = []
        for match in matches:
            if match in visited:
                continue
                
            m1 = minhashes[skill_id]
            m2 = minhashes[match]
            jaccard = m1.jaccard(m2)
            
            if jaccard >= 0.7:
                group.append(match)
                visited.add(match)
                
        if group:
            dup_groups.append(group)

    print(f"Grouped skills into {len(dup_groups)} duplicate clusters.")
    
    skill_lookup = {s["id"]: s for s in skills}
    
    for i, group in enumerate(dup_groups):
        cluster_id = f"cluster-{i:03d}"
        sorted_group = sorted(group, key=lambda sid: sort_key(sid, skill_lookup))
        head_id = sorted_group[0]
        alternatives = sorted_group[1:]
        
        head_skill = skill_lookup[head_id]
        head_skill["cluster_id"] = cluster_id
        for alt_id in alternatives:
            alt_skill = skill_lookup[alt_id]
            alt_skill["cluster_id"] = cluster_id

    save_skills(SKILLS_JSON, skills)
    print("Deduplicated skills. Stamped cluster_id in database.")

if __name__ == "__main__":
    run_dedup()
