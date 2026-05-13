@echo off
set "PY=C:\projects\ai\content_bot\.venv\Scripts\python.exe"
set "APP=C:\projects\ai\content_bot\run_bot.py"
set "LOG=C:\projects\ai\content_bot\logs\bot_current.log"
if not exist "%~dp0logs" mkdir "%~dp0logs"
:loop
"%PY%" -u "%APP%" >> "%LOG%" 2>&1
timeout /t 5 /nobreak >nul
goto loop
