import unittest
import json
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
from kitchen.simmatrix import (
    normalize_words, lexical_jaccard, shared_keywords, validate_pair_score,
    prepare_simmatrix_input, apply_simmatrix_assignments,
)

DOC_A = "Generates Word documents from structured outlines with heading styles and tables of contents included."
DOC_B = "Generates Excel spreadsheets from structured outlines with heading styles and formulas included in workbooks."
DOC_C = "Deploys cloud infrastructure using terraform modules and monitors uptime metrics across regions continuously daily."
FRONT_X = "Scaffolds React components with Tailwind styling and generates Storybook stories automatically for review."
FRONT_Y = "Builds Vue components with Tailwind styling and writes Cypress end-to-end tests for critical flows."


def make_skill(id_, capability_id, summary_text):
    return {
        "id": id_,
        "name": id_,
        "status": "active",
        "provenance": "official",
        "tier": "shell",
        "origin": {"org": "org1", "repo": "r1", "path": "p1"},
        "upstream": {"blob_sha": f"sha_{id_}", "fetched_at": "2026-07-07T08:00:00Z"},
        "frontmatter_description": f"{id_} description",
        "capability_id": capability_id,
        "cluster_id": f"cluster-{id_}",
        "summary": {
            "text": summary_text,
            "basis": "body",
            "body_blob_sha": f"sha_{id_}",
            "generated_by": "llm",
            "generated_at": "2026-07-01T00:00:00Z",
        } if summary_text else None,
    }


class TestLexicalHelpers(unittest.TestCase):
    def test_normalize_words_drops_stopwords_and_short_tokens(self):
        words = normalize_words("Uses the API to run a quick job")
        self.assertNotIn("the", words)
        self.assertNotIn("to", words)
        self.assertNotIn("a", words)
        self.assertIn("api", words)
        self.assertIn("quick", words)

    def test_lexical_jaccard_symmetric_and_bounded(self):
        a, b, c = normalize_words(DOC_A), normalize_words(DOC_B), normalize_words(DOC_C)
        self.assertAlmostEqual(lexical_jaccard(a, b), lexical_jaccard(b, a))
        self.assertGreater(lexical_jaccard(a, b), lexical_jaccard(a, c))
        self.assertEqual(lexical_jaccard(set(), a), 0.0)

    def test_shared_keywords_is_actual_intersection(self):
        a, b = normalize_words(DOC_A), normalize_words(DOC_B)
        shared = shared_keywords(a, b)
        self.assertTrue(set(shared).issubset(a & b))
        self.assertIn("structured", shared)


class TestValidatePairScore(unittest.TestCase):
    def _valid(self):
        return {
            "score": 82,
            "shared_elements": ["Both generate office documents from an outline"],
            "key_differences": ["A targets Word, B targets Excel"],
            "reason": "Both convert a structured outline into a formatted office document.",
        }

    def test_valid_passes(self):
        self.assertEqual(validate_pair_score(self._valid())["score"], 82)

    def test_score_out_of_range_rejected(self):
        bad = self._valid()
        bad["score"] = 101
        with self.assertRaises(ValueError):
            validate_pair_score(bad)

    def test_score_not_int_rejected(self):
        bad = self._valid()
        bad["score"] = "82"
        with self.assertRaises(ValueError):
            validate_pair_score(bad)

    def test_missing_key_differences_rejected(self):
        bad = self._valid()
        bad["key_differences"] = []
        with self.assertRaises(ValueError):
            validate_pair_score(bad)

    def test_too_many_shared_elements_rejected(self):
        bad = self._valid()
        bad["shared_elements"] = ["a", "b", "c", "d", "e"]
        with self.assertRaises(ValueError):
            validate_pair_score(bad)

    def test_multiline_reason_rejected(self):
        bad = self._valid()
        bad["reason"] = "line one\nline two"
        with self.assertRaises(ValueError):
            validate_pair_score(bad)


class TestPrepareApply(unittest.TestCase):
    def _skills_fixture(self):
        return {
            "schema_version": 1,
            "skills": [
                make_skill("sim-doc-a", "documents", DOC_A),
                make_skill("sim-doc-b", "documents", DOC_B),
                make_skill("sim-doc-c", "documents", DOC_C),
                make_skill("sim-front-x", "frontend", FRONT_X),
                make_skill("sim-front-y", "frontend", FRONT_Y),
                make_skill("sim-no-summary", "documents", None),
                make_skill("sim-unassigned", "unassigned", DOC_A),
            ]
        }

    def _setup(self, tmpdir):
        tmp_dir = Path(tmpdir)
        paths = {
            "skills": tmp_dir / "skills.json",
            "similarity": tmp_dir / "similarity.json",
            "input": tmp_dir / "simmatrix_input.json",
            "output": tmp_dir / "simmatrix_output.json",
        }
        with open(paths["skills"], "w", encoding="utf-8") as f:
            json.dump(self._skills_fixture(), f)
        return paths

    def _patched(self, paths):
        return patch.multiple(
            "kitchen.simmatrix",
            SKILLS_JSON=paths["skills"],
            SIMILARITY_JSON=paths["similarity"],
        )

    def _load_skills(self, paths):
        with open(paths["skills"], "r", encoding="utf-8") as f:
            return {s["id"]: s for s in json.load(f)["skills"]}

    def test_prepare_only_shortlists_within_capability_bucket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)
            with self._patched(paths):
                prepare_simmatrix_input(paths["input"])
            with open(paths["input"], "r", encoding="utf-8") as f:
                prepared = json.load(f)

            pair_keys = {p["pair_key"] for p in prepared["pairs_needing_scores"]}
            self.assertIn("sim-doc-a|sim-doc-b", pair_keys)
            self.assertIn("sim-doc-a|sim-doc-c", pair_keys)
            self.assertIn("sim-front-x|sim-front-y", pair_keys)
            for key in pair_keys:
                self.assertNotIn("sim-no-summary", key)
                self.assertNotIn("sim-unassigned", key)
            for p in prepared["pairs_needing_scores"]:
                a_cap = "documents" if "doc" in p["a"]["id"] else "frontend"
                b_cap = "documents" if "doc" in p["b"]["id"] else "frontend"
                self.assertEqual(a_cap, b_cap)

    def test_full_prepare_apply_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)
            with self._patched(paths):
                prepare_simmatrix_input(paths["input"])
                scores = {
                    "scores": {
                        "sim-doc-a|sim-doc-b": {
                            "score": 78,
                            "shared_elements": ["Both generate office documents from a structured outline"],
                            "key_differences": ["A targets Word, B targets Excel"],
                            "reason": "Both convert a structured outline into a formatted office document.",
                        },
                        "sim-doc-a|sim-doc-c": {
                            "score": 12,
                            "shared_elements": ["Both are automation skills"],
                            "key_differences": ["A formats documents, C manages cloud infrastructure"],
                            "reason": "Unrelated domains beyond both being automation tasks.",
                        },
                        "sim-front-x|sim-front-y": {
                            "score": 65,
                            "shared_elements": ["Both scaffold styled UI components with Tailwind"],
                            "key_differences": ["X uses React/Storybook, Y uses Vue/Cypress"],
                            "reason": "Both scaffold Tailwind-styled components for a frontend framework.",
                        },
                    }
                }
                with open(paths["output"], "w", encoding="utf-8") as f:
                    json.dump(scores, f)
                apply_simmatrix_assignments(paths["output"])

            with open(paths["similarity"], "r", encoding="utf-8") as f:
                similarity = json.load(f)

            pairs_by_key = {(p["a"], p["b"]): p for p in similarity["pairs"]}
            self.assertEqual(len(pairs_by_key), 3)
            top = pairs_by_key[("sim-doc-a", "sim-doc-b")]
            self.assertEqual(top["score"], 78)
            self.assertGreater(top["lexical_score"], 0)
            self.assertTrue(set(top["shared_keywords"]).issubset(normalize_words(DOC_A) & normalize_words(DOC_B)))
            self.assertEqual(top["a_summary_sha"], hashlib.sha256(DOC_A.encode("utf-8")).hexdigest())
            self.assertEqual(top["generated_by"], "llm")

    def test_apply_rejects_self_pair_and_unknown_and_bad_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)
            with self._patched(paths):
                prepare_simmatrix_input(paths["input"])
                bad_scores = {
                    "scores": {
                        "sim-doc-a|sim-doc-a": {"score": 90, "shared_elements": ["x"], "key_differences": ["y"], "reason": "r"},
                        "sim-doc-a|no-such-skill": {"score": 90, "shared_elements": ["x"], "key_differences": ["y"], "reason": "r"},
                        "sim-doc-a|sim-doc-b": {"score": 999, "shared_elements": ["x"], "key_differences": ["y"], "reason": "r"},
                    }
                }
                with open(paths["output"], "w", encoding="utf-8") as f:
                    json.dump(bad_scores, f)
                apply_simmatrix_assignments(paths["output"])
            with open(paths["similarity"], "r", encoding="utf-8") as f:
                similarity = json.load(f)
            self.assertEqual(similarity["pairs"], [])

    def test_incremental_skip_then_requeue_on_summary_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)
            with self._patched(paths):
                prepare_simmatrix_input(paths["input"])
                with open(paths["input"], "r", encoding="utf-8") as f:
                    first = json.load(f)
                scores = {"scores": {p["pair_key"]: {
                    "score": 50, "shared_elements": ["shared"], "key_differences": ["diff"], "reason": "reason sentence."
                } for p in first["pairs_needing_scores"]}}
                with open(paths["output"], "w", encoding="utf-8") as f:
                    json.dump(scores, f)
                apply_simmatrix_assignments(paths["output"])

                # Re-running prepare with nothing changed -> nothing queued.
                prepare_simmatrix_input(paths["input"])
                with open(paths["input"], "r", encoding="utf-8") as f:
                    second = json.load(f)
                self.assertEqual(second["pairs_needing_scores"], [])

                # Change sim-doc-a's summary -> only pairs touching it requeue.
                skills = self._load_skills(paths)
                skills["sim-doc-a"]["summary"]["text"] = DOC_A + " Now also exports to PDF directly."
                with open(paths["skills"], "w", encoding="utf-8") as f:
                    json.dump({"schema_version": 1, "skills": list(skills.values())}, f)

                prepare_simmatrix_input(paths["input"])
                with open(paths["input"], "r", encoding="utf-8") as f:
                    third = json.load(f)
                requeued = {p["pair_key"] for p in third["pairs_needing_scores"]}
                self.assertEqual(requeued, {"sim-doc-a|sim-doc-b", "sim-doc-a|sim-doc-c"})

    def test_apply_carries_over_unchanged_pairs_and_drops_ineligible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)
            with self._patched(paths):
                prepare_simmatrix_input(paths["input"])
                with open(paths["input"], "r", encoding="utf-8") as f:
                    first = json.load(f)
                scores = {"scores": {p["pair_key"]: {
                    "score": 50, "shared_elements": ["shared"], "key_differences": ["diff"], "reason": "reason sentence."
                } for p in first["pairs_needing_scores"]}}
                with open(paths["output"], "w", encoding="utf-8") as f:
                    json.dump(scores, f)
                apply_simmatrix_assignments(paths["output"])

            with open(paths["similarity"], "r", encoding="utf-8") as f:
                similarity = json.load(f)
            self.assertEqual(len(similarity["pairs"]), 4)  # a-b, a-c, b-c, x-y

            # Second apply run with an empty scores file (nothing new this
            # round) must not drop the prior results.
            with self._patched(paths):
                with open(paths["output"], "w", encoding="utf-8") as f:
                    json.dump({"scores": {}}, f)
                apply_simmatrix_assignments(paths["output"])
            with open(paths["similarity"], "r", encoding="utf-8") as f:
                similarity = json.load(f)
            self.assertEqual(len(similarity["pairs"]), 4)

            # Now make sim-doc-c ineligible (drop its capability) and re-apply
            # with no new scores - its pairs must be dropped from the matrix.
            skills = self._load_skills(paths)
            skills["sim-doc-c"]["capability_id"] = "unassigned"
            with open(paths["skills"], "w", encoding="utf-8") as f:
                json.dump({"schema_version": 1, "skills": list(skills.values())}, f)
            with self._patched(paths):
                with open(paths["output"], "w", encoding="utf-8") as f:
                    json.dump({"scores": {}}, f)
                apply_simmatrix_assignments(paths["output"])
            with open(paths["similarity"], "r", encoding="utf-8") as f:
                similarity = json.load(f)
            remaining_keys = {(p["a"], p["b"]) for p in similarity["pairs"]}
            self.assertNotIn(("sim-doc-a", "sim-doc-c"), remaining_keys)
            self.assertNotIn(("sim-doc-b", "sim-doc-c"), remaining_keys)
            self.assertEqual(len(remaining_keys), 2)

    def test_apply_missing_output_file_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)
            with self._patched(paths):
                apply_simmatrix_assignments(paths["output"])  # never written
            self.assertFalse(paths["similarity"].exists())


if __name__ == "__main__":
    unittest.main()
