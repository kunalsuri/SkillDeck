import unittest
import jsonschema
from kitchen.schemas import (
    SOURCES_SCHEMA, INSTALL_MATRIX_SCHEMA, SKILLS_SCHEMA, KB_SCHEMA, validate_json
)

class TestSchemas(unittest.TestCase):
    def test_sources_schema_valid(self):
        valid_sources = {
            "schema_version": 1,
            "sources": [
                {
                    "id": "src-1",
                    "org": "org-1",
                    "repo_url": "https://github.com/org-1/repo-1",
                    "kind": "official",
                    "vendor": "google",
                    "default_license": "Apache-2.0",
                    "notes": "some notes"
                }
            ]
        }
        # Should not raise exception
        validate_json(valid_sources, SOURCES_SCHEMA)

    def test_sources_schema_invalid(self):
        invalid_sources = {
            "schema_version": "not-an-int",
            "sources": []
        }
        with self.assertRaises(jsonschema.ValidationError):
            validate_json(invalid_sources, SOURCES_SCHEMA)

    def test_install_matrix_schema_valid(self):
        valid_matrix = {
            "schema_version": 1,
            "methods": [
                {
                    "tool_id": "claude-code",
                    "method": "plugin",
                    "template": "/plugin install {plugin_name}",
                    "requires_hints": ["plugin_name"],
                    "verified_on": "2026-07-01",
                    "doc_url": "https://example.com/docs"
                }
            ],
            "fallback_order": {
                "claude-code": ["plugin"],
                "claude-ai": ["builtin"],
                "vscode-copilot": ["manual"],
                "cursor": ["manual"],
                "antigravity": ["npx"],
                "gemini-cli": ["npx"]
            }
        }
        validate_json(valid_matrix, INSTALL_MATRIX_SCHEMA)

    def test_install_matrix_schema_invalid(self):
        invalid_matrix = {
            "schema_version": 1,
            "methods": [],
            "fallback_order": {} # missing keys
        }
        with self.assertRaises(jsonschema.ValidationError):
            validate_json(invalid_matrix, INSTALL_MATRIX_SCHEMA)

    def test_skills_schema_valid(self):
        valid_skills = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "skills": [
                {
                    "id": "skill-1",
                    "source_id": "src-1",
                    "provenance": "official",
                    "origin": {
                        "org": "org-1",
                        "repo": "repo-1",
                        "path": "skills/skill-1",
                        "default_branch": "main"
                    },
                    "name": "skill-1",
                    "frontmatter_description": "desc",
                    "license": "MIT",
                    "mirrorable": True,
                    "upstream": {
                        "commit_sha": "abc",
                        "blob_sha": "def",
                        "fetched_at": "2026-07-07T09:00:00Z"
                    },
                    "status": "active",
                    "tier": "shell",
                    "capability_id": "documents",
                    "native_ecosystem": "claude",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "reviewed_commit_sha": None,
                    "reject_reason": None,
                    "freshness": None,
                    "upstream_changed_at": None,
                    "lifecycle_phase": "build"
                }
            ]
        }
        validate_json(valid_skills, SKILLS_SCHEMA)

    def test_skills_schema_invalid(self):
        invalid_skills = {
            "schema_version": 1
            # "generated_at" and "skills" are required but missing
        }
        with self.assertRaises(jsonschema.ValidationError):
            validate_json(invalid_skills, SKILLS_SCHEMA)

    def test_skills_schema_invalid_lifecycle_phase(self):
        invalid_skills = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "skills": [
                {
                    "id": "skill-1",
                    "source_id": "src-1",
                    "provenance": "official",
                    "origin": {
                        "org": "org-1",
                        "repo": "repo-1",
                        "path": "skills/skill-1",
                        "default_branch": "main"
                    },
                    "name": "skill-1",
                    "frontmatter_description": "desc",
                    "license": "MIT",
                    "mirrorable": True,
                    "upstream": {
                        "commit_sha": "abc",
                        "blob_sha": "def",
                        "fetched_at": "2026-07-07T09:00:00Z"
                    },
                    "status": "active",
                    "tier": "shell",
                    "capability_id": "documents",
                    "native_ecosystem": "claude",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "lifecycle_phase": "not-a-real-phase"
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError):
            validate_json(invalid_skills, SKILLS_SCHEMA)

    def test_kb_schema_valid(self):
        valid_kb = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "tools": [{"id": "claude-code", "label": "Claude"}],
            "capabilities": [{"id": "documents", "label": "Docs", "order": 1}],
            "lifecycle_phases": [{"id": "build", "label": "Build", "order": 3}],
            "entries": [
                {
                    "capability_id": "documents",
                    "recommended": {
                        "default": "skill-1",
                        "by_tool": {}
                    },
                    "card": {
                        "title": "Make report",
                        "what_it_does": "Does reports.",
                        "try_saying": "Say report.",
                        "generated_by": "llm",
                        "generated_at": "2026-07-07T10:00:00Z"
                    },
                    "skill_refs": {
                        "skill-1": {
                            "name": "skill-1",
                            "repo_url": "https://github.com/org/repo/tree/main/path",
                            "provenance": "official",
                            "vendor": "anthropic",
                            "license": "MIT",
                            "review_status": "auto_summarized",
                            "reviewed_at": None,
                            "lifecycle_phase": "build",
                            "install": {
                                "claude-code": "run command"
                            },
                            "nutrition": {
                                "token_estimate": 320,
                                "word_count": 250,
                                "line_count": 40,
                                "basis": "body",
                                "trigger": "Use this when users request generative art.",
                                "body_blob_sha": "abc123",
                                "computed_at": "2026-07-07T10:00:00Z"
                            },
                            "summary": "Generates generative art reports from prompts and saves them as documents."
                        }
                    },
                    "alternatives": []
                }
            ]
        }
        validate_json(valid_kb, KB_SCHEMA)

    def test_kb_schema_valid_with_null_nutrition(self):
        # nutrition is nullable: null means the nutrition stage hasn't run yet.
        valid_kb = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "tools": [{"id": "claude-code", "label": "Claude"}],
            "capabilities": [{"id": "documents", "label": "Docs", "order": 1}],
            "lifecycle_phases": [{"id": "build", "label": "Build", "order": 3}],
            "entries": [
                {
                    "capability_id": "documents",
                    "recommended": {"default": "skill-1", "by_tool": {}},
                    "card": {
                        "title": "Make report",
                        "what_it_does": "Does reports.",
                        "try_saying": "Say report.",
                        "generated_by": "llm",
                        "generated_at": "2026-07-07T10:00:00Z"
                    },
                    "skill_refs": {
                        "skill-1": {
                            "name": "skill-1",
                            "repo_url": "https://github.com/org/repo/tree/main/path",
                            "provenance": "official",
                            "vendor": "anthropic",
                            "license": "MIT",
                            "review_status": "auto_summarized",
                            "reviewed_at": None,
                            "install": {"claude-code": "run command"},
                            "nutrition": None,
                            "summary": None
                        }
                    },
                    "alternatives": []
                }
            ]
        }
        validate_json(valid_kb, KB_SCHEMA)

    def test_kb_schema_invalid_missing_nutrition_key(self):
        invalid_kb = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "tools": [{"id": "claude-code", "label": "Claude"}],
            "capabilities": [{"id": "documents", "label": "Docs", "order": 1}],
            "lifecycle_phases": [{"id": "build", "label": "Build", "order": 3}],
            "entries": [
                {
                    "capability_id": "documents",
                    "recommended": {"default": "skill-1", "by_tool": {}},
                    "card": {
                        "title": "Make report",
                        "what_it_does": "Does reports.",
                        "try_saying": "Say report.",
                        "generated_by": "llm",
                        "generated_at": "2026-07-07T10:00:00Z"
                    },
                    "skill_refs": {
                        "skill-1": {
                            "name": "skill-1",
                            "repo_url": "https://github.com/org/repo/tree/main/path",
                            "provenance": "official",
                            "vendor": "anthropic",
                            "license": "MIT",
                            "review_status": "auto_summarized",
                            "reviewed_at": None,
                            "install": {"claude-code": "run command"}
                            # "nutrition" deliberately omitted
                        }
                    },
                    "alternatives": []
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError):
            validate_json(invalid_kb, KB_SCHEMA)

    def test_skills_schema_valid_without_nutrition_field(self):
        # Old records without "nutrition" at all must still validate.
        valid_skills = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "skills": [
                {
                    "id": "skill-1",
                    "source_id": "src-1",
                    "provenance": "official",
                    "origin": {
                        "org": "org-1",
                        "repo": "repo-1",
                        "path": "skills/skill-1",
                        "default_branch": "main"
                    },
                    "name": "skill-1",
                    "frontmatter_description": "desc",
                    "license": "MIT",
                    "mirrorable": True,
                    "upstream": {
                        "commit_sha": "abc",
                        "blob_sha": "def",
                        "fetched_at": "2026-07-07T09:00:00Z"
                    },
                    "status": "active",
                    "tier": "shell",
                    "capability_id": "documents",
                    "native_ecosystem": "claude",
                    "reviewed_by": None,
                    "reviewed_at": None
                }
            ]
        }
        validate_json(valid_skills, SKILLS_SCHEMA)

    def test_kb_schema_invalid(self):
        invalid_kb = {
            "schema_version": 1,
            "generated_at": "2026-07-07T10:00:00Z",
            "tools": [],
            "capabilities": [],
            "lifecycle_phases": [],
            "entries": [
                {
                    "capability_id": "documents",
                    "recommended": {
                        "default": "skill-1",
                        "by_tool": {}
                    },
                    "card": {
                        "title": "Make report",
                        "what_it_does": "Does reports.",
                        "try_saying": "Say report.",
                        "generated_by": "invalid-generated-by-value", # invalid
                        "generated_at": "2026-07-07T10:00:00Z"
                    },
                    "skill_refs": {},
                    "alternatives": []
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError):
            validate_json(invalid_kb, KB_SCHEMA)

if __name__ == "__main__":
    unittest.main()
