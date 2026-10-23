@echo off
cd /d "%~dp0"
set /p PORT=Arduino COM port (e.g. COM5):
python 02_doppler_radar.py --max-kmh 10 --port %PORT% --no-sound
pause
