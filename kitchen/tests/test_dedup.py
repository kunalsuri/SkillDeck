import unittest
from unittest.mock import MagicMock, patch
import json
import tempfile
import hashlib
import base64
from pathlib import Path
from kitchen.dedup import (
    normalize_text, get_shingles, get_skill_body, sort_key, run_dedup
)

class TestDedup(unittest.TestCase):
    def test_normalize_text(self):
        text = "Hello, World!  This is a   test..."
        self.assertEqual(normalize_text(text), "hello world this is a test")

    def test_get_shingles(self):
        text = "one two three four five"
        shingles = get_shingles(text, k=3)
        expected = {"one two three", "two three four", "three four five"}
        self.assertEqual(shingles, expected)

    def test_sort_key_logic(self):
        # We want to verify priority:
        # 1. Provenance: official (3) > partner (2) > community (1)
        # 2. Tier: core (2) > shell (1)
        # 3. Fetched_at: later > earlier (in sort_key it is fetched_at.timestamp() which is minimized since it's positive? No, sort_key returns:
        # (-prov_score, -tier_score, fetched_at.timestamp(), sid)
        # So it sorts ascending:
        # -prov_score (more negative is first -> official -3, partner -2, community -1 -> official first)
        # -tier_score (more negative is first -> core -2, shell -1 -> core first)
        # fetched_at.timestamp() (smaller timestamp is first -> earlier fetched_at first)
        # sid (alphabetical asc)
        
        lookup = {
            "s1": {
                "provenance": "official", "tier": "shell", "upstream": {"fetched_at": "2026-07-07T10:00:00Z"}
            },
            "s2": {
                "provenance": "partner", "tier": "core", "upstream": {"fetched_at": "2026-07-07T09:00:00Z"}
            },
            "s3": {
                "provenance": "official", "tier": "core", "upstream": {"fetched_at": "2026-07-07T11:00:00Z"}
            },
            "s4": {
                "provenance": "official", "tier": "core", "upstream": {"fetched_at": "2026-07-07T08:00:00Z"}
            },
            "s5": {
                "provenance": "official", "tier": "core", "upstream": {"fetched_at": "2026-07-07T08:00:00Z"}
            }
        }
        
        # Sort s1..s5
        sids = ["s1", "s2", "s3", "s4", "s5"]
        sorted_sids = sorted(sids, key=lambda sid: sort_key(sid, lookup))
        # Expected order:
        # official-core is better than partner-core or official-shell.
        # Among official-core (s3, s4, s5):
        # s4 and s5 have earlier fetched_at (2026-07-07T08:00:00Z) than s3 (2026-07-07T11:00:00Z), so s4/s5 outrank s3.
        # Between s4 and s5, they are identical, so alphabetical: s4 then s5.
        # So: s4, s5, s3, s1 (official-shell), s2 (partner-core)
        self.assertEqual(sorted_sids, ["s4", "s5", "s3", "s1", "s2"])

    def test_run_dedup_pipeline(self):
        # Create active skills that have similar body texts vs a different body text
        doc_original = "This is a detailed skill for working with Word documents and reporting tools. It converts txt to docx."
        doc_near_dup = "This is a detailed skill for working with Word documents and reporting tools. It converts txt to docx!" # punctuation difference
        doc_different = "This is a frontend skill for building web pages using React and Tailwind CSS framework."

        skills_content = {
            "schema_version": 1,
            "skills": [
                {
                    "id": "skill-orig",
                    "status": "active",
                    "provenance": "official",
                    "tier": "core",
                    "origin": {"org": "org1", "repo": "r1", "path": "p1"},
                    "upstream": {"blob_sha": "sha_orig", "fetched_at": "2026-07-07T08:00:00Z"},
                    "frontmatter_description": "desc"
                },
                {
                    "id": "skill-dup",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org2", "repo": "r2", "path": "p2"},
                    "upstream": {"blob_sha": "sha_dup", "fetched_at": "2026-07-07T09:00:00Z"},
                    "frontmatter_description": "desc"
                },
                {
                    "id": "skill-diff",
                    "status": "active",
                    "provenance": "official",
                    "tier": "shell",
                    "origin": {"org": "org3", "repo": "r3", "path": "p3"},
                    "upstream": {"blob_sha": "sha_diff", "fetched_at": "2026-07-07T10:00:00Z"},
                    "frontmatter_description": "desc"
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # We must mock CACHE_DIR to match where git blobs are stored
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_cache_dir.mkdir()
            
            # Write cache files for the three blobs
            def write_cache_file(org, repo, sha, content):
                url = f"https://api.github.com/repos/{org}/{repo}/git/blobs/{sha}"
                url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
                encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                cache_file = tmp_cache_dir / f"{url_hash}.json"
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({"body": {"content": encoded}}, f)

            write_cache_file("org1", "r1", "sha_orig", doc_original)
            write_cache_file("org2", "r2", "sha_dup", doc_near_dup)
            write_cache_file("org3", "r3", "sha_diff", doc_different)

            tmp_skills = Path(tmpdir) / "skills.json"
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(skills_content, f)

            with patch("kitchen.dedup.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir):
                run_dedup()

            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        # Inspect resulting cluster assignments
        skills_res = {s["id"]: s for s in result["skills"]}
        
        # skill-orig and skill-dup are near duplicates and should share the same cluster_id
        # skill-diff should have a different cluster_id
        orig_cluster = skills_res["skill-orig"].get("cluster_id")
        dup_cluster = skills_res["skill-dup"].get("cluster_id")
        diff_cluster = skills_res["skill-diff"].get("cluster_id")

        self.assertIsNotNone(orig_cluster)
        self.assertEqual(orig_cluster, dup_cluster)
        self.assertIsNotNone(diff_cluster)
        self.assertNotEqual(orig_cluster, diff_cluster)

if __name__ == "__main__":
    unittest.main()
