@echo off
cd /d "%~dp0"
REM ---- Set TEE_UA once with setx (see README). Don't put your email here: this file is public on GitHub. ----
if "%TEE_UA%"=="" set TEE_UA=TeeSheetBot/0.1 (+mailto:YOUR_EMAIL_HERE)

echo Updating tee times...
python backend\build_feed.py
echo.
echo Opening your tee time site at http://localhost:8000
start "" http://localhost:8000
echo Leave this window open while you use the site. Close it to stop.
cd site
python -m http.server 8000
