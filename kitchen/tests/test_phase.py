import unittest
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from kitchen.phase import prepare_phase_input, apply_phase_assignments

@contextmanager
def patch_module_paths(tmp_skills, tmp_cache_dir):
    with patch("kitchen.phase.SKILLS_JSON", tmp_skills), \
         patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir):
        yield

class TestPhase(unittest.TestCase):
    def _skills_fixture(self):
        return {
            "schema_version": 1,
            "skills": [
                # 1. A core manually reviewed skill -> keeps its phase, no classification needed.
                {
                    "id": "build-skill-manual",
                    "name": "build-skill-manual",
                    "status": "active",
                    "provenance": "official",
                    "tier": "core",
                    "origin": {"org": "org1", "repo": "r1", "path": "p1"},
                    "upstream": {"blob_sha": "sha_manual", "fetched_at": "2026-07-07T08:00:00Z"},
                    "frontmatter_description": "manual description",
                    "capability_id": "frontend",
                    "lifecycle_phase": "build",
                    "cluster_id": "cluster-manual"
                },
                # 2. A skill head that needs classification.
                {
                    "id": "test-skill-to-classify",
                    "name": "test-skill-to-classify",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org2", "repo": "r2", "path": "p2"},
                    "upstream": {"blob_sha": "sha_cluster", "fetched_at": "2026-07-07T09:00:00Z"},
                    "frontmatter_description": "to classify description",
                    "capability_id": "testing",
                    "lifecycle_phase": None,
                    "cluster_id": "cluster-to-classify"
                },
                # 3. Alternative twin of the above, to verify propagation.
                {
                    "id": "test-skill-twin",
                    "name": "test-skill-twin",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org2", "repo": "r2", "path": "p2-alt"},
                    "upstream": {"blob_sha": "sha_twin", "fetched_at": "2026-07-07T09:30:00Z"},
                    "frontmatter_description": "twin description",
                    "capability_id": "testing",
                    "lifecycle_phase": None,
                    "cluster_id": "cluster-to-classify"
                },
                # 4. A non-software-engineering skill the agent will leave null.
                {
                    "id": "doc-skill-not-applicable",
                    "name": "doc-skill-not-applicable",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org3", "repo": "r3", "path": "p3"},
                    "upstream": {"blob_sha": "sha_doc", "fetched_at": "2026-07-07T10:00:00Z"},
                    "frontmatter_description": "document description",
                    "capability_id": "documents",
                    "lifecycle_phase": None,
                    "cluster_id": "cluster-doc"
                },
                # 5. Not yet capability-classified -> excluded from phase classification entirely.
                {
                    "id": "unassigned-skill",
                    "name": "unassigned-skill",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org4", "repo": "r4", "path": "p4"},
                    "upstream": {"blob_sha": "sha_unassigned", "fetched_at": "2026-07-07T10:30:00Z"},
                    "frontmatter_description": "unassigned description",
                    "capability_id": "unassigned",
                    "lifecycle_phase": None,
                    "cluster_id": "cluster-unassigned"
                }
            ]
        }

    def test_prepare_and_apply_phase_assignments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_input = Path(tmpdir) / "phase_input.json"
            tmp_output = Path(tmpdir) / "phase_output.json"
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_cache_dir.mkdir()

            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(self._skills_fixture(), f)

            with patch_module_paths(tmp_skills, tmp_cache_dir):
                path = prepare_phase_input(tmp_input)
                self.assertEqual(path, tmp_input)

                with open(tmp_input, "r", encoding="utf-8") as f:
                    prepared = json.load(f)

                # Manually assigned head is reported, but not sent for classification.
                already_ids = {a["skill_id"] for a in prepared["already_assigned"]}
                self.assertIn("build-skill-manual", already_ids)

                # Unassigned-capability skill never enters phase classification at all.
                needing_ids = {n["skill_id"] for n in prepared["heads_needing_classification"]}
                self.assertEqual(needing_ids, {"test-skill-to-classify", "doc-skill-not-applicable"})
                self.assertNotIn("unassigned-skill", needing_ids)

                # Simulate the agent's classification output.
                assignments = {
                    "assignments": {
                        "test-skill-to-classify": "verify",
                        "doc-skill-not-applicable": None
                    }
                }
                with open(tmp_output, "w", encoding="utf-8") as f:
                    json.dump(assignments, f)

                apply_phase_assignments(tmp_output)

            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        skills_res = {s["id"]: s for s in result["skills"]}

        self.assertEqual(skills_res["build-skill-manual"]["lifecycle_phase"], "build")
        self.assertEqual(skills_res["test-skill-to-classify"]["lifecycle_phase"], "verify")
        self.assertEqual(skills_res["test-skill-twin"]["lifecycle_phase"], "verify")
        self.assertIsNone(skills_res["doc-skill-not-applicable"]["lifecycle_phase"])
        self.assertIsNone(skills_res["unassigned-skill"]["lifecycle_phase"])

    def test_apply_defaults_unknown_phase_to_null(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_output = Path(tmpdir) / "phase_output.json"
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_cache_dir.mkdir()

            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(self._skills_fixture(), f)

            with open(tmp_output, "w", encoding="utf-8") as f:
                json.dump({"assignments": {"test-skill-to-classify": "not-a-real-phase"}}, f)

            with patch_module_paths(tmp_skills, tmp_cache_dir):
                apply_phase_assignments(tmp_output)

            with open(tmp_skills, "r", encoding="utf-8") as f:
                result = json.load(f)

        skills_res = {s["id"]: s for s in result["skills"]}
        self.assertIsNone(skills_res["test-skill-to-classify"]["lifecycle_phase"])

if __name__ == "__main__":
    unittest.main()
