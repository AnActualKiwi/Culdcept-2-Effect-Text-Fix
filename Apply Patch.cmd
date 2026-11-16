@echo off
setlocal EnableExtensions
title Culdcept 2 Effect Text Fix

set "ISO=%~1"
if defined ISO goto :run

echo Drag the pristine Culdcept USA ISO onto this file.
echo.
set /p "ISO=ISO path: "
if not defined ISO goto :cancelled

:run
set "ISO=%ISO:"=%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_patch.ps1" -IsoPath "%ISO%"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" goto :success
echo Patch failed. Read the message above.
goto :paused

:success
echo Done.

:paused
pause
exit /b %RC%

:cancelled
echo No ISO selected.
pause
exit /b 1
