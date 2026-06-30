@echo off
setlocal
set "ROOT=C:\projects\ai\content_bot"
cd /d "%ROOT%"
echo AFTERNOON SLOT LIVE PUBLISH IS BLOCKED BY DEFAULT.
echo.
echo Use a dry-run preview first:
echo   python tools/lena_autopublish_approved_queue_v2_8.py --dry-run --slot-keyword afternoon
echo.
echo Manual live execution requires Nicolas approval and BOTH flags:
echo   --live --i-understand-this-can-publish
echo.
".venv\Scripts\python.exe" ".\tools\lena_validate_approved_queue_autopublisher_v2_8.py"
echo.
pause
endlocal
