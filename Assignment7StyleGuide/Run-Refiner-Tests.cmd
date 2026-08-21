@echo off
setlocal
cd /d "%~dp0.."
docker compose run --rm claude python3 Assignment7StyleGuide/test_refiner.py
set EXIT_CODE=%ERRORLEVEL%
echo.
if %EXIT_CODE% EQU 0 (
    echo Assignment 7 refiner smoke tests passed.
) else (
    echo Assignment 7 refiner smoke tests failed with exit code %EXIT_CODE%.
)
exit /b %EXIT_CODE%
