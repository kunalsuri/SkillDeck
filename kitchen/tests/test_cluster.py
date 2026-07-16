import unittest
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from kitchen.cluster import prepare_cluster_input, apply_cluster_assignments

@contextmanager
def patch_module_paths(tmp_skills, tmp_cache_dir):
    with patch("kitchen.cluster.SKILLS_JSON", tmp_skills), \
         patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir):
        yield

class TestCluster(unittest.TestCase):
    def _skills_fixture(self):
        return {
            "schema_version": 1,
            "skills": [
                # 1. A core manually reviewed skill -> keeps its capability, no classification needed.
                {
                    "id": "doc-skill-manual",
                    "name": "doc-skill-manual",
                    "status": "active",
                    "provenance": "official",
                    "tier": "core",
                    "origin": {"org": "org1", "repo": "r1", "path": "p1"},
                    "upstream": {"blob_sha": "sha_manual", "fetched_at": "2026-07-07T08:00:00Z"},
                    "frontmatter_description": "manual description",
                    "capability_id": "documents",
                    "cluster_id": "cluster-manual"
                },
                # 2. A skill head that needs classification.
                {
                    "id": "doc-skill-to-cluster",
                    "name": "doc-skill-to-cluster",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org2", "repo": "r2", "path": "p2"},
                    "upstream": {"blob_sha": "sha_cluster", "fetched_at": "2026-07-07T09:00:00Z"},
                    "frontmatter_description": "to cluster description",
                    "capability_id": "unassigned",
                    "cluster_id": "cluster-to-cluster"
                },
                # 3. Alternative twin of the above, to verify propagation.
                {
                    "id": "doc-skill-twin",
                    "name": "doc-skill-twin",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org2", "repo": "r2", "path": "p2-alt"},
                    "upstream": {"blob_sha": "sha_twin", "fetched_at": "2026-07-07T09:30:00Z"},
                    "frontmatter_description": "twin description",
                    "capability_id": "unassigned",
                    "cluster_id": "cluster-to-cluster"
                },
                # 4. A skill head that the agent will leave unassigned.
                {
                    "id": "weird-skill-unassigned",
                    "name": "weird-skill-unassigned",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org3", "repo": "r3", "path": "p3"},
                    "upstream": {"blob_sha": "sha_weird", "fetched_at": "2026-07-07T10:00:00Z"},
                    "frontmatter_description": "weird description",
                    "capability_id": "unassigned",
                    "cluster_id": "cluster-weird"
                }
            ]
        }

    def test_prepare_and_apply_cluster_assignments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_input = Path(tmpdir) / "cluster_input.json"
            tmp_output = Path(tmpdir) / "cluster_output.json"
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_cache_dir.mkdir()

            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(self._skills_fixture(), f)

            with patch_module_paths(tmp_skills, tmp_cache_dir):
                path = prepare_cluster_input(tmp_input)
                self.assertEqual(path, tmp_input)

                with open(tmp_input, "r", encoding="utf-8") as f:
                    prepared = json.load(f)

                # Manually assigned head is reported, but not sent for classification.
                already_ids = {a["skill_id"] for a in prepared["already_assigned"]}
                self.assertIn("doc-skill-manual", already_ids)

                needing_ids = {n["skill_id"] for n in prepared["heads_needing_classification"]}
                self.assertEqual(needing_ids, {"doc-skill-to-cluster", "weird-skill-unassigned"})

                # Simulate the agent's classification output.
                assignments = {
                    "assignments": {
                        "doc-skill-to-cluster": "documents",
                        "weird-skill-unassigned": "unassigned"
                    }
                }
                with open(tmp_output, "w", encoding="utf-8") as f:
                    json.dump(assignments, f)

                apply_cluster_assignments(tmp_output)

            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        skills_res = {s["id"]: s for s in result["skills"]}

        self.assertEqual(skills_res["doc-skill-manual"]["capability_id"], "documents")
        self.assertEqual(skills_res["doc-skill-to-cluster"]["capability_id"], "documents")
        self.assertEqual(skills_res["doc-skill-twin"]["capability_id"], "documents")
        self.assertEqual(skills_res["weird-skill-unassigned"]["capability_id"], "unassigned")

    def test_apply_defaults_unknown_capability_to_unassigned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_output = Path(tmpdir) / "cluster_output.json"
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_cache_dir.mkdir()

            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(self._skills_fixture(), f)

            with open(tmp_output, "w", encoding="utf-8") as f:
                json.dump({"assignments": {"doc-skill-to-cluster": "not-a-real-capability"}}, f)

            with patch_module_paths(tmp_skills, tmp_cache_dir):
                apply_cluster_assignments(tmp_output)

            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        skills_res = {s["id"]: s for s in result["skills"]}
        self.assertEqual(skills_res["doc-skill-to-cluster"]["capability_id"], "unassigned")

if __name__ == "__main__":
    unittest.main()
