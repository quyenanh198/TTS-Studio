<#
.SYNOPSIS
  Build a portable Windows folder: dist\TTSStudio\ (embedded Python + deps + built UI).
  Requires: node/npm, and either `uv` on PATH or `python -m uv` (pip install uv).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\build.ps1
  powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -WithASRGpu   # also bundle CUDA libs for whisper
#>
param(
  [string]$PythonVersion = "3.12",
  [switch]$WithASRGpu,
  [switch]$SkipFrontend
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist\TTSStudio"
$BuildDir = Join-Path $Root "build"

function Invoke-Uv {
  if (Get-Command uv -ErrorAction SilentlyContinue) { & uv @args }
  else { & python -m uv @args }
  if ($LASTEXITCODE -ne 0) { throw "uv failed: $args" }
}

Write-Host "==> Clean dist" -ForegroundColor Cyan
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
New-Item -ItemType Directory -Force $Dist | Out-Null
New-Item -ItemType Directory -Force $BuildDir | Out-Null

if (-not $SkipFrontend) {
  Write-Host "==> Build frontend" -ForegroundColor Cyan
  Push-Location (Join-Path $Root "frontend")
  if (-not (Test-Path node_modules)) { npm ci }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
  Pop-Location
}

Write-Host "==> Fetch embedded Python $PythonVersion (python-build-standalone via uv)" -ForegroundColor Cyan
$PyRoot = Join-Path $BuildDir "python"
Invoke-Uv python install $PythonVersion --install-dir $PyRoot
$PyDir = Get-ChildItem $PyRoot -Directory | Where-Object { $_.Name -like "cpython-$PythonVersion*windows*" } | Select-Object -First 1
if (-not $PyDir) { throw "embedded python not found under $PyRoot" }
Copy-Item -Recurse -Force $PyDir.FullName (Join-Path $Dist "python")
$Py = Join-Path $Dist "python\python.exe"
# uv's python-build-standalone marks itself externally-managed (PEP 668); the bundled copy is ours to manage.
Get-ChildItem (Join-Path $Dist "python") -Recurse -Filter "EXTERNALLY-MANAGED" | Remove-Item -Force

Write-Host "==> Install Python deps into embedded interpreter" -ForegroundColor Cyan
& $Py -m ensurepip --upgrade | Out-Null
& $Py -m pip install --no-cache-dir --upgrade pip | Out-Null
& $Py -m pip install --no-cache-dir -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
if ($WithASRGpu) {
  & $Py -m pip install --no-cache-dir nvidia-cublas-cu12 nvidia-cudnn-cu12
}

Write-Host "==> Copy app files" -ForegroundColor Cyan
Copy-Item -Recurse -Force (Join-Path $Root "backend") (Join-Path $Dist "backend")
Get-ChildItem (Join-Path $Dist "backend") -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force (Join-Path $Dist "backend\tests") -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Join-Path $Dist "frontend") | Out-Null
Copy-Item -Recurse -Force (Join-Path $Root "frontend\dist") (Join-Path $Dist "frontend\dist")
Copy-Item -Force (Join-Path $Root "launcher.py") $Dist
Copy-Item -Force (Join-Path $Root "scripts\run.bat") (Join-Path $Dist "TTS Studio.bat")
Copy-Item -Force (Join-Path $Root "scripts\run-silent.vbs") (Join-Path $Dist "TTS Studio (no console).vbs")
Copy-Item -Force (Join-Path $Root "README.md") $Dist

$size = (Get-ChildItem $Dist -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("==> Done: {0}  ({1:N0} MB)" -f $Dist, $size) -ForegroundColor Green
Write-Host "Run: `"$Dist\TTS Studio.bat`"  |  Installer: iscc installer\TTSStudio.iss"
