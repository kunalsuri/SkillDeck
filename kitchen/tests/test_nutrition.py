import unittest
from unittest.mock import patch
import json
import tempfile
import hashlib
import base64
from pathlib import Path
from kitchen.nutrition import extract_trigger, compute_metrics, run_nutrition


def _write_blob_cache(cache_dir: Path, org: str, repo: str, blob_sha: str, content: str):
    url = f"https://api.github.com/repos/{org}/{repo}/git/blobs/{blob_sha}"
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    with open(cache_dir / f"{url_hash}.json", "w", encoding="utf-8") as f:
        json.dump({"body": {"content": encoded}}, f)


def _make_skill(**overrides):
    skill = {
        "id": "skill-a",
        "status": "active",
        "tier": "core",
        "frontmatter_description": "Creates reports. Use this when users request generative art.",
        "origin": {"org": "org1", "repo": "repo1", "path": "p1", "default_branch": "main"},
        "upstream": {"blob_sha": "sha_a", "fetched_at": "2026-07-07T08:00:00Z"},
    }
    skill.update(overrides)
    return skill


class TestExtractTrigger(unittest.TestCase):
    def test_matches_trigger_phrase(self):
        desc = "Creates reports for teams. Use this when users request generative art. Extra sentence here."
        self.assertEqual(
            extract_trigger(desc),
            "Use this when users request generative art."
        )

    def test_matches_bare_trigger_word(self):
        desc = "Does a thing. Trigger: whenever a PR is opened."
        self.assertEqual(extract_trigger(desc), "Trigger: whenever a PR is opened.")

    def test_no_match_falls_back_to_first_sentence(self):
        desc = "This skill formats code. It has no special phrasing at all."
        self.assertEqual(extract_trigger(desc), "This skill formats code.")

    def test_truncates_over_200_chars(self):
        desc = "Use this when " + ("x" * 250) + "."
        trigger = extract_trigger(desc)
        self.assertEqual(len(trigger), 200)
        self.assertTrue(trigger.endswith("…"))

    def test_empty_description_returns_empty_string(self):
        self.assertEqual(extract_trigger(""), "")
        self.assertEqual(extract_trigger("   "), "")


class TestComputeMetrics(unittest.TestCase):
    def test_formula_values_on_fixed_string(self):
        text = "The quick brown fox jumps over the lazy dog."  # 44 chars, 9 words, 1 line
        self.assertEqual(len(text), 44)
        metrics = compute_metrics(text)
        self.assertEqual(metrics["token_estimate"], 11)  # round(44 / 4) == 11
        self.assertEqual(metrics["word_count"], 9)
        self.assertEqual(metrics["line_count"], 1)

    def test_line_count_multi_line(self):
        text = "line one\nline two\nline three"
        metrics = compute_metrics(text)
        self.assertEqual(metrics["line_count"], 3)

    def test_crlf_normalized_before_counting(self):
        crlf_text = "line one\r\nline two\r\nline three"
        lf_text = "line one\nline two\nline three"
        self.assertEqual(compute_metrics(crlf_text), compute_metrics(lf_text))


class TestRunNutrition(unittest.TestCase):
    def _run(self, tmpdir, skills, cache_files=None, mirror_files=None):
        tmp_dir = Path(tmpdir)
        tmp_skills = tmp_dir / "skills.json"
        tmp_cache = tmp_dir / ".kitchen_cache"
        tmp_mirror = tmp_dir / "mirror"
        tmp_cache.mkdir(parents=True, exist_ok=True)
        tmp_mirror.mkdir(parents=True, exist_ok=True)

        for fn in (cache_files or []):
            fn(tmp_cache)
        for fn in (mirror_files or []):
            fn(tmp_mirror)

        with open(tmp_skills, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "generated_at": "2026-07-07T10:00:00Z", "skills": skills}, f)

        with patch("kitchen.nutrition.SKILLS_JSON", tmp_skills), \
             patch("kitchen.dedup.CACHE_DIR", tmp_cache), \
             patch("kitchen.dedup.MIRROR_DIR", tmp_mirror):
            run_nutrition()

        with open(tmp_skills, "r", encoding="utf-8") as f:
            return {s["id"]: s for s in json.load(f)["skills"]}

    def test_body_basis_from_blob_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill = _make_skill()
            body = "Full SKILL.md body content here, quite a bit longer than the description."
            result = self._run(
                tmpdir, [skill],
                cache_files=[lambda d: _write_blob_cache(d, "org1", "repo1", "sha_a", body)]
            )
            n = result["skill-a"]["nutrition"]
            self.assertEqual(n["basis"], "body")
            self.assertEqual(n["body_blob_sha"], "sha_a")
            self.assertEqual(n["token_estimate"], round(len(body) / 4))
            self.assertIsNotNone(n["computed_at"])

    def test_mirror_fallback_basis_body(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill = _make_skill()
            body = "Mirrored body content, used when the blob cache is cold."
            result = self._run(
                tmpdir, [skill],
                mirror_files=[lambda d: (d / "skill-a.md").write_text(body, encoding="utf-8")]
            )
            n = result["skill-a"]["nutrition"]
            self.assertEqual(n["basis"], "body")
            self.assertEqual(n["body_blob_sha"], "sha_a")

    def test_description_fallback_when_no_body_resolvable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill = _make_skill()
            result = self._run(tmpdir, [skill])
            n = result["skill-a"]["nutrition"]
            self.assertEqual(n["basis"], "description")
            self.assertIsNone(n["body_blob_sha"])
            self.assertEqual(n["token_estimate"], round(len(skill["frontmatter_description"]) / 4))

    def test_trigger_always_extracted_from_description_even_with_body(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill = _make_skill()
            body = "Totally different body text with no trigger phrasing whatsoever here."
            result = self._run(
                tmpdir, [skill],
                cache_files=[lambda d: _write_blob_cache(d, "org1", "repo1", "sha_a", body)]
            )
            n = result["skill-a"]["nutrition"]
            self.assertEqual(n["trigger"], "Use this when users request generative art.")

    def test_idempotent_second_run_no_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill = _make_skill()
            body = "Stable body content for the idempotency check."
            cache_fn = lambda d: _write_blob_cache(d, "org1", "repo1", "sha_a", body)

            tmp_dir = Path(tmpdir)
            tmp_skills = tmp_dir / "skills.json"
            tmp_cache = tmp_dir / ".kitchen_cache"
            tmp_mirror = tmp_dir / "mirror"
            tmp_cache.mkdir(parents=True, exist_ok=True)
            tmp_mirror.mkdir(parents=True, exist_ok=True)
            cache_fn(tmp_cache)
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump({"schema_version": 1, "generated_at": "2026-07-07T10:00:00Z", "skills": [skill]}, f)

            with patch("kitchen.nutrition.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.dedup.CACHE_DIR", tmp_cache), \
                 patch("kitchen.dedup.MIRROR_DIR", tmp_mirror):
                run_nutrition()
                with open(tmp_skills, "r", encoding="utf-8") as f:
                    first = json.load(f)["skills"][0]["nutrition"]

                run_nutrition()
                with open(tmp_skills, "r", encoding="utf-8") as f:
                    second = json.load(f)["skills"][0]["nutrition"]

            self.assertEqual(first, second)
            self.assertEqual(first["computed_at"], second["computed_at"])

    def test_never_downgrades_body_basis_when_body_becomes_unresolvable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill = _make_skill(nutrition={
                "token_estimate": 50, "word_count": 40, "line_count": 5,
                "basis": "body", "trigger": "Use this when x.",
                "body_blob_sha": "sha_a", "computed_at": "2026-01-01T00:00:00Z"
            })
            # No cache file, no mirror file this time -> body unresolvable.
            result = self._run(tmpdir, [skill])
            n = result["skill-a"]["nutrition"]
            self.assertEqual(n["basis"], "body")
            self.assertEqual(n["computed_at"], "2026-01-01T00:00:00Z")
            self.assertEqual(n["token_estimate"], 50)

    def test_recomputes_when_blob_sha_changed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill = _make_skill(nutrition={
                "token_estimate": 1, "word_count": 1, "line_count": 1,
                "basis": "body", "trigger": "", "body_blob_sha": "old_sha",
                "computed_at": "2026-01-01T00:00:00Z"
            })
            body = "Fresh body content after an upstream change."
            result = self._run(
                tmpdir, [skill],
                cache_files=[lambda d: _write_blob_cache(d, "org1", "repo1", "sha_a", body)]
            )
            n = result["skill-a"]["nutrition"]
            self.assertEqual(n["body_blob_sha"], "sha_a")
            self.assertNotEqual(n["computed_at"], "2026-01-01T00:00:00Z")

    def test_rejected_and_gone_skills_untouched(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gone = _make_skill(id="skill-gone", status="gone")
            rejected = _make_skill(id="skill-rejected", tier="rejected")
            result = self._run(tmpdir, [gone, rejected])
            self.assertNotIn("nutrition", result["skill-gone"])
            self.assertNotIn("nutrition", result["skill-rejected"])


if __name__ == "__main__":
    unittest.main()
