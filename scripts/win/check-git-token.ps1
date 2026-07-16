<#
.SYNOPSIS
    SkillDeck GitHub Token Diagnostic & Loader Script
.DESCRIPTION
    Checks for GITHUB_TOKEN across all sources (.env file, current session,
    persistent User-level env var) and reports status. Loads from .env into
    the current session if not already set.

    Checks performed:
    1. Does .env exist in the project root?
    2. Is GITHUB_TOKEN defined in .env?
    3. Is GITHUB_TOKEN set in the current PowerShell session?
    4. Is GITHUB_TOKEN set as a persistent User-level environment variable?
    5. Is the token still valid (not revoked)? -- calls GitHub API
    6. Is the token accidentally exposed in any tracked file?

    If the token is found in .env but not in the session, it is loaded
    automatically so downstream scripts (kitchen pipeline, dev-run, etc.)
    can use it immediately.
.EXAMPLE
    .\scripts\win\check-git-token.ps1
.EXAMPLE
    # Dot-source to export the token into your current session:
    . .\scripts\win\check-git-token.ps1
#>

# Ensure script halts on error
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------
if ($PSScriptRoot) {
    # Script is in scripts/win, so parent's parent is project root
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
} else {
    $CurrentDir = (Get-Location).Path
    if ($CurrentDir -match "scripts[\\/]win$" -or $CurrentDir -match "scripts[\\/]linux$") {
        $ProjectRoot = Split-Path -Parent (Split-Path -Parent $CurrentDir)
    } elseif ($CurrentDir.EndsWith("scripts", [System.StringComparison]::OrdinalIgnoreCase)) {
        $ProjectRoot = Split-Path -Parent $CurrentDir
    } else {
        $ProjectRoot = $CurrentDir
    }
}

# ---------------------------------------------------------
# Helper Functions (matching dev-*.ps1 style)
# ---------------------------------------------------------
function Write-Header($text) {
    Write-Host "`n--- $text ---" -ForegroundColor Yellow
}

function Write-WarningMsg($text) {
    Write-Host "[WARNING] $text" -ForegroundColor Yellow
}

function Write-Success($text) {
    Write-Host "[SUCCESS] $text" -ForegroundColor Green
}

function Write-ErrorMsg($text) {
    Write-Host "[ERROR] $text" -ForegroundColor Red
}

function Write-Info($text) {
    Write-Host "[INFO] $text" -ForegroundColor Cyan
}

function Write-SecurityAlert($lines) {
    Write-Host ""
    Write-Host ("  " + "=" * 62) -ForegroundColor Red
    foreach ($line in $lines) {
        Write-Host "  !! $line" -ForegroundColor Red
    }
    Write-Host ("  " + "=" * 62) -ForegroundColor Red
    Write-Host ""
}

# Mask a token for safe display: show first 4 and last 4 chars
function Get-MaskedToken($token) {
    if ($token.Length -le 10) {
        return "****"
    }
    $prefix = $token.Substring(0, 4)
    $suffix = $token.Substring($token.Length - 4)
    return "${prefix}...${suffix}"
}

# Build the token-detection regex via concatenation so PowerShell's parser
# never sees a bare {n,} quantifier in the source text.
function Get-TokenRegexPattern {
    $ghp  = 'ghp_[A-Za-z0-9]'         + '{20,}'
    $fpat = 'github_pat_[A-Za-z0-9_]' + '{20,}'
    $gho  = 'gho_[A-Za-z0-9]'         + '{20,}'
    $ghs  = 'ghs_[A-Za-z0-9]'         + '{20,}'
    return "$ghp|$fpat|$gho|$ghs"
}

# ---------------------------------------------------------
# State tracking
# ---------------------------------------------------------
$EnvFileExists  = $false
$EnvFileToken   = $null
$SessionToken   = $null
$PersistToken   = $null
$TokenLoaded    = $false
$IssuesFound    = 0

Write-Header "SkillDeck GitHub Token Diagnostic"

# ---------------------------------------------------------
# 1. Check .env file
# ---------------------------------------------------------
Write-Header "1. Checking .env file"

$EnvFilePath = Join-Path $ProjectRoot ".env"

if (Test-Path $EnvFilePath) {
    $EnvFileExists = $true
    Write-Success ".env file found at: $EnvFilePath"

    # Parse .env for GITHUB_TOKEN (handles KEY=VALUE, with optional quotes)
    $envContent = Get-Content $EnvFilePath -ErrorAction SilentlyContinue
    foreach ($line in $envContent) {
        $trimmed = $line.Trim()
        # Skip comments and blank lines
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }

        if ($trimmed -match '^\s*GITHUB_TOKEN\s*=\s*(.+)$') {
            $rawValue = $Matches[1].Trim()
            # Strip surrounding quotes (single or double)
            $rawValue = $rawValue -replace '^["'']|["'']$', ''
            if ($rawValue -ne "" -and $rawValue -ne "ghp_your_token_here") {
                $EnvFileToken = $rawValue
            }
        }
    }

    if ($EnvFileToken) {
        $masked = Get-MaskedToken $EnvFileToken
        Write-Success "GITHUB_TOKEN found in .env: $masked"
    } else {
        Write-WarningMsg "GITHUB_TOKEN not set in .env (missing, empty, or still the placeholder)."
        Write-Info "Edit .env and replace the placeholder with your real token."
        $IssuesFound++
    }
} else {
    Write-WarningMsg ".env file not found."
    Write-Info "Create one by copying the template:"
    Write-Info "  Copy-Item `"$ProjectRoot\.env.example`" `"$ProjectRoot\.env`""
    Write-Info "  Then edit .env and add your GITHUB_TOKEN."
    $IssuesFound++
}

# ---------------------------------------------------------
# 2. Check current PowerShell session
# ---------------------------------------------------------
Write-Header "2. Checking current session"

$SessionToken = $env:GITHUB_TOKEN

if ($SessionToken) {
    $masked = Get-MaskedToken $SessionToken
    Write-Success "GITHUB_TOKEN is set in this session: $masked"
} else {
    Write-WarningMsg "GITHUB_TOKEN is NOT set in the current session."
    $IssuesFound++
}

# ---------------------------------------------------------
# 3. Check persistent User-level environment variable
# ---------------------------------------------------------
Write-Header "3. Checking persistent User-level env var"

$PersistToken = [Environment]::GetEnvironmentVariable("GITHUB_TOKEN", "User")

if ($PersistToken) {
    $masked = Get-MaskedToken $PersistToken
    Write-Success "GITHUB_TOKEN is set at User level: $masked"
    Write-Info "(Available to all new terminals automatically.)"
} else {
    Write-Info "GITHUB_TOKEN is NOT set as a persistent User-level variable."
    Write-Info "This is fine if you prefer .env."
}

# ---------------------------------------------------------
# 4. Load token into session if needed
# ---------------------------------------------------------
Write-Header "4. Loading token into session"

if (-not $SessionToken) {
    if ($EnvFileToken) {
        $env:GITHUB_TOKEN = $EnvFileToken
        $TokenLoaded = $true
        $masked = Get-MaskedToken $EnvFileToken
        Write-Success "Loaded GITHUB_TOKEN from .env into session: $masked"
        $IssuesFound--  # Resolve the session issue since we just fixed it
        $SessionToken = $env:GITHUB_TOKEN
    } elseif ($PersistToken) {
        $env:GITHUB_TOKEN = $PersistToken
        $TokenLoaded = $true
        $masked = Get-MaskedToken $PersistToken
        Write-Success "Loaded GITHUB_TOKEN from User-level env var into session: $masked"
        $IssuesFound--
        $SessionToken = $env:GITHUB_TOKEN
    } else {
        Write-ErrorMsg "No GITHUB_TOKEN found in any source. The kitchen pipeline will be rate-limited."
        Write-Info "To fix this:"
        Write-Info "  1. Copy .env.example to .env and add your token, OR"
        Write-Info "  2. Set it persistently:"
        Write-Info '     [Environment]::SetEnvironmentVariable("GITHUB_TOKEN", "ghp_yourToken", "User")'
    }
} else {
    Write-Info "Session already has GITHUB_TOKEN -- no loading needed."
}

# ---------------------------------------------------------
# 5. Token validity check (GitHub API)
# ---------------------------------------------------------
Write-Header "5. Checking token validity (GitHub API)"

$ActiveToken = $env:GITHUB_TOKEN

if (-not $ActiveToken) {
    Write-WarningMsg "No token in session -- skipping validity check."
} else {
    Write-Info "Calling https://api.github.com/user to verify token..."
    try {
        $headers = @{
            "Authorization" = "Bearer $ActiveToken"
            "User-Agent"    = "SkillDeck-check-git-token/1.0"
            "Accept"        = "application/vnd.github+json"
            "X-GitHub-Api-Version" = "2022-11-28"
        }

        $response = Invoke-WebRequest -Uri "https://api.github.com/user" `
            -Headers $headers `
            -UseBasicParsing `
            -ErrorAction SilentlyContinue

        $statusCode = $response.StatusCode

        if ($statusCode -eq 200) {
            # Parse login from response body
            $body = $response.Content | ConvertFrom-Json
            $login = $body.login
            $scopes = $response.Headers["X-OAuth-Scopes"]
            Write-Success "Token is VALID. Authenticated as: $login"
            if ($scopes) {
                Write-Info "Token scopes: $scopes"
            }
            # Warn if scopes don't include 'repo' (needed for private repos)
            if ($scopes -and $scopes -notmatch 'repo') {
                Write-WarningMsg "Token does not include 'repo' scope."
                Write-Info "For the kitchen pipeline you typically need at least 'public_repo' scope."
            }
        } elseif ($statusCode -eq 401) {
            Write-SecurityAlert @(
                "Token is INVALID or REVOKED (HTTP 401).",
                "Generate a new token at: https://github.com/settings/tokens"
            )
            $IssuesFound++
        } elseif ($statusCode -eq 403) {
            Write-WarningMsg "Token returned HTTP 403 -- possibly suspended or lacks API access."
            Write-Info "Check the token at: https://github.com/settings/tokens"
            $IssuesFound++
        } else {
            Write-WarningMsg "Unexpected HTTP status: $statusCode"
        }
    } catch {
        # Invoke-WebRequest throws on 4xx/5xx if -ErrorAction is not SilentlyContinue
        $statusCode = $_.Exception.Response.StatusCode.Value__
        if ($statusCode -eq 401) {
            Write-SecurityAlert @(
                "Token is INVALID or REVOKED (HTTP 401).",
                "Generate a new token at: https://github.com/settings/tokens"
            )
            $IssuesFound++
        } elseif ($statusCode -eq 403) {
            Write-WarningMsg "Token returned HTTP 403 -- possibly suspended or lacks API access."
            $IssuesFound++
        } elseif ($_.Exception.Message -match "network|connect|resolve") {
            Write-WarningMsg "Could not reach GitHub API -- check your internet connection."
            Write-Info "Skipping validity check."
        } else {
            Write-WarningMsg "GitHub API check failed: $($_.Exception.Message)"
        }
    }
}

# ---------------------------------------------------------
# 6. Security scan -- check for exposed tokens in tracked files
# ---------------------------------------------------------
Write-Header "6. Security scan (exposed tokens in tracked files)"

# Check if git is available
$gitAvailable = $false
try {
    $null = git --version 2>$null
    $gitAvailable = $true
} catch { }

if ($gitAvailable) {
    Push-Location $ProjectRoot
    try {
        # Scan tracked files for token-like strings using Select-String.
        $trackedFiles = git ls-files 2>$null
        $excludeList = @('.env.example', 'scripts/win/check-git-token.ps1', 'scripts/linux/check-git-token.sh')
        $exposedFiles = @()
        $tokenPat = Get-TokenRegexPattern

        if ($trackedFiles) {
            foreach ($tf in $trackedFiles) {
                # Skip self and template files
                $skip = $false
                foreach ($excl in $excludeList) {
                    if ($tf -eq $excl) { $skip = $true; break }
                }
                if ($skip) { continue }

                $fullPath = Join-Path $ProjectRoot $tf
                if (Test-Path $fullPath -PathType Leaf) {
                    try {
                        $hit = Select-String -Path $fullPath -Pattern $tokenPat -Quiet -ErrorAction SilentlyContinue
                        if ($hit) { $exposedFiles += $tf }
                    } catch {
                        # Skip binary/unreadable files silently
                    }
                }
            }
        }

        if ($exposedFiles.Count -gt 0) {
            Write-SecurityAlert @(
                "SECURITY WARNING: Token-like strings found in tracked files!",
                "These may be committed to version control."
            )
            Write-ErrorMsg "Files containing possible tokens:"
            foreach ($file in $exposedFiles) {
                Write-Host "    - $file" -ForegroundColor Red
            }
            Write-Host ""
            Write-ErrorMsg "ACTION REQUIRED:"
            Write-Info "  1. Remove the token from these files immediately."
            Write-Info "  2. Revoke the exposed token at: https://github.com/settings/tokens"
            Write-Info "  3. Generate a new token and store it in .env only."
            $IssuesFound++
        } else {
            Write-Success "No token-like strings found in tracked files."
        }

        # Check if .env is properly gitignored
        if ($EnvFileExists) {
            $ignored = git check-ignore ".env" 2>$null
            if ($ignored) {
                Write-Success ".env is properly listed in .gitignore."
            } else {
                Write-SecurityAlert @(
                    "SECURITY WARNING: .env is NOT ignored by git!",
                    "Your token could be committed to version control."
                )
                Write-ErrorMsg "Add .env to your .gitignore immediately!"
                $IssuesFound++
            }
        }
    } finally {
        Pop-Location
    }
} else {
    Write-WarningMsg "git not found -- skipping tracked-file security scan."
}

# ---------------------------------------------------------
# Summary
# ---------------------------------------------------------
Write-Header "Summary"

if ($IssuesFound -le 0) {
    Write-Host ""
    Write-Host "  All checks passed! GITHUB_TOKEN is ready to use." -ForegroundColor Green
    $finalToken = $env:GITHUB_TOKEN
    if ($finalToken) {
        $masked = Get-MaskedToken $finalToken
        Write-Host "  Active token: $masked" -ForegroundColor Green
    }
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "  $IssuesFound issue(s) found -- see details above." -ForegroundColor Yellow
    Write-Host ""
}

# Return success/failure for scripting
if ($IssuesFound -gt 0) {
    exit 1
}
