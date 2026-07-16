import unittest
from unittest.mock import patch
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from kitchen.rank import (
    days_since, ecosystem_match, score_skill, run_rank
)

class TestRank(unittest.TestCase):
    def test_days_since(self):
        now = datetime.now(timezone.utc)
        # 65 days ago
        fetched_at = datetime.fromtimestamp(now.timestamp() - 65 * 24 * 3600, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        self.assertEqual(days_since(fetched_at), 65)
        
        # Invalid date
        self.assertEqual(days_since("invalid-date"), 0)

    def test_ecosystem_match(self):
        self.assertTrue(ecosystem_match("claude", "claude-code"))
        self.assertTrue(ecosystem_match("claude", "claude-ai"))
        self.assertTrue(ecosystem_match("google", "antigravity"))
        self.assertTrue(ecosystem_match("google", "gemini-cli"))
        self.assertTrue(ecosystem_match("vscode", "vscode-copilot"))
        self.assertTrue(ecosystem_match("vscode", "cursor"))
        self.assertFalse(ecosystem_match("generic", "claude-code"))
        self.assertFalse(ecosystem_match("google", "cursor"))

    def test_score_skill_details(self):
        # 1. Base community skill
        community_skill = {
            "tier": "shell",
            "provenance": "community",
            "license": "unspecified",
            "upstream": {"fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
            "native_ecosystem": "generic"
        }
        # community(100) + license(0) + freshness(20) = 120
        self.assertEqual(score_skill(community_skill), 120)

        # 2. Official core skill (reviewed) with Apache-2.0 and freshness
        official_reviewed = {
            "tier": "core",
            "reviewed_by": "Maintainer",
            "provenance": "official",
            "license": "Apache-2.0",
            "upstream": {"fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
            "native_ecosystem": "claude"
        }
        # core-reviewed(1000) + official(300) + license(30) + freshness(20) = 1350
        self.assertEqual(score_skill(official_reviewed), 1350)
        
        # With target tool bonus (ecosystem claude matches claude-code)
        # 1350 + 50 = 1400
        self.assertEqual(score_skill(official_reviewed, "claude-code"), 1400)
        
        # With non-matching target tool
        # 1350 + 0 = 1350
        self.assertEqual(score_skill(official_reviewed, "antigravity"), 1350)

    def test_run_rank_pipeline(self):
        skills_content = {
            "schema_version": 1,
            "skills": [
                {
                    "id": "skill-1",
                    "status": "active",
                    "tier": "shell",
                    "provenance": "community",
                    "license": "MIT",
                    "upstream": {"fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
                    "native_ecosystem": "google"
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(skills_content, f)

            with patch("kitchen.rank.SKILLS_JSON", tmp_skills):
                run_rank()

            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        skill = result["skills"][0]
        # Check scores populated
        self.assertIn("score_default", skill)
        self.assertIn("scores_by_tool", skill)
        self.assertEqual(skill["score_default"], 100 + 30 + 20) # community(100)+MIT(30)+freshness(20) = 150
        self.assertEqual(skill["scores_by_tool"]["antigravity"], 150 + 50) # ecosystem google matches antigravity (+50)
        self.assertEqual(skill["scores_by_tool"]["claude-code"], 150)

if __name__ == "__main__":
    unittest.main()
