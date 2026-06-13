@echo off
REM DeskTimer launcher -- runs from source via pythonw (no console window).
REM Uses %~dp0 so it works regardless of where the project folder lives.
REM NOTE: intentionally NOT a packaged exe (avoids AV false-positives and
REM anti-cheat exe-signature blacklists -- see CLAUDE.md decision log).
start "" /d "%~dp0" "%~dp0venv\Scripts\pythonw.exe" main.py
