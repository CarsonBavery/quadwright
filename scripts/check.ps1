# Run the same checks as CI. Usage: .\scripts\check.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$bin = Join-Path ".venv" "Scripts"
foreach ($cmd in @(
    @("ruff.exe", "check", "."),
    @("ruff.exe", "format", "--check", "."),
    @("pytest.exe"),
    @("quadwright.exe", "validate", "configs\campuses\example-university.yaml")
)) {
    $exe = Join-Path $bin $cmd[0]; $rest = @($cmd | Select-Object -Skip 1)
    & $exe @rest
    if ($LASTEXITCODE -ne 0) { throw "$($cmd -join ' ') failed" }
}
Write-Host "All checks passed." -ForegroundColor Green
