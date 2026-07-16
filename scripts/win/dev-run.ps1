<#
.SYNOPSIS
    SkillDeck Development Environment Launch Script
.DESCRIPTION
    This script verifies the development environment status and starts the
    Astro development server for the frontend site.
    It:
    1. Verifies that prerequisites are met and dependencies are installed.
    2. Ensures data/kb.json is present (generating it if missing).
    3. Runs the Astro dev server.
    4. Displays access URLs and helpful pipeline usage commands.
.EXAMPLE
    .\scripts\win\dev-run.ps1
#>

# Ensure script halts on error
$ErrorActionPreference = "Stop"

# Since this script resides in the /scripts subdirectory, the project root is the parent directory
if ($PSScriptRoot) {
    # Script is in scripts/win, so parent's parent is project root
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
} else {
    # Fallback if PSScriptRoot is not set (e.g., interactive copy-paste)
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
# Helper Functions
# ---------------------------------------------------------
function Write-Header($text) {
    Write-Host "`n--- $text ---" -ForegroundColor Yellow
}

function Write-Step($text) {
    Write-Host "[*] $text" -ForegroundColor White
}

function Write-WarningMsg($text) {
    Write-Host "[WARNING] $text" -ForegroundColor Yellow
}

function Write-Success($text) {
    Write-Host "[SUCCESS] $text" -ForegroundColor Green
}

# Verifies that Node.js/npm works and recovers if using a non-functional version (e.g., restricted NVM install)
function Ensure-WorkingNode {
    Write-Step "Verifying Node.js and npm functionality..."
    
    $TestNode = {
        try {
            $version = & node -v 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -like "v*") {
                $npmVer = & npm -v 2>$null
                if ($LASTEXITCODE -eq 0) {
                    return $true
                }
            }
        } catch {}
        return $false
    }

    # 1. Test current PATH node/npm
    if (Get-Command "node" -ErrorAction SilentlyContinue) {
        if (& $TestNode) {
            Write-Step "Default Node.js installation is functional."
            return
        }
        Write-WarningMsg "Default Node.js in PATH is non-functional (possibly NVM/EPERM issue)."
    } else {
        Write-Step "Node.js not found in default PATH."
    }

    # 2. Search alternatives
    Write-Step "Searching for alternative working Node.js installations..."
    $candidateDirs = @()
    
    # Check FNM in AppData
    $fnmVersionsPath = Join-Path $env:APPDATA "fnm\node-versions"
    if (Test-Path $fnmVersionsPath) {
        $fnmDirs = Get-ChildItem -Path $fnmVersionsPath -Directory -ErrorAction SilentlyContinue | 
            Sort-Object Name -Descending | 
            ForEach-Object { Join-Path $_.FullName "installation" }
        foreach ($d in $fnmDirs) {
            if (Test-Path $d) { $candidateDirs += $d }
        }
    }
    
    # Check System Node
    $systemNode = "C:\Program Files\nodejs"
    if (Test-Path $systemNode) {
        $candidateDirs += $systemNode
    }
    
    # Test each candidate
    $foundWorking = $false
    foreach ($dir in $candidateDirs) {
        $oldPath = $env:PATH
        $env:PATH = "$dir;" + $env:PATH
        
        if (& $TestNode) {
            Write-Success "Found working Node.js/npm at: $dir"
            $foundWorking = $true
            break
        } else {
            # Restore PATH if not working
            $env:PATH = $oldPath
        }
    }
    
    if (-not $foundWorking) {
        Write-Error "No functional Node.js/npm installation found. Please ensure Node.js is installed and accessible."
        exit 1
    }
}

# ---------------------------------------------------------
# 1. Quick Verification Checks
# ---------------------------------------------------------
Write-Header "Verifying Development Environment"

# Python check
$VenvDir = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvDir) -or -not (Test-Path $PythonExe)) {
    Write-Host "Error: Virtual environment not found or incomplete. Please run .\scripts\win\dev-setup.ps1 first." -ForegroundColor Red
    exit 1
}
Write-Step "Isolated virtual environment verified."

# Node.js & npm checks
Ensure-WorkingNode

# Node modules check
$SiteDir = Join-Path $ProjectRoot "site"
$NodeModulesDir = Join-Path $SiteDir "node_modules"
if (-not (Test-Path $NodeModulesDir)) {
    Write-WarningMsg "site/node_modules not found. Running npm install..."
    Push-Location $SiteDir
    try {
        & npm install
    } finally {
        Pop-Location
    }
}
Write-Step "Frontend dependencies verified."

# Knowledge Base data check
$KbJsonFile = Join-Path $ProjectRoot "data\kb.json"
if (-not (Test-Path $KbJsonFile)) {
    Write-WarningMsg "data/kb.json is missing. Generating default/initial knowledge base..."
    Push-Location $ProjectRoot
    try {
        $env:PYTHONPATH = $ProjectRoot
        & $PythonExe -m kitchen emit
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Failed to auto-generate kb.json. Please run .\scripts\win\dev-setup.ps1" -ForegroundColor Red
            exit 1
        }
    } finally {
        $env:PYTHONPATH = $null
        Pop-Location
    }
}
Write-Step "Knowledge base data verified."

# Check for GitHub token (optional for dev server, required for the kitchen's ingest/canonicalize/freshness stages)
$GithubToken = $env:GITHUB_TOKEN
if (-not $GithubToken) {
    Write-WarningMsg "GITHUB_TOKEN environment variable is not set."
    Write-Host "          This is OK for running the local Astro website." -ForegroundColor Gray
    Write-Host "          However, to run the offline pipeline ingest/canonicalize stages, you will need to set it." -ForegroundColor Gray
    Write-Host "          Example: `$env:GITHUB_TOKEN='your-token'" -ForegroundColor Gray
    Write-Host "          Capability clustering and card writing are done by the /skilldeck-ingest Claude Code command, not an API key." -ForegroundColor Gray
}

# ---------------------------------------------------------
# 2. Starting Dev Server
# ---------------------------------------------------------
Write-Header "Starting SkillDeck Development Server"

Write-Host "Access URLs:" -ForegroundColor Cyan
Write-Host "  - Local Website:      http://localhost:4321/" -ForegroundColor Green
Write-Host "  - Static Files View:  file:///$SiteDir/dist/index.html (after building)" -ForegroundColor Green
Write-Host "`nPipeline Helper Commands (run in virtual environment):" -ForegroundColor Cyan
Write-Host "  - Run scriptable stages (ingest/canonicalize/dedup/rank): python -m kitchen pipeline" -ForegroundColor Gray
Write-Host "  - Full ingest incl. capability clustering + cards: run the /skilldeck-ingest command in Claude Code" -ForegroundColor Gray
Write-Host "  - Generate static data/kb.json: python -m kitchen emit" -ForegroundColor Gray
Write-Host "  - Run pipeline unit tests:    python -m unittest discover -s kitchen/tests" -ForegroundColor Gray
Write-Host "`nPress Ctrl+C to terminate the development server.`n" -ForegroundColor Yellow

# Navigate to site and run dev server
Push-Location $SiteDir
try {
    & npm run dev
} catch {
    Write-Host "Dev server stopped: $_" -ForegroundColor Cyan
} finally {
    Pop-Location
}
