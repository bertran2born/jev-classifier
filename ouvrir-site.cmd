@echo off
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
    echo Installez uv dans PowerShell : winget install --id astral-sh.uv -e
    echo Puis fermez et rouvrez le terminal ou l'Explorateur.
    pause
    exit /b 1
)
uv run --locked jev.py
if errorlevel 1 pause
