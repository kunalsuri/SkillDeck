// Mirrors kitchen/schemas.py's KB_SCHEMA - the shape of data/kb.json. Shared
// by every frontend component that consumes the knowledge base, so the shape
// only needs to be updated in one place when the schema changes.
export interface Tool {
  id: string;
  label: string;
}

export interface Capability {
  id: string;
  label: string;
  order: number;
}

export interface LifecyclePhase {
  id: string;
  label: string;
  order: number;
}

export interface Card {
  title: string;
  what_it_does: string;
  try_saying: string;
  generated_by: string;
  generated_at: string;
}

export interface Nutrition {
  token_estimate: number;
  word_count: number;
  line_count: number;
  basis: 'body' | 'description';
  trigger: string;
  body_blob_sha: string | null;
  computed_at: string;
}

export interface SkillRef {
  name: string;
  repo_url: string;
  provenance: string;
  vendor: string | null;
  license: string;
  review_status: string;
  reviewed_at: string | null;
  freshness: string | null;
  upstream_changed_at: string | null;
  upstream_fetched_at: string | null;
  lifecycle_phase: string | null;
  install: Record<string, string>;
  nutrition: Nutrition | null;
  // Optional until the next `python -m kitchen emit` regenerates kb.json;
  // null when the summary stage hasn't produced text for the skill yet.
  summary?: string | null;
}

export interface KBEntry {
  capability_id: string;
  recommended: {
    default: string;
    by_tool: Record<string, string>;
  };
  card: Card;
  skill_refs: Record<string, SkillRef>;
  alternatives: string[];
}

// Same shape as SkillRef, plus capability_id: null for a skill that was
// never assigned one of the 8 curated capabilities (too domain-specific
// for the fixed taxonomy) but is still a real, browsable skill.
export interface AllSkillsEntry extends SkillRef {
  capability_id: string | null;
}

export interface KB {
  schema_version: number;
  generated_at: string;
  tools: Tool[];
  capabilities: Capability[];
  lifecycle_phases: LifecyclePhase[];
  entries: KBEntry[];
  // Superset of every entry's skill_refs: every active, non-rejected skill
  // regardless of capability assignment. Backs the publisher/vendor browse
  // view and per-skill detail pages so a skill can be independently
  // browsable without ever landing in one of the 8 capabilities.
  all_skills: Record<string, AllSkillsEntry>;
}
