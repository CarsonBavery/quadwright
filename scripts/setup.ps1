# Quadwright setup for Windows PowerShell.
# Usage: .\scripts\setup.ps1 [-Ml]
param([switch]$Ml)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$extras = if ($Ml) { "dev,ml" } else { "dev" }

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!! $msg" -ForegroundColor Yellow }
function Run($exe, [string[]]$argList) {
    & $exe @argList
    if ($LASTEXITCODE -ne 0) { throw "$exe $($argList -join ' ') failed (exit $LASTEXITCODE)" }
}

Step "Finding Python 3.11+"
$py = $null
foreach ($line in @("py -3.12", "py -3.11", "py -3", "python")) {
    $candidate = $line -split " "
    $exe = $candidate[0]; $pre = @($candidate | Select-Object -Skip 1)
    if (Get-Command $exe -ErrorAction SilentlyContinue) {
        & $exe @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $candidate; break }
    }
}
if (-not $py) { throw "Python 3.11 or newer is required: https://www.python.org/downloads/" }
$pyExe = $py[0]; $pyPre = @($py | Select-Object -Skip 1)
& $pyExe @pyPre --version

Step "Creating virtual environment (.venv)"
if (-not (Test-Path ".venv")) { Run $pyExe ($pyPre + @("-m", "venv", ".venv")) }
$venvPy = Join-Path ".venv" "Scripts\python.exe"
$bin = Join-Path ".venv" "Scripts"
Run $venvPy @("-m", "pip", "install", "--upgrade", "pip", "--quiet")

Step "Installing Quadwright [$extras] (first run can take a few minutes)"
Run $venvPy @("-m", "pip", "install", "-e", ".[$extras]")

Step "Creating local data folders"
New-Item -ItemType Directory -Force -Path "data\raw", "data\interim", "outputs" | Out-Null

Step "Setting up git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Warn "git not found; install it from https://git-scm.com and re-run."
} else {
    if (-not (Test-Path ".git")) { Run "git" @("init", "-b", "main") }
    Run (Join-Path $bin "pre-commit.exe") @("install")
}

Step "Checking: lint, tests, example config"
Run (Join-Path $bin "ruff.exe") @("check", ".")
& (Join-Path $bin "ruff.exe") format --check .
if ($LASTEXITCODE -ne 0) { Warn "Formatting differs; run: ruff format ." }
Run (Join-Path $bin "pytest.exe") @()
Run (Join-Path $bin "quadwright.exe") @("validate", "configs\campuses\example-university.yaml")

Step "Optional tools"
if (Get-Command npx -ErrorAction SilentlyContinue) {
    Write-Host "Node.js found. Measure token usage any time with: npx ccusage@latest daily"
} else {
    Warn "Node.js not found. Install it later for ccusage, Ponytail, and Context7: https://nodejs.org"
}

Write-Host @"

Setup complete.
Next:
  1. Activate the environment in new terminals:  .\.venv\Scripts\Activate.ps1
  2. Make your first commit and push (docs\SETUP.md, step 2)
  3. Install the Claude Code plugins (docs\SETUP.md, step 3)
"@ -ForegroundColor Green
