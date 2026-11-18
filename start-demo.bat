@echo off
rem Starts PipeDelta for the demo. Double-click this file.
rem Offline: no GitHub token is used, and any token in this window is cleared.
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo Could not find the .venv folder. Run the one-time setup in docs\SETUP.md first.
  pause
  exit /b 1
)

set PIPEDELTA_GITHUB_TOKEN=
set GITHUB_TOKEN=
set GH_TOKEN=

call ".venv\Scripts\activate.bat"
if exist demo.db del demo.db

echo Starting PipeDelta. Keep this window open during the demo.
echo Chrome will open http://127.0.0.1:8765 in a few seconds.
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8765"

pipedelta serve --db demo.db

echo.
echo PipeDelta has stopped. If this was not on purpose, close this window and double-click start-demo.bat again.
pause
