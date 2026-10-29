@echo off
rem Opens the radar flowgraph in GNU Radio Companion (block diagram, settings, run button).
setlocal
set "RC=%USERPROFILE%\radioconda"
if not exist "%RC%\python.exe" set "RC=%ProgramData%\radioconda"
if not exist "%RC%\python.exe" (
    echo GNU Radio is not installed. Install radioconda first - see DEPLOY.md.
    pause
    exit /b 1
)
call "%RC%\Scripts\activate.bat" "%RC%"
cd /d "%~dp0gnuradio"
start "" gnuradio-companion doppler_radar.grc
