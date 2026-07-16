<#
.SYNOPSIS
    SkillDeck Development Environment Setup and Validation Script
.DESCRIPTION
    This script performs a complete, idempotent development setup:
    1. Checks prerequisites (PowerShell, Python, Node.js, npm).
    2. Verifies or creates the isolated Python virtual environment (.venv).
    3. Upgrades pip and installs Python dependencies from requirements.txt.
    4. Installs Node.js dependencies in the site directory.
    5. Generates the initial data/kb.json artifact if missing.
    6. Validates the Python codebase via unit tests.
    7. Validates the Astro frontend codebase via a production build test.
.EXAMPLE
    .\scripts\win\dev-setup.ps1
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

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "        SkillDeck Development Setup & Validation" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot" -ForegroundColor Gray

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
function Write-Header($text) {
    Write-Host "`n--- $text ---" -ForegroundColor Yellow
}

function Write-Success($text) {
    Write-Host "[SUCCESS] $text" -ForegroundColor Green
}

function Write-Step($text) {
    Write-Host "[*] $text" -ForegroundColor White
}

function Write-WarningMsg($text) {
    Write-Host "[WARNING] $text" -ForegroundColor Yellow
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
# 1. Prerequisite Checks
# ---------------------------------------------------------
Write-Header "Checking Prerequisites"

# PowerShell Version Check
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Error "PowerShell 5.1 or higher is required. Current version: $($PSVersionTable.PSVersion.Major)"
    exit 1
}
Write-Step "PowerShell version: $($PSVersionTable.PSVersion)"

# Python Check
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not installed or not in system PATH."
    exit 1
}

$pythonVersionString = & python --version 2>&1
Write-Step "System Python: $pythonVersionString"
if ($pythonVersionString -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        Write-Error "Python version 3.11+ is required. Found: $pythonVersionString"
        exit 1
    }
} else {
    Write-Error "Could not parse Python version."
    exit 1
}

# Ensure Node is working and set working PATH
Ensure-WorkingNode

$nodeVersion = & node -v
Write-Step "Node.js version: $nodeVersion"

$npmVersion = & npm -v
Write-Step "npm version: $npmVersion"

Write-Success "Prerequisites check passed."

# ---------------------------------------------------------
# 2. Python Virtual Environment (.venv) Setup
# ---------------------------------------------------------
Write-Header "Setting up Python Virtual Environment"

$VenvDir = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $VenvDir)) {
    Write-Step "Creating isolated virtual environment in .venv..."
    & python -m venv $VenvDir
    Write-Success "Virtual environment created."
} else {
    Write-Step "Isolated virtual environment (.venv) already exists."
}

# Upgrade pip
Write-Step "Upgrading pip..."
& $PythonExe -m pip install --upgrade pip --quiet --use-deprecated=legacy-certs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to upgrade pip inside virtual environment."
    exit 1
}

# Install requirements.txt
$ReqsFile = Join-Path $ProjectRoot "requirements.txt"
if (-not (Test-Path $ReqsFile)) {
    Write-Error "requirements.txt not found at $ReqsFile."
    exit 1
}

Write-Step "Installing Python dependencies from requirements.txt..."
& $PipExe install -r $ReqsFile --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install Python dependencies."
    exit 1
}
Write-Step "Installing pytest for development tests..."
$oldErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $PipExe install pytest --disable-pip-version-check --quiet
if ($LASTEXITCODE -ne 0) {
    Write-WarningMsg "Failed to install pytest inside virtual environment."
}
$ErrorActionPreference = $oldErrorAction
Write-Success "Python environment setup complete."

# ---------------------------------------------------------
# 3. Node.js dependencies Setup
# ---------------------------------------------------------
Write-Header "Setting up Frontend Dependencies"

$SiteDir = Join-Path $ProjectRoot "site"
if (-not (Test-Path $SiteDir)) {
    Write-Error "site directory not found at $SiteDir"
    exit 1
}

Write-Step "Navigating to $SiteDir and running npm install..."
Push-Location $SiteDir
try {
    & npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Error "npm install failed in $SiteDir"
        exit 1
    }
} finally {
    Pop-Location
}
Write-Success "Frontend dependencies setup complete."

# ---------------------------------------------------------
# 4. Generate Missing Development Artifacts (kb.json)
# ---------------------------------------------------------
Write-Header "Validating and Generating Development Artifacts"

$KbJsonFile = Join-Path $ProjectRoot "data\kb.json"
if (-not (Test-Path $KbJsonFile)) {
    Write-Step "data/kb.json not found. Generating initial knowledge base via Python kitchen..."
    
    # Run the emit pipeline command to generate kb.json
    Push-Location $ProjectRoot
    try {
        $env:PYTHONPATH = $ProjectRoot
        & $PythonExe -m kitchen emit
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to generate kb.json using python -m kitchen emit"
            exit 1
        }
    } finally {
        $env:PYTHONPATH = $null
        Pop-Location
    }
    Write-Success "Initial data/kb.json successfully generated."
} else {
    Write-Step "data/kb.json already exists."
}

# ---------------------------------------------------------
# 5. Validation and Testing
# ---------------------------------------------------------
Write-Header "Validating Pipeline and Frontend Toolchains"

# Run Python kitchen unit tests
Write-Step "Running Python pipeline unit tests..."
Push-Location $ProjectRoot
try {
    $env:PYTHONPATH = $ProjectRoot
    $oldErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $PythonExe -c "import pytest" 2>$null
    $hasPytest = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $oldErrorAction

    if ($hasPytest) {
        & $PythonExe -m pytest kitchen/tests/
    } else {
        Write-WarningMsg "pytest not found. Falling back to standard unittest discovery..."
        & $PythonExe -m unittest discover -s kitchen/tests
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Python unit tests failed."
        exit 1
    }
} finally {
    $env:PYTHONPATH = $null
    Pop-Location
}
Write-Success "Python pipeline tests passed."

# Run Frontend component unit tests
Write-Step "Running Frontend component unit tests..."
Push-Location $SiteDir
try {
    & npm run test
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend component unit tests failed."
        exit 1
    }
} finally {
    Pop-Location
}
Write-Success "Frontend component unit tests passed."

# Run Frontend build test
Write-Step "Validating frontend build toolchain..."
Push-Location $SiteDir
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend build validation failed."
        exit 1
    }
} finally {
    Pop-Location
}
Write-Success "Frontend build validation succeeded."

# Run Frontend E2E browser tests
Write-Step "Running Frontend E2E browser tests..."
Push-Location $SiteDir
try {
    & npm run test:e2e
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend E2E browser tests failed."
        exit 1
    }
} finally {
    Pop-Location
}
Write-Success "Frontend E2E browser tests passed."

# 6. GITHUB_TOKEN Diagnostic Check (Non-Blocking)
Write-Header "Running GitHub Token Diagnostic"
try {
    $TokenScript = Join-Path $PSScriptRoot "check-git-token.ps1"
    if (Test-Path $TokenScript) {
        # Run token script using call operator.
        # Temporarily set ErrorActionPreference so that we catch non-terminating errors,
        # but don't halt dev-setup script on token verification issues.
        $oldErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $TokenScript
        $ErrorActionPreference = $oldErrorAction
        # Reset exit code to ensure dev-setup remains successful
        $global:LASTEXITCODE = 0
    } else {
        Write-WarningMsg "check-git-token.ps1 not found at $TokenScript"
    }
} catch {
    Write-WarningMsg "GitHub Token diagnostic failed to run: $($_.Exception.Message)"
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  SkillDeck Setup and Validation Completed Successfully!" -ForegroundColor Green
Write-Host "  You can now run the app using .\scripts\win\dev-run.ps1" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
