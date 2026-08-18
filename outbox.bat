@echo off
rem ----- Outbox web server. Uses waitress on Windows (gunicorn is POSIX-only).
rem       Restarts the server if it ever exits.
cd /d %~dp0
:loop
%USERPROFILE%\.cargo\bin\uv.exe run outbox-web
timeout /t 5 /nobreak
goto :loop
