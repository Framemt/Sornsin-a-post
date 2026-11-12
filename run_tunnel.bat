@echo off
title Tunnel Service (ngrok / Cloudflare) - PostEase AI
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe app\auto_tunnel.py
) else (
    python app\auto_tunnel.py
)
pause
