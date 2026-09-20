param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

& $Python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --collect-binaries glfw `
    --name DotEBLPreview --paths src gui_entry.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Output "Built $PSScriptRoot\dist\DotEBLPreview.exe"
