@echo off
setlocal
set "ROOT=C:\projects\ai\content_bot\lenadelapi_website_hpe2"
set "PYTHON_EXE=C:\Python314\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Missing Python interpreter: %PYTHON_EXE%
  exit /b 1
)
cd /d "%ROOT%"
"%PYTHON_EXE%" ".\tools\lena_build_approved_publish_queue_v2_8.py"
if errorlevel 1 exit /b %errorlevel%
"%PYTHON_EXE%" ".\tools\lena_validate_approved_queue_autopublisher_v2_8.py"
if errorlevel 1 exit /b %errorlevel%
"%PYTHON_EXE%" ".\tools\lena_autopublish_approved_queue_v2_8.py" --scheduled-autonomous --slot-keyword afternoon --limit 1
endlocal
