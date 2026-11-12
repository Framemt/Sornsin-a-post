@echo off
title Stop PostEase AI
cd /d "%~dp0"

echo ========================================================
echo   Stopping PostEase AI and Cloudflare Tunnel...
echo ========================================================
echo.

:: ปิด Cloudflare Tunnel หรือ ngrok
taskkill /F /IM cloudflared.exe >nul 2>&1
taskkill /F /IM ngrok.exe >nul 2>&1
if %errorlevel% == 0 (
    echo [+] Tunnel service stopped.
) else (
    echo [-] Tunnel was not running.
)

:: ปิด Python ที่รัน Uvicorn / PostEase AI
taskkill /F /IM python.exe >nul 2>&1
if %errorlevel% == 0 (
    echo [+] Python web server stopped.
) else (
    echo [-] Python server was not running.
)

echo.
echo ========================================================
echo   All systems stopped successfully!
echo ========================================================
timeout /t 3 >nul
exit
