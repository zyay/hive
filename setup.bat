@echo off
REM Hive Setup Script for Windows
REM Installs dependencies and checks Tailscale

echo === Hive Setup ===
echo.

REM Python venv
echo [1/3] Setting up Python environment...
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt
pip install -e .
echo   Python OK
echo.

REM Check Tailscale
echo [2/3] Checking Tailscale...
where tailscale >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   Tailscale already installed
    for /f "tokens=*" %%i in ('tailscale ip -4 2^>nul') do set TAILSCALE_IP=%%i
) else (
    echo   Tailscale not found.
    echo   Install: winget install Tailscale.Tailscale
    echo   Or download: https://tailscale.com/download/windows
    set TAILSCALE_IP=not-installed
)
echo.

REM Initialize DB
echo [3/3] Initializing database...
venv\Scripts\python.exe -c "from hive.core.db import init_db; init_db()" 2>nul
echo   Database OK
echo.

echo === Setup Complete ===
echo.
echo Start Hive:
echo   venv\Scripts\python.exe main.py
echo.
echo Access Hive:
echo   Local:     http://127.0.0.1:8000
if defined TAILSCALE_IP if not "%TAILSCALE_IP%"=="not-installed" (
    echo   Tailscale: http://%TAILSCALE_IP%:8000
    echo.
    echo Share this URL with anyone on your Tailnet!
)
echo.
pause
