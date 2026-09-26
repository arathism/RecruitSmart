@echo off
echo ==========================================
echo    RECRUIT SMART - Clean Run
echo ==========================================
cd /d "%~dp0"

echo [1/4] Clearing Python cache...
if exist app\__pycache__ rmdir /s /q app\__pycache__
if exist app\auth\__pycache__ rmdir /s /q app\auth\__pycache__
if exist app\main\__pycache__ rmdir /s /q app\main\__pycache__
if exist app\candidate\__pycache__ rmdir /s /q app\candidate\__pycache__
if exist app\recruiter\__pycache__ rmdir /s /q app\recruiter\__pycache__
if exist app\admin\__pycache__ rmdir /s /q app\admin\__pycache__
if exist app\api\__pycache__ rmdir /s /q app\api\__pycache__
if exist app\utils\__pycache__ rmdir /s /q app\utils\__pycache__
if exist __pycache__ rmdir /s /q __pycache__

echo [2/4] Activating virtual environment...
call venv\Scripts\activate

echo [3/4] Installing dependencies...
pip install flask flask-sqlalchemy flask-login flask-wtf flask-mail flask-migrate flask-limiter flask-cors werkzeug sqlalchemy alembic python-dotenv email-validator python-dateutil PyPDF2 python-docx Pillow numpy scikit-learn

echo [4/4] Starting server...
python run.py

echo.
echo Server stopped. Press any key to exit.
pause > nul
