#!/usr/bin/env bash

# SkillDeck Development Environment Launch Script
# 1. Verifies that prerequisites are met and dependencies are installed.
# 2. Ensures data/kb.json is present (generating it if missing).
# 3. Runs the Astro dev server.
# 4. Displays access URLs and helpful pipeline usage commands.

# Ensure script halts on error
set -e

# Since this script resides in the /scripts subdirectory, the project root is the parent directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Helper Functions and Colors
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
WHITE='\033[0;37m'
GRAY='\033[0;90m'
RED='\033[0;31m'
RESET='\033[0m'

write_header() {
    echo -e "\n${YELLOW}--- $1 ---${RESET}"
}

write_step() {
    echo -e "${WHITE}[*] $1${RESET}"
}

write_warning() {
    echo -e "${YELLOW}[WARNING] $1${RESET}"
}

write_success() {
    echo -e "${GREEN}[SUCCESS] $1${RESET}"
}

write_error() {
    echo -e "${RED}[ERROR] $1${RESET}" >&2
}

# Verifies that Node.js/npm works and recovers if using a non-functional version
test_node_npm() {
    local node_cmd="$1"
    local npm_cmd="$2"
    if command -v "$node_cmd" >/dev/null 2>&1 && command -v "$npm_cmd" >/dev/null 2>&1; then
        local node_ver
        node_ver=$("$node_cmd" -v 2>/dev/null)
        if [ $? -eq 0 ] && [[ "$node_ver" == v* ]]; then
            if "$npm_cmd" -v >/dev/null 2>&1; then
                return 0
            fi
        fi
    fi
    return 1
}

ensure_working_node() {
    write_step "Verifying Node.js and npm functionality..."
    
    # 1. Test current PATH node/npm
    if test_node_npm "node" "npm"; then
        write_step "Default Node.js installation is functional."
        return 0
    fi
    
    write_warning "Default Node.js in PATH is non-functional or not found."
    write_step "Searching for alternative working Node.js installations..."
    
    local candidate_dirs=()
    
    # NVM paths
    if [ -d "$HOME/.nvm/versions/node" ]; then
        for dir in $(ls -vd "$HOME/.nvm/versions/node"/*/bin 2>/dev/null | tac); do
            if [ -d "$dir" ]; then
                candidate_dirs+=("$dir")
            fi
        done
    fi
    
    # FNM paths
    if [ -d "$HOME/.local/share/fnm/node-versions" ]; then
        for dir in $(ls -vd "$HOME/.local/share/fnm/node-versions"/*/installation/bin 2>/dev/null | tac); do
            if [ -d "$dir" ]; then
                candidate_dirs+=("$dir")
            fi
        done
    elif [ -d "$HOME/.fnm/node-versions" ]; then
        for dir in $(ls -vd "$HOME/.fnm/node-versions"/*/bin 2>/dev/null | tac); do
            if [ -d "$dir" ]; then
                candidate_dirs+=("$dir")
            fi
        done
    fi
    
    # System Node paths
    for sys_dir in "/usr/local/bin" "/usr/bin" "/opt/node/bin"; do
        if [ -d "$sys_dir" ]; then
            candidate_dirs+=("$sys_dir")
        fi
    done
    
    local found_working=false
    for dir in "${candidate_dirs[@]}"; do
        local original_path="$PATH"
        export PATH="$dir:$PATH"
        
        if test_node_npm "node" "npm"; then
            write_success "Found working Node.js/npm at: $dir"
            found_working=true
            break
        else
            export PATH="$original_path"
        fi
    done
    
    if [ "$found_working" = false ]; then
        write_error "No functional Node.js/npm installation found. Please ensure Node.js is installed and accessible."
        exit 1
    fi
}

# ---------------------------------------------------------
# 1. Quick Verification Checks
# ---------------------------------------------------------
write_header "Verifying Development Environment"

VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"

if [ ! -d "$VENV_DIR" ] || [ ! -f "$PYTHON_EXE" ]; then
    echo -e "${RED}Error: Virtual environment not found or incomplete. Please run ./scripts/linux/dev-setup.sh first.${RESET}" >&2
    exit 1
fi
write_step "Isolated virtual environment verified."

# Node.js & npm checks
ensure_working_node

# Node modules check
SITE_DIR="$PROJECT_ROOT/site"
NODE_MODULES_DIR="$SITE_DIR/node_modules"
if [ ! -d "$NODE_MODULES_DIR" ]; then
    write_warning "site/node_modules not found. Running npm install..."
    (
        cd "$SITE_DIR" || exit 1
        npm install
    )
fi
write_step "Frontend dependencies verified."

# Knowledge Base data check
KB_JSON_FILE="$PROJECT_ROOT/data/kb.json"
if [ ! -f "$KB_JSON_FILE" ]; then
    write_warning "data/kb.json is missing. Generating default/initial knowledge base..."
    (
        cd "$PROJECT_ROOT" || exit 1
        export PYTHONPATH="$PROJECT_ROOT"
        "$PYTHON_EXE" -m kitchen emit
    )
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to auto-generate kb.json. Please run ./scripts/linux/dev-setup.sh${RESET}" >&2
        exit 1
    fi
fi
write_step "Knowledge base data verified."

# Check for GitHub token (optional for dev server, required for the kitchen's ingest/canonicalize/freshness stages)
if [ -z "${GITHUB_TOKEN:-}" ]; then
    write_warning "GITHUB_TOKEN environment variable is not set."
    echo -e "${GRAY}          This is OK for running the local Astro website.${RESET}"
    echo -e "${GRAY}          However, to run the offline pipeline ingest/canonicalize stages, you will need to set it.${RESET}"
    echo -e "${GRAY}          Example: export GITHUB_TOKEN='your-token'${RESET}"
    echo -e "${GRAY}          Capability clustering and card writing are done by the /skilldeck-ingest Claude Code command, not an API key.${RESET}"
fi

# ---------------------------------------------------------
# 2. Starting Dev Server
# ---------------------------------------------------------
write_header "Starting SkillDeck Development Server"

echo -e "${CYAN}Access URLs:${RESET}"
echo -e "  - Local Website:      ${GREEN}http://localhost:4321/${RESET}"
echo -e "  - Static Files View:  ${GREEN}file://$SITE_DIR/dist/index.html${RESET} (after building)"
echo -e "\n${CYAN}Pipeline Helper Commands (run in virtual environment):${RESET}"
echo -e "  - Run scriptable stages (ingest/canonicalize/dedup/rank): ${GRAY}python -m kitchen pipeline${RESET}"
echo -e "  - Full ingest incl. capability clustering + cards: ${GRAY}run the /skilldeck-ingest command in Claude Code${RESET}"
echo -e "  - Generate static data/kb.json: ${GRAY}python -m kitchen emit${RESET}"
echo -e "  - Run pipeline unit tests:    ${GRAY}python -m unittest discover -s kitchen/tests${RESET}"
echo -e "\n${YELLOW}Press Ctrl+C to terminate the development server.${RESET}\n"

# Navigate to site and run dev server
(
    cd "$SITE_DIR" || exit 1
    npm run dev
) || {
    echo -e "${CYAN}Dev server stopped.${RESET}"
}
