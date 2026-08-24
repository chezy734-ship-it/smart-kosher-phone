@echo off
chcp 65001 >nul 2>&1
title Smart Kosher Phone - Uninstall
echo ============================================
echo   Smart Kosher Phone - Uninstall
echo ============================================
echo.

:: Remove desktop shortcut
if exist "%USERPROFILE%\Desktop\SmartKosherPhone.lnk" (
    del "%USERPROFILE%\Desktop\SmartKosherPhone.lnk" 2>nul
    echo [OK] Desktop shortcut removed
)

:: Remove Start Menu shortcut
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\SmartKosherPhone.lnk" (
    del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\SmartKosherPhone.lnk" 2>nul
    echo [OK] Start Menu shortcut removed
)

echo.
echo The application folder will NOT be deleted automatically.
echo To fully remove, delete this folder manually:
echo   %~dp0
echo.
pause
