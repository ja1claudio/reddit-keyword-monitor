$ErrorActionPreference = "Stop"

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

& $python -m pip install --upgrade pyinstaller
& $python -m PyInstaller --noconfirm --clean --windowed --name "RedditKeywordMonitor" --collect-all praw web_app.py

Write-Host "Build complete: dist\RedditKeywordMonitor\RedditKeywordMonitor.exe"
