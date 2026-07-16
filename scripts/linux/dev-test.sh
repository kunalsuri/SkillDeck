#!/usr/bin/env bash

# SkillDeck Development Environment Testing Script
# Runs all test suites in the repository:
# 1. Python pipeline unit tests (via pytest)
# 2. Frontend component unit tests (via Vitest)
# 3. Frontend E2E browser tests (via Playwright)

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

write_success() {
    echo -e "${GREEN}[SUCCESS] $1${RESET}"
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
echo -e "${CYAN}             SkillDeck Test Suite Runner${RESET}"
echo -e "${CYAN}==========================================================${RESET}"
echo -e "${GRAY}Project Root: $PROJECT_ROOT${RESET}"

# 1. Environment Check
write_header "Checking Testing Environment"

VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"

if [ ! -d "$VENV_DIR" ] || [ ! -f "$PYTHON_EXE" ]; then
    write_error "Virtual environment not found. Please run ./scripts/linux/dev-setup.sh first."
    exit 1
fi
write_step "Python virtual environment verified."

ensure_working_node

SITE_DIR="$PROJECT_ROOT/site"
NODE_MODULES_DIR="$SITE_DIR/node_modules"
if [ ! -d "$NODE_MODULES_DIR" ]; then
    write_error "site/node_modules not found. Please run ./scripts/linux/dev-setup.sh first."
    exit 1
fi
write_step "Node.js dependencies verified."

# Initialize tracking variables
python_passed=false
frontend_unit_passed=false
frontend_e2e_passed=false

# 2. Run Python tests
write_header "Running Python Pipeline Tests"
(
    cd "$PROJECT_ROOT" || exit 1
    export PYTHONPATH="$PROJECT_ROOT"
    "$PYTHON_EXE" -m pytest kitchen/tests/
) && {
    python_passed=true
    write_success "Python pipeline tests passed."
} || {
    write_warning "Python pipeline tests failed."
}

# 3. Run Frontend unit tests
write_header "Running Frontend Unit Tests"
(
    cd "$SITE_DIR" || exit 1
    npm run test
) && {
    frontend_unit_passed=true
    write_success "Frontend unit tests passed."
} || {
    write_warning "Frontend unit tests failed."
}

# 4. Run Frontend E2E tests
write_header "Running Frontend E2E Tests"
write_step "Building frontend before running E2E tests..."
(
    cd "$SITE_DIR" || exit 1
    npm run build && npm run test:e2e
) && {
    frontend_e2e_passed=true
    write_success "Frontend E2E tests passed."
} || {
    write_warning "Frontend E2E tests failed."
}

# 5. Summary
write_header "Test Execution Summary"

printf "Python Pipeline Unit Tests:      "
if [ "$python_passed" = true ]; then
    echo -e "${GREEN}PASSED${RESET}"
else
    echo -e "${RED}FAILED${RESET}"
fi

printf "Frontend Component Unit Tests:  "
if [ "$frontend_unit_passed" = true ]; then
    echo -e "${GREEN}PASSED${RESET}"
else
    echo -e "${RED}FAILED${RESET}"
fi

printf "Frontend E2E Browser Tests:     "
if [ "$frontend_e2e_passed" = true ]; then
    echo -e "${GREEN}PASSED${RESET}"
else
    echo -e "${RED}FAILED${RESET}"
fi

echo -e "\n${CYAN}==========================================================${RESET}"

if [ "$python_passed" = true ] && [ "$frontend_unit_passed" = true ] && [ "$frontend_e2e_passed" = true ]; then
    echo -e "${GREEN}  All test suites completed successfully!${RESET}"
    echo -e "${GREEN}==========================================================${RESET}"
    exit 0
else
    echo -e "${RED}  Some test suites failed. Review the logs above.${RESET}"
    echo -e "${RED}==========================================================${RESET}"
    exit 1
fi
