@echo off
rem Starts the MAP Inc letter server on port 8000. Run from a console that stays open,
rem or install as a service with NSSM (see README).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python manage.py migrate --noinput
if errorlevel 1 (
  echo Database migration failed - check mapinc.ini and that PostgreSQL is running.
  pause
  exit /b 1
)
waitress-serve --listen=0.0.0.0:8000 --threads=4 mapinc.wsgi:application
