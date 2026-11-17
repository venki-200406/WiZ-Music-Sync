@echo off
setlocal
cd /d "%~dp0"
title Building WiZ Music Sync

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from python.org and tick "Add python.exe to PATH".
  pause & exit /b 1
)

echo.
echo [1/3] Installing what the build needs (first time takes a few minutes)...
python -m pip install --upgrade numpy sounddevice PySide6-Essentials pyinstaller
if errorlevel 1 goto :fail

echo.
echo [2/3] Building the app...
python -m PyInstaller --noconfirm --clean --windowed ^
  --name "WiZ Music Sync" ^
  --icon "%~dp0assets\app.ico" ^
  --add-data "%~dp0assets;assets" ^
  --collect-all _sounddevice_data ^
  --exclude-module tkinter ^
  --distpath "%~dp0dist" ^
  --workpath "%TEMP%\wizmusicsync_build" ^
  --specpath "%TEMP%\wizmusicsync_build" ^
  "%~dp0app.py"
if errorlevel 1 goto :fail

copy /y "%~dp0README.md" "%~dp0dist\WiZ Music Sync\README.txt" >nul

echo.
echo [3/3] Adding a Desktop shortcut...
powershell -NoProfile -Command ^
  "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\WiZ Music Sync.lnk\"); $s.TargetPath='%~dp0dist\WiZ Music Sync\WiZ Music Sync.exe'; $s.WorkingDirectory='%~dp0dist\WiZ Music Sync'; $s.Save()"

echo.
echo ===========================================================
echo  Done!  Your app is in:  dist\WiZ Music Sync
echo  Start it with the "WiZ Music Sync" shortcut on your Desktop.
echo ===========================================================
explorer "%~dp0dist\WiZ Music Sync"
pause
exit /b 0

:fail
echo.
echo Build failed. Scroll up to see the error.
pause
exit /b 1
