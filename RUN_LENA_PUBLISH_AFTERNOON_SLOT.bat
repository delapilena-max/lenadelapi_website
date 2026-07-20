@echo off
setlocal
set "ROOT=%LENA_AUTOPUBLISH_PRODUCTION_ROOT%"
if not defined ROOT set "ROOT=%CONTENT_BOT_ROOT%"
if not defined ROOT (
  echo Missing production root environment variable: LENA_AUTOPUBLISH_PRODUCTION_ROOT or CONTENT_BOT_ROOT
  exit /b 1
)
set "PYTHON_EXE=%LENA_AUTOPUBLISH_PYTHON_EXE%"
if not defined PYTHON_EXE set "PYTHON_EXE=%CONTENT_BOT_PYTHON_EXE%"
if not defined PYTHON_EXE (
  echo Missing Python interpreter environment variable: LENA_AUTOPUBLISH_PYTHON_EXE or CONTENT_BOT_PYTHON_EXE
  exit /b 1
)
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
