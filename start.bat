@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Setup hasn't been run yet. Double-click setup.bat first.
    pause
    exit /b 1
)
echo Starting Job Application Agent... a browser tab will open shortly.
echo Keep this window open while you use the app - closing it stops the app.
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py
pause
