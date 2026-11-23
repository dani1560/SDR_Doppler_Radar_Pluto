@echo off
rem ============================================================
rem  SDR Doppler Radar - GNU Radio version with the radar screen
rem  Runs gnuradio\doppler_radar_screen.grc: same radar as
rem  START_GNURADIO.bat, plus a radar circle (PPI), speed cards,
rem  spectrum and waterfall (gnuradio\radar_screen.py).
rem  Close the window to stop. Needs radioconda (GNU Radio) in
rem  %USERPROFILE%\radioconda or %ProgramData%\radioconda - see DEPLOY.md.
rem ============================================================
setlocal
set "RC=%USERPROFILE%\radioconda"
if not exist "%RC%\python.exe" set "RC=%ProgramData%\radioconda"
set "HERE=%~dp0"
title SDR Doppler Radar - Radar Screen
if not exist "%RC%\python.exe" goto no_gnuradio

call "%RC%\Scripts\activate.bat" "%RC%"
rem pyserial (Arduino LED display) is not part of radioconda: install it once for this user
python -c "import serial" >nul 2>&1
if errorlevel 1 (
    echo Installing pyserial for the Arduino display...
    python -m pip install --user -q pyserial
)
rem The Pluto needs about 30 s after plugging in before it answers
ping -n 1 -w 1000 192.168.2.1 >nul 2>&1
if errorlevel 1 (
    echo The Pluto is not answering on 192.168.2.1.
    echo Plug it in, wait about 30 s until its LED blinks, then press a key to try anyway.
    pause
)
cd /d "%HERE%gnuradio"
echo Building the flowgraph...
grcc -o . doppler_radar_screen.grc
if errorlevel 1 goto grcc_failed
rem Show the flowgraph in GNU Radio Companion next to the radar (for viewing; the radar below is already running it)
echo Opening the flowgraph in GNU Radio Companion...
start "GNU Radio Companion" gnuradio-companion doppler_radar_screen.grc
echo Starting the radar. Stand still for 3 s while it learns the background.
echo Do not also press Run in GNU Radio Companion: the Pluto can only be used by one radar at a time.
python doppler_radar_screen.py
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
