@echo off
REM Run this once as Administrator to register the daily task.
REM Task fires at 07:00 every day; orchestrator handles all timing from there.

SET TASK=ContentBotOrchestrator
SET SCRIPT=C:\projects\ai\content_bot\run_daily.bat

schtasks /delete /tn "%TASK%" /f >nul 2>&1
schtasks /create ^
  /tn "%TASK%" ^
  /tr "\"%SCRIPT%\"" ^
  /sc daily ^
  /st 07:00 ^
  /rl HIGHEST ^
  /ru "%USERNAME%" ^
  /f

echo.
echo Task "%TASK%" registered. Fires daily at 07:00.
echo Orchestrator will handle all human-pattern timing from there.
echo Logs: C:\projects\ai\content_bot\logs\
pause
