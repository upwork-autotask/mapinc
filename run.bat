@echo off
rem Starts the MAP Inc letter server on port 8000. Run from a console that stays open,
rem or install as a service with NSSM (see README).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python manage.py check
if errorlevel 1 (
  echo Configuration check failed - fix mapinc.ini as described above and try again.
  pause
  exit /b 1
)
python manage.py migrate --noinput
if errorlevel 1 (
  echo Database migration failed - check mapinc.ini and that PostgreSQL is running.
  pause
  exit /b 1
)
rem Behind IIS set MAPINC_LISTEN=127.0.0.1:8000 so nothing bypasses the proxy.
if "%MAPINC_LISTEN%"=="" set MAPINC_LISTEN=0.0.0.0:8000
waitress-serve --listen=%MAPINC_LISTEN% --threads=4 mapinc.wsgi:application
