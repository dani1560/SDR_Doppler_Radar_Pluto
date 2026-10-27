@echo off
rem ============================================================
rem  SDR Doppler Radar - one-click setup and launcher
rem  Double-click this file. It checks Python, the Python packages,
rem  the libiio driver, the PlutoSDR and the Arduino, installs what
rem  is missing, then shows a menu.
rem ============================================================
setlocal
cd /d "%~dp0"
title SDR Doppler Radar

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

:menu
rem --- 4. Status of the hardware ----------------------------------
cls
echo ============================================================
echo                 SDR DOPPLER RADAR - PlutoSDR
echo ============================================================
set "PLUTO=NOT FOUND"
python -c "import adi; adi.Pluto('ip:192.168.2.1')" >nul 2>&1
if not errorlevel 1 set "PLUTO=connected"
set "PORT="
for /f "delims=" %%p in ('python arduino_port.py 2^>nul') do set "PORT=%%p"
echo   PlutoSDR : %PLUTO%
if defined PORT (echo   Arduino  : %PORT%) else (echo   Arduino  : not found - radar runs without the LED display)
echo ------------------------------------------------------------
echo   1  Run radar - walking / hand wave   (alarm loudest at 10 km/h)
echo   2  Run radar - cars / bicycles       (alarm loudest at 60 km/h)
echo   3  Test the Pluto                    (peak at +100 kHz = OK)
echo   4  Test the Arduino display          (Pluto not needed)
echo   5  Upload the sketch to the Arduino  (needs Arduino IDE)
echo   6  Install Pluto drivers             (first time on a new laptop)
echo   7  Open the speed log
echo   0  Exit
echo ------------------------------------------------------------
echo   To stop the radar: close its plot window.
echo ============================================================
set "CHOICE="
set /p CHOICE=Choose 0-7 and press Enter:
if "%CHOICE%"=="1" (set "MAXKMH=10" & goto radar)
if "%CHOICE%"=="2" (set "MAXKMH=60" & goto radar)
if "%CHOICE%"=="3" goto pluto_test
if "%CHOICE%"=="4" goto arduino_test
if "%CHOICE%"=="5" goto upload
if "%CHOICE%"=="6" (call :install_drivers & goto menu)
if "%CHOICE%"=="7" goto log
if "%CHOICE%"=="0" exit /b 0
goto menu

:radar
if not "%PLUTO%"=="connected" goto no_pluto
if defined PORT (
    python 02_doppler_radar.py --max-kmh %MAXKMH% --port %PORT%
) else (
    python 02_doppler_radar.py --max-kmh %MAXKMH%
)
pause
goto menu

:pluto_test
if not "%PLUTO%"=="connected" goto no_pluto
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
if errorlevel 1 (echo UPLOAD FAILED. Check the USB cable and the COM port.) else (echo Upload OK. The display should show 8888, then ----.)
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

rem --- helpers and error messages ---------------------------------
:install_drivers
echo Unplug the Pluto, then press a key. Accept the Windows admin prompts.
pause >nul
start "" /wait "drivers\PlutoSDR-M2k-USB-Drivers.exe"
start "" /wait "drivers\libiio-0.26.ga0eca0d2-setup.exe"
echo Done. Plug the Pluto into its MIDDLE micro-USB port and wait 30 s.
pause
exit /b 0

:no_pluto
echo.
echo PlutoSDR not found. Check:
echo   - Pluto plugged into its MIDDLE micro-USB port, wait 30 s for the Ready LED
echo   - no other radar window is still open
echo   - first time on this laptop? choose 6 to install the drivers
pause
goto menu

:no_arduino
echo.
echo Arduino not found. Plug in the Nano. If it still does not appear,
echo install the CH340 driver (clone Nanos) or try another USB cable.
pause
goto menu

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
