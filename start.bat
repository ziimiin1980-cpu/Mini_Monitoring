@echo off
rem Mini Monitoring launcher
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment .venv not found.
    echo Create it:  py -3.13 -m venv .venv
    echo Then install: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] Settings file .env not found.
    echo Copy .env.example to .env and set the PostgreSQL password.
    pause
    exit /b 1
)

echo Mini Monitoring: http://127.0.0.1:8000/
echo Press Ctrl+C to stop the server.
echo.

.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Server stopped.
pause
