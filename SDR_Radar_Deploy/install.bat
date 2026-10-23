@echo off
cd /d "%~dp0"
echo Installing Python packages for the SDR Doppler radar...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: install failed. Is Python installed and on PATH?
    pause
    exit /b 1
)
echo.
echo Checking connection to PlutoSDR...
python -c "import adi; s = adi.Pluto('ip:192.168.2.1'); print('PlutoSDR connected OK, LO =', s.rx_lo)"
pause
