@echo off
for /f "usebackq delims=" %%A in (powershell -NoProfile -Command "Get-Secret -Name 'MASTODON_BASE_URL' -AsPlainText") do set "MASTODON_BASE_URL=%%A"
for /f "usebackq delims=" %%A in (powershell -NoProfile -Command "Get-Secret -Name 'MASTODON_ACCESS_TOKEN' -AsPlainText") do set "MASTODON_ACCESS_TOKEN=%%A"
set BOT_UPLOAD_METHOD=local
set BOT_OUTBOX_DIR=C:\projects\ai\content_bot\outbox\ai_lady\staging
"C:\projects\ai\content_bot\.venv\Scripts\python.exe" "C:\projects\ai\content_bot\run_bot.py"
