import unittest
from unittest.mock import patch
import json
import tempfile
import base64
import hashlib
from pathlib import Path
from kitchen.cli import run_pipeline
from kitchen.cluster import prepare_cluster_input, apply_cluster_assignments
from kitchen.cards import prepare_cards_input, apply_card_assignments
from kitchen.summary import prepare_summary_input, apply_summary_assignments
from kitchen.emit import run_emit
from kitchen.schemas import validate_json, KB_SCHEMA

class TestGoldenPipeline(unittest.TestCase):
    @patch("kitchen.ingest.GitHubClient")
    @patch("kitchen.canonicalize.GitHubClient")
    def test_end_to_end_pipeline(self, mock_client_canon, mock_client_ingest):
        # 1. Setup Mock API Clients & Data
        # Source 1: Direct official source (Google)
        # Source 2: Aggregator source
        sources_content = {
            "schema_version": 1,
            "sources": [
                {
                    "id": "direct-official",
                    "org": "google",
                    "repo_url": "https://github.com/google/skills",
                    "kind": "official",
                    "vendor": "google",
                    "default_license": "Apache-2.0"
                },
                {
                    "id": "agg-seed",
                    "org": "agg-org",
                    "repo_url": "https://github.com/agg-org/agg-repo",
                    "kind": "aggregator",
                    "vendor": None,
                    "default_license": None
                }
            ]
        }

        install_matrix = {
            "schema_version": 1,
            "methods": [
                {
                    "tool_id": "claude-code",
                    "method": "manual",
                    "template": "copy-cmd {org}/{repo}/{skill_name}",
                    "requires_hints": [],
                    "verified_on": "2026-07-01",
                    "doc_url": "https://example.com/docs"
                }
            ],
            "fallback_order": {
                "claude-code": ["manual"],
                "claude-ai": ["manual"],
                "vscode-copilot": ["manual"],
                "cursor": ["manual"],
                "antigravity": ["manual"],
                "gemini-cli": ["manual"]
            }
        }

        # 2. Mock GitHub API client calls (default branch lookup, tree listing, file retrieval)
        agg_readme = "Checkout community skill at https://github.com/org2/community-skills/tree/main/skills/comm-doc"
        encoded_agg_readme = base64.b64encode(agg_readme.encode("utf-8")).decode("utf-8")

        skill_1_md = """---
name: doc-writer
description: Creates beautiful reports
capability: documents
---
Write documents skill body text content. Detailed reports can be output.
"""
        encoded_skill_1 = base64.b64encode(skill_1_md.encode("utf-8")).decode("utf-8")

        skill_2_md = """---
name: doc-helper
description: Helper for reports
capability: documents
---
Write documents skill body text content. Detailed reports can be output!
"""
        encoded_skill_2 = base64.b64encode(skill_2_md.encode("utf-8")).decode("utf-8")

        tree_direct = {
            "sha": "sha_tree_dir",
            "tree": [
                {"path": "skills/doc-writer/SKILL.md", "type": "blob", "sha": "sha_blob_dir"}
            ]
        }

        tree_comm = {
            "sha": "sha_tree_comm",
            "tree": [
                {"path": "skills/comm-doc/SKILL.md", "type": "blob", "sha": "sha_blob_comm"}
            ]
        }

        def make_mock_client(mock_cls):
            client = mock_cls.return_value
            client.get_repo_default_branch.return_value = "main"

            def mock_get(url, is_json=True):
                if "repos/google/skills/git/trees" in url:
                    return tree_direct
                elif "repos/google/skills/git/blobs" in url:
                    return {"content": encoded_skill_1}
                elif "repos/agg-org/agg-repo/readme" in url:
                    return {"content": encoded_agg_readme}
                elif "repos/org2/community-skills/git/trees" in url:
                    return tree_comm
                elif "repos/org2/community-skills/git/blobs" in url:
                    return {"content": encoded_skill_2}
                elif "license" in url:
                    return {"license": {"spdx_id": "MIT"}}
                return {}

            client.get.side_effect = mock_get
            return client

        make_mock_client(mock_client_ingest)
        make_mock_client(mock_client_canon)

        # 3. Run the Integration Pipeline in a temp environment
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir = Path(tmpdir)
            tmp_sources = tmp_dir / "sources.json"
            tmp_skills = tmp_dir / "skills.json"
            tmp_matrix = tmp_dir / "install_matrix.json"
            tmp_kb = tmp_dir / "kb.json"
            tmp_mirror = tmp_dir / "mirror"
            tmp_cache_dir = tmp_dir / ".kitchen_cache"
            tmp_cluster_input = tmp_dir / "cluster_input.json"
            tmp_cluster_output = tmp_dir / "cluster_output.json"
            tmp_cards_input = tmp_dir / "cards_input.json"
            tmp_cards_output = tmp_dir / "cards_output.json"
            tmp_cards_cache = tmp_dir / "cards_cache.json"
            tmp_summary_input = tmp_dir / "summary_input.json"
            tmp_summary_output = tmp_dir / "summary_output.json"

            tmp_mirror.mkdir(parents=True, exist_ok=True)
            tmp_cache_dir.mkdir(parents=True, exist_ok=True)

            with open(tmp_sources, "w", encoding="utf-8") as f:
                json.dump(sources_content, f)
            with open(tmp_matrix, "w", encoding="utf-8") as f:
                json.dump(install_matrix, f)

            def populate_blob_cache(org, repo, sha, content):
                url = f"https://api.github.com/repos/{org}/{repo}/git/blobs/{sha}"
                url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
                encoded_val = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                with open(tmp_cache_dir / f"{url_hash}.json", "w", encoding="utf-8") as f:
                    json.dump({"body": {"content": encoded_val}}, f)

            populate_blob_cache("google", "skills", "sha_blob_dir", skill_1_md)
            populate_blob_cache("org2", "community-skills", "sha_blob_comm", skill_2_md)

            with patch("kitchen.ingest.SOURCES_JSON", tmp_sources), \
                 patch("kitchen.ingest.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.canonicalize.SOURCES_JSON", tmp_sources), \
                 patch("kitchen.canonicalize.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.dedup.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir), \
                 patch("kitchen.cluster.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.cards.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.cards.CARDS_CACHE_FILE", tmp_cards_cache), \
                 patch("kitchen.summary.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.rank.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.nutrition.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.emit.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.emit.INSTALL_MATRIX_JSON", tmp_matrix), \
                 patch("kitchen.emit.KB_JSON", tmp_kb), \
                 patch("kitchen.emit.MIRROR_DIR", tmp_mirror):

                # Scriptable stages: ingest -> canonicalize -> dedup -> rank
                run_pipeline()

                # Capability clustering: prepare -> (agent classifies) -> apply
                prepare_cluster_input(tmp_cluster_input)
                with open(tmp_cluster_input, "r", encoding="utf-8") as f:
                    cluster_in = json.load(f)
                assignments = {h["skill_id"]: "documents" for h in cluster_in["heads_needing_classification"]}
                with open(tmp_cluster_output, "w", encoding="utf-8") as f:
                    json.dump({"assignments": assignments}, f)
                apply_cluster_assignments(tmp_cluster_output)

                # Card writing: prepare -> (agent writes cards) -> apply
                prepare_cards_input(tmp_cards_input)
                with open(tmp_cards_input, "r", encoding="utf-8") as f:
                    cards_in = json.load(f)
                cards_out = {
                    h["skill_id"]: {
                        "title": "Create report doc",
                        "what_it_does": "Generates report documents.",
                        "try_saying": "Create a report doc."
                    }
                    for h in cards_in["heads_needing_cards"]
                }
                with open(tmp_cards_output, "w", encoding="utf-8") as f:
                    json.dump({"cards": cards_out}, f)
                apply_card_assignments(tmp_cards_output)

                # Skill Summaries: prepare -> (agent writes summaries) -> apply
                prepare_summary_input(tmp_summary_input)
                with open(tmp_summary_input, "r", encoding="utf-8") as f:
                    summary_in = json.load(f)
                summaries_out = {
                    h["skill_id"]: (
                        "Generates structured report documents from prompts, laying out "
                        "sections and formatting the output for direct sharing with readers."
                    )
                    for h in summary_in["heads_needing_summaries"]
                }
                with open(tmp_summary_output, "w", encoding="utf-8") as f:
                    json.dump({"summaries": summaries_out}, f)
                apply_summary_assignments(tmp_summary_output)

                run_emit()

            # 4. Verify Outputs
            self.assertTrue(tmp_kb.exists())

            with open(tmp_kb, "r", encoding="utf-8") as f:
                kb_data = json.load(f)

            validate_json(kb_data, KB_SCHEMA)

            self.assertEqual(len(kb_data["entries"]), 1)
            entry = kb_data["entries"][0]
            self.assertEqual(entry["capability_id"], "documents")

            # Elect head logic:
            # - doc-writer provenance is official (prov_score=3)
            # - doc-helper provenance is community (prov_score=1)
            # - doc-writer is head (recommended default)
            self.assertEqual(entry["recommended"]["default"], "google-doc-writer")
            self.assertEqual(entry["alternatives"], ["org2-doc-helper"])

            self.assertEqual(entry["card"]["title"], "Create report doc")

            self.assertEqual(entry["skill_refs"]["google-doc-writer"]["name"], "doc-writer")
            self.assertEqual(entry["skill_refs"]["google-doc-writer"]["license"], "Apache-2.0")

            # The head's Skill Summary lands in kb.json and is propagated to
            # its dedup-cluster twin as well.
            self.assertTrue(
                entry["skill_refs"]["google-doc-writer"]["summary"].startswith("Generates structured report")
            )
            self.assertTrue(
                entry["skill_refs"]["org2-doc-helper"]["summary"].startswith("Generates structured report")
            )

            self.assertTrue((tmp_mirror / "google-doc-writer.md").exists())
            self.assertTrue((tmp_mirror / "org2-doc-helper.md").exists())

if __name__ == "__main__":
    unittest.main()
