@echo off
echo ==========================================
echo    RECRUIT SMART - Starting Server
echo ==========================================
cd /d "%~dp0"

echo Clearing old cache...
if exist app\__pycache__ rmdir /s /q app\__pycache__
if exist app\auth\__pycache__ rmdir /s /q app\auth\__pycache__
if exist app\main\__pycache__ rmdir /s /q app\main\__pycache__
if exist app\candidate\__pycache__ rmdir /s /q app\candidate\__pycache__
if exist app\recruiter\__pycache__ rmdir /s /q app\recruiter\__pycache__
if exist app\admin\__pycache__ rmdir /s /q app\admin\__pycache__
if exist app\api\__pycache__ rmdir /s /q app\api\__pycache__
if exist app\utils\__pycache__ rmdir /s /q app\utils\__pycache__
if exist __pycache__ rmdir /s /q __pycache__

echo.
echo Installing dependencies (no virtual environment needed)...
echo This avoids a known bug where the Microsoft Store version of Python
echo hangs/fails when creating a venv (broken ensurepip in that build).
echo.
python -m pip install --user -r requirements.txt
if errorlevel 1 (
    echo.
    echo ==========================================
    echo   Dependency installation failed.
    echo   Try running this manually to see the full error:
    echo   python -m pip install --user -r requirements.txt
    echo ==========================================
    pause
    exit /b 1
)

echo.
echo Starting server...
python run.py

echo.
echo Server stopped. Press any key to exit.
pause > nul
