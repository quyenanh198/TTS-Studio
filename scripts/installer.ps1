# Compile the Windows installer with Inno Setup 6 (run scripts\build.ps1 first).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$candidates = @(
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $cmd = Get-Command iscc -ErrorAction SilentlyContinue; if ($cmd) { $iscc = $cmd.Source } }
if (-not $iscc) { throw "Inno Setup 6 not found. Install: winget install JRSoftware.InnoSetup" }
if (-not (Test-Path (Join-Path $Root "dist\TTSStudio\launcher.py"))) { throw "dist\TTSStudio missing - run scripts\build.ps1 first" }
& $iscc (Join-Path $Root "installer\TTSStudio.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
Get-ChildItem (Join-Path $Root "dist") -Filter "TTSStudio-Setup-*.exe" | ForEach-Object { Write-Host ("==> {0}  ({1:N1} MB)" -f $_.FullName, ($_.Length / 1MB)) -ForegroundColor Green }
