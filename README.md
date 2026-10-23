# SDR Doppler Radar with Speed Alarm

CW Doppler radar on an ADALM-PLUTO SDR at 2.482 GHz. Measures target speed in km/h and sounds an alarm:
louder and higher-pitched for faster targets, faster beeps for closer (stronger) echoes.

After each pass, the **last speed** (peak speed of that pass) stays on the laptop screen and on the
Arduino LED display until the next pass. Every pass is logged to `speed_log.csv` (date, time, speed, direction).

## Folder contents

| File | Purpose |
|---|---|
| `02_doppler_radar.py` | Main radar program (spectrum, speed display, alarm) |
| `01_pluto_test.py` | Hardware check: shows a peak at +100 kHz if TX and RX work |
| `03_alarm_test.py` | Arduino check without the Pluto: sends simulated passes (`python 03_alarm_test.py COM5`) |
| `speed_alarm/speed_alarm.ino` | Arduino Nano buzzer alarm + TM1637 LED speed display |
| `speed_log.csv` | Created on first pass: one row per measured pass |
| `requirements.txt` | Python packages |
| `install.bat` | Installs Python packages and tests the Pluto connection |
| `run_radar.bat` | Starts the radar with the laptop-speaker alarm |
| `run_radar_arduino.bat` | Starts the radar with the Arduino buzzer alarm |
| `drivers/` | PlutoSDR USB driver and libiio v0.26 installers (Windows) |
| `pluto_recovery/` | Firmware v0.39 files for updating or recovering the Pluto |

## Setup on a new Windows laptop

1. Install **Python 3.10 or newer** from python.org. Tick **"Add Python to PATH"**.
2. With the Pluto **unplugged**, run `drivers\PlutoSDR-M2k-USB-Drivers.exe` as administrator.
3. Run `drivers\libiio-0.26.ga0eca0d2-setup.exe` as administrator.
   Use libiio **v0.26**, not v1.x: the Python package is pinned to `pylibiio==0.25` to match it.
4. Plug the Pluto into its **middle** micro-USB port (the USB symbol, not the power port).
   Wait about 30 s: the Ready LED comes on and a `PlutoSDR` drive appears.
5. Double-click `install.bat`. It should end with `PlutoSDR connected OK`.
6. Double-click `run_radar.bat`.

## Arduino buzzer + LED display (optional)

Wiring (buzzer must be on D9, it uses Timer1's hardware PWM):

```
Buzzer:   Nano D9 --[1k]--> NPN base (2N2222 / BC547)
          NPN emitter --> GND
          NPN collector --> buzzer (-)
          buzzer (+) --> 5V

TM1637:   CLK --> D2
          DIO --> D3
          VCC --> 5V
          GND --> GND
```

The display shows the live speed (whole km/h) during a pass, then holds the last speed. `----` means no pass yet.

1. Install Arduino IDE and, for clone Nanos, the CH340 driver.
2. In Arduino IDE: Tools -> Manage Libraries -> install **"TM1637" by Avishay Orpaz**.
3. Open `speed_alarm/speed_alarm.ino`. Board: **Arduino Nano**; for clones, Processor: **ATmega328P (Old Bootloader)**.
4. Upload. The display shows `8888` and the buzzer chirps (wiring OK), then `----`. Close the Serial Monitor.
4. Run `run_radar_arduino.bat` and enter the Nano's COM port.

## Command-line options

```
python 02_doppler_radar.py [--max-kmh 60] [--port COM5] [--no-sound] [--rx-gain 30] [--tx-gain -10]
```

| Option | Meaning |
|---|---|
| `--max-kmh` | Speed at which the alarm is loudest. Use 10 indoors, 60+ for cars |
| `--port` | Arduino COM port; sends `S<kmh>,P<proximity>,V<volume>,L<last kmh>` lines at 115200 baud |
| `--no-sound` | Turn off the laptop-speaker alarm |
| `--rx-gain` | RX gain, 0..70 dB. Lower it if the screen shows `CLIPPING` |
| `--tx-gain` | TX attenuation, 0 (max power) to -89 dB |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `CLIPPING` on screen | Lower `--rx-gain` (e.g. 20), or separate the TX and RX antennas |
| False targets with no one moving | Turn off ceiling fans; point the antennas away from moving objects |
| Noisy spectrum | Wi-Fi interference. The radar uses 2.482 GHz to avoid it; change `CENTER_FREQ` if needed |
| `Open unlocked: -16` / device busy | Another radar window is still running. Close it first |
| No `PlutoSDR` drive, Ready LED off, LED1 on | Firmware stuck. Hold button **S1** inside the case (next to the data USB port) while plugging in, then flash with `dfu-util` from the driver install folder: `dfu-util -a boot.dfu -D boot.dfu`, `dfu-util -a uboot-env.dfu -D uboot-env.dfu`, `dfu-util -a firmware.dfu -D pluto.dfu` (files in `pluto_recovery/`) |

## Radar parameters

| Parameter | Value |
|---|---|
| Carrier | 2.482 GHz (top of the 2.4 GHz ISM band, above Wi-Fi) |
| Waveform | CW tone at +100 kHz offset |
| Sample rate | 1 MS/s, decimated to 8 kS/s |
| FFT | 4096 points (0.5 s), ~1.95 Hz bins, ~0.42 km/h resolution |
| Speed range | about 3 to 215 km/h, approaching and receding |
| Clutter rejection | Mirror-peak test (fans) plus 2-frame confirmation |
