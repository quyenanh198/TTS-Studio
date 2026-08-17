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
# WebView2 Evergreen bootstrapper (Microsoft permanent link). Bundled so Setup can install the runtime when missing.
$redist = Join-Path $Root "installer\redist"
New-Item -ItemType Directory -Force $redist | Out-Null
$wv2 = Join-Path $redist "MicrosoftEdgeWebview2Setup.exe"
if (-not (Test-Path $wv2)) {
  Write-Host "==> Downloading WebView2 bootstrapper" -ForegroundColor Cyan
  Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $wv2
}
$sig = Get-AuthenticodeSignature $wv2
if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notlike "CN=Microsoft Corporation*") { throw "WebView2 bootstrapper signature invalid: $($sig.Status)" }
# Single source of truth for the version: pyproject.toml. Old installers are removed so only one exists.
$ver = (Select-String -Path (Join-Path $Root "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $ver) { throw "version not found in pyproject.toml" }
Get-ChildItem (Join-Path $Root "dist") -Filter "TTSStudio-Setup-*.exe" -ErrorAction SilentlyContinue | Remove-Item -Force
Write-Host "==> Building installer v$ver" -ForegroundColor Cyan
& $iscc "/DAppVersion=$ver" (Join-Path $Root "installer\TTSStudio.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
Get-ChildItem (Join-Path $Root "dist") -Filter "TTSStudio-Setup-*.exe" | ForEach-Object { Write-Host ("==> {0}  ({1:N1} MB)" -f $_.FullName, ($_.Length / 1MB)) -ForegroundColor Green }
