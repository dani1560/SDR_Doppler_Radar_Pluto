@echo off
cd /d "%~dp0"
rem Laptop-speaker alarm. For bench tests use --max-kmh 10, for cars use the default (60).
python 02_doppler_radar.py --max-kmh 10
pause
