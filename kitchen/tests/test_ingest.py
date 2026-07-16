import unittest
from unittest.mock import MagicMock, patch
import json
import tempfile
import base64
from pathlib import Path
from kitchen.ingest import ingest_all

class TestIngest(unittest.TestCase):
    @patch("kitchen.ingest.GitHubClient")
    def test_ingest_all_pipeline(self, mock_client_cls):
        sources_content = {
            "sources": [
                {
                    "id": "direct-source",
                    "org": "anthropics",
                    "repo_url": "https://github.com/anthropics/skills",
                    "kind": "official",
                    "vendor": "anthropic",
                    "default_license": "Apache-2.0"
                },
                {
                    "id": "aggregator-to-skip",
                    "org": "agg-org",
                    "repo_url": "https://github.com/agg-org/agg-repo",
                    "kind": "aggregator",
                    "vendor": None,
                    "default_license": None
                }
            ]
        }
        
        # Pre-existing skills.json contains one skill that will remain and one that will vanish
        existing_skills = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "skills": [
                {
                    "id": "anthropics-old-vanished-skill",
                    "source_id": "direct-source",
                    "provenance": "official",
                    "origin": {
                        "org": "anthropics",
                        "repo": "skills",
                        "path": "skills/vanished",
                        "default_branch": "main"
                    },
                    "name": "vanished",
                    "frontmatter_description": "old desc",
                    "license": "Apache-2.0",
                    "mirrorable": True,
                    "upstream": {
                        "commit_sha": "old_commit",
                        "blob_sha": "old_blob",
                        "fetched_at": "2026-07-07T08:00:00Z"
                    },
                    "status": "active",
                    "tier": "core",
                    "capability_id": "documents",
                    "native_ecosystem": "claude",
                    "reviewed_by": "John Doe",
                    "reviewed_at": "2026-07-07T08:00:00Z",
                    "reviewed_commit_sha": "old_commit"
                }
            ]
        }

        mock_client = mock_client_cls.return_value
        mock_client.get_repo_default_branch.return_value = "main"

        # Mock direct tree response containing a new SKILL.md
        tree_response = {
            "sha": "new_tree_sha",
            "tree": [
                {
                    "path": "skills/new-skill/SKILL.md",
                    "type": "blob",
                    "sha": "new_blob_sha"
                }
            ]
        }
        
        skill_md_content = """---
name: new-skill
description: Brand new skill
capability: frontend
---
New skill body
"""
        encoded_skill = base64.b64encode(skill_md_content.encode("utf-8")).decode("utf-8")
        
        def mock_get(url, is_json=True):
            if "git/trees" in url:
                return tree_response
            elif "git/blobs" in url:
                return {"content": encoded_skill}
            return {}

        mock_client.get.side_effect = mock_get

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_sources = Path(tmpdir) / "sources.json"
            tmp_skills = Path(tmpdir) / "skills.json"
            
            with open(tmp_sources, "w", encoding="utf-8") as f:
                json.dump(sources_content, f)
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(existing_skills, f)

            with patch("kitchen.ingest.SOURCES_JSON", tmp_sources), \
                 patch("kitchen.ingest.SKILLS_JSON", tmp_skills):
                ingest_all()

            # Read back and verify output
            with open(tmp_skills, "r", encoding="utf-8") as f:
                result_data = json.load(f)

        skills = {s["id"]: s for s in result_data["skills"]}
        
        # Verify new skill is ingested
        self.assertIn("anthropics-new-skill", skills)
        new_s = skills["anthropics-new-skill"]
        self.assertEqual(new_s["name"], "new-skill")
        self.assertEqual(new_s["status"], "active")
        self.assertEqual(new_s["provenance"], "official")
        self.assertEqual(new_s["tier"], "shell")
        self.assertEqual(new_s["capability_id"], "frontend")
        
        # Verify old skill has vanished and status flipped to "gone"
        self.assertIn("anthropics-old-vanished-skill", skills)
        old_s = skills["anthropics-old-vanished-skill"]
        self.assertEqual(old_s["status"], "gone")
        self.assertEqual(old_s["tier"], "core") # retains core tier
        self.assertEqual(old_s["reviewed_by"], "John Doe") # retains reviews

    @patch("kitchen.ingest.GitHubClient")
    def test_ingest_reactivates_unchanged_gone_skill(self, mock_client_cls):
        """A skill still present upstream (blob_sha unchanged) but stale-marked
        'gone' on disk must be flipped back to 'active' via the skip-unchanged
        path, while retaining its reviewed/tier/capability metadata."""
        sources_content = {
            "sources": [
                {
                    "id": "direct-source",
                    "org": "anthropics",
                    "repo_url": "https://github.com/anthropics/skills",
                    "kind": "official",
                    "vendor": "anthropic",
                    "default_license": "Apache-2.0"
                }
            ]
        }

        # Present upstream (blob_sha will match the tree) but wrongly 'gone'
        existing_skills = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "skills": [
                {
                    "id": "anthropics-present-skill",
                    "source_id": "direct-source",
                    "provenance": "official",
                    "origin": {
                        "org": "anthropics",
                        "repo": "skills",
                        "path": "skills/present",
                        "default_branch": "main"
                    },
                    "name": "present",
                    "frontmatter_description": "still here",
                    "license": "Apache-2.0",
                    "mirrorable": True,
                    "upstream": {
                        "commit_sha": "old_commit",
                        "blob_sha": "match_blob",
                        "fetched_at": "2026-07-07T08:00:00Z"
                    },
                    "status": "gone",  # stale — must be re-activated
                    "tier": "core",
                    "capability_id": "documents",
                    "native_ecosystem": "claude",
                    "reviewed_by": "John Doe",
                    "reviewed_at": "2026-07-07T08:00:00Z",
                    "reviewed_commit_sha": "old_commit"
                }
            ]
        }

        mock_client = mock_client_cls.return_value
        mock_client.get_repo_default_branch.return_value = "main"

        # Same skill, same blob sha -> triggers the skip-unchanged branch
        tree_response = {
            "sha": "new_tree_sha",
            "tree": [
                {
                    "path": "skills/present/SKILL.md",
                    "type": "blob",
                    "sha": "match_blob"
                }
            ]
        }

        def mock_get(url, is_json=True):
            if "git/trees" in url:
                return tree_response
            return {}

        mock_client.get.side_effect = mock_get

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_sources = Path(tmpdir) / "sources.json"
            tmp_skills = Path(tmpdir) / "skills.json"

            with open(tmp_sources, "w", encoding="utf-8") as f:
                json.dump(sources_content, f)
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(existing_skills, f)

            with patch("kitchen.ingest.SOURCES_JSON", tmp_sources), \
                 patch("kitchen.ingest.SKILLS_JSON", tmp_skills):
                ingest_all()

            with open(tmp_skills, "r", encoding="utf-8") as f:
                result_data = json.load(f)

        skills = {s["id"]: s for s in result_data["skills"]}
        self.assertIn("anthropics-present-skill", skills)
        s = skills["anthropics-present-skill"]
        # Core assertion: the stale 'gone' is reset to 'active'
        self.assertEqual(s["status"], "active")
        # Skip path did not re-parse the body (proves fetch was skipped)
        self.assertEqual(s["frontmatter_description"], "still here")
        # Curated metadata survives the skip path
        self.assertEqual(s["tier"], "core")
        self.assertEqual(s["capability_id"], "documents")
        self.assertEqual(s["reviewed_by"], "John Doe")

if __name__ == "__main__":
    unittest.main()
