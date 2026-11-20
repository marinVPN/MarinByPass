# Build MarinByPass.exe (single file with engines inside)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$root = $PSScriptRoot

python -m PyInstaller `
    --noconfirm --clean --onefile --windowed --uac-admin `
    --name MarinByPass `
    --icon "$root\assets\icon.ico" `
    --version-file "$root\version_info.txt" `
    --exclude-module numpy `
    --add-data "$root\assets;assets" `
    --add-data "$root\engine;engine" `
    --add-data "$root\licences;licences" `
    --distpath "$root\dist" `
    --workpath "$root\build" `
    --specpath "$root\build" `
    "$root\app\main.py"

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with code $LASTEXITCODE" }
Write-Host ""
Write-Host "Built: dist\MarinByPass.exe" -ForegroundColor Green
