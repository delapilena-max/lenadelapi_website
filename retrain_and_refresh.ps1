& ".\.venv\Scripts\python.exe" ".\train_classifier.py"
Start-Sleep -Seconds 2
try { Invoke-WebRequest -Uri "http://127.0.0.1:5000/refresh" -Method Post -UseBasicParsing -TimeoutSec 10 } catch {}
