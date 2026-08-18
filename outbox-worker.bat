@echo off
rem ----- Outbox delivery worker. This is NOT optional: without it messages are
rem       accepted into the queue but never handed to SMTP.
cd /d %~dp0
:loop
%USERPROFILE%\.cargo\bin\uv.exe run python -m worker.queue_worker
timeout /t 5 /nobreak
goto :loop
