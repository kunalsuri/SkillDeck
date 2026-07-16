import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from kitchen.cards import (
    load_cards_cache, save_cards_cache, validate_card,
    prepare_cards_input, apply_card_assignments
)

class TestCards(unittest.TestCase):
    def test_load_save_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_file = Path(tmpdir) / "cards_cache.json"

            with patch("kitchen.cards.CARDS_CACHE_FILE", tmp_file):
                save_cards_cache({})
                self.assertEqual(load_cards_cache(), {})

                cache_data = {"key": {"title": "Test Title"}}
                save_cards_cache(cache_data)
                self.assertEqual(load_cards_cache(), cache_data)

    def test_validate_card_success(self):
        card = validate_card({
            "title": "Build pages",
            "what_it_does": "Builds web UI. Polishes code.",
            "try_saying": "Create a React page."
        })
        self.assertEqual(card["title"], "Build pages")

    def test_validate_card_title_too_long(self):
        with self.assertRaises(ValueError):
            validate_card({
                "title": "Build pages for my awesome new website now",
                "what_it_does": "Builds web UI.",
                "try_saying": "Create a page."
            })

    def test_validate_card_missing_fields(self):
        with self.assertRaises(ValueError):
            validate_card({"title": "", "what_it_does": "x.", "try_saying": "y"})

    def _skills_fixture(self):
        return {
            "schema_version": 1,
            "skills": [
                # Head of cluster-1
                {
                    "id": "skill-1",
                    "name": "skill-1",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org1", "repo": "r1", "path": "p1"},
                    "upstream": {"blob_sha": "sha1", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "documents",
                    "cluster_id": "cluster-1",
                    "score_default": 150
                },
                # Alternative twin of cluster-1 (not the head, should be skipped)
                {
                    "id": "skill-2",
                    "name": "skill-2",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org1", "repo": "r1", "path": "p2"},
                    "upstream": {"blob_sha": "sha2", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "documents",
                    "cluster_id": "cluster-1",
                    "score_default": 100
                },
                # Head of cluster-2, which already has a human-locked card in cache
                {
                    "id": "skill-human-locked",
                    "name": "skill-human-locked",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org2", "repo": "r2", "path": "p3"},
                    "upstream": {"blob_sha": "sha3", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "documents",
                    "cluster_id": "cluster-2",
                    "score_default": 150
                }
            ]
        }

    def test_prepare_and_apply_cards(self):
        mock_cache = {
            "skill-human-locked:some_old_sha": {
                "title": "Human Title",
                "what_it_does": "Does something.",
                "try_saying": "Try.",
                "generated_by": "human"
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_cache_file = Path(tmpdir) / "cards_cache.json"
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_input = Path(tmpdir) / "cards_input.json"
            tmp_output = Path(tmpdir) / "cards_output.json"
            tmp_cache_dir.mkdir()

            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(self._skills_fixture(), f)
            with open(tmp_cache_file, "w", encoding="utf-8") as f:
                json.dump(mock_cache, f)

            with patch("kitchen.cards.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.cards.CARDS_CACHE_FILE", tmp_cache_file), \
                 patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir):

                prepare_cards_input(tmp_input)
                with open(tmp_input, "r", encoding="utf-8") as f:
                    prepared = json.load(f)

                needing_ids = {n["skill_id"] for n in prepared["heads_needing_cards"]}
                self.assertEqual(needing_ids, {"skill-1"})

                cards_out = {
                    "cards": {
                        "skill-1": {
                            "title": "Generated Title",
                            "what_it_does": "Does something generated.",
                            "try_saying": "Try generated."
                        }
                    }
                }
                with open(tmp_output, "w", encoding="utf-8") as f:
                    json.dump(cards_out, f)

                apply_card_assignments(tmp_output)

            with open(tmp_cache_file, "r", encoding="utf-8") as f:
                saved_cache = json.load(f)

        # 1. skill-1 card should be applied
        self.assertIn("skill-1:sha1", saved_cache)
        self.assertEqual(saved_cache["skill-1:sha1"]["generated_by"], "llm")
        self.assertEqual(saved_cache["skill-1:sha1"]["title"], "Generated Title")

        # 2. skill-2 (alternative) card should not exist (not head)
        self.assertNotIn("skill-2:sha2", saved_cache)

        # 3. skill-human-locked card is preserved, associated with its current sha
        self.assertIn("skill-human-locked:sha3", saved_cache)
        self.assertEqual(saved_cache["skill-human-locked:sha3"]["generated_by"], "human")
        self.assertEqual(saved_cache["skill-human-locked:sha3"]["title"], "Human Title")

    def test_apply_skips_invalid_card(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_cache_file = Path(tmpdir) / "cards_cache.json"
            tmp_output = Path(tmpdir) / "cards_output.json"

            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(self._skills_fixture(), f)

            with open(tmp_output, "w", encoding="utf-8") as f:
                json.dump({"cards": {"skill-1": {"title": "Way too many words for a title field"}}}, f)

            with patch("kitchen.cards.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.cards.CARDS_CACHE_FILE", tmp_cache_file):
                apply_card_assignments(tmp_output)

            with open(tmp_cache_file, "r", encoding="utf-8") as f:
                saved_cache = json.load(f)

        self.assertNotIn("skill-1:sha1", saved_cache)

if __name__ == "__main__":
    unittest.main()
