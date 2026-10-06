@echo off
title CineBite - public share link
setlocal EnableDelayedExpansion

echo.
echo ============================================
echo    CineBite  -  starting site + link
echo ============================================
echo.

rem ---- 1. start the website on localhost:8000 ----
start "CineBite server" cmd /k "cd /d %~dp0 && py run.py"
echo    [1/2] Website starting on http://127.0.0.1:8000 ...
timeout /t 5 /nobreak >nul

rem ---- 2. start the public tunnel, capture its output ----
set "LOG=%TEMP%\cinebite_tunnel.log"
if exist "%LOG%" del "%LOG%"
echo    [2/2] Creating public link ...

start "" /b "%LOCALAPPDATA%\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8000 > "%LOG%" 2>&1

set "URL="
for /l %%i in (1,1,40) do (
    if not defined URL (
        timeout /t 2 /nobreak >nul
        if exist "%LOG%" (
            for /f "tokens=2 delims=|" %%u in ('findstr /i "trycloudflare.com" "%LOG%"') do (
                for /f "tokens=* delims= " %%v in ("%%u") do set "URL=%%v"
            )
        )
    )
)

echo.
if defined URL (
    echo    --------------------------------------------
    echo    SHARE THIS LINK WITH YOUR COLLEAGUES:
    echo.
    echo      !URL!
    echo    --------------------------------------------
    echo.
    start "" "!URL!"
) else (
    echo    Could not read the link yet. Check the
    echo    cloudflared window, or rerun share.bat.
)

echo    Keep this window open - closing it takes the
echo    site offline. Press Ctrl+C here to stop.
echo.
pause
endlocal
