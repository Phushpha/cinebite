@echo off
title CineBite - Movie + Popcorn Booking
cd /d "%~dp0"
echo.
echo   Starting CineBite on http://localhost:8000
echo   Press Ctrl+C to stop.
echo.
py run.py
pause
