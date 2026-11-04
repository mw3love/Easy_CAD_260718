@echo off
rem Magic Board web board server (watch PC, 2026-11-04). Task Scheduler "MagicBoard board server" runs this at logon.
rem Does nothing if port 5191 is already listening. Public URL = Tailscale Funnel 8443 -> 5191 (kept separately).
netstat -ano | findstr /R /C:"127.0.0.1:5191 .*LISTENING" >nul && exit /b 0
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
start "MagicBoard board server" /min "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe" web\server.py --host 127.0.0.1