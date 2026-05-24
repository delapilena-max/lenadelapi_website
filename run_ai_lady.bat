@echo off
setlocal enabledelayedexpansion

REM === Activate virtual environment ===
cd /d %~dp0
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Exiting.
    exit /b 1
)

REM === Environment variables for poster/watcher ===
set POSTER_HEADLESS=true
set POSTER_CONFIDENCE_THRESHOLD=0.80
set POSTER_FORCE_MEDIA=
set POSTER_PREPARED_DIR=outbox\prepared

REM === Python executable override (optional) ===
set PYTHON=python

REM === Logging ===
set LOGDIR=nodes\ai_lady_instagram\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set LOGFILE=%LOGDIR%\run_ai_lady.log

echo [%DATE% %TIME%] Starting AI Lady automation >> "%LOGFILE%"
@echo off
setlocal enabledelayedexpansion

cd /d %~dp0
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Exiting.
    exit /b 1
)

set POSTER_HEADLESS=true
set POSTER_CONFIDENCE_THRESHOLD=0.80
set POSTER_FORCE_MEDIA=
set POSTER_PREPARED_DIR=outbox\prepared

set PYTHON=python

set LOGDIR=nodes\ai_lady_instagram\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set LOGFILE=%LOGDIR%\run_ai_lady.log

echo [%DATE% %TIME%] Starting AI Lady automation >> "%LOGFILE%"

%PYTHON% nodes\ai_lady_instagram\watcher.py >> "%LOGFILE%" 2>&1

echo [%DATE% %TIME%] AI Lady automation stopped >> "%LOGFILE%"
endlocal
exit /b 0

REM === Run watcher loop ===
%PYTHON% nodes\ai_lady_instagram\watcher.py >> "%LOGFILE%" 2>&1

echo [%DATE% %TIME%] AI Lady automation stopped >> "%LOGFILE%"
endlocal
exit /b 0
