import unittest
from unittest.mock import patch
import json
import tempfile
import base64
from pathlib import Path
from kitchen.canonicalize import (
    extract_github_repos, resolve_license, canonicalize_all
)

class TestCanonicalize(unittest.TestCase):
    def test_extract_github_repos_detailed(self):
        readme = """
        Some repository links:
        - Link 1: https://github.com/foo/bar
        - Link 2: https://github.com/baz/qux/tree/main/subfolder
        - Link 3 (duplicate): https://github.com/foo/bar
        - Link 4 (false positive asset): https://github.com/user-attachments/assets/xyz
        - Link 5 (false positive badge): https://github.com/awesome-re/badge
        """
        repos = extract_github_repos(readme)
        # Expected extracted repos: foo/bar (path=""), baz/qux (path="subfolder")
        self.assertEqual(len(repos), 2)
        self.assertEqual(repos[0], {"org": "foo", "repo": "bar", "path": ""})
        self.assertEqual(repos[1], {"org": "baz", "repo": "qux", "path": "subfolder"})

    @patch("kitchen.utils.GitHubClient")
    def test_resolve_license_permissive(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = {
            "license": {
                "spdx_id": "MIT"
            }
        }
        lic, mirrorable = resolve_license(mock_client, "org", "repo")
        self.assertEqual(lic, "MIT")
        self.assertTrue(mirrorable)

    @patch("kitchen.utils.GitHubClient")
    def test_resolve_license_non_permissive(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = {
            "license": {
                "spdx_id": "GPL-3.0"
            }
        }
        lic, mirrorable = resolve_license(mock_client, "org", "repo")
        self.assertEqual(lic, "GPL-3.0")
        self.assertFalse(mirrorable)

    @patch("kitchen.utils.GitHubClient")
    def test_resolve_license_unspecified(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.get.side_effect = Exception("Not Found")
        lic, mirrorable = resolve_license(mock_client, "org", "repo")
        self.assertEqual(lic, "unspecified")
        self.assertFalse(mirrorable)

    @patch("kitchen.canonicalize.GitHubClient")
    def test_canonicalize_all_pipeline(self, mock_client_cls):
        # Mock sources.json containing an aggregator source
        sources_content = {
            "sources": [
                {
                    "id": "agg-source",
                    "org": "agg-org",
                    "repo_url": "https://github.com/agg-org/agg-repo",
                    "kind": "aggregator",
                    "vendor": None,
                    "default_license": None
                }
            ]
        }
        
        # Mock existing skills.json (empty)
        existing_skills = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "skills": []
        }

        mock_client = mock_client_cls.return_value
        mock_client.get_repo_default_branch.return_value = "main"
        
        # Base64 encoded values for aggregator README and discovered SKILL.md
        readme_md = "Check out https://github.com/google/skills/tree/main/skills/docs"
        encoded_readme = base64.b64encode(readme_md.encode("utf-8")).decode("utf-8")
        
        tree_response = {
            "sha": "tree_sha_123",
            "tree": [
                {
                    "path": "skills/docs/SKILL.md",
                    "type": "blob",
                    "sha": "blob_sha_456"
                }
            ]
        }
        
        license_response = {
            "license": {
                "spdx_id": "Apache-2.0"
            }
        }
        
        skill_md_content = """---
name: doc-skill
description: Handled documents
capability: documents
---
Skill body content
"""
        encoded_skill = base64.b64encode(skill_md_content.encode("utf-8")).decode("utf-8")
        
        def mock_get(url, is_json=True):
            if "readme" in url:
                return {"content": encoded_readme}
            elif "git/trees" in url:
                return tree_response
            elif "license" in url:
                return license_response
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

            with patch("kitchen.canonicalize.SOURCES_JSON", tmp_sources), \
                 patch("kitchen.canonicalize.SKILLS_JSON", tmp_skills):
                canonicalize_all()

            # Read back skills.json and verify the Canonicalization output
            with open(tmp_skills, "r", encoding="utf-8") as f:
                result_data = json.load(f)

        self.assertEqual(len(result_data["skills"]), 1)
        skill = result_data["skills"][0]
        self.assertEqual(skill["id"], "google-doc-skill")
        self.assertEqual(skill["provenance"], "official") # google is in OFFICIAL_ORGS
        self.assertEqual(skill["license"], "Apache-2.0")
        self.assertTrue(skill["mirrorable"])
        self.assertEqual(skill["capability_id"], "documents")

if __name__ == "__main__":
    unittest.main()
