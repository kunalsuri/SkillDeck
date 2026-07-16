<#
.SYNOPSIS
    SkillDeck Development Environment Testing Script
.DESCRIPTION
    This script runs all test suites in the repository:
    1. Python pipeline unit tests (via pytest)
    2. Frontend component unit tests (via Vitest)
    3. Frontend E2E browser tests (via Playwright)
.EXAMPLE
    .\scripts\win\dev-test.ps1
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
Write-Host "             SkillDeck Test Suite Runner" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot" -ForegroundColor Gray

# Helper functions
function Write-Header($text) {
    Write-Host "`n--- $text ---" -ForegroundColor Yellow
}

function Write-Step($text) {
    Write-Host "[*] $text" -ForegroundColor White
}

function Write-Success($text) {
    Write-Host "[SUCCESS] $text" -ForegroundColor Green
}

function Write-WarningMsg($text) {
    Write-Host "[WARNING] $text" -ForegroundColor Yellow
}

# Verifies that Node.js/npm works and recovers if using a non-functional version
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

# 1. Environment Check
Write-Header "Checking Testing Environment"

$VenvDir = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvDir) -or -not (Test-Path $PythonExe)) {
    Write-Error "Virtual environment not found. Please run .\scripts\win\dev-setup.ps1 first."
    exit 1
}
Write-Step "Python virtual environment verified."

Ensure-WorkingNode

$SiteDir = Join-Path $ProjectRoot "site"
$NodeModulesDir = Join-Path $SiteDir "node_modules"
if (-not (Test-Path $NodeModulesDir)) {
    Write-Error "site/node_modules not found. Please run .\scripts\win\dev-setup.ps1 first."
    exit 1
}
Write-Step "Node.js dependencies verified."

# Initialize tracking variables
$PythonPassed = $false
$FrontendUnitPassed = $false
$FrontendE2EPassed = $false

# 2. Run Python tests
Write-Header "Running Python Pipeline Tests"
Push-Location $ProjectRoot
try {
    $env:PYTHONPATH = $ProjectRoot
    & $PythonExe -m pytest kitchen/tests/
    if ($LASTEXITCODE -eq 0) {
        $PythonPassed = $true
        Write-Success "Python pipeline tests passed."
    } else {
        Write-WarningMsg "Python pipeline tests failed."
    }
} catch {
    Write-WarningMsg "Failed to execute Python tests: $_"
} finally {
    $env:PYTHONPATH = $null
    Pop-Location
}

# 3. Run Frontend unit tests
Write-Header "Running Frontend Unit Tests"
Push-Location $SiteDir
try {
    & npm run test
    if ($LASTEXITCODE -eq 0) {
        $FrontendUnitPassed = $true
        Write-Success "Frontend unit tests passed."
    } else {
        Write-WarningMsg "Frontend unit tests failed."
    }
} catch {
    Write-WarningMsg "Failed to execute Frontend unit tests: $_"
} finally {
    Pop-Location
}

# 4. Run Frontend E2E tests
Write-Header "Running Frontend E2E Tests"
Write-Step "Building frontend before running E2E tests..."
Push-Location $SiteDir
try {
    & npm run build
    if ($LASTEXITCODE -eq 0) {
        & npm run test:e2e
        if ($LASTEXITCODE -eq 0) {
            $FrontendE2EPassed = $true
            Write-Success "Frontend E2E tests passed."
        } else {
            Write-WarningMsg "Frontend E2E tests failed."
        }
    } else {
        Write-WarningMsg "Frontend build failed; skipping E2E tests."
    }
} catch {
    Write-WarningMsg "Failed to execute Frontend E2E tests: $_"
} finally {
    Pop-Location
}

# 5. Summary
Write-Header "Test Execution Summary"

Write-Host "Python Pipeline Unit Tests:      " -NoNewline
if ($PythonPassed) { Write-Host "PASSED" -ForegroundColor Green } else { Write-Host "FAILED" -ForegroundColor Red }

Write-Host "Frontend Component Unit Tests:  " -NoNewline
if ($FrontendUnitPassed) { Write-Host "PASSED" -ForegroundColor Green } else { Write-Host "FAILED" -ForegroundColor Red }

Write-Host "Frontend E2E Browser Tests:     " -NoNewline
if ($FrontendE2EPassed) { Write-Host "PASSED" -ForegroundColor Green } else { Write-Host "FAILED" -ForegroundColor Red }

Write-Host "`n==========================================================" -ForegroundColor Cyan

if ($PythonPassed -and $FrontendUnitPassed -and $FrontendE2EPassed) {
    Write-Host "  All test suites completed successfully!" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    exit 0
} else {
    Write-Host "  Some test suites failed. Review the logs above." -ForegroundColor Red
    Write-Host "==========================================================" -ForegroundColor Red
    exit 1
}
