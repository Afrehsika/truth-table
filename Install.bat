@echo off
setlocal
cd /d "%~dp0"
title Truth Table to Logic Circuit Synthesizer - Setup

echo ============================================================================
echo   TRUTH TABLE TO LOGIC CIRCUIT SYNTHESIZER - INSTALLER
echo ============================================================================
echo.

if exist "dist\TruthTableSynthesizer_Setup.exe" (
    echo Starting Graphical Setup Wizard...
    start "" "dist\TruthTableSynthesizer_Setup.exe"
    exit /b 0
)

echo Running Installer Wizard...
python installer_wizard.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo If Python is not installed, please run 'build_installer.py' first or run dist\TruthTableSynthesizer_Setup.exe.
    pause
)

