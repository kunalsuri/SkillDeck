import unittest
from unittest.mock import patch
import json
import tempfile
from pathlib import Path
from kitchen.freshness import check_freshness

class TestFreshness(unittest.TestCase):
    @patch("kitchen.freshness.GitHubClient")
    def test_check_freshness_pipeline(self, mock_client_cls):
        # We have two active core skills:
        # - skill-ok: stays up-to-date (upstream sha matches local blob_sha)
        # - skill-drifted: drifts (upstream sha differs from local blob_sha)
        skills_content = {
            "schema_version": 1,
            "skills": [
                {
                    "id": "skill-ok",
                    "status": "active",
                    "tier": "core",
                    "provenance": "official",
                    "origin": {"org": "o1", "repo": "r1", "path": "p1", "default_branch": "main"},
                    "upstream": {"commit_sha": "c1", "blob_sha": "sha_ok_local", "fetched_at": "2026-07-07T08:00:00Z"},
                    "freshness": None,
                    "upstream_changed_at": None
                },
                {
                    "id": "skill-drifted",
                    "status": "active",
                    "tier": "core",
                    "provenance": "official",
                    "origin": {"org": "o2", "repo": "r2", "path": "p2", "default_branch": "main"},
                    "upstream": {"commit_sha": "c2", "blob_sha": "sha_drifted_local", "fetched_at": "2026-07-07T08:00:00Z"},
                    "freshness": None,
                    "upstream_changed_at": None
                }
            ]
        }

        mock_client = mock_client_cls.return_value
        
        # Define mock client GET responses
        def mock_get(url, is_json=True):
            if "repos/o1/r1" in url:
                return {"sha": "sha_ok_local"} # matches local
            elif "repos/o2/r2" in url:
                return {"sha": "sha_drifted_upstream"} # differs from local
            return {}
            
        mock_client.get.side_effect = mock_get

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(skills_content, f)

            with patch("kitchen.freshness.SKILLS_JSON", tmp_skills):
                check_freshness()

            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        skills_res = {s["id"]: s for s in result["skills"]}
        
        # skill-ok should remain up-to-date
        self.assertIsNone(skills_res["skill-ok"]["freshness"])
        self.assertEqual(skills_res["skill-ok"]["upstream"]["blob_sha"], "sha_ok_local")
        
        # skill-drifted should be marked drifted, update upstream_changed_at, and update upstream.blob_sha
        self.assertEqual(skills_res["skill-drifted"]["freshness"], "drifted")
        self.assertIsNotNone(skills_res["skill-drifted"]["upstream_changed_at"])
        self.assertEqual(skills_res["skill-drifted"]["upstream"]["blob_sha"], "sha_drifted_upstream")

if __name__ == "__main__":
    unittest.main()
