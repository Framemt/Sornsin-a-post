@echo off
title PostEase AI - Social Auto Poster
cd /d "%~dp0"

echo ========================================================
echo   Starting PostEase AI Server...
echo ========================================================
echo.

:: Check virtual environment
if not exist "venv" (
    echo [1/3] Creating virtual environment...
    python -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate

:: Check and install dependencies
echo [2/4] Checking requirements...
python -m pip install -q -r requirements.txt

:: Start Tunnel (Cloudflare) automatically in a separate window
echo [3/4] Starting Cloudflare Auto-Tunnel & LINE Webhook Sync...
start "PostEase AI - Tunnel Service" cmd /c run_tunnel.bat

:: Open browser automatically
echo [4/4] Opening browser at http://localhost:8000/login ...
start "" "http://localhost:8000/login"

echo.
echo ========================================================
echo   PostEase AI is running!
echo   - Local Web:    http://localhost:8000
echo   - Cloudflare Tunnel is auto-syncing with LINE Bot!
echo   (Keep this window open while using the app)
echo ========================================================
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
