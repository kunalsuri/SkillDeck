#!/usr/bin/env bash
# SkillDeck GitHub Token Diagnostic & Loader Script (check-git-token.sh)
# =======================================================================
# Checks for GITHUB_TOKEN across all sources (.env file, current session,
# shell profile) and reports status. Loads from .env if not already set.
#
# Checks performed:
#   1. Does .env exist in the project root?
#   2. Is GITHUB_TOKEN defined in .env?
#   3. Is GITHUB_TOKEN set in the current session?
#   4. Is GITHUB_TOKEN in a shell profile?
#   5. Load token into session if needed.
#   6. Is the token still valid (not revoked)? -- calls GitHub API
#   7. Is the token accidentally exposed in any tracked file?
#
# Usage:
#   bash scripts/linux/check-git-token.sh        # run in subshell (diagnostic only)
#   source scripts/linux/check-git-token.sh      # export token into current session

set -euo pipefail

# ---------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ---------------------------------------------------------
# Helpers (matching dev-*.sh style)
# ---------------------------------------------------------
write_header()  { printf '\n--- %s ---\n' "$1"; }
write_warning() { printf '\033[33m[WARNING] %s\033[0m\n' "$1"; }
write_success() { printf '\033[32m[SUCCESS] %s\033[0m\n' "$1"; }
write_error()   { printf '\033[31m[ERROR] %s\033[0m\n' "$1"; }
write_info()    { printf '\033[36m[INFO] %s\033[0m\n' "$1"; }

write_security_alert() {
    echo ""
    printf '\033[31m  %s\033[0m\n' "$(printf '=%.0s' {1..62})"
    while [ "$#" -gt 0 ]; do
        printf '\033[31m  !! %s\033[0m\n' "$1"
        shift
    done
    printf '\033[31m  %s\033[0m\n' "$(printf '=%.0s' {1..62})"
    echo ""
}

# Mask token: show first 4 and last 4 chars
mask_token() {
    local token="$1"
    local len=${#token}
    if [ "$len" -le 10 ]; then
        echo "****"
    else
        echo "${token:0:4}...${token: -4}"
    fi
}

# ---------------------------------------------------------
# State tracking
# ---------------------------------------------------------
ENV_FILE_EXISTS=false
ENV_FILE_TOKEN=""
SESSION_TOKEN=""
TOKEN_LOADED=false
ISSUES=0

write_header "SkillDeck GitHub Token Diagnostic"

# ---------------------------------------------------------
# 1. Check .env file
# ---------------------------------------------------------
write_header "1. Checking .env file"

ENV_FILE="$PROJECT_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
    ENV_FILE_EXISTS=true
    write_success ".env file found at: $ENV_FILE"

    # Parse GITHUB_TOKEN from .env (skip comments, handle quotes)
    while IFS= read -r line || [ -n "$line" ]; do
        trimmed="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        # Skip comments and blank lines
        [[ -z "$trimmed" || "$trimmed" == \#* ]] && continue

        if [[ "$trimmed" =~ ^GITHUB_TOKEN[[:space:]]*=[[:space:]]*(.+)$ ]]; then
            raw_value="${BASH_REMATCH[1]}"
            # Strip surrounding quotes
            raw_value="$(echo "$raw_value" | sed "s/^[\"']//;s/[\"']$//")"
            if [ -n "$raw_value" ] && [ "$raw_value" != "ghp_your_token_here" ]; then
                ENV_FILE_TOKEN="$raw_value"
            fi
        fi
    done < "$ENV_FILE"

    if [ -n "$ENV_FILE_TOKEN" ]; then
        masked=$(mask_token "$ENV_FILE_TOKEN")
        write_success "GITHUB_TOKEN found in .env: $masked"
    else
        write_warning "GITHUB_TOKEN not set in .env (missing, empty, or still the placeholder)."
        write_info "Edit .env and replace the placeholder with your real token."
        ISSUES=$((ISSUES + 1))
    fi
else
    write_warning ".env file not found."
    write_info "Create one by copying the template:"
    write_info "  cp \"$PROJECT_ROOT/.env.example\" \"$PROJECT_ROOT/.env\""
    write_info "  Then edit .env and add your GITHUB_TOKEN."
    ISSUES=$((ISSUES + 1))
fi

# ---------------------------------------------------------
# 2. Check current shell session
# ---------------------------------------------------------
write_header "2. Checking current session (\$GITHUB_TOKEN)"

SESSION_TOKEN="${GITHUB_TOKEN:-}"

if [ -n "$SESSION_TOKEN" ]; then
    masked=$(mask_token "$SESSION_TOKEN")
    write_success "GITHUB_TOKEN is set in this session: $masked"
else
    write_warning "GITHUB_TOKEN is NOT set in the current session."
    ISSUES=$((ISSUES + 1))
fi

# ---------------------------------------------------------
# 3. Check shell profile (informational)
# ---------------------------------------------------------
write_header "3. Checking shell profile for GITHUB_TOKEN"

PROFILE_FOUND=false
for profile_file in "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$profile_file" ]; then
        if grep -q 'GITHUB_TOKEN' "$profile_file" 2>/dev/null; then
            write_info "GITHUB_TOKEN reference found in: $profile_file"
            PROFILE_FOUND=true
        fi
    fi
done

if [ "$PROFILE_FOUND" = false ]; then
    write_info "GITHUB_TOKEN not found in shell profile files."
    write_info "This is fine if you prefer .env."
fi

# ---------------------------------------------------------
# 4. Load token into session if needed
# ---------------------------------------------------------
write_header "4. Loading token into session"

if [ -z "$SESSION_TOKEN" ]; then
    if [ -n "$ENV_FILE_TOKEN" ]; then
        export GITHUB_TOKEN="$ENV_FILE_TOKEN"
        SESSION_TOKEN="$ENV_FILE_TOKEN"
        TOKEN_LOADED=true
        masked=$(mask_token "$ENV_FILE_TOKEN")
        write_success "Loaded GITHUB_TOKEN from .env into session: $masked"
        ISSUES=$((ISSUES - 1))
    else
        write_error "No GITHUB_TOKEN found in any source. The kitchen pipeline will be rate-limited."
        write_info "To fix this:"
        write_info "  1. Copy .env.example to .env and add your token, OR"
        write_info "  2. Add to your shell profile:"
        write_info "     echo 'export GITHUB_TOKEN=\"ghp_yourToken\"' >> ~/.bashrc"
    fi
else
    write_info "Session already has GITHUB_TOKEN -- no loading needed."
fi

# ---------------------------------------------------------
# 5. Token validity check (GitHub API)
# ---------------------------------------------------------
write_header "5. Checking token validity (GitHub API)"

ACTIVE_TOKEN="${GITHUB_TOKEN:-}"

if [ -z "$ACTIVE_TOKEN" ]; then
    write_warning "No token in session -- skipping validity check."
elif ! command -v curl &>/dev/null; then
    write_warning "curl not found -- skipping validity check."
    write_info "Install curl to enable token validation."
else
    write_info "Calling https://api.github.com/user to verify token..."

    HTTP_STATUS=$(curl -s -o /tmp/skilldeck_gh_resp.json -w "%{http_code}" \
        -H "Authorization: Bearer $ACTIVE_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        -H "User-Agent: SkillDeck-check-git-token/1.0" \
        "https://api.github.com/user" 2>/dev/null || echo "000")

    if [ "$HTTP_STATUS" = "200" ]; then
        # Extract login from JSON response
        LOGIN=$(grep -o '"login":"[^"]*"' /tmp/skilldeck_gh_resp.json 2>/dev/null | head -1 | sed 's/"login":"//;s/"//')
        write_success "Token is VALID. Authenticated as: ${LOGIN:-<unknown>}"

        # Check scopes from response headers (need -v for headers, retry with -i)
        SCOPES=$(curl -s -I \
            -H "Authorization: Bearer $ACTIVE_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            -H "User-Agent: SkillDeck-check-git-token/1.0" \
            "https://api.github.com/user" 2>/dev/null \
            | grep -i "x-oauth-scopes:" | sed 's/x-oauth-scopes: *//i' | tr -d '\r')

        if [ -n "$SCOPES" ]; then
            write_info "Token scopes: $SCOPES"
            if ! echo "$SCOPES" | grep -q 'repo'; then
                write_warning "Token does not include 'repo' scope."
                write_info "For the kitchen pipeline you typically need at least 'public_repo' scope."
            fi
        fi

    elif [ "$HTTP_STATUS" = "401" ]; then
        write_security_alert \
            "Token is INVALID or REVOKED (HTTP 401)." \
            "Generate a new token at: https://github.com/settings/tokens"
        ISSUES=$((ISSUES + 1))

    elif [ "$HTTP_STATUS" = "403" ]; then
        write_warning "Token returned HTTP 403 -- possibly suspended or lacks API access."
        write_info "Check the token at: https://github.com/settings/tokens"
        ISSUES=$((ISSUES + 1))

    elif [ "$HTTP_STATUS" = "000" ]; then
        write_warning "Could not reach GitHub API -- check your internet connection."
        write_info "Skipping validity check."

    else
        write_warning "Unexpected HTTP status from GitHub API: $HTTP_STATUS"
    fi

    rm -f /tmp/skilldeck_gh_resp.json
fi

# ---------------------------------------------------------
# 6. Security scan -- check for exposed tokens in tracked files
# ---------------------------------------------------------
write_header "6. Security scan (exposed tokens in tracked files)"

if command -v git &>/dev/null; then
    cd "$PROJECT_ROOT"

    # Search tracked files for GitHub token patterns (exclude safe files)
    GREP_RESULTS=$(git grep -l -I -E \
        '(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}|ghs_[A-Za-z0-9]{20,})' \
        -- ':!.env.example' ':!scripts/win/check-git-token.ps1' ':!scripts/linux/check-git-token.sh' \
        2>/dev/null || true)

    if [ -n "$GREP_RESULTS" ]; then
        write_security_alert \
            "SECURITY WARNING: Token-like strings found in tracked files!" \
            "These may be committed to version control."
        write_error "Files containing possible tokens:"
        echo "$GREP_RESULTS" | while IFS= read -r file; do
            printf '    - %s\n' "$file"
        done
        echo ""
        write_error "ACTION REQUIRED:"
        write_info "  1. Remove the token from these files immediately."
        write_info "  2. Revoke the exposed token at: https://github.com/settings/tokens"
        write_info "  3. Generate a new token and store it in .env only."
        ISSUES=$((ISSUES + 1))
    else
        write_success "No token-like strings found in tracked files."
    fi

    # Check if .env is properly gitignored
    if [ "$ENV_FILE_EXISTS" = true ]; then
        if git check-ignore ".env" &>/dev/null; then
            write_success ".env is properly listed in .gitignore."
        else
            write_security_alert \
                "SECURITY WARNING: .env is NOT ignored by git!" \
                "Your token could be committed to version control."
            write_error "Add .env to your .gitignore immediately!"
            ISSUES=$((ISSUES + 1))
        fi
    fi
else
    write_warning "git not found -- skipping tracked-file security scan."
fi

# ---------------------------------------------------------
# Summary
# ---------------------------------------------------------
write_header "Summary"

if [ "$ISSUES" -le 0 ]; then
    echo ""
    printf '\033[32m  All checks passed! GITHUB_TOKEN is ready to use.\033[0m\n'
    final_token="${GITHUB_TOKEN:-}"
    if [ -n "$final_token" ]; then
        masked=$(mask_token "$final_token")
        printf '\033[32m  Active token: %s\033[0m\n' "$masked"
    fi
    echo ""
else
    echo ""
    printf '\033[33m  %d issue(s) found -- see details above.\033[0m\n' "$ISSUES"
    echo ""
fi

# Return success/failure for scripting
if [ "$ISSUES" -gt 0 ]; then
    exit 1
fi
