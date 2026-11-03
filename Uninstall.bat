@echo off
setlocal
title Uninstalling Truth Table to Logic Circuit Synthesizer...
echo ============================================================================
echo   UNINSTALL TRUTH TABLE TO LOGIC CIRCUIT SYNTHESIZER
echo ============================================================================
echo.

set "TARGET_DIR=%LOCALAPPDATA%\Programs\TruthTableSynthesizer"
set "DESKTOP_LNK=%USERPROFILE%\Desktop\Truth Table to Logic Circuit Synthesizer.lnk"
set "START_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Truth Table to Logic Circuit Synthesizer"

echo [1/3] Removing Desktop Shortcut...
if exist "%DESKTOP_LNK%" del /f /q "%DESKTOP_LNK%"

echo [2/3] Removing Start Menu Shortcuts...
if exist "%START_DIR%" (
    del /f /q "%START_DIR%\*.lnk" 2>nul
    rmdir /s /q "%START_DIR%" 2>nul
)

echo [3/3] Removing Application Files...
if exist "%TARGET_DIR%" (
    rmdir /s /q "%TARGET_DIR%" 2>nul
)

echo.
echo Uninstallation completed successfully!
echo.
pause

