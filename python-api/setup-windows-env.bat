@echo off
echo Creating Windows-compatible Python environment...

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+ first.
    pause
    exit /b 1
)

REM Remove old venv if exists
if exist venv rmdir /s /q venv

REM Create new virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo Installing dependencies...
pip install --no-cache-dir -r requirements.txt

echo.
echo Setup complete! To activate the environment:
echo   venv\Scripts\activate.bat
echo.
echo To run the API:
echo   python main.py
echo.
pause