import unittest
import json
import base64
import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from kitchen.summary import (
    validate_summary, prepare_summary_input, apply_summary_assignments
)

VALID_SUMMARY = (
    "Generates Word documents from structured outlines, applying heading styles, "
    "tables of contents, and page numbering. It reads markdown input and produces "
    "a formatted .docx file ready to share."
)


@contextmanager
def patch_module_paths(tmp_skills, tmp_cache_dir, tmp_mirror_dir):
    with patch("kitchen.summary.SKILLS_JSON", tmp_skills), \
         patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir), \
         patch("kitchen.dedup.MIRROR_DIR", tmp_mirror_dir):
        yield


def populate_blob_cache(cache_dir, org, repo, sha, content):
    url = f"https://api.github.com/repos/{org}/{repo}/git/blobs/{sha}"
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    with open(cache_dir / f"{url_hash}.json", "w", encoding="utf-8") as f:
        json.dump({"body": {"content": encoded}}, f)


class TestValidateSummary(unittest.TestCase):
    def test_valid_summary_passes(self):
        self.assertEqual(validate_summary(f"  {VALID_SUMMARY}  "), VALID_SUMMARY)

    def test_empty_or_non_string_rejected(self):
        for bad in ["", "   ", None, 42]:
            with self.assertRaises(ValueError):
                validate_summary(bad)

    def test_too_short_rejected(self):
        with self.assertRaises(ValueError):
            validate_summary("Writes documents quickly.")

    def test_too_long_rejected(self):
        with self.assertRaises(ValueError):
            validate_summary("word " * 121)

    def test_multiline_rejected(self):
        with self.assertRaises(ValueError):
            validate_summary(VALID_SUMMARY.replace(". It reads", ".\nIt reads"))

    def test_too_many_sentences_rejected(self):
        with self.assertRaises(ValueError):
            validate_summary(
                "It writes docs fully. It reads files nightly. It saves output there. "
                "It styles headings now. It numbers pages twice. It ships results fast."
            )

    def test_verbatim_description_copy_rejected(self):
        desc = (
            "Creates formatted Word documents from structured outlines with heading "
            "styles, page numbers, and tables of contents included in the final file."
        )
        # Long enough to pass the length rules, so only the verbatim check fires.
        with self.assertRaises(ValueError):
            validate_summary(f"  {desc.upper()} ", desc)


class TestSummaryPrepareApply(unittest.TestCase):
    def _skills_fixture(self):
        return {
            "schema_version": 1,
            "skills": [
                # 1. Head of cluster-a (official beats community twin in head election).
                {
                    "id": "sum-head",
                    "name": "sum-head",
                    "status": "active",
                    "provenance": "official",
                    "tier": "shell",
                    "origin": {"org": "org1", "repo": "r1", "path": "p1"},
                    "upstream": {"blob_sha": "sha_head", "fetched_at": "2026-07-07T08:00:00Z"},
                    "frontmatter_description": "head description",
                    "capability_id": "documents",
                    "cluster_id": "cluster-a"
                },
                # 2. Near-duplicate twin in the same cluster; must inherit the head's summary.
                {
                    "id": "sum-twin",
                    "name": "sum-twin",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org2", "repo": "r2", "path": "p2"},
                    "upstream": {"blob_sha": "sha_twin", "fetched_at": "2026-07-07T09:00:00Z"},
                    "frontmatter_description": "twin description",
                    "capability_id": "documents",
                    "cluster_id": "cluster-a"
                },
                # 3. Head with a summary already current for its blob_sha -> skipped.
                {
                    "id": "sum-cached",
                    "name": "sum-cached",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org3", "repo": "r3", "path": "p3"},
                    "upstream": {"blob_sha": "sha_cached", "fetched_at": "2026-07-07T10:00:00Z"},
                    "frontmatter_description": "cached description",
                    "capability_id": "documents",
                    "cluster_id": "cluster-b",
                    "summary": {
                        "text": "Existing cached summary text that was written for the current blob and stays untouched.",
                        "basis": "body",
                        "body_blob_sha": "sha_cached",
                        "generated_by": "llm",
                        "generated_at": "2026-07-01T00:00:00Z"
                    }
                },
                # 4. Head with a human-locked summary -> never queued, never overwritten.
                {
                    "id": "sum-human",
                    "name": "sum-human",
                    "status": "active",
                    "provenance": "community",
                    "tier": "core",
                    "origin": {"org": "org4", "repo": "r4", "path": "p4"},
                    "upstream": {"blob_sha": "sha_human", "fetched_at": "2026-07-07T11:00:00Z"},
                    "frontmatter_description": "human description",
                    "capability_id": "documents",
                    "cluster_id": "cluster-c",
                    "summary": {
                        "text": "Curator-written summary that stays exactly as the human editor left it here.",
                        "basis": "body",
                        "body_blob_sha": "old_sha",
                        "generated_by": "human",
                        "generated_at": "2026-06-01T00:00:00Z"
                    }
                },
                # 5. No cached body available -> description-basis summary.
                {
                    "id": "sum-desc",
                    "name": "sum-desc",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org5", "repo": "r5", "path": "p5"},
                    "upstream": {"blob_sha": "sha_desc", "fetched_at": "2026-07-07T12:00:00Z"},
                    "frontmatter_description": "desc-only description",
                    "capability_id": "documents",
                    "cluster_id": "cluster-d"
                },
                # 6. Not capability-assigned -> not eligible at all.
                {
                    "id": "sum-unassigned",
                    "name": "sum-unassigned",
                    "status": "active",
                    "provenance": "community",
                    "tier": "shell",
                    "origin": {"org": "org6", "repo": "r6", "path": "p6"},
                    "upstream": {"blob_sha": "sha_un", "fetched_at": "2026-07-07T13:00:00Z"},
                    "frontmatter_description": "unassigned description",
                    "capability_id": "unassigned",
                    "cluster_id": "cluster-e"
                }
            ]
        }

    def _setup(self, tmpdir):
        tmp_dir = Path(tmpdir)
        paths = {
            "skills": tmp_dir / "skills.json",
            "cache": tmp_dir / ".kitchen_cache",
            "mirror": tmp_dir / "mirror",
            "input": tmp_dir / "summary_input.json",
            "output": tmp_dir / "summary_output.json",
        }
        paths["cache"].mkdir()
        paths["mirror"].mkdir()
        with open(paths["skills"], "w", encoding="utf-8") as f:
            json.dump(self._skills_fixture(), f)
        # sum-head has a cached body -> "body" basis; sum-desc stays cold.
        populate_blob_cache(paths["cache"], "org1", "r1", "sha_head", "Full body of the head skill.")
        return paths

    def _load_skills(self, paths):
        with open(paths["skills"], "r", encoding="utf-8") as f:
            return {s["id"]: s for s in json.load(f)["skills"]}

    def test_prepare_and_apply_summaries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)

            with patch_module_paths(paths["skills"], paths["cache"], paths["mirror"]):
                prepare_summary_input(paths["input"])
                with open(paths["input"], "r", encoding="utf-8") as f:
                    prepared = json.load(f)

                needing = {n["skill_id"]: n for n in prepared["heads_needing_summaries"]}
                self.assertEqual(set(needing.keys()), {"sum-head", "sum-desc"})
                self.assertEqual(needing["sum-head"]["basis"], "body")
                self.assertEqual(needing["sum-head"]["members"], ["sum-head", "sum-twin"])
                self.assertEqual(needing["sum-head"]["body_excerpt"], "Full body of the head skill.")
                self.assertEqual(needing["sum-desc"]["basis"], "description")
                self.assertEqual(needing["sum-desc"]["body_excerpt"], "desc-only description")

                desc_summary = (
                    "Provides guidance for desc-only workflows, covering the setup steps "
                    "and commands users need to run the underlying tool."
                )
                with open(paths["output"], "w", encoding="utf-8") as f:
                    json.dump({"summaries": {
                        "sum-head": VALID_SUMMARY,
                        "sum-desc": desc_summary
                    }}, f)

                apply_summary_assignments(paths["output"])

            skills = self._load_skills(paths)

            self.assertEqual(skills["sum-head"]["summary"]["text"], VALID_SUMMARY)
            self.assertEqual(skills["sum-head"]["summary"]["basis"], "body")
            self.assertEqual(skills["sum-head"]["summary"]["body_blob_sha"], "sha_head")
            self.assertEqual(skills["sum-head"]["summary"]["generated_by"], "llm")

            # Propagated verbatim to the cluster twin.
            self.assertEqual(skills["sum-twin"]["summary"]["text"], VALID_SUMMARY)

            self.assertEqual(skills["sum-desc"]["summary"]["basis"], "description")
            self.assertIsNone(skills["sum-desc"]["summary"]["body_blob_sha"])

            # Cached and human-locked summaries untouched.
            self.assertTrue(skills["sum-cached"]["summary"]["text"].startswith("Existing cached"))
            self.assertEqual(skills["sum-human"]["summary"]["generated_by"], "human")
            self.assertNotIn("summary", skills["sum-unassigned"])

    def test_prepare_is_idempotent_until_upstream_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)

            with patch_module_paths(paths["skills"], paths["cache"], paths["mirror"]):
                prepare_summary_input(paths["input"])
                with open(paths["output"], "w", encoding="utf-8") as f:
                    json.dump({"summaries": {
                        "sum-head": VALID_SUMMARY,
                        "sum-desc": (
                            "Provides guidance for desc-only workflows, covering the setup "
                            "steps and commands users need to run the underlying tool."
                        )
                    }}, f)
                apply_summary_assignments(paths["output"])

                # Second prepare: everything is current -> nothing queued.
                prepare_summary_input(paths["input"])
                with open(paths["input"], "r", encoding="utf-8") as f:
                    self.assertEqual(json.load(f)["heads_needing_summaries"], [])

                # Upstream body change on sum-head -> queued again once the new
                # body is fetchable.
                skills = self._load_skills(paths)
                skills["sum-head"]["upstream"]["blob_sha"] = "sha_head_v2"
                with open(paths["skills"], "w", encoding="utf-8") as f:
                    json.dump({"schema_version": 1, "skills": list(skills.values())}, f)
                populate_blob_cache(paths["cache"], "org1", "r1", "sha_head_v2", "New body v2.")

                # A real body appearing for sum-desc (mirror file) -> upgrade queued too.
                (paths["mirror"] / "sum-desc.md").write_text("Fresh mirrored body.", encoding="utf-8")

                prepare_summary_input(paths["input"])
                with open(paths["input"], "r", encoding="utf-8") as f:
                    requeued = {n["skill_id"] for n in json.load(f)["heads_needing_summaries"]}
                self.assertEqual(requeued, {"sum-head", "sum-desc"})

    def test_stale_body_summary_kept_until_body_refetchable(self):
        # Upstream drifted but neither the blob cache nor a mirror has the new
        # body: the old body-based summary must be kept, not queued for a
        # description-quality rewrite.
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)
            skills = self._load_skills(paths)
            skills["sum-cached"]["upstream"]["blob_sha"] = "sha_cached_v2"
            with open(paths["skills"], "w", encoding="utf-8") as f:
                json.dump({"schema_version": 1, "skills": list(skills.values())}, f)

            with patch_module_paths(paths["skills"], paths["cache"], paths["mirror"]):
                prepare_summary_input(paths["input"])

            with open(paths["input"], "r", encoding="utf-8") as f:
                queued = {n["skill_id"] for n in json.load(f)["heads_needing_summaries"]}
            self.assertNotIn("sum-cached", queued)

    def test_apply_rejects_invalid_unknown_and_locked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)

            with open(paths["output"], "w", encoding="utf-8") as f:
                json.dump({"summaries": {
                    "sum-head": "Too short to pass.",
                    "sum-twin": VALID_SUMMARY,       # member, not an eligible head
                    "no-such-skill": VALID_SUMMARY,  # unknown id
                    "sum-human": VALID_SUMMARY       # human-locked
                }}, f)

            with patch_module_paths(paths["skills"], paths["cache"], paths["mirror"]):
                apply_summary_assignments(paths["output"])

            skills = self._load_skills(paths)
            self.assertNotIn("summary", skills["sum-head"])
            self.assertNotIn("summary", skills["sum-twin"])
            self.assertTrue(skills["sum-human"]["summary"]["text"].startswith("Curator-written"))

    def test_apply_missing_output_file_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup(tmpdir)
            with patch_module_paths(paths["skills"], paths["cache"], paths["mirror"]):
                apply_summary_assignments(paths["output"])  # never written
            skills = self._load_skills(paths)
            self.assertNotIn("summary", skills["sum-head"])


if __name__ == "__main__":
    unittest.main()
