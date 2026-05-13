@echo off
REM Content Bot — Daily Orchestrator Runner
REM Called by Windows Task Scheduler every morning at 07:00

cd /d C:\projects\ai\content_bot
call .venv\Scripts\activate.bat

echo [%DATE% %TIME%] Orchestrator starting >> logs\task_runner.log
python orchestrator.py >> logs\task_runner.log 2>&1
echo [%DATE% %TIME%] Orchestrator done >> logs\task_runner.log
