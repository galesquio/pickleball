# Build standalone Pickleball.exe (requires .venv with dev dependencies)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

& .\.venv\Scripts\pip install -r requirements-dev.txt
& .\.venv\Scripts\pyinstaller pickleball.spec --noconfirm

Write-Host ""
Write-Host "Built: dist\Pickleball.exe"
Write-Host "SQLite DB is created next to the exe on first run."
