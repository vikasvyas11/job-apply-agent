@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Job Application Agent - first-time setup
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on this computer.
    echo Install it from https://www.python.org/downloads/ first ^(check the
    echo box "Add python.exe to PATH" during install^), then run this script again.
    pause
    exit /b 1
)

echo [1/4] Creating a private Python environment for this app...
python -m venv .venv
if errorlevel 1 (
    echo Failed to create the virtual environment. See the error above.
    pause
    exit /b 1
)

echo [2/4] Installing required packages ^(this can take a few minutes^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install packages. See the error above.
    pause
    exit /b 1
)

echo [3/4] Installing the headless browser used as a fallback for tricky job pages...
".venv\Scripts\python.exe" -m playwright install chromium

echo [4/4] Checking for Ollama ^(runs the AI model locally, for free^)...
where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo Ollama was not found. Install it from https://ollama.com/download
    echo ^(just download and run the installer, no configuration needed^),
    echo then come back and run this script again to finish setup.
    pause
    exit /b 1
) else (
    echo Ollama found.
)

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo Next: double-click start.bat, then go to the Setup page in your browser
echo to add your name, CV, and Google Doc template.
echo.
pause
