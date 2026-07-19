import jsonschema

# Shared shape for the "nutrition" (context-cost) object, nullable at the
# call site: null means the nutrition stage hasn't run for that skill yet.
NUTRITION_SCHEMA = {
    "type": ["object", "null"],
    "required": ["token_estimate", "word_count", "line_count", "basis", "trigger", "body_blob_sha", "computed_at"],
    "properties": {
        "token_estimate": {"type": "integer", "minimum": 0},
        "word_count": {"type": "integer", "minimum": 0},
        "line_count": {"type": "integer", "minimum": 1},
        "basis": {"type": "string", "enum": ["body", "description"]},
        "trigger": {"type": "string", "maxLength": 200},
        "body_blob_sha": {"type": ["string", "null"]},
        "computed_at": {"type": "string", "format": "date-time"}
    }
}

# Shared shape for the "summary" (Skill Summary) object on skills.json
# records, nullable at the call site: null/absent means the summary stage
# hasn't run for that skill yet. kb.json carries only the text (see
# KB_SCHEMA's skill_refs).
SUMMARY_SCHEMA = {
    "type": ["object", "null"],
    "required": ["text", "basis", "body_blob_sha", "generated_by", "generated_at"],
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "basis": {"type": "string", "enum": ["body", "description"]},
        "body_blob_sha": {"type": ["string", "null"]},
        "generated_by": {"type": "string", "enum": ["llm", "human"]},
        "generated_at": {"type": "string", "format": "date-time"}
    }
}

# Schema for sources.json
SOURCES_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "sources"],
    "properties": {
        "schema_version": {"type": "integer"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "org", "repo_url", "kind", "vendor", "default_license"],
                "properties": {
                    "id": {"type": "string"},
                    "org": {"type": "string"},
                    "repo_url": {"type": "string", "format": "uri"},
                    "kind": {"type": "string", "enum": ["official", "partner", "community", "aggregator"]},
                    "vendor": {"type": ["string", "null"]},
                    "default_license": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]}
                }
            }
        }
    }
}

# Schema for install_matrix.json
INSTALL_MATRIX_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "methods", "fallback_order"],
    "properties": {
        "schema_version": {"type": "integer"},
        "methods": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tool_id", "method", "template", "requires_hints", "verified_on", "doc_url"],
                "properties": {
                    "tool_id": {"type": "string", "enum": ["claude-code", "claude-ai", "vscode-copilot", "antigravity", "gemini-cli", "cursor"]},
                    "method": {"type": "string", "enum": ["plugin", "manual", "builtin", "npx"]},
                    "template": {"type": "string"},
                    "requires_hints": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "verified_on": {"type": "string", "format": "date"},
                    "doc_url": {"type": "string", "format": "uri"}
                }
            }
        },
        "fallback_order": {
            "type": "object",
            "required": ["claude-code", "claude-ai", "vscode-copilot", "cursor", "antigravity", "gemini-cli"],
            "properties": {
                "claude-code": {"type": "array", "items": {"type": "string"}},
                "claude-ai": {"type": "array", "items": {"type": "string"}},
                "vscode-copilot": {"type": "array", "items": {"type": "string"}},
                "cursor": {"type": "array", "items": {"type": "string"}},
                "antigravity": {"type": "array", "items": {"type": "string"}},
                "gemini-cli": {"type": "array", "items": {"type": "string"}}
            }
        }
    }
}

# Schema for skills.json
SKILLS_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "generated_at", "skills"],
    "properties": {
        "schema_version": {"type": "integer"},
        "generated_at": {"type": "string", "format": "date-time"},
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id", "source_id", "provenance", "origin", "name", 
                    "frontmatter_description", "license", "mirrorable", 
                    "upstream", "status", "tier", "capability_id", 
                    "native_ecosystem", "reviewed_by", "reviewed_at"
                ],
                "properties": {
                    "id": {"type": "string"},
                    "source_id": {"type": "string"},
                    "provenance": {"type": "string", "enum": ["official", "partner", "community"]},
                    "origin": {
                        "type": "object",
                        "required": ["org", "repo", "path", "default_branch"],
                        "properties": {
                            "org": {"type": "string"},
                            "repo": {"type": "string"},
                            "path": {"type": "string"},
                            "default_branch": {"type": "string"}
                        }
                    },
                    "name": {"type": "string"},
                    "frontmatter_description": {"type": "string"},
                    "license": {"type": "string"},
                    "mirrorable": {"type": "boolean"},
                    "upstream": {
                        "type": "object",
                        "required": ["commit_sha", "blob_sha", "fetched_at"],
                        "properties": {
                            "commit_sha": {"type": "string"},
                            "blob_sha": {"type": "string"},
                            "fetched_at": {"type": "string", "format": "date-time"}
                        }
                    },
                    "status": {"type": "string", "enum": ["active", "gone"]},
                    "tier": {"type": "string", "enum": ["core", "shell", "rejected"]},
                    "capability_id": {"type": "string"},
                    "capability_assigned_blob_sha": {"type": ["string", "null"]},
                    "native_ecosystem": {"type": "string", "enum": ["claude", "google", "vscode", "generic"]},
                    "install_hints": {"type": "object"},
                    "reviewed_by": {"type": ["string", "null"]},
                    "reviewed_at": {"type": ["string", "null"]},
                    "reviewed_commit_sha": {"type": ["string", "null"]},
                    "reject_reason": {"type": ["string", "null"]},
                    "freshness": {"type": ["string", "null"], "enum": ["drifted", None]},
                    "upstream_changed_at": {"type": ["string", "null"]},
                    "lifecycle_phase": {
                        "type": ["string", "null"],
                        "enum": ["define", "plan", "build", "verify", "review", "ship", None]
                    },
                    "phase_assigned_blob_sha": {"type": ["string", "null"]},
                    "nutrition": NUTRITION_SCHEMA,
                    "summary": SUMMARY_SCHEMA
                }
            }
        }
    }
}

# Shared shape for a resolved skill reference (kb.json's skill_refs items
# and all_skills items are the same shape; all_skills additionally carries
# capability_id since it isn't implied by an enclosing capability entry).
SKILL_REF_SCHEMA = {
    "type": "object",
    "required": ["name", "repo_url", "provenance", "license", "review_status", "reviewed_at", "install", "nutrition", "summary"],
    "properties": {
        "name": {"type": "string"},
        "repo_url": {"type": "string", "format": "uri"},
        "provenance": {"type": "string", "enum": ["official", "partner", "community"]},
        "vendor": {"type": ["string", "null"]},
        "license": {"type": "string"},
        "review_status": {"type": "string", "enum": ["human_read", "auto_summarized"]},
        "reviewed_at": {"type": ["string", "null"]},
        "freshness": {"type": ["string", "null"], "enum": ["drifted", None]},
        "upstream_changed_at": {"type": ["string", "null"]},
        "upstream_fetched_at": {"type": ["string", "null"]},
        "lifecycle_phase": {
            "type": ["string", "null"],
            "enum": ["define", "plan", "build", "verify", "review", "ship", None]
        },
        "install": {
            "type": "object",
            "additionalProperties": {"type": "string"}
        },
        "nutrition": NUTRITION_SCHEMA,
        "summary": {"type": ["string", "null"]}
    }
}

ALL_SKILLS_ENTRY_SCHEMA = {
    "type": "object",
    "required": SKILL_REF_SCHEMA["required"] + ["capability_id"],
    "properties": {
        **SKILL_REF_SCHEMA["properties"],
        "capability_id": {"type": ["string", "null"]}
    }
}

# Schema for kb.json
KB_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "generated_at", "tools", "capabilities", "lifecycle_phases", "entries", "all_skills"],
    "properties": {
        "schema_version": {"type": "integer"},
        "generated_at": {"type": "string", "format": "date-time"},
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"}
                }
            }
        },
        "capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "label", "order"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "order": {"type": "integer"}
                }
            }
        },
        "lifecycle_phases": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "label", "order"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "order": {"type": "integer"}
                }
            }
        },
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["capability_id", "recommended", "card", "skill_refs", "alternatives"],
                "properties": {
                    "capability_id": {"type": "string"},
                    "recommended": {
                        "type": "object",
                        "required": ["default", "by_tool"],
                        "properties": {
                            "default": {"type": "string"},
                            "by_tool": {
                                "type": "object",
                                "additionalProperties": {"type": "string"}
                            }
                        }
                    },
                    "card": {
                        "type": "object",
                        "required": ["title", "what_it_does", "try_saying", "generated_by", "generated_at"],
                        "properties": {
                            "title": {"type": "string"},
                            "what_it_does": {"type": "string"},
                            "try_saying": {"type": "string"},
                            "generated_by": {"type": "string", "enum": ["llm", "fallback", "human"]},
                            "generated_at": {"type": "string", "format": "date-time"}
                        }
                    },
                    "skill_refs": {
                        "type": "object",
                        "additionalProperties": SKILL_REF_SCHEMA
                    },
                    "alternatives": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                }
            }
        },
        "all_skills": {
            "type": "object",
            "additionalProperties": ALL_SKILLS_ENTRY_SCHEMA
        }
    }
}

def validate_json(data: dict, schema: dict):
    jsonschema.validate(instance=data, schema=schema)
