import unittest
from unittest.mock import MagicMock, patch
import json
import tempfile
import hashlib
import base64
from pathlib import Path
from kitchen.emit import (
    resolve_install_command, get_vendor, run_emit, load_previous_cards_by_capability
)
from kitchen.schemas import validate_json, KB_SCHEMA

class TestEmit(unittest.TestCase):
    def test_get_vendor(self):
        self.assertEqual(get_vendor("anthropics"), "anthropic")
        self.assertEqual(get_vendor("googleworkspace"), "google")
        self.assertEqual(get_vendor("otherorg"), None)

    def test_resolve_install_command_pipeline(self):
        # Mock skill and methods
        skill = {
            "name": "my-skill",
            "origin": {
                "org": "my-org",
                "repo": "my-repo",
                "path": "skills/my-skill"
            },
            "install_hints": {
                "claude-code": {
                    "plugin_name": "custom-plugin",
                    "marketplace": "custom-market"
                }
            }
        }
        
        methods_dict = {
            ("claude-code", "plugin"): {
                "template": "/plugin install {plugin_name}@{marketplace}",
                "requires_hints": ["plugin_name", "marketplace"]
            },
            ("claude-code", "manual"): {
                "template": "Copy files to ~/.claude/skills/{skill_name}",
                "requires_hints": []
            }
        }
        
        # Test success plugin path
        cmd = resolve_install_command(skill, "claude-code", methods_dict, ["plugin", "manual"])
        self.assertEqual(cmd, "/plugin install custom-plugin@custom-market")
        
        # Test fallback to manual when hints are missing
        skill_no_hints = skill.copy()
        skill_no_hints["install_hints"] = {}
        cmd_fallback = resolve_install_command(skill_no_hints, "claude-code", methods_dict, ["plugin", "manual"])
        self.assertEqual(cmd_fallback, "Copy files to ~/.claude/skills/my-skill")

    @patch("kitchen.emit.load_cards_cache")
    def test_run_emit_pipeline(self, mock_load_cards):
        # We mock load_cards_cache to return a test card
        mock_load_cards.return_value = {
            "skill-head:sha_head": {
                "title": "Clean report",
                "what_it_does": "Cleans documents.",
                "try_saying": "Clean it.",
                "generated_by": "llm",
                "generated_at": "2026-07-07T10:00:00Z"
            }
        }
        
        skills_content = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "skills": [
                # 1. Active core skill (elected cluster-1 head, mirrorable=True)
                {
                    "id": "skill-head",
                    "name": "skill-head",
                    "status": "active",
                    "tier": "core",
                    "provenance": "official",
                    "license": "MIT",
                    "mirrorable": True,
                    "origin": {"org": "anthropics", "repo": "skills", "path": "skills/head", "default_branch": "main"},
                    "upstream": {"commit_sha": "sha_h", "blob_sha": "sha_head", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "documents",
                    "cluster_id": "cluster-1",
                    "score_default": 1000,
                    "scores_by_tool": {t: 1000 for t in ["claude-code", "claude-ai", "vscode-copilot", "antigravity", "gemini-cli", "cursor"]},
                    "reviewed_by": "Bob",
                    "reviewed_at": "2026-07-07T09:00:00Z",
                    "freshness": "drifted",
                    "upstream_changed_at": "2026-07-06T00:00:00Z",
                    "lifecycle_phase": None,
                    "nutrition": {
                        "token_estimate": 100, "word_count": 80, "line_count": 12,
                        "basis": "body", "trigger": "Use this when users need reports.",
                        "body_blob_sha": "sha_head", "computed_at": "2026-07-08T00:00:00Z"
                    },
                    "summary": {
                        "text": "Cleans and restructures report documents into a consistent layout with numbered sections.",
                        "basis": "body", "body_blob_sha": "sha_head",
                        "generated_by": "llm", "generated_at": "2026-07-08T00:00:00Z"
                    }
                },
                # 2. Active shell skill in cluster-1 (non-mirrorable MIT, community, not head)
                {
                    "id": "skill-twin",
                    "name": "skill-twin",
                    "status": "active",
                    "tier": "shell",
                    "provenance": "community",
                    "license": "unspecified",
                    "mirrorable": False,
                    "origin": {"org": "org2", "repo": "r2", "path": "p2", "default_branch": "main"},
                    "upstream": {"commit_sha": "sha_t", "blob_sha": "sha_twin", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "documents",
                    "cluster_id": "cluster-1",
                    "score_default": 100,
                    "scores_by_tool": {t: 100 for t in ["claude-code", "claude-ai", "vscode-copilot", "antigravity", "gemini-cli", "cursor"]},
                    "reviewed_by": None,
                    "reviewed_at": None
                },
                # 3. Vanished skill (should be skipped)
                {
                    "id": "skill-gone",
                    "name": "skill-gone",
                    "status": "gone",
                    "tier": "shell",
                    "provenance": "community",
                    "license": "MIT",
                    "mirrorable": True,
                    "origin": {"org": "o3", "repo": "r3", "path": "p3", "default_branch": "main"},
                    "upstream": {"commit_sha": "s3", "blob_sha": "sb3", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "documents",
                    "cluster_id": "cluster-1"
                },
                # 4. & 5. Two DIFFERENT clusters both assigned to the same capability
                # (not deduped together) - must still collapse into one kb.json entry.
                {
                    "id": "skill-cap-a",
                    "name": "skill-cap-a",
                    "status": "active",
                    "tier": "core",
                    "provenance": "official",
                    "license": "MIT",
                    "mirrorable": True,
                    "origin": {"org": "org4", "repo": "r4", "path": "p4", "default_branch": "main"},
                    "upstream": {"commit_sha": "sha_4", "blob_sha": "sha_cap_a", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "testing",
                    "cluster_id": "cluster-2",
                    "score_default": 900,
                    "scores_by_tool": {t: 900 for t in ["claude-code", "claude-ai", "vscode-copilot", "antigravity", "gemini-cli", "cursor"]},
                    "reviewed_by": "Alice",
                    "reviewed_at": "2026-07-07T09:00:00Z",
                    "lifecycle_phase": "verify"
                },
                {
                    "id": "skill-cap-b",
                    "name": "skill-cap-b",
                    "status": "active",
                    "tier": "shell",
                    "provenance": "community",
                    "license": "MIT",
                    "mirrorable": False,
                    "origin": {"org": "org5", "repo": "r5", "path": "p5", "default_branch": "main"},
                    "upstream": {"commit_sha": "sha_5", "blob_sha": "sha_cap_b", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "testing",
                    "cluster_id": "cluster-3",
                    "score_default": 100,
                    "scores_by_tool": {t: 100 for t in ["claude-code", "claude-ai", "vscode-copilot", "antigravity", "gemini-cli", "cursor"]},
                    "reviewed_by": None,
                    "reviewed_at": None
                },
                # 6. & 7. A capability where the highest-scoring member is an
                # unreviewed shell skill and a lower-scoring member is core -
                # the reviewed core skill must still win the recommendation.
                {
                    "id": "skill-design-shell",
                    "name": "skill-design-shell",
                    "status": "active",
                    "tier": "shell",
                    "provenance": "community",
                    "license": "MIT",
                    "mirrorable": False,
                    "origin": {"org": "org6", "repo": "r6", "path": "p6", "default_branch": "main"},
                    "upstream": {"commit_sha": "sha_6", "blob_sha": "sha_design_shell", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "design",
                    "cluster_id": "cluster-4",
                    "score_default": 950,
                    "scores_by_tool": {t: 950 for t in ["claude-code", "claude-ai", "vscode-copilot", "antigravity", "gemini-cli", "cursor"]},
                    "reviewed_by": None,
                    "reviewed_at": None
                },
                {
                    "id": "skill-design-core",
                    "name": "skill-design-core",
                    "status": "active",
                    "tier": "core",
                    "provenance": "community",
                    "license": "MIT",
                    "mirrorable": False,
                    "origin": {"org": "org7", "repo": "r7", "path": "p7", "default_branch": "main"},
                    "upstream": {"commit_sha": "sha_7", "blob_sha": "sha_design_core", "fetched_at": "2026-07-07T08:00:00Z"},
                    "capability_id": "design",
                    "cluster_id": "cluster-5",
                    "score_default": 200,
                    "scores_by_tool": {t: 200 for t in ["claude-code", "claude-ai", "vscode-copilot", "antigravity", "gemini-cli", "cursor"]},
                    "reviewed_by": "Carol",
                    "reviewed_at": "2026-07-07T09:00:00Z"
                }
            ]
        }

        # Mock install_matrix.json
        install_matrix = {
            "schema_version": 1,
            "methods": [
                {
                    "tool_id": "claude-code",
                    "method": "manual",
                    "template": "manual-install {org}/{repo}/{skill_name}",
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

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_skills = Path(tmpdir) / "skills.json"
            tmp_matrix = Path(tmpdir) / "install_matrix.json"
            tmp_kb = Path(tmpdir) / "kb.json"
            tmp_mirror = Path(tmpdir) / "mirror"
            tmp_cache_dir = Path(tmpdir) / ".kitchen_cache"
            tmp_cache_dir.mkdir()
            
            with open(tmp_skills, "w", encoding="utf-8") as f:
                json.dump(skills_content, f)
            with open(tmp_matrix, "w", encoding="utf-8") as f:
                json.dump(install_matrix, f)
                
            # Write mock cache file for skill-head body so get_skill_body doesn't fall back to empty string
            url = "https://api.github.com/repos/anthropics/skills/git/blobs/sha_head"
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            encoded_body = base64.b64encode("Mirrored SKILL.md body".encode("utf-8")).decode("utf-8")
            with open(tmp_cache_dir / f"{url_hash}.json", "w", encoding="utf-8") as f:
                json.dump({"body": {"content": encoded_body}}, f)

            with patch("kitchen.emit.SKILLS_JSON", tmp_skills), \
                 patch("kitchen.emit.INSTALL_MATRIX_JSON", tmp_matrix), \
                 patch("kitchen.emit.KB_JSON", tmp_kb), \
                 patch("kitchen.emit.MIRROR_DIR", tmp_mirror), \
                 patch("kitchen.dedup.CACHE_DIR", tmp_cache_dir):
                run_emit()

            # 1. Verify kb.json compiled correctly
            with open(tmp_kb, "r", encoding="utf-8") as f:
                kb_data = json.load(f)

            entries_by_cap = {e["capability_id"]: e for e in kb_data["entries"]}

            # Exactly one entry per capability - no duplicate capability_id entries
            self.assertEqual(len(kb_data["entries"]), 3)
            self.assertEqual(set(entries_by_cap.keys()), {"documents", "testing", "design"})

            # lifecycle_phases is emitted at the top level (mirrors capabilities/tools)
            self.assertEqual([p["id"] for p in kb_data["lifecycle_phases"]],
                              ["define", "plan", "build", "verify", "review", "ship"])

            entry = entries_by_cap["documents"]
            self.assertEqual(entry["recommended"]["default"], "skill-head")

            # 2. Check skill_refs review statuses
            self.assertEqual(entry["skill_refs"]["skill-head"]["review_status"], "human_read")
            self.assertEqual(entry["skill_refs"]["skill-twin"]["review_status"], "auto_summarized")
            self.assertIn("skill-twin", entry["alternatives"])

            # 2c. lifecycle_phase passes through per skill_ref (null if unset)
            self.assertIsNone(entry["skill_refs"]["skill-head"]["lifecycle_phase"])
            self.assertEqual(
                entries_by_cap["testing"]["skill_refs"]["skill-cap-a"]["lifecycle_phase"], "verify"
            )

            # 2b. Check freshness drift passthrough (skill-head drifted, skill-twin clean)
            self.assertEqual(entry["skill_refs"]["skill-head"]["freshness"], "drifted")
            self.assertEqual(entry["skill_refs"]["skill-head"]["upstream_changed_at"], "2026-07-06T00:00:00Z")
            self.assertEqual(entry["skill_refs"]["skill-head"]["upstream_fetched_at"], "2026-07-07T08:00:00Z")
            self.assertIsNone(entry["skill_refs"]["skill-twin"]["freshness"])

            # 2d. nutrition passes through per skill_ref; a skill without it emits null
            self.assertEqual(entry["skill_refs"]["skill-head"]["nutrition"]["basis"], "body")
            self.assertEqual(entry["skill_refs"]["skill-head"]["nutrition"]["token_estimate"], 100)
            self.assertIsNone(entry["skill_refs"]["skill-twin"]["nutrition"])

            # 2e. summary text passes through per skill_ref; a skill without one emits null
            self.assertEqual(
                entry["skill_refs"]["skill-head"]["summary"],
                "Cleans and restructures report documents into a consistent layout with numbered sections."
            )
            self.assertIsNone(entry["skill_refs"]["skill-twin"]["summary"])

            # KB validation passes with a mix of present and null nutrition.
            validate_json(kb_data, KB_SCHEMA)

            # 3. Check resolved install commands
            self.assertEqual(entry["skill_refs"]["skill-head"]["install"]["claude-code"], "manual-install anthropics/skills/skill-head")
            
            # 4. Check mirrored files
            self.assertTrue((tmp_mirror / "skill-head.md").exists())
            with open(tmp_mirror / "skill-head.md", "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "Mirrored SKILL.md body")
                
            # Non-mirrorable skill-twin should NOT be mirrored
            self.assertFalse((tmp_mirror / "skill-twin.md").exists())

            # 5. Capability collision: skill-cap-a and skill-cap-b are in DIFFERENT
            # clusters but share capability_id "testing" - must merge into one
            # entry, not silently drop one of them.
            testing_entry = entries_by_cap["testing"]
            self.assertEqual(testing_entry["recommended"]["default"], "skill-cap-a")
            self.assertIn("skill-cap-b", testing_entry["alternatives"])
            self.assertIn("skill-cap-a", testing_entry["skill_refs"])
            self.assertIn("skill-cap-b", testing_entry["skill_refs"])

            # 6. recommended.default is gated to core-tier where one exists:
            # skill-design-shell outscores skill-design-core but is unreviewed,
            # so the reviewed (lower-scoring) core skill must win instead.
            design_entry = entries_by_cap["design"]
            self.assertEqual(design_entry["recommended"]["default"], "skill-design-core")
            self.assertIn("skill-design-shell", design_entry["alternatives"])

def _make_skill(mirrorable=True, capability_id="documents"):
    return {
        "id": "skill-head",
        "name": "skill-head",
        "status": "active",
        "tier": "core",
        "provenance": "official",
        "license": "MIT",
        "mirrorable": mirrorable,
        "origin": {"org": "anthropics", "repo": "skills", "path": "skills/head", "default_branch": "main"},
        "upstream": {"commit_sha": "sha_h", "blob_sha": "sha_head", "fetched_at": "2026-07-07T08:00:00Z"},
        "capability_id": capability_id,
        "cluster_id": "cluster-1",
        "score_default": 1000,
        "scores_by_tool": {t: 1000 for t in ["claude-code", "claude-ai", "vscode-copilot", "antigravity", "gemini-cli", "cursor"]},
        "reviewed_by": "Bob",
        "reviewed_at": "2026-07-07T09:00:00Z",
        "freshness": None,
        "upstream_changed_at": None,
        "lifecycle_phase": None,
    }


INSTALL_MATRIX_FIXTURE = {
    "schema_version": 1,
    "methods": [
        {
            "tool_id": "claude-code",
            "method": "manual",
            "template": "manual-install {org}/{repo}/{skill_name}",
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


class TestEmitPhase0FreshClone(unittest.TestCase):
    """Covers SPEC-01 Phase 0: emit must not destroy committed data (cards,
    mirror bodies) when the local .kitchen_cache/ is cold, as it is on a
    fresh clone."""

    def _setup_dirs(self, tmpdir):
        tmp_dir = Path(tmpdir)
        paths = {
            "skills": tmp_dir / "skills.json",
            "matrix": tmp_dir / "install_matrix.json",
            "kb": tmp_dir / "kb.json",
            "mirror": tmp_dir / "mirror",
            "cache": tmp_dir / ".kitchen_cache",
        }
        paths["mirror"].mkdir(parents=True, exist_ok=True)
        paths["cache"].mkdir(parents=True, exist_ok=True)
        with open(paths["skills"], "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "generated_at": "2026-07-07T10:00:00Z", "skills": [_make_skill()]}, f)
        with open(paths["matrix"], "w", encoding="utf-8") as f:
            json.dump(INSTALL_MATRIX_FIXTURE, f)
        return paths

    def _patches(self, paths, cards_cache_return):
        return [
            patch("kitchen.emit.SKILLS_JSON", paths["skills"]),
            patch("kitchen.emit.INSTALL_MATRIX_JSON", paths["matrix"]),
            patch("kitchen.emit.KB_JSON", paths["kb"]),
            patch("kitchen.emit.MIRROR_DIR", paths["mirror"]),
            patch("kitchen.dedup.CACHE_DIR", paths["cache"]),
            patch("kitchen.dedup.MIRROR_DIR", paths["mirror"]),
            patch("kitchen.emit.load_cards_cache", return_value=cards_cache_return),
        ]

    def _run_with_patches(self, patches):
        started = [p.start() for p in patches]
        try:
            run_emit()
        finally:
            for p in patches:
                p.stop()

    def test_cold_cache_with_existing_llm_card_is_kept_verbatim(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup_dirs(tmpdir)
            previous_kb = {
                "schema_version": 1,
                "generated_at": "2026-07-06T00:00:00Z",
                "tools": [], "capabilities": [], "lifecycle_phases": [],
                "entries": [{
                    "capability_id": "documents",
                    "recommended": {"default": "skill-head", "by_tool": {}},
                    "card": {
                        "title": "Real card",
                        "what_it_does": "Real description.",
                        "try_saying": "Do the real thing.",
                        "generated_by": "llm",
                        "generated_at": "2026-07-01T00:00:00Z",
                    },
                    "skill_refs": {}, "alternatives": []
                }]
            }
            with open(paths["kb"], "w", encoding="utf-8") as f:
                json.dump(previous_kb, f)

            self._run_with_patches(self._patches(paths, {}))

            with open(paths["kb"], "r", encoding="utf-8") as f:
                kb_data = json.load(f)
            card = kb_data["entries"][0]["card"]
            self.assertEqual(card["title"], "Real card")
            self.assertEqual(card["generated_by"], "llm")
            self.assertEqual(card["generated_at"], "2026-07-01T00:00:00Z")

    def test_cold_cache_no_existing_kb_falls_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup_dirs(tmpdir)
            # No kb.json written at all.
            self._run_with_patches(self._patches(paths, {}))

            with open(paths["kb"], "r", encoding="utf-8") as f:
                kb_data = json.load(f)
            self.assertEqual(kb_data["entries"][0]["card"]["generated_by"], "fallback")

    def test_warm_cards_cache_wins_over_previous_kb_card(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup_dirs(tmpdir)
            previous_kb = {
                "schema_version": 1, "generated_at": "2026-07-06T00:00:00Z",
                "tools": [], "capabilities": [], "lifecycle_phases": [],
                "entries": [{
                    "capability_id": "documents",
                    "recommended": {"default": "skill-head", "by_tool": {}},
                    "card": {
                        "title": "Stale card", "what_it_does": "Stale.", "try_saying": "Stale.",
                        "generated_by": "llm", "generated_at": "2026-07-01T00:00:00Z",
                    },
                    "skill_refs": {}, "alternatives": []
                }]
            }
            with open(paths["kb"], "w", encoding="utf-8") as f:
                json.dump(previous_kb, f)

            warm_cache = {
                "skill-head:sha_head": {
                    "title": "Fresh card", "what_it_does": "Fresh.", "try_saying": "Fresh.",
                    "generated_by": "llm", "generated_at": "2026-07-09T00:00:00Z",
                }
            }
            self._run_with_patches(self._patches(paths, warm_cache))

            with open(paths["kb"], "r", encoding="utf-8") as f:
                kb_data = json.load(f)
            self.assertEqual(kb_data["entries"][0]["card"]["title"], "Fresh card")

    def test_mirror_file_untouched_when_blob_cache_cold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup_dirs(tmpdir)
            mirror_path = paths["mirror"] / "skill-head.md"
            mirror_path.write_text("Committed real SKILL.md body.", encoding="utf-8")

            self._run_with_patches(self._patches(paths, {}))

            self.assertEqual(mirror_path.read_text(encoding="utf-8"), "Committed real SKILL.md body.")

    def test_mirror_file_deleted_when_skill_no_longer_emitted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup_dirs(tmpdir)
            stale_path = paths["mirror"] / "skill-gone.md"
            stale_path.write_text("Orphaned body.", encoding="utf-8")

            self._run_with_patches(self._patches(paths, {}))

            self.assertFalse(stale_path.exists())

    def test_mirror_file_rewritten_from_warm_blob_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._setup_dirs(tmpdir)
            mirror_path = paths["mirror"] / "skill-head.md"
            mirror_path.write_text("Stale committed body.", encoding="utf-8")

            url = "https://api.github.com/repos/anthropics/skills/git/blobs/sha_head"
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            encoded_body = base64.b64encode("Fresh upstream body.".encode("utf-8")).decode("utf-8")
            with open(paths["cache"] / f"{url_hash}.json", "w", encoding="utf-8") as f:
                json.dump({"body": {"content": encoded_body}}, f)

            self._run_with_patches(self._patches(paths, {}))

            self.assertEqual(mirror_path.read_text(encoding="utf-8"), "Fresh upstream body.")


class TestLoadPreviousCardsByCapability(unittest.TestCase):
    def test_missing_kb_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "does-not-exist.json"
            with patch("kitchen.emit.KB_JSON", missing):
                self.assertEqual(load_previous_cards_by_capability(), {})

    def test_malformed_kb_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "kb.json"
            bad.write_text("{not valid json", encoding="utf-8")
            with patch("kitchen.emit.KB_JSON", bad):
                self.assertEqual(load_previous_cards_by_capability(), {})


if __name__ == "__main__":
    unittest.main()
