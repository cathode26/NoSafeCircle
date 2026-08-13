@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0GoalOrientedAgent\Setup-Assignment5-Analysis.ps1"
echo.
pause
