@echo off
setlocal
cd /d "%~dp0.."
docker compose run --rm claude python3 Assignment7StyleGuide/test_evaluator.py
set EXIT_CODE=%ERRORLEVEL%
echo.
if %EXIT_CODE% EQU 0 (
    echo Assignment 7 evaluator smoke tests passed.
) else (
    echo Assignment 7 evaluator smoke tests failed with exit code %EXIT_CODE%.
)
exit /b %EXIT_CODE%
