@echo off
cd /d "%~dp0"
python -m pip install --quiet numpy sounddevice PySide6-Essentials
start "" pythonw app.py
