@echo off
cd /d C:\projects\ai\content_bot

IF "%~1"=="" (
    FOR /F "usebackq delims=" %%D IN (`.venv\Scripts\python.exe -c "from datetime import date; print(date.today().isoformat())"`) DO SET POST_DATE=%%D
) ELSE (
    SET POST_DATE=%~1
)

IF NOT EXIST logs\scheduler\%POST_DATE% MKDIR logs\scheduler\%POST_DATE%
SET LOGFILE=logs\scheduler\%POST_DATE%\publish_evening_%POST_DATE%.log

echo [%DATE% %TIME%] START evening slot publish >> %LOGFILE%

.venv\Scripts\python.exe tools\lena_autopublish_approved_queue_v2_8.py ^
    --date %POST_DATE% ^
    --platforms "Instagram Feed,Facebook Page" ^
    --slot-keyword evening ^
    --max-attempts 3 ^
    >> %LOGFILE% 2>&1

SET RC=%ERRORLEVEL%
echo [%DATE% %TIME%] END evening slot publish  rc=%RC% >> %LOGFILE%
exit /b %RC%
