#!/usr/bin/env bash

# SkillDeck Development Environment Setup and Validation Script
# Idempotent setup for Linux/macOS:
# 1. Checks prerequisites (Python, Node.js, npm).
# 2. Verifies or creates the isolated Python virtual environment (.venv).
# 3. Upgrades pip and installs Python dependencies from requirements.txt.
# 4. Installs Node.js dependencies in the site directory.
# 5. Generates the initial data/kb.json artifact if missing.
# 6. Validates the Python codebase via unit tests.
# 7. Validates the Astro frontend codebase via a production build test.

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

write_success() {
    echo -e "${GREEN}[SUCCESS] $1${RESET}"
}

write_step() {
    echo -e "${WHITE}[*] $1${RESET}"
}

write_warning() {
    echo -e "${YELLOW}[WARNING] $1${RESET}"
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

echo -e "${CYAN}==========================================================${RESET}"
echo -e "${CYAN}        SkillDeck Development Setup & Validation${RESET}"
echo -e "${CYAN}==========================================================${RESET}"
echo -e "${GRAY}Project Root: $PROJECT_ROOT${RESET}"

# ---------------------------------------------------------
# 1. Prerequisite Checks
# ---------------------------------------------------------
write_header "Checking Prerequisites"

# Python Check
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    write_error "Python is not installed or not in system PATH."
    exit 1
fi

python_version_string=$("$PYTHON_CMD" --version 2>&1)
write_step "System Python: $python_version_string"

if [[ "$python_version_string" =~ Python[[:space:]]([0-9]+)\.([0-9]+) ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        write_error "Python version 3.11+ is required. Found: $python_version_string"
        exit 1
    fi
else
    write_error "Could not parse Python version."
    exit 1
fi

# Ensure Node is working and set working PATH
ensure_working_node

node_version=$(node -v)
write_step "Node.js version: $node_version"

npm_version=$(npm -v)
write_step "npm version: $npm_version"

write_success "Prerequisites check passed."

# ---------------------------------------------------------
# 2. Python Virtual Environment (.venv) Setup
# ---------------------------------------------------------
write_header "Setting up Python Virtual Environment"

VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"
PIP_EXE="$VENV_DIR/bin/pip"

# If .venv exists but is incomplete/broken (missing python or pip), clean it up
if [ -d "$VENV_DIR" ] && { [ ! -f "$PYTHON_EXE" ] || [ ! -f "$PIP_EXE" ]; }; then
    write_warning ".venv directory exists but is incomplete/broken. Cleaning it..."
    rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    write_step "Creating isolated virtual environment in .venv..."
    if ! "$PYTHON_CMD" -m venv "$VENV_DIR" 2>/dev/null; then
        write_warning "Standard venv creation failed (possibly missing ensurepip). Attempting build without pip..."
        # Clean up any partial directory
        rm -rf "$VENV_DIR"
        if ! "$PYTHON_CMD" -m venv --without-pip "$VENV_DIR"; then
            write_error "Failed to create virtual environment. Ensure python3-venv is installed."
            rm -rf "$VENV_DIR"
            exit 1
        fi
        write_step "Virtual environment created without pip. Bootstrapping pip..."
        if ! curl -sS https://bootstrap.pypa.io/get-pip.py | "$PYTHON_EXE"; then
            write_error "Failed to bootstrap pip inside virtual environment."
            rm -rf "$VENV_DIR"
            exit 1
        fi
    fi
    write_success "Virtual environment created."
else
    write_step "Isolated virtual environment (.venv) already exists."
fi

# Upgrade pip
write_step "Upgrading pip..."
if ! "$PYTHON_EXE" -m pip install --upgrade pip --quiet --use-deprecated=legacy-certs; then
    write_error "Failed to upgrade pip inside virtual environment."
    exit 1
fi

# Install requirements.txt
REQS_FILE="$PROJECT_ROOT/requirements.txt"
if [ ! -f "$REQS_FILE" ]; then
    write_error "requirements.txt not found at $REQS_FILE."
    exit 1
fi

write_step "Installing Python dependencies from requirements.txt..."
if ! "$PIP_EXE" install -r "$REQS_FILE" --disable-pip-version-check; then
    write_error "Failed to install Python dependencies."
    exit 1
fi
write_step "Installing pytest for development tests..."
if ! "$PIP_EXE" install pytest --disable-pip-version-check --quiet; then
    write_warning "Failed to install pytest inside virtual environment."
fi
write_success "Python environment setup complete."

# ---------------------------------------------------------
# 3. Node.js dependencies Setup
# ---------------------------------------------------------
write_header "Setting up Frontend Dependencies"

SITE_DIR="$PROJECT_ROOT/site"
if [ ! -d "$SITE_DIR" ]; then
    write_error "site directory not found at $SITE_DIR"
    exit 1
fi

write_step "Navigating to $SITE_DIR and running npm install..."
(
    cd "$SITE_DIR" || exit 1
    npm install
)
if [ $? -ne 0 ]; then
    write_error "npm install failed in $SITE_DIR"
    exit 1
fi
write_success "Frontend dependencies setup complete."

# ---------------------------------------------------------
# 4. Generate Missing Development Artifacts (kb.json)
# ---------------------------------------------------------
write_header "Validating and Generating Development Artifacts"

KB_JSON_FILE="$PROJECT_ROOT/data/kb.json"
if [ ! -f "$KB_JSON_FILE" ]; then
    write_step "data/kb.json not found. Generating initial knowledge base via Python kitchen..."
    
    # Run the emit pipeline command to generate kb.json
    (
        cd "$PROJECT_ROOT" || exit 1
        export PYTHONPATH="$PROJECT_ROOT"
        "$PYTHON_EXE" -m kitchen emit
    )
    if [ $? -ne 0 ]; then
        write_error "Failed to generate kb.json using python -m kitchen emit"
        exit 1
    fi
    write_success "Initial data/kb.json successfully generated."
else
    write_step "data/kb.json already exists."
fi

# ---------------------------------------------------------
# 5. Validation and Testing
# ---------------------------------------------------------
write_header "Validating Pipeline and Frontend Toolchains"

# Run Python kitchen unit tests
write_step "Running Python pipeline unit tests..."
(
    cd "$PROJECT_ROOT" || exit 1
    export PYTHONPATH="$PROJECT_ROOT"
    if "$PYTHON_EXE" -c "import pytest" >/dev/null 2>&1; then
        "$PYTHON_EXE" -m pytest kitchen/tests/
    else
        write_warning "pytest not found. Falling back to standard unittest discovery..."
        "$PYTHON_EXE" -m unittest discover -s kitchen/tests
    fi
)
if [ $? -ne 0 ]; then
    write_error "Python unit tests failed."
    exit 1
fi
write_success "Python pipeline tests passed."

# Run Frontend component unit tests
write_step "Running Frontend component unit tests..."
(
    cd "$SITE_DIR" || exit 1
    npm run test
)
if [ $? -ne 0 ]; then
    write_error "Frontend component unit tests failed."
    exit 1
fi
write_success "Frontend component unit tests passed."

# Run Frontend build test
write_step "Validating frontend build toolchain..."
(
    cd "$SITE_DIR" || exit 1
    npm run build
)
if [ $? -ne 0 ]; then
    write_error "Frontend build validation failed."
    exit 1
fi
write_success "Frontend build validation succeeded."

# Run Frontend E2E browser tests
write_step "Running Frontend E2E browser tests..."
(
    cd "$SITE_DIR" || exit 1
    npm run test:e2e
)
if [ $? -ne 0 ]; then
    write_error "Frontend E2E browser tests failed."
    exit 1
fi
write_success "Frontend E2E browser tests passed."

# 6. GITHUB_TOKEN Diagnostic Check (Non-Blocking)
write_header "Running GitHub Token Diagnostic"
TOKEN_SCRIPT="$SCRIPT_DIR/check-git-token.sh"
if [ -f "$TOKEN_SCRIPT" ]; then
    bash "$TOKEN_SCRIPT" || true
else
    write_warning "check-git-token.sh not found at $TOKEN_SCRIPT"
fi

echo -e "\n${GREEN}==========================================================${RESET}"
echo -e "${GREEN}  SkillDeck Setup and Validation Completed Successfully!${RESET}"
echo -e "${GREEN}  You can now run the app using ./scripts/linux/dev-run.sh${RESET}"
echo -e "${GREEN}==========================================================${RESET}"
