# Run in PowerShell from the project root (or double-click after allowing scripts).
# Requires Python 3.9+ on PATH.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "==> Installing editable package + PyInstaller..." -ForegroundColor Cyan
python -m pip install -U pip
pip install -e ".[dev]"

Write-Host "==> Cleaning previous build..." -ForegroundColor Cyan
Remove-Item -Recurse -Force "build\envelope-studio", "dist\EnvelopeStudio" -ErrorAction SilentlyContinue

Write-Host "==> Running PyInstaller..." -ForegroundColor Cyan
pyinstaller -y envelope-studio.spec

Write-Host ""
Write-Host "==> Done. Run the app with:" -ForegroundColor Green
Write-Host "    dist\EnvelopeStudio\EnvelopeStudio.exe"
Write-Host ""
