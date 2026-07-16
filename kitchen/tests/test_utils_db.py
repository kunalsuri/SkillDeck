import unittest
import tempfile
import json
from pathlib import Path
from kitchen.utils import load_all_skills, save_skills, get_existing_matching_skill

class TestUtilsDB(unittest.TestCase):
    def test_single_file_fallback(self):
        # When path is not default data/skills.json (e.g., in a temp dir or named differently)
        # load_all_skills and save_skills should treat it as a single file database.
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db_path = Path(tmpdir) / "custom_skills.json"
            
            skills = [
                {
                    "id": "anthropic-doc",
                    "source_id": "anthropic-official",
                    "name": "doc",
                    "origin": {"org": "anthropics", "repo": "skills", "path": "skills/doc", "default_branch": "main"},
                    "upstream": {"blob_sha": "sha1", "commit_sha": "c1", "fetched_at": "2026-07-08T00:00:00Z"}
                },
                {
                    "id": "google-sheets",
                    "source_id": "google-official",
                    "name": "sheets",
                    "origin": {"org": "google", "repo": "skills", "path": "skills/sheets", "default_branch": "main"},
                    "upstream": {"blob_sha": "sha256", "commit_sha": "c256", "fetched_at": "2026-07-08T00:00:00Z"}
                }
            ]
            
            # Save using custom path
            save_skills(temp_db_path, skills)
            
            # Verify file exists and contains all skills
            self.assertTrue(temp_db_path.exists())
            with open(temp_db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertEqual(len(data.get("skills", [])), 2)
                
            # Load back using custom path
            loaded = load_all_skills(temp_db_path)
            self.assertEqual(len(loaded), 2)
            self.assertIn("anthropic-doc", loaded)
            self.assertIn("google-sheets", loaded)

    def test_multi_file_split_and_load(self):
        # Create a mock 'data' directory structure to trigger is_default behavior
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            skills_json_path = data_dir / "skills.json"
            
            # Create a legacy skills.json file to test legacy fallback
            legacy_skills = {
                "schema_version": 1,
                "skills": [
                    {
                        "id": "legacy-skill",
                        "source_id": "legacy-source",
                        "name": "legacy",
                        "origin": {"org": "legacy", "repo": "skills", "path": "skills/legacy", "default_branch": "main"},
                        "upstream": {"blob_sha": "sha_leg", "commit_sha": "c_leg", "fetched_at": "2026-07-08T00:00:00Z"}
                    }
                ]
            }
            with open(skills_json_path, "w", encoding="utf-8") as f:
                json.dump(legacy_skills, f)
                
            # Calling load_all_skills when no skill-*.json files exist should fallback to legacy skills.json
            loaded_legacy = load_all_skills(skills_json_path)
            self.assertEqual(len(loaded_legacy), 1)
            self.assertIn("legacy-skill", loaded_legacy)
            
            # Now save active skills
            skills = [
                {
                    "id": "anthropic-doc",
                    "source_id": "anthropic-official",
                    "name": "doc",
                    "origin": {"org": "anthropics", "repo": "skills", "path": "skills/doc", "default_branch": "main"},
                    "upstream": {"blob_sha": "sha1", "commit_sha": "c1", "fetched_at": "2026-07-08T00:00:00Z"}
                },
                {
                    "id": "anthropic-ppt",
                    "source_id": "anthropic-official",
                    "name": "ppt",
                    "origin": {"org": "anthropics", "repo": "skills", "path": "skills/ppt", "default_branch": "main"},
                    "upstream": {"blob_sha": "sha2", "commit_sha": "c2", "fetched_at": "2026-07-08T00:00:00Z"}
                },
                {
                    "id": "google-sheets",
                    "source_id": "google-official",
                    "name": "sheets",
                    "origin": {"org": "google", "repo": "skills", "path": "skills/sheets", "default_branch": "main"},
                    "upstream": {"blob_sha": "sha3", "commit_sha": "c3", "fetched_at": "2026-07-08T00:00:00Z"}
                }
            ]
            
            save_skills(skills_json_path, skills)
            
            # Verify legacy skills.json has been deleted
            self.assertFalse(skills_json_path.exists())
            
            # Verify split files are created
            anthropic_file = data_dir / "skill-anthropic-official.json"
            google_file = data_dir / "skill-google-official.json"
            self.assertTrue(anthropic_file.exists())
            self.assertTrue(google_file.exists())
            
            # Check anthropic content
            with open(anthropic_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertEqual(len(data["skills"]), 2)
                
            # Check google content
            with open(google_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertEqual(len(data["skills"]), 1)
                
            # Load back all split files
            loaded = load_all_skills(skills_json_path)
            self.assertEqual(len(loaded), 3)
            self.assertIn("anthropic-doc", loaded)
            self.assertIn("anthropic-ppt", loaded)
            self.assertIn("google-sheets", loaded)
            
            # Test cleanup of obsolete files:
            # Let's save again but without the google source skill
            save_skills(skills_json_path, skills[:2])
            self.assertFalse(google_file.exists()) # Should be deleted as obsolete
            self.assertTrue(anthropic_file.exists())
            
            # Load back should now only contain the anthropic skills
            loaded_after_cleanup = load_all_skills(skills_json_path)
            self.assertEqual(len(loaded_after_cleanup), 2)
            self.assertIn("anthropic-doc", loaded_after_cleanup)
            self.assertNotIn("google-sheets", loaded_after_cleanup)

    def test_get_existing_matching_skill(self):
        existing_skills = {
            "anthropic-doc": {
                "id": "anthropic-doc",
                "source_id": "anthropic-official",
                "name": "doc",
                "origin": {"org": "anthropics", "repo": "skills", "path": "skills/doc", "default_branch": "main"},
                "upstream": {"blob_sha": "sha123", "commit_sha": "c1", "fetched_at": "2026-07-08T00:00:00Z"}
            }
        }
        
        # Exact match
        match = get_existing_matching_skill(existing_skills, "anthropics", "skills", "skills/doc/SKILL.md", "sha123")
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], "anthropic-doc")
        
        # Case insensitive org/repo match
        match = get_existing_matching_skill(existing_skills, "ANTHROPICS", "SKILLS", "skills/doc/SKILL.md", "sha123")
        self.assertIsNotNone(match)
        
        # Wrong sha
        match = get_existing_matching_skill(existing_skills, "anthropics", "skills", "skills/doc/SKILL.md", "different_sha")
        self.assertIsNone(match)
        
        # Wrong path
        match = get_existing_matching_skill(existing_skills, "anthropics", "skills", "skills/ppt/SKILL.md", "sha123")
        self.assertIsNone(match)

if __name__ == "__main__":
    unittest.main()
