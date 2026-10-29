@echo off
rem ============================================================
rem  SDR Doppler Radar - GNU Radio version
rem  Runs gnuradio\doppler_radar.grc. Sliders in the window set the
rem  frequency, max speed, speed limit, RX gain and TX power.
rem  Close the window to stop. Needs radioconda (GNU Radio) in
rem  %USERPROFILE%\radioconda or %ProgramData%\radioconda - see DEPLOY.md.
rem ============================================================
setlocal
set "RC=%USERPROFILE%\radioconda"
if not exist "%RC%\python.exe" set "RC=%ProgramData%\radioconda"
set "HERE=%~dp0"
title SDR Doppler Radar - GNU Radio
if not exist "%RC%\python.exe" goto no_gnuradio

call "%RC%\Scripts\activate.bat" "%RC%"
rem pyserial (Arduino LED display) is not part of radioconda: install it once for this user
python -c "import serial" >nul 2>&1
if errorlevel 1 (
    echo Installing pyserial for the Arduino display...
    python -m pip install --user -q pyserial
)
cd /d "%HERE%gnuradio"
echo Building the flowgraph...
grcc -o . doppler_radar.grc
if errorlevel 1 goto grcc_failed
echo Starting the radar. Stand still for 3 s while it learns the background.
python doppler_radar.py
endlocal

rem Mute the transmitter after the flowgraph has closed (uses the normal Python with pyadi-iio)
python -c "import adi; adi.Pluto('ip:192.168.2.1').tx_hardwaregain_chan0 = -89" >nul 2>&1
echo Radar stopped. TX is off.
pause
exit /b 0

:grcc_failed
echo ERROR: the flowgraph could not be built (see the messages above).
pause
exit /b 1

:no_gnuradio
echo GNU Radio is not installed.
echo Install radioconda (folder %USERPROFILE%\radioconda or %ProgramData%\radioconda) from
echo https://github.com/radioconda/radioconda-installer/releases , then run this file again.
pause
exit /b 1
