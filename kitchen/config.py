from pathlib import Path

# Paths
KITCHEN_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = KITCHEN_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
SOURCES_JSON = DATA_DIR / "sources.json"
SKILLS_JSON = DATA_DIR / "skills.json"
INSTALL_MATRIX_JSON = DATA_DIR / "install_matrix.json"
KB_JSON = DATA_DIR / "kb.json"

MIRROR_DIR = PROJECT_ROOT / "mirror"
CACHE_DIR = PROJECT_ROOT / ".kitchen_cache"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
MIRROR_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Provenance Mapping
OFFICIAL_ORGS = {
    "anthropics",
    "google",
    "googleworkspace",
    "google-labs-code",
    "vercel-labs",
}

# Add some partner orgs for demonstration
PARTNER_ORGS = {
    "microsoft",
    "meta",
    "cohere",
    "huggingface",
    "openai",
    "nvidia",
    "datadog-labs",
    "block",
    "skills",
}

# Thresholds
JACCARD_THRESHOLD = 0.7

# Capabilities list (defined in §3.4)
CAPABILITIES = [
    {"id": "documents", "label": "Create & edit documents", "order": 1},
    {"id": "data-analysis", "label": "Analyze data & spreadsheets", "order": 2},
    {"id": "frontend", "label": "Build web pages & UI", "order": 3},
    {"id": "cloud-ops", "label": "Work with Google Cloud", "order": 4},
    {"id": "testing", "label": "Test web apps & code", "order": 5},
    {"id": "planning", "label": "Plan long agent tasks", "order": 6},
    {"id": "agent-building", "label": "Build MCP servers & agents", "order": 7},
    {"id": "design", "label": "Design, themes & branding", "order": 8}
]

# Lifecycle phases for the Software Engineering / SDLC page (id/label/order,
# same shape as CAPABILITIES). Inspired by addyosmani/agent-skills.
LIFECYCLE_PHASES = [
    {"id": "define", "label": "Define", "order": 1},
    {"id": "plan", "label": "Plan", "order": 2},
    {"id": "build", "label": "Build", "order": 3},
    {"id": "verify", "label": "Verify", "order": 4},
    {"id": "review", "label": "Review", "order": 5},
    {"id": "ship", "label": "Ship", "order": 6},
]

TOOLS = [
    {"id": "claude-code", "label": "Claude Code"},
    {"id": "claude-ai", "label": "Claude.ai"},
    {"id": "vscode-copilot", "label": "VS Code / Copilot"},
    {"id": "antigravity", "label": "Antigravity"},
    {"id": "gemini-cli", "label": "Gemini CLI"},
    {"id": "cursor", "label": "Cursor"}
]
