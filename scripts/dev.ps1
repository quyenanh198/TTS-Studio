# Dev: backend on :8765 (auto-reload) + Vite on :5173. Open http://localhost:5173
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
Start-Process -NoNewWindow -FilePath $Py -ArgumentList "-m","uvicorn","app.main:app","--reload","--port","8765","--app-dir","backend" -WorkingDirectory $Root
Push-Location (Join-Path $Root "frontend"); npm run dev; Pop-Location
