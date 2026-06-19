@echo off
REM run.bat — Auto-restart wrapper for bot.py (Windows)
REM Usage: run.bat [max_restarts]

set MAX_RESTARTS=%1
if "%MAX_RESTARTS%"=="" set MAX_RESTARTS=0
set RESTART_DELAY=3
set COUNTER=0

echo ================================================
echo   Bot Runner with Auto-Restart (Windows)
echo   Max restarts: %MAX_RESTARTS% (0 = unlimited)
echo ================================================

:loop
echo [%date% %time%] Starting bot...
python bot.py
set EXIT_CODE=%ERRORLEVEL%
set /a COUNTER+=1

echo [%date% %time%] Bot exited with code %EXIT_CODE%

if %MAX_RESTARTS% GTR 0 if %COUNTER% GEQ %MAX_RESTARTS% (
    echo [%date% %time%] Reached max restarts. Exiting.
    exit /b %EXIT_CODE%
)

echo [%date% %time%] Restarting in %RESTART_DELAY%s... (attempt %COUNTER%)
timeout /t %RESTART_DELAY% /nobreak >nul
goto loop
