@echo off
rem ============================================================
rem  SDR Doppler Radar - double-click to start the radar
rem  Checks Python, the Python packages, the libiio driver, the
rem  PlutoSDR and the Arduino, installs what is missing, then starts
rem  the radar straight away. Close the plot window to stop.
rem  Tests, sketch upload and drivers: double-click TOOLS.bat.
rem ============================================================
setlocal
cd /d "%~dp0"
title SDR Doppler Radar

rem --- Radar settings: change these if you like --------------------
rem  LIMIT  = speed limit in km/h; faster passes are CAPTURED
rem  MAXKMH = speed at which the alarm is loudest
rem  For cars use LIMIT=50, MAXKMH=60, MAX_SPEED=220, TX_GAIN=-10, MIN_SIGNAL=15.
rem  FREQ_MHZ  = carrier frequency (2400-2483 with the 2.4 GHz antennas)
rem  MAX_SPEED = highest speed searched in km/h (up to ~740 at 2482 MHz)
rem  TX_GAIN    = TX attenuation in dB (-30 short range, -10 long range, 0 max power)
rem  MIN_SIGNAL = min target signal in dB (35 = only close targets ~1-2 m, 15 = longest range)
set "LIMIT=10"
set "MAXKMH=10"
set "FREQ_MHZ=2482"
set "MAX_SPEED=60"
set "TX_GAIN=-30"
set "MIN_SIGNAL=35"

rem --- 1. Python --------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 goto old_python

rem --- 2. Python packages -----------------------------------------
python -c "import importlib.util as u, sys; sys.exit(any(u.find_spec(m) is None for m in ['adi', 'iio', 'numpy', 'scipy', 'matplotlib', 'serial', 'sounddevice']))"
if errorlevel 1 (
    echo Installing Python packages, please wait...
    python -m pip install -r requirements.txt
    if errorlevel 1 goto pip_failed
)

rem --- 3. libiio driver (needed by the Pluto Python package) ------
python -c "import iio" >nul 2>&1
if errorlevel 1 (
    echo.
    echo libiio is not installed. Starting the driver installers...
    call :install_drivers
)

if /i "%~1"=="menu" goto menu

rem --- 4. Start the radar -----------------------------------------
:autostart
cls
call :detect
echo   PlutoSDR : %PLUTO%
if defined PORT (echo   Arduino  : %PORT%) else (echo   Arduino  : not found - radar runs without the LED display)
echo   Speed limit %LIMIT% km/h. Close the plot window to stop.
echo.
if not "%PLUTO%"=="connected" (
    call :pluto_help
    echo Plug in the Pluto, then press a key to try again.
    pause >nul
    goto autostart
)
call :run_radar
pause
exit /b 0

rem --- Tools menu (TOOLS.bat) -------------------------------------
:menu
cls
echo ============================================================
echo                 SDR DOPPLER RADAR - TOOLS
echo ============================================================
call :detect
echo   PlutoSDR : %PLUTO%
if defined PORT (echo   Arduino  : %PORT%) else (echo   Arduino  : not found)
echo ------------------------------------------------------------
echo   1  Run radar - walking / hand wave   (capture over 10 km/h)
echo   2  Run radar - cars / bicycles       (capture over 50 km/h)
echo   3  Test the Pluto                    (peak at +100 kHz = OK)
echo   4  Test the Arduino display          (Pluto not needed)
echo   5  Upload the sketch to the Arduino  (needs Arduino IDE)
echo   6  Install Pluto drivers             (first time on a new laptop)
echo   7  Open the speed log
echo   0  Exit
echo ============================================================
set "CHOICE="
set /p CHOICE=Choose 0-7 and press Enter:
if "%CHOICE%"=="1" (set "MAXKMH=10" & set "LIMIT=10" & goto menu_radar)
if "%CHOICE%"=="2" (set "MAXKMH=60" & set "LIMIT=50" & goto menu_radar)
if "%CHOICE%"=="3" goto pluto_test
if "%CHOICE%"=="4" goto arduino_test
if "%CHOICE%"=="5" goto upload
if "%CHOICE%"=="6" (call :install_drivers & goto menu)
if "%CHOICE%"=="7" goto log
if "%CHOICE%"=="0" exit /b 0
goto menu

:menu_radar
if not "%PLUTO%"=="connected" goto menu_no_pluto
call :run_radar
pause
goto menu

:pluto_test
if not "%PLUTO%"=="connected" goto menu_no_pluto
python 01_pluto_test.py
pause
goto menu

:arduino_test
if not defined PORT goto no_arduino
python 03_alarm_test.py %PORT%
pause
goto menu

:upload
if not defined PORT goto no_arduino
set "CLI="
if exist "%ProgramFiles%\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" set "CLI=%ProgramFiles%\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
if exist "%LOCALAPPDATA%\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" set "CLI=%LOCALAPPDATA%\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
if not defined CLI (
    echo Arduino IDE not found. Install Arduino IDE 2 from arduino.cc/en/software, then try again.
    pause
    goto menu
)
echo Close the Arduino IDE if it is open, then press a key.
pause >nul
echo Installing the Nano board support and the TM1637 library...
"%CLI%" core install arduino:avr
"%CLI%" lib install TM1637
echo Uploading to %PORT% ...
"%CLI%" compile --upload -p %PORT% --fqbn arduino:avr:nano:cpu=atmega328old speed_alarm
if errorlevel 1 (
    echo Old-bootloader upload failed, trying the new bootloader...
    "%CLI%" compile --upload -p %PORT% --fqbn arduino:avr:nano:cpu=atmega328 speed_alarm
)
if errorlevel 1 (echo UPLOAD FAILED. Check the USB cable and the COM port.) else (echo Upload OK. The display shows 88:88, then ----.)
pause
goto menu

:log
if not exist speed_log.csv (
    echo No passes logged yet.
    pause
    goto menu
)
start "" speed_log.csv
goto menu

:menu_no_pluto
call :pluto_help
pause
goto menu

:no_arduino
echo.
echo Arduino not found. Plug in the Nano. If it still does not appear,
echo install the CH340 driver (clone Nanos) or try another USB cable.
pause
goto menu

rem --- helpers ----------------------------------------------------
:detect
set "PLUTO=NOT FOUND"
python -c "import adi; adi.Pluto('ip:192.168.2.1')" >nul 2>&1
if not errorlevel 1 set "PLUTO=connected"
set "PORT="
for /f "delims=" %%p in ('python arduino_port.py 2^>nul') do set "PORT=%%p"
exit /b 0

:run_radar
if defined PORT (
    python 02_doppler_radar.py --max-kmh %MAXKMH% --limit %LIMIT% --freq-mhz %FREQ_MHZ% --max-speed %MAX_SPEED% --tx-gain %TX_GAIN% --min-signal %MIN_SIGNAL% --port %PORT%
) else (
    python 02_doppler_radar.py --max-kmh %MAXKMH% --limit %LIMIT% --freq-mhz %FREQ_MHZ% --max-speed %MAX_SPEED% --tx-gain %TX_GAIN% --min-signal %MIN_SIGNAL%
)
exit /b 0

:pluto_help
echo PlutoSDR not found. Check:
echo   - Pluto plugged into its MIDDLE micro-USB port, wait 30 s for the Ready LED
echo   - no other radar window is still open
echo   - first time on this laptop? run TOOLS.bat and choose 6 to install the drivers
exit /b 0

:install_drivers
echo Unplug the Pluto, then press a key. Accept the Windows admin prompts.
pause >nul
start "" /wait "drivers\PlutoSDR-M2k-USB-Drivers.exe"
start "" /wait "drivers\libiio-0.26.ga0eca0d2-setup.exe"
echo Done. Plug the Pluto into its MIDDLE micro-USB port and wait 30 s.
pause
exit /b 0

:no_python
echo Python is not installed.
echo Install Python 3.10 or newer from python.org and tick "Add Python to PATH",
echo then double-click this file again.
start "" https://www.python.org/downloads/
pause
exit /b 1

:old_python
echo Python 3.10 or newer is needed. Install it from python.org, then try again.
pause
exit /b 1

:pip_failed
echo.
echo ERROR: installing the Python packages failed. Check the internet connection.
pause
exit /b 1
