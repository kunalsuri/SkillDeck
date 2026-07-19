import unittest
from unittest.mock import patch
import json
import tempfile
from pathlib import Path
from kitchen.review import (
    get_git_username, edit_card_workflow, review_skill, show_queue
)

class TestReview(unittest.TestCase):
    @patch("subprocess.check_output")
    def test_get_git_username(self, mock_subprocess):
        mock_subprocess.return_value = b"Test Maintainer\n"
        self.assertEqual(get_git_username(), "Test Maintainer")
        
        # Fallback
        mock_subprocess.side_effect = Exception("No git config")
        with patch.dict("os.environ", {"USERNAME": "EnvUser"}):
            self.assertEqual(get_git_username(), "EnvUser")

    @patch("kitchen.review.run_editor")
    def test_edit_card_workflow(self, mock_run_editor):
        mock_run_editor.return_value = '{"title": "Edited Title", "what_it_does": "Does edited.", "try_saying": "Try edited."}'
        
        cards_cache = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_cache_file = Path(tmpdir) / "cards_cache.json"
            
            with patch("kitchen.cards.CARDS_CACHE_FILE", tmp_cache_file):
                card = edit_card_workflow("skill-1", "blob-1", cards_cache)
                
        self.assertEqual(card["title"], "Edited Title")
        self.assertEqual(card["generated_by"], "human")

    @patch("builtins.input")
    @patch("kitchen.review.get_git_username")
    def test_review_skill_promote(self, mock_get_user, mock_input):
        mock_get_user.return_value = "Bob"
        # user selects 'p' for promote
        mock_input.return_value = "p"
        
        skills_content = {
            "schema_version": 1,
            "skills": [
                {
                    "id": "skill-1",
                    "status": "active",
                    "tier": "shell",
                    "provenance": "community",
                    "license": "MIT",
                    "mirrorable": True,
                    "origin": {"org": "org1", "repo": "r1", "path": "p1"},
                    "name": "skill-1",
                    "upstream": {"commit_sha": "commit_123", "blob_sha": "blob_123", "fetched_at": "2026-07-07T08:00:00Z"},
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "reviewed_commit_sha": None
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_cache_dir.mkdir()
            
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(skills_content, f)
                
            with patch("kitchen.review.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir):
                review_skill("skill-1")
                
            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        skill = result["skills"][0]
        self.assertEqual(skill["tier"], "core")
        self.assertEqual(skill["reviewed_by"], "Bob")
        self.assertEqual(skill["reviewed_commit_sha"], "commit_123")

    @patch("builtins.input")
    def test_review_skill_reject(self, mock_input):
        # user selects 'r' and enters reason "unneeded"
        mock_input.side_effect = ["r", "unneeded"]
        
        skills_content = {
            "schema_version": 1,
            "skills": [
                {
                    "id": "skill-1",
                    "status": "active",
                    "tier": "shell",
                    "provenance": "community",
                    "license": "MIT",
                    "mirrorable": True,
                    "origin": {"org": "org1", "repo": "r1", "path": "p1"},
                    "name": "skill-1",
                    "upstream": {"commit_sha": "commit_123", "blob_sha": "blob_123", "fetched_at": "2026-07-07T08:00:00Z"}
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_cache_dir.mkdir()
            
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(skills_content, f)
                
            with patch("kitchen.review.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir):
                review_skill("skill-1")
                
            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        skill = result["skills"][0]
        self.assertEqual(skill["tier"], "rejected")
        self.assertEqual(skill["reject_reason"], "unneeded")

    @patch("sys.stdout")
    def test_show_queue_sorting(self, mock_stdout):
        skills_content = {
            "schema_version": 1,
            "skills": [
                # Cluster 1: size 3
                {
                    "id": "skill-a", "status": "active", "tier": "shell", "provenance": "community",
                    "cluster_id": "cluster-1", "origin": {"org": "o", "repo": "r", "path": "p"}, "name": "a",
                    "upstream": {"fetched_at": "2026-07-07T08:00:00Z"}, "score_default": 100
                },
                {
                    "id": "skill-b", "status": "active", "tier": "shell", "provenance": "official",
                    "cluster_id": "cluster-1", "origin": {"org": "o", "repo": "r", "path": "p"}, "name": "b",
                    "upstream": {"fetched_at": "2026-07-07T08:00:00Z"}, "score_default": 300
                },
                {
                    "id": "skill-c", "status": "active", "tier": "shell", "provenance": "community",
                    "cluster_id": "cluster-1", "origin": {"org": "o", "repo": "r", "path": "p"}, "name": "c",
                    "upstream": {"fetched_at": "2026-07-07T08:00:00Z"}, "score_default": 100
                },
                # Cluster 2: size 1
                {
                    "id": "skill-d", "status": "active", "tier": "shell", "provenance": "official",
                    "cluster_id": "cluster-2", "origin": {"org": "o", "repo": "r", "path": "p"}, "name": "d",
                    "upstream": {"fetched_at": "2026-07-07T08:00:00Z"}, "score_default": 300
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(skills_content, f)
                
            with patch("kitchen.review.SKILLS_JSON", tmp_skills), \
                 patch("builtins.print") as mock_print:
                show_queue()
                
            calls = [call[0][0] for call in mock_print.call_args_list if len(call[0]) > 0]
            queue_lines = [line for line in calls if "skill-b" in line or "skill-d" in line]
            
            self.assertEqual(len(queue_lines), 2)
            self.assertIn("skill-b", queue_lines[0])
            self.assertIn("skill-d", queue_lines[1])

if __name__ == "__main__":
    unittest.main()
